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
python3 demo_sender.py
python3 demo_sender.py --system-id "DAQ-NODE-03" --message "Readout buffer overflow"
python3 demo_sender.py --ip 192.168.1.255 --port 37020
```

The daemon logs to `/tmp/daq_alert.log` and stores its PID at `/tmp/daq_alert.pid`.

## Setup

```bash
pip install -r requirements.txt  # PyQt5>=5.15 is the only dependency
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
- `daq_alert.py` — Main application: UDP listener thread, alert window GUI, daemon lifecycle
- `demo_sender.py` — Test utility to send mock alert messages
- `config.py` — Shared constants (`BROADCAST_PORT=37020`, log/PID file paths)

## No Test Framework

There is no automated test suite. Use `demo_sender.py` for manual functional testing.
