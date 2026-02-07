# ============================================================
# Main application
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="PHREG multi-reactor pH controller")

    ap.add_argument("--mm44_ports", type=str, default=MM44_PORTS_DEFAULT)
    ap.add_argument("--mfc", type=str, default=MFC_PORT_DEFAULT)
    ap.add_argument("--no_mfc", action="store_true")
    ap.add_argument("--raw", action="store_true")
    ap.add_argument("--dt", type=float, default=DT_DEFAULT)

    ap.add_argument("--deadband", type=float, default=PH_DEADBAND_DEFAULT)
    ap.add_argument("--mode", choices=["co2_only", "split"], default="split")

    ap.add_argument("--log_enable", action="store_true")
    ap.add_argument("--log_dir", type=str, default=LOG_DIR_DEFAULT)
    ap.add_argument("--log_interval", type=int, default=LOG_INTERVAL_S)
    ap.add_argument("--log_retention_days", type=int, default=LOG_RETENTION_DAYS)

    args = ap.parse_args()

    mm44_ports = [p.strip() for p in args.mm44_ports.split(",") if p.strip()]
    if len(mm44_ports) != 2:
        print("[FATAL] Exactly two MM44 ports are required")
        sys.exit(2)

    reactors = [r for r in REACTORS_DEFAULT]

    pids = {}
    for r in reactors:
        if args.mode == "co2_only":
            pids[r.name] = PID(PID_KP, PID_KI, PID_KD, 0.0, CO2_MAX)
        else:
            pids[r.name] = PID(PID_KP, PID_KI, PID_KD, -100.0, CO2_MAX)

    co2_cmd = {r.name: 0.0 for r in reactors}
    air_cmd = {r.name: r.air_baseline for r in reactors}

    last_ph_time = {r.name: 0.0 for r in reactors}
    last_co2_flow = {r.name: None for r in reactors}

    alarms = set()
    state = S_INIT

    mm44_list = []
    mm44_data = {}
    last_mm44_raw = {}

    air_mfc = {}
    co2_mfc = {}

    show_raw = args.raw
    last_t = time.time()

    log_enabled = args.log_enable
    last_log_ts = 0.0
    last_logged_minute = {r.name: None for r in reactors}

    if log_enabled:
        ensure_dir(args.log_dir)

    print("PHREG controller started")
    print(f"Mode: {args.mode}, deadband: ±{args.deadband}")

    try:
        while True:
            now = time.time()
            dt = max(now - last_t, 0.01)
            last_t = now

            # ---------- INIT ----------
            if state == S_INIT:
                alarms.clear()

                mm44_list, ok_mm44 = open_mm44_all(mm44_ports)
                if not ok_mm44:
                    alarms.add("MM44_OPEN_FAIL")

                if not args.no_mfc:
                    try:
                        for r in reactors:
                            air_mfc[r.name] = make_mfc(args.mfc, r.air_addr)
                            co2_mfc[r.name] = make_mfc(args.mfc, r.co2_addr)
                            write_u16(air_mfc[r.name], REG_CTRL_MODE, 10)
                            write_u16(co2_mfc[r.name], REG_CTRL_MODE, 10)
                    except Exception:
                        alarms.add("MFC_INIT_FAIL")

                if alarms:
                    state = S_FAILSAFE
                else:
                    state = S_RUN

            # ---------- Read MM44 ----------
            for idx, ser in enumerate(mm44_list):
                for _ in range(6):
                    try:
                        raw = ser.readline().decode(errors="ignore").strip()
                    except Exception:
                        alarms.add("MM44_READ_FAIL")
                        break

                    if not raw:
                        break

                    last_mm44_raw[idx] = raw
                    if show_raw:
                        print(f"RAW[{idx}]: {raw}")

                    parsed = parse_mm44_line(raw)
                    if parsed:
                        mm44_data.setdefault(idx, {}).update(parsed)

            validate_mapping(mm44_data, reactors, alarms)

            # ---------- Build reactor values ----------
            reactor_values = {}

            for r in reactors:
                ph_block = get_channel(mm44_data, r.ph_mm44, r.ph_ch)
                ph = ph_block.get("value") if ph_block else None

                if ph is not None and 0.0 <= ph <= 14.0:
                    last_ph_time[r.name] = time.time()

                reactor_values[r.name] = {
                    "enabled": r.enabled,
                    "pH": ph,
                    "ph_sp": r.ph_sp,
                    "air_baseline": r.air_baseline,
                    "air_cmd": air_cmd[r.name],
                    "co2_cmd": co2_cmd[r.name],
                }

            # ---------- Stale detection ----------
            for r in reactors:
                key = f"{r.name}_PH_STALE"
                if last_ph_time[r.name] and (time.time() - last_ph_time[r.name]) > MM44_STALE_SEC:
                    alarms.add(key)
                else:
                    alarms.discard(key)

            # ---------- Control ----------
            if state == S_RUN:
                for r in reactors:
                    if not r.enabled or f"{r.name}_PH_STALE" in alarms:
                        apply_safe_outputs_for_reactor(
                            r, co2_cmd, air_cmd, air_mfc, co2_mfc, args.no_mfc
                        )
                        continue

                    ph = reactor_values[r.name]["pH"]
                    if ph is None:
                        continue

                    if abs(ph - r.ph_sp) <= args.deadband:
                        control_signal = 0.0
                    else:
                        control_signal = pids[r.name].update(ph, r.ph_sp, dt)

                    if args.mode == "co2_only" or control_signal >= 0:
                        target_co2 = clamp(control_signal, CO2_MIN, CO2_MAX)
                        target_air = r.air_baseline
                    else:
                        target_co2 = 0.0
                        target_air = clamp_air(r.air_baseline + abs(control_signal))

                    co2_cmd[r.name] = rate_limit(
                        target_co2, co2_cmd[r.name], CO2_RATE_LIMIT_PER_S * dt
                    )
                    air_cmd[r.name] = rate_limit(
                        target_air, air_cmd[r.name], AIR_RATE_LIMIT_PER_S * dt
                    )

                    if not args.no_mfc:
                        mfc_try(write_f32, co2_mfc[r.name], REG_VALVE_CMD, co2_cmd[r.name])
                        mfc_try(write_f32, air_mfc[r.name], REG_VALVE_CMD, air_cmd[r.name])
                        flow, _ = mfc_try(read_f32, co2_mfc[r.name], REG_FLOW_ACTUAL)
                        last_co2_flow[r.name] = flow

            # ---------- Dashboard ----------
            try:
                with open(MM44_LATEST_JSON, "w") as f:
                    json.dump({
                        "ts": now_iso(),
                        "state": state,
                        "alarms": sorted(list(alarms)),
                        "reactors": reactor_values,
                    }, f)
            except Exception:
                pass

            # ---------- Logging ----------
            if log_enabled and (time.time() - last_log_ts) >= args.log_interval:
                last_log_ts = time.time()
                purge_old_logs(args.log_dir, datetime.now(), args.log_retention_days)

                header = [
                    "timestamp", "reactor", "state", "enabled",
                    "pH", "ph_sp", "air_cmd", "co2_cmd", "alarms"
                ]

                minute_tag = datetime.now().strftime("%Y-%m-%d %H:%M")
                for r in reactors:
                    if last_logged_minute[r.name] == minute_tag:
                        continue
                    last_logged_minute[r.name] = minute_tag

                    row = {
                        "timestamp": now_iso(),
                        "reactor": r.name,
                        "state": state,
                        "enabled": r.enabled,
                        "pH": reactor_values[r.name]["pH"],
                        "ph_sp": r.ph_sp,
                        "air_cmd": air_cmd[r.name],
                        "co2_cmd": co2_cmd[r.name],
                        "alarms": ",".join(sorted(alarms)),
                    }
                    append_csv_row(
                        reactor_log_path(args.log_dir, r.name, datetime.now()),
                        header, row
                    )

            time.sleep(args.dt)

    except KeyboardInterrupt:
        print("\nStopping controller (safe shutdown)")

    finally:
        for r in reactors:
            try:
                if r.name in co2_mfc:
                    write_f32(co2_mfc[r.name], REG_VALVE_CMD, 0.0)
            except Exception:
                pass

        close_mm44_all(mm44_list)
        print("Shutdown complete")


if __name__ == "__main__":
    main()
