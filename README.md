PHREG – Multi-Reactor pH Controller

PHREG is a robust, safety-oriented pH regulation system for up to three independent bioreactors, designed for real laboratory and industrial environments.

This project is not a simulation and not a demo.
It is written with the assumption that hardware fails, sensors go stale, and operators make runtime changes.

Features

Independent pH control for up to 3 reactors

MM44 multi-channel pH / DO sensor support

AIR and CO₂ control via Modbus RTU MFCs

Split-range control (CO₂ ↓ pH, AIR ↑ pH)

Deterministic state machine

Explicit failsafe behavior

Runtime enable / disable per reactor

CLI + JSON dashboard interface

Per-reactor CSV logging with retention

Repository Structure
.
├── phreg_core.py        # Core logic, PID, helpers, parsing
├── phreg_hardware.py    # Hardware interfaces & safety layer
├── phreg_controller.py  # Main control loop (entry point)
└── README.md

Design choice

The project is split for clarity, but control remains centralized in phreg_controller.py.

System Architecture
MM44 Sensors
    ↓
Parsing & Validation
    ↓
State Machine
    ↓
Per-Reactor PID Control
    ↓
Rate Limiting
    ↓
MFC Actuation (AIR / CO₂)


Each reactor is isolated in software.
A failure in one reactor does not affect the others.

Control Strategy

Control error is defined as:

error = measured_pH − pH_setpoint


Positive error → pH too high → inject CO₂

Negative error → pH too low → increase AIR

Supported modes

CO₂-only mode
AIR fixed at baseline, CO₂ reduces pH

Split-range mode (default)
CO₂ reduces pH, AIR raises pH when below setpoint

Deadbands and rate limits prevent oscillation and valve chatter.

Safety Philosophy

If anything is uncertain, do nothing dangerous.

Guaranteed behaviors:

Missing or stale pH → no gas injection

MFC communication failure → CO₂ forced to 0

Disabled reactor → isolated in software

AIR baseline clamped to a safe minimum

Explicit safe initialization and shutdown

There are no silent fallbacks.

Requirements
Software

Python 3.9+

Linux (recommended for serial stability)

Python dependencies
pip install pyserial minimalmodbus

Hardware

MM44 pH / DO transmitters

Modbus RTU Mass Flow Controllers (AIR / CO₂)

USB-RS485 adapter

Industrial PC or lab workstation

How to Run
Basic start
python phreg_controller.py

Specify serial ports
python phreg_controller.py \
  --mm44_ports /dev/ttyUSB0,/dev/ttyUSB1 \
  --mfc /dev/ttyUSB2

Run without MFCs (monitoring only)
python phreg_controller.py --no_mfc

Enable CSV logging
python phreg_controller.py --log_enable

Runtime Interaction
1. Command-Line Interface (CLI)

Available commands while running:

sp R1 7.40        # Set pH setpoint
air R1 20         # Set AIR baseline
enable R2 on      # Enable reactor
enable R2 off     # Disable reactor
status            # Show system state
raw on|off        # Toggle raw MM44 output
q                 # Quit safely


Changes apply immediately and safely.

2. Dashboard JSON Interface
Telemetry output
/tmp/mm44_latest.json


Contains:

Current state

Alarms

Per-reactor values

Actuator commands

Command input
/tmp/mm44_cmd.json


Example:

{
  "ts": "2026-02-07T12:30:00",
  "rid": 1,
  "sp_ph": 7.30,
  "air_baseline": 25,
  "enabled": true
}


Designed for web or GUI dashboards.

3. CSV Logging

One file per reactor

One row per minute

Monthly rotation

Automatic retention cleanup

Example:

R1_2026-02.csv
R2_2026-02.csv

Failure Modes
Condition	Behavior
pH stale	Gas injection disabled
MFC error	CO₂ forced to 0
Reactor disabled	AIR & CO₂ off
Startup / shutdown	Safe state enforced
Intended Audience

Embedded & control engineers

Industrial automation developers

Research labs running live experiments

This project assumes familiarity with:

PID control

Modbus RTU

Serial instrumentation

License

MIT License (or specify otherwise)

Summary

This project prioritizes:

Correctness over elegance

Explicit safety over clever abstractions

Real hardware behavior over theory
