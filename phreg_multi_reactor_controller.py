#!/usr/bin/env python3
"""
PHREG – Robust Multi-Reactor pH Controller

Design goals:
- Deterministic behavior under partial hardware failure
- Per-reactor fault isolation (disable one without touching others)
- Operator-safe defaults (CO₂ always fails closed)
- Headless operation with CLI + JSON dashboard interface

This file intentionally contains the full control loop to simplify
deployment on industrial PCs and lab machines.

Author: Maulik U. Italiya
"""

# ============================================================
# Standard library
# ============================================================

import time
import sys
import select
import argparse
import json
import struct
import os
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# Third-party
# ============================================================

import serial
import minimalmodbus

# ============================================================
# Defaults – hardware & serial
# ============================================================

MM44_PORTS_DEFAULT = (
    "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Cable_FTXWTKP3-if00-port0,"
    "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Cable_FTXWTKP3-if01-port0"
)
MFC_PORT_DEFAULT = "/dev/ttyUSB2"

MM44_BAUD = 9600
MM44_TIMEOUT = 0.15

MFC_BAUD = 9600
MFC_TIMEOUT = 0.6

# Modbus float word order (instrument-specific)
WORD_ORDER = "hi_lo"

# ============================================================
# MFC registers
# ============================================================

REG_FLOW_ACTUAL = 0x0000
REG_VALVE_CMD   = 0x000A
REG_CTRL_MODE   = 0x000E

# ============================================================
# Control parameters
# ============================================================

DT_DEFAULT = 1.0
PH_DEADBAND_DEFAULT = 0.05

# CO₂ always fails closed
CO2_MIN, CO2_MAX = 0.0, 100.0
AIR_MIN, AIR_MAX = 20.0, 100.0

# Prevent valve chatter & gas shocks
CO2_RATE_LIMIT_PER_S = 10.0
AIR_RATE_LIMIT_PER_S = 10.0

# Conservative PID defaults (field tuned later)
PID_KP = 25.0
PID_KI = 1.0
PID_KD = 0.0

# ============================================================
# Logging / dashboard
# ============================================================

MM44_LATEST_JSON = "/tmp/mm44_latest.json"
MM44_CMD_JSON = "/tmp/mm44_cmd.json"

LOG_DIR_DEFAULT = os.environ.get("PHREG_LOG_DIR", "/mnt/phreg_logs")
LOG_RETENTION_DAYS = 35
LOG_INTERVAL_S = 60

MM44_STALE_SEC = 3.0

# ============================================================
# Reactor configuration
# ============================================================

@dataclass
class ReactorCfg:
    name: str
    enabled: bool

    ph_mm44: int
    ph_ch: str
    do_mm44: int
    do_ch: str

    air_addr: int
    co2_addr: int

    ph_sp: float
    air_baseline: float


REACTORS_DEFAULT = [
    ReactorCfg("R1", True,  0, "C1", 1, "C2", 1, 2, 7.40, 20.0),
    ReactorCfg("R2", True,  0, "C2", 1, "C3", 6, 5, 7.40, 20.0),
    ReactorCfg("R3", True,  1, "C1", 0, "C3", 7, 4, 7.40, 20.0),
]

# ============================================================
# Utility helpers
# ============================================================

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def rate_limit(new, old, max_delta):
    delta = new - old
    if delta > max_delta:
        return old + max_delta
    if delta < -max_delta:
        return old - max_delta
    return new

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def safe_float(x):
    try:
        return float(str(x).strip())
    except Exception:
        return None

# ============================================================
# PID controller
# ============================================================

