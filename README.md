# mu2edaq-bigredbox

This is the Peter Shanahan inspired "BIG RED BOX"(tm)

Peter's box popped up when there was a major DAQ error, and was design to be big and red.  Basically there is no question that there is a problem when this things appears.

So welcome to the mu2e version of the big red box.

This is more sophisticated than the original Shanahan design but still super simple to use.

A daemon runs the main application anywhere within the DAQ network (typically on a main node where run control or other applications are running).  It then listens for BROADCAST UDP messages on a port.

If a message is broadcast in this manner (and here it can be from any place in the DAQ and the sender doesn't need to know anything about the reciever) it is picked up by the application, and a BIG RED BOX appears (with some additional info).

This is written using QT5 so it's portable. C, C++, and Python sender libraries are provided under `libs/` along with three example programs (`example-sender-c`, `example-sender-cpp`, `example-sender-py`).

## Features

- Listens for UDP broadcast messages on a configurable port (default: 37020)
- Displays a full-screen-style alert window with the system ID, timestamp, and error message
- Stays on top of other windows until acknowledged
- Rate-limits incoming messages to prevent flooding and unresponsiveness
- Caps the number of simultaneous alert windows
- Has a **Pause** box to turn off incoming messages
- Has a history of **Errors Received** and a counter which can open up a history so you can see what is going wrong.
- Runs as a background daemon with PID and log file management

## Requirements

- Python 3.9+
- A display environment (X11 / `DISPLAY` variable set)

This does work with ssh forwarded X11 connections

## Install

Create and activate a Python virtual environment, then install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # PyQt5>=5.15
```

## Usage

```bash
# Start the alert listener as a background daemon
./start_daq_alert.sh

# Stop the daemon
./stop_daq_alert.sh

# Send a test alert to verify the GUI works
python3 demo_sender.py
python3 demo_sender.py --system-id "DAQ-NODE-03" --message "Readout buffer overflow"
python3 demo_sender.py --ip 192.168.1.255 --port 37020
```

The daemon writes logs to `/tmp/daq_alert.log` and stores its PID at `/tmp/daq_alert.pid`.

## Alert payload format

External DAQ systems broadcast JSON over UDP:

```json
{
  "system_id": "DAQ-NODE-01",
  "timestamp": "2026-03-11T14:32:00",
  "message": "Critical error in the data acquisition pipeline."
}
```

## Architecture

```
UDP broadcast (port 37020)
        │
        ▼
UDPListenerThread   ← background QThread, emits message_received signal
        │
        ▼
  DAQAlertApp       ← throttles & caps windows, owns the Qt event loop
        │
        ▼
  AlertWindow       ← always-on-top PyQt5 window, tracks per-window history
```

**Key files:**

| File | Purpose |
|------|---------|
| `daq_alert.py` | Main application: UDP listener thread, alert window GUI, daemon lifecycle |
| `demo_sender.py` | Test utility to send mock alert messages |
| `config.py` | Shared constants (`BROADCAST_PORT`, `MESSAGE_RATE_LIMIT`, `MAX_ALERT_WINDOWS`, log/PID paths) |
| `start_daq_alert.sh` | Start the daemon in the background |
| `stop_daq_alert.sh` | Stop the running daemon |
| `libs/` | C, C++, and Python alert-sender libraries with CMake build system |
| `libs/examples/` | Example sender programs for each library interface |
| `BUILD.md` | Full build and installation instructions |

## Configuration

Edit `config.py` to change defaults:

| Constant | Default | Description |
|----------|---------|-------------|
| `BROADCAST_PORT` | `37020` | UDP port to listen on |
| `MESSAGE_RATE_LIMIT` | `10.0` | Max messages accepted per second |
| `MAX_ALERT_WINDOWS` | `2` | Max simultaneous alert windows |
| `LOG_FILE` | `/tmp/daq_alert.log` | Daemon log path |
| `PID_FILE` | `/tmp/daq_alert.pid` | Daemon PID file path |

## Dismissing an alert

Click **ACKNOWLEDGE**, or press `Enter`, `Esc`, or `Space`.
