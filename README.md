# mu2edaq-bigredbox

This is the Peter Shanahan inspired "BIG RED BOX"(tm)

Peter's box popped up when there was a major DAQ error, and was design to be big and red.  Basically there is no question that there is a problem when this things appears.

So welcome to the mu2e version of the big red box.

This is more sophisticated than the original Shanahan design but still super simple to use.

A daemon runs the main application anywhere within the DAQ network (typically on a main node where run control or other applications are running).  It then listens for BROADCAST UDP messages on a port.

If a message is broadcast in this manner (and here it can be from any place in the DAQ and the sender doesn't need to know anything about the reciever) it is picked up by the application, and a BIG RED BOX appears (with some additional info).

This is written using Qt6 (PyQt6) so it's portable. C, C++, and Python sender libraries are provided under `libs/` along with three example programs (`example-sender-c`, `example-sender-cpp`, `example-sender-py`).

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
- PyQt6 (Qt 6.4 or later) — installed automatically as a dependency
- A display environment (X11 / `DISPLAY` variable set)

This does work with ssh forwarded X11 connections.

> **Qt6 note.** The GUI was migrated from PyQt5 to PyQt6; there is no longer any
> Qt5 dependency. PyQt6 6.10 and later require Python 3.10+, so on Python 3.9
> pip resolves to PyQt6 6.9.1 (verified on manylinux) — that is fine, since the
> code uses no API introduced after 6.4. On Linux, Qt6 needs the
> usual X11 client libraries (`libxkbcommon-x11`, `libEGL`, `xcb-cursor`); on
> RHEL/AlmaLinux install `libxkbcommon-x11 xcb-util-cursor mesa-libEGL`.

## Install

The listener is a standard Python package (`mu2edaq-bigredbox`). The bootstrap
script creates `venv/` and installs it in editable mode:

```bash
./bootstrap.sh          # add --dev for pytest and build tooling
source venv/bin/activate
```

Or install it by hand into any environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install .                       # or: pip install -e .
pip install '.[discovery]'          # plus mu2edaq-discovery auto-discovery
```

Installing provides two commands:

| Command | Purpose |
|---------|---------|
| `mu2edaq-bigredbox` | Run the alert listener (also `python -m mu2edaq_bigredbox`) |
| `mu2edaq-bigredbox-send` | Send a test alert |

Man pages are installed to `<prefix>/share/man/man1`; inside a venv read them
with `man ./venv/share/man/man1/mu2edaq-bigredbox.1`.

## Usage

```bash
# Start the alert listener as a background daemon
./start_daq_alert.sh

# Stop the daemon
./stop_daq_alert.sh

# Send a test alert to verify the GUI works
mu2edaq-bigredbox-send
mu2edaq-bigredbox-send --system-id "DAQ-NODE-03" --message "Readout buffer overflow"
mu2edaq-bigredbox-send --ip 192.168.1.255 --port 37020
```

`daq_alert.py` and `demo_sender.py` remain at the repository root as thin
shims, so `python3 daq_alert.py` and `python3 demo_sender.py` still work from a
checkout even when the package is not installed.

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
  AlertWindow       ← always-on-top PyQt6 window, tracks per-window history
```

**Key files:**

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package build (setuptools, `src/` layout, console scripts, man pages) |
| `src/mu2edaq_bigredbox/daq_alert.py` | Main application: UDP listener thread, alert window GUI, daemon lifecycle |
| `src/mu2edaq_bigredbox/demo_sender.py` | Test utility to send mock alert messages |
| `src/mu2edaq_bigredbox/config.py` | Shared constants (`BROADCAST_PORT`, `MESSAGE_RATE_LIMIT`, `MAX_ALERT_WINDOWS`, log/PID paths) |
| `daq_alert.py`, `demo_sender.py` | Root-level compatibility shims for running from a checkout |
| `man/man1/` | Man pages for both console scripts |
| `tests/test_packaging.py` | pytest checks for the package build and the UDP payload |
| `tests/test_gui.py` | Headless PyQt6 widget tests (offscreen platform) |
| `bootstrap.sh` | Create `venv/` and install the package |
| `start_daq_alert.sh` | Start the daemon in the background |
| `stop_daq_alert.sh` | Stop the running daemon |
| `libs/` | C, C++, and Python alert-sender libraries with CMake build system |
| `libs/examples/` | Example sender programs for each library interface |
| `BUILD.md` | Full build and installation instructions |

## Configuration

Edit `src/mu2edaq_bigredbox/config.py` to change defaults:

| Constant | Default | Description |
|----------|---------|-------------|
| `BROADCAST_PORT` | `37020` | UDP port to listen on (overridden by `CRS_PORT_UDP`) |
| `MESSAGE_RATE_LIMIT` | `10.0` | Max messages accepted per second |
| `MAX_ALERT_WINDOWS` | `2` | Max simultaneous alert windows |
| `LOG_FILE` | `/tmp/daq_alert.log` | Daemon log path |
| `PID_FILE` | `/tmp/daq_alert.pid` | Daemon PID file path |

## Dismissing an alert

Click **ACKNOWLEDGE**, or press `Enter`, `Esc`, or `Space`.

## Tests

```bash
./bootstrap.sh --dev
source venv/bin/activate
pytest
```

The suite runs headless — `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen`,
so no `DISPLAY` is needed. `tests/test_gui.py` constructs the real PyQt6
widgets, which is what catches the scoped-enum errors the Qt5→Qt6 port can
introduce. To watch the windows while testing, override the platform:

```bash
QT_QPA_PLATFORM=xcb pytest        # cocoa on macOS, windows on Win32
```