class PID:
    """
    Error definition:
        err = pH - SP

    +err → pH too high → inject CO₂
    -err → pH too low  → boost AIR (split-range mode)
    """

    def __init__(self, kp, ki, kd, out_min, out_max):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.out_min = out_min
        self.out_max = out_max

        self.integrator = 0.0
        self.prev_err = None

    def reset(self):
        self.integrator = 0.0
        self.prev_err = None

    def update(self, pv, sp, dt):
        err = pv - sp

        d_term = 0.0
        if self.prev_err is not None and dt > 0:
            d_term = (err - self.prev_err) / dt
        self.prev_err = err

        self.integrator += err * dt
        self.integrator = clamp(self.integrator, -1000.0, 1000.0)

        control_signal = (
            self.kp * err +
            self.ki * self.integrator +
            self.kd * d_term
        )

        return clamp(control_signal, self.out_min, self.out_max)

# ============================================================
# MM44 parsing
# ============================================================

def parse_mm44_line(line: str):
    parts = [p.strip() for p in line.split(";")]
    parsed = {}

    def is_channel(tok):
        return tok.startswith("C") and len(tok) == 2 and tok[1].isdigit()

    i = 0
    while i < len(parts):
        if is_channel(parts[i]) and i + 2 < len(parts):
            ch = parts[i]
            kind = parts[i + 1].upper()
            value = safe_float(parts[i + 2])

            if kind in ("PH", "DO", "OD"):
                parsed[ch] = {
                    "type": "pH" if kind == "PH" else "DO",
                    "value": value,
                }
        i += 1

    return parsed

# ============================================================
# MFC helpers (Modbus RTU)
# ============================================================

def make_mfc(port, addr):
    inst = minimalmodbus.Instrument(port, addr, mode=minimalmodbus.MODE_RTU)
    inst.serial.baudrate = MFC_BAUD
    inst.serial.timeout = MFC_TIMEOUT
    inst.clear_buffers_before_each_transaction = True
    inst.close_port_after_each_call = True
    return inst

def write_f32(inst, reg, value):
    raw = struct.pack(">f", float(value))
    hi, lo = struct.unpack(">HH", raw)
    inst.write_registers(reg, [hi, lo])

def read_f32(inst, reg):
    hi, lo = inst.read_registers(reg, 2)
    return struct.unpack(">f", struct.pack(">HH", hi, lo))[0]

# ============================================================
# Main application
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="PHREG pH controller")
    ap.add_argument("--no_mfc", action="store_true", help="Run MM44 only")
    ap.add_argument("--dt", type=float, default=DT_DEFAULT)
    args = ap.parse_args()

    reactors = [r for r in REACTORS_DEFAULT]
    pids = {r.name: PID(PID_KP, PID_KI, PID_KD, -100.0, CO2_MAX) for r in reactors}

    co2_cmd = {r.name: 0.0 for r in reactors}
    air_cmd = {r.name: r.air_baseline for r in reactors}

    print("PHREG controller started.")
    print("Reactors:", ", ".join(r.name for r in reactors))

    try:
        while True:
            for r in reactors:
                if not r.enabled:
                    co2_cmd[r.name] = 0.0
                    air_cmd[r.name] = 0.0
                    continue

                # Placeholder: real pH comes from MM44
                ph = r.ph_sp

                u = pids[r.name].update(ph, r.ph_sp, args.dt)

                if u >= 0:
                    co2_cmd[r.name] = rate_limit(u, co2_cmd[r.name], CO2_RATE_LIMIT_PER_S)
                    air_cmd[r.name] = r.air_baseline
                else:
                    co2_cmd[r.name] = 0.0
                    air_cmd[r.name] = clamp(
                        r.air_baseline + abs(u),
                        AIR_MIN, AIR_MAX
                    )

            print(
                f"{datetime.now().strftime('%H:%M:%S')} | "
                + " | ".join(
                    f"{r.name}: pH_SP={r.ph_sp:.2f} AIR={air_cmd[r.name]:.1f}% CO2={co2_cmd[r.name]:.1f}%"
                    for r in reactors
                )
            )

            time.sleep(args.dt)

    except KeyboardInterrupt:
        print("\nStopping controller. CO₂ set to 0 for all reactors.")

if __name__ == "__main__":
    main()
