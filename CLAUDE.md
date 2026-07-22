# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`mu2edaq-bigredbox` is a PyQt6-based GUI daemon for the Mu2e experiment's Data Acquisition (DAQ) system. It displays prominent alert windows when fatal/critical errors are broadcast over the network.

## Compatibility

All code should be compatible with python 3.9.

The GUI uses **Qt6 via PyQt6** (migrated from PyQt5). Do not reintroduce PyQt5
imports. PyQt6 requires fully scoped enums — `Qt.AlignmentFlag.AlignLeft`, not
`Qt.AlignLeft`; `QFont.Weight.Bold`, not `QFont.Bold` — and these fail only at
widget-construction time, so add coverage in `tests/test_gui.py` for new
widgets. `QDesktopWidget` no longer exists; use `widget.screen()`. Use
`app.exec()`, not `app.exec_()`. See the migration table in BUILD.md.

Note that PyQt6 6.10+ requires Python 3.10+, so a 3.9 environment resolves to
PyQt6 6.9.1; keep to APIs available in Qt 6.4.

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

Requires a `DISPLAY` environment variable set (X11/GUI environment) to run the
app. The test suite does not — it renders offscreen.

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
- `tests/conftest.py` — forces `QT_QPA_PLATFORM=offscreen` before Qt is imported

**Entry points:** `mu2edaq-bigredbox` (listener, also `python -m mu2edaq_bigredbox`)
and `mu2edaq-bigredbox-send` (test sender).

**Single-instance invariant:** `UDPListenerThread` binds its socket in
`__init__` (on the calling thread), so a port clash raises `OSError` straight
away; `DAQAlertApp` catches it and exits with `EXIT_PORT_IN_USE` (3). Do not
move the bind back into `run()` — that was the original bug: the app stayed
alive with a dead listener thread and overwrote the PID file of the real
listener. The PID file is written only after a successful bind, so port
ownership is the source of truth. `start_daq_alert.sh` probes the port as well
as the PID file, and `stop_daq_alert.sh` falls back to the port holder.

**Service discovery:** when `mu2edaq-discovery` is installed, `DAQAlertApp`
starts a `Responder` advertising app `bigredbox` on the UDP alert port. It
reports `version=__version__` plus a `meta` map built by
`discovery_metadata()` in `daq_alert.py` (package version, Qt, PyQt, Python,
UDP port). Keep `meta` values short strings — mu2edaq-discovery caps a
datagram at 1400 bytes. The whole responder is best-effort: a missing package
or a failure must never block startup.

    mu2edaq-discover --filter app=bigredbox --json

## Tests

```bash
pytest                          # headless; no DISPLAY needed
QT_QPA_PLATFORM=xcb pytest      # to watch the windows (cocoa on macOS)
```

- `tests/test_packaging.py` — package metadata, `CRS_PORT_UDP` override, UDP
  payload format, console-script registration
- `tests/test_gui.py` — PyQt6 widget construction, alert update/counter, pause
  checkbox, history dialog, key handling, listener thread lifecycle

`pyproject.toml` pins `qt_api = "pyqt6"` for pytest-qt. End-to-end behaviour
still warrants a manual check with `mu2edaq-bigredbox-send`.
