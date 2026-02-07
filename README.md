PHREG – Multi-Reactor pH Controller

Detailed Technical Documentation

1. Introduction

PHREG (pH REGulation) is a robust, safety-oriented pH control system designed for real laboratory and industrial bioprocess environments.
It supports up to three independent reactors, each controlled in isolation, using industrial-grade instrumentation.

This project is not a simulation and not a teaching example.
It is designed with the assumption that:

Sensors may fail or provide stale data

Communication with actuators may be unreliable

Operators may enable or disable reactors at runtime

Safety must always override control objectives

The controller enforces explicit safety behavior at every stage of execution.

2. System Overview

The controller interfaces with the following hardware:

MM44 multi-channel transmitters

pH measurement

Dissolved Oxygen (DO) measurement

Mass Flow Controllers (MFCs)

AIR flow control

CO₂ flow control

Communication via Modbus RTU

Host system

Linux-based lab PC or industrial PC

Python runtime (headless operation)

Each reactor has:

One pH input

One DO input (monitored, not controlled)

One AIR MFC

One CO₂ MFC

Reactors are fully independent in software.

3. Repository Structure

The project is split into three logical modules for clarity and maintainability:

phreg_core.py
phreg_hardware.py
phreg_controller.py

3.1 phreg_core.py

Contains pure logic and shared infrastructure:

Constants and configuration defaults

Reactor configuration (ReactorCfg)

Utility functions (clamping, rate limiting)

PID controller implementation

MM44 data parsing

CSV logging helpers

JSON helper functions

This file contains no direct hardware side effects.

3.2 phreg_hardware.py

Contains hardware-specific logic and safety mechanisms:

Modbus RTU helpers for MFCs

MM44 serial open/close helpers

Channel mapping validation

Alarm generation

Safety output functions

State machine definitions

This file is responsible for safe interaction with hardware.

3.3 phreg_controller.py

This is the application entry point:

Argument parsing

Initialization logic

State machine execution

Main control loop

Runtime CLI handling

Dashboard JSON I/O

CSV logging execution

Safe shutdown logic

This file orchestrates the entire system.

4. High-Level Architecture

The controller follows a deterministic execution pipeline:

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


Each stage must succeed before the next stage is allowed to influence hardware.

5. Control Strategy
5.1 Error Definition

The pH control error is defined as:

error = measured_pH − pH_setpoint


Interpretation:

Positive error → pH too high → reduce pH

Negative error → pH too low → increase pH

5.2 Operating Modes
CO₂-Only Mode

AIR is held at a fixed baseline

CO₂ is used exclusively to reduce pH

Suitable when aeration must remain constant

Split-Range Mode (Default)

CO₂ reduces pH when pH is too high

AIR increases pH when pH is too low

Prevents aggressive CO₂ usage

Mirrors real bioprocess control practice

5.3 PID Control

Each reactor has:

Its own PID controller

Its own integrator

No cross-coupling between reactors

Features:

Configurable gains

Anti-windup via integrator clamping

Deadband around setpoint

Output clamping

5.4 Rate Limiting

All actuator commands are rate-limited to:

Prevent valve chatter

Prevent pressure shocks

Reduce mechanical wear

Rate limits are applied after PID computation.

6. State Machine

The controller operates in four states:

6.1 INIT

Hardware initialization

Serial port opening

MFC control mode setup

Outputs forced to safe values

No control action is allowed.

6.2 RUN

Normal closed-loop operation

PID control active

All safety checks enforced

6.3 DEGRADED

Partial functionality

Active alarms

Control continues where safe

6.4 FAILSAFE

CO₂ forced to 0 for all reactors

AIR forced to safe state

Control action disabled

Transition to FAILSAFE is immediate and deterministic.

7. Safety Philosophy

The controller follows one strict rule:

If anything is uncertain, do nothing dangerous.

Guaranteed behaviors:

Missing or stale pH → no gas injection

Any MFC communication failure → CO₂ = 0

Disabled reactor → isolated in software

AIR baseline clamped to minimum safe value

Explicit safe startup and shutdown

There are no silent fallbacks.

8. Runtime Interaction
8.1 Command-Line Interface (CLI)

Available while the controller is running:

sp R1 7.40        # Set pH setpoint
air R1 20         # Set AIR baseline
enable R2 on      # Enable reactor
enable R2 off     # Disable reactor
status            # Print system state
raw on|off        # Toggle raw MM44 output
q                 # Safe shutdown


Changes apply immediately and safely.

8.2 Dashboard JSON Interface
Telemetry output
/tmp/mm44_latest.json


Contains:

System state

Active alarms

Per-reactor sensor values

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


Designed for GUI or web dashboards.

8.3 CSV Logging

One CSV file per reactor

One row per minute

Monthly file rotation

Retention-based cleanup

Purpose:

Experiment traceability

Validation

Post-analysis

9. Installation & Execution
9.1 Requirements

Python 3.9+

Linux (recommended)

USB-RS485 adapter

9.2 Dependencies
pip install pyserial minimalmodbus

9.3 Run
python phreg_controller.py


Optional flags:

--no_mfc
--log_enable
--mm44_ports
--mfc

10. Intended Audience

This project is intended for:

Control engineers

Embedded systems developers

Industrial automation engineers

Research laboratories running live experiments

It assumes familiarity with:

PID control

Modbus RTU

Industrial instrumentation

11. Design Summary

This controller prioritizes:

Correctness over elegance

Explicit safety over clever abstractions

Real hardware behavior over theoretical purity

The codebase is intentionally conservative, verbose, and defensive.

12. Conclusion

PHREG is a production-grade pH controller built for environments where failure has real consequences.
It reflects real-world engineering constraints rather than academic idealization.
