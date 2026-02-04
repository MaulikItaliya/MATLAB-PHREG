# ============================================================
# MFC (Modbus RTU) helpers
# ============================================================

def make_mfc(port, addr):
    """Create and configure a Modbus RTU instrument for an MFC."""
    inst = minimalmodbus.Instrument(port, addr, mode=minimalmodbus.MODE_RTU)
    inst.serial.baudrate = MFC_BAUD
    inst.serial.parity = serial.PARITY_NONE
    inst.serial.stopbits = 2
    inst.serial.bytesize = 8
    inst.serial.timeout = MFC_TIMEOUT
    inst.clear_buffers_before_each_transaction = True
    inst.close_port_after_each_call = True
    return inst

def write_u16(inst, reg, value):
    inst.write_register(reg, int(value), 0, functioncode=6, signed=False)

def read_f32(inst, reg):
    w0, w1 = inst.read_registers(reg, 2, functioncode=3)
    if WORD_ORDER == "hi_lo":
        raw = struct.pack(">HH", w0, w1)
    else:
        raw = struct.pack(">HH", w1, w0)
    return struct.unpack(">f", raw)[0]

def write_f32(inst, reg, value):
    raw = struct.pack(">f", float(value))
    hi, lo = struct.unpack(">HH", raw)
    if WORD_ORDER == "hi_lo":
        inst.write_registers(reg, [hi, lo])
    else:
        inst.write_registers(reg, [lo, hi])

def mfc_try(op, *args, retries=3, delay=0.05):
    """
    Execute a Modbus operation with retries.
    Returns (result, error).
    """
    last_err = None
    for _ in range(retries):
        try:
            return op(*args), None
        except Exception as e:
            last_err = e
            time.sleep(delay)
    return None, last_err

# ============================================================
# MM44 channel access helpers
# ============================================================

def get_channel(mm44_data, mm44_idx: int, ch: str):
    dev = mm44_data.get(mm44_idx, {})
    return dev.get(ch.upper())

# ============================================================
# Mapping validation
# ============================================================

def validate_mapping(mm44_data, reactors, alarms):
    """
    Ensure each reactor's mapped channels exist and match expected types.
    Raises alarms but does not crash the controller.
    """
    for r in reactors:
        ph_block = get_channel(mm44_data, r.ph_mm44, r.ph_ch)
        do_block = get_channel(mm44_data, r.do_mm44, r.do_ch)

        # ---- pH validation ----
        ph_missing = f"MAP_CH_MISSING_{r.name}_PH"
        ph_mismatch = f"MAP_TYPE_MISMATCH_{r.name}_PH"

        if ph_block is None:
            if r.ph_mm44 in mm44_data:
                alarms.add(ph_missing)
            else:
                alarms.discard(ph_missing)
            alarms.discard(ph_mismatch)
        else:
            alarms.discard(ph_missing)
            if ph_block.get("type") != "pH":
                alarms.add(ph_mismatch)
            else:
                alarms.discard(ph_mismatch)

        # ---- DO validation ----
        do_missing = f"MAP_CH_MISSING_{r.name}_DO"
        do_mismatch = f"MAP_TYPE_MISMATCH_{r.name}_DO"

        if do_block is None:
            if r.do_mm44 in mm44_data:
                alarms.add(do_missing)
            else:
                alarms.discard(do_missing)
            alarms.discard(do_mismatch)
        else:
            alarms.discard(do_missing)
            if do_block.get("type") != "DO":
                alarms.add(do_mismatch)
            else:
                alarms.discard(do_mismatch)

# ============================================================
# State machine definitions
# ============================================================

S_INIT     = "INIT"
S_RUN      = "RUN"
S_DEGRADED = "DEGRADED"
S_FAILSAFE = "FAILSAFE"

# ============================================================
# Safety output helpers
# ============================================================

def apply_safe_outputs_for_reactor(r, co2_cmd, air_cmd, air_mfc, co2_mfc, no_mfc):
    """
    Force a single reactor into a safe state.
    CO₂ -> 0
    AIR -> 0
    """
    co2_cmd[r.name] = 0.0
    air_cmd[r.name] = 0.0

    if no_mfc:
        return

    if r.name in co2_mfc:
        mfc_try(write_f32, co2_mfc[r.name], REG_VALVE_CMD, 0.0)

    if r.name in air_mfc:
        mfc_try(write_f32, air_mfc[r.name], REG_VALVE_CMD, 0.0)

def failsafe_outputs_all(reactors, co2_cmd, air_cmd, air_mfc, co2_mfc, no_mfc):
    """
    Global failsafe:
    All reactors → CO₂ = 0, AIR = 0
    """
    for r in reactors:
        apply_safe_outputs_for_reactor(
            r, co2_cmd, air_cmd, air_mfc, co2_mfc, no_mfc
        )

# ============================================================
# MM44 serial helpers
# ============================================================

def close_mm44_all(mm44_list):
    for s in mm44_list:
        try:
            s.close()
        except Exception:
            pass
    return []

def open_mm44_all(mm44_ports):
    mm44_list = []
    ok = True

    for p in mm44_ports:
        try:
            ser = serial.Serial(p, MM44_BAUD, timeout=MM44_TIMEOUT)
            time.sleep(0.25)
            mm44_list.append(ser)
            print(f"[MM44] open: {p}")
        except Exception as e:
            print(f"[MM44] open failed on {p}: {e}")
            ok = False

    return mm44_list, ok and len(mm44_list) == len(mm44_ports)
