# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`mu2edaq-bigredbox` is a PyQt5-based GUI daemon for the Mu2e experiment's Data Acquisition (DAQ) system. It displays prominent alert windows when fatal/critical errors are broadcast over the network.

## Compatibility

All code should be compatible with python 3.9

## Running the Application

```bash
# Start the alert listener as a background daemon
./start_daq_alert.sh

# Stop the daemon
./stop_daq_alert.sh

# Send a test alert (to verify the GUI works)
mu2edaq-bigredbox-send
mu2edaq-bigredbox-send --system-id "DAQ-NODE-03" --message "Readout buffer overflow"
mu2edaq-bigredbox-send --ip 192.168.1.255 --port 37020
```

The daemon logs to `/tmp/daq_alert.log` and stores its PID at `/tmp/daq_alert.pid`.

## Setup

```bash
./bootstrap.sh            # creates venv/ and installs the package (--dev adds pytest)
source venv/bin/activate

# or, manually:
pip install -e '.[dev]'
```

Requires a `DISPLAY` environment variable set (X11/GUI environment).

## Architecture

**UDP publish-subscribe pattern:**
- External DAQ systems broadcast JSON alert payloads via UDP to port 37020
- `UDPListenerThread` in `daq_alert.py` receives these in a background thread and emits a Qt signal
- `DAQAlertApp` handles the signal and creates `AlertWindow` instances
- Alert windows stay on top and are dismissed via Enter/Esc/Space or button click

**Payload format:**
```json
{"system_id": "...", "timestamp": "<ISO 8601>", "message": "..."}
```

**Key files:**
- `pyproject.toml` — setuptools build; `src/` layout, console scripts, man pages
- `src/mu2edaq_bigredbox/daq_alert.py` — Main application: UDP listener thread, alert window GUI, daemon lifecycle
- `src/mu2edaq_bigredbox/demo_sender.py` — Test utility to send mock alert messages
- `src/mu2edaq_bigredbox/config.py` — Shared constants (`BROADCAST_PORT=37020`, log/PID file paths)
- `daq_alert.py`, `demo_sender.py` (repo root) — compatibility shims that import from the package
- `man/man1/` — man pages for `mu2edaq-bigredbox` and `mu2edaq-bigredbox-send`

**Entry points:** `mu2edaq-bigredbox` (listener, also `python -m mu2edaq_bigredbox`)
and `mu2edaq-bigredbox-send` (test sender).

## Tests

`pytest` runs the packaging/protocol smoke tests in `tests/`. The GUI has no
automated coverage — use `mu2edaq-bigredbox-send` for manual functional testing.
