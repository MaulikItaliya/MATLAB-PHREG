# PHREG Dashboard

This dashboard provides a lightweight user interface for monitoring
and controlling the PHREG multi-reactor pH controller.

## How it works

The dashboard communicates with the controller via JSON files:

- Telemetry (read-only):
  `/tmp/mm44_latest.json`

- Commands (write):
  `/tmp/mm44_cmd.json`

No direct process or network communication is used.

## Requirements

- PHREG controller running
- Access to `/tmp`
- Modern web browser (or Python runtime, depending on implementation)

## Usage

1. Start the controller:
   ```bash
   python phreg_controller.py

