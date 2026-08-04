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
- Has a **Pause** box that suppresses all incoming alerts while ticked — no
  new windows open and no open window updates (see *Pausing alerts* below)
- Has a history of **Errors Received** and a counter which can open up a history so you can see what is going wrong.
- Reads each alert aloud via Qt's `QTextToSpeech`, with the spoken text
  driven by configurable per-`system_id` templates (see *Text-to-speech*
  below), and a **Mute Audio** box to silence it without hiding the window
- Runs as a background daemon with PID and log file management

## Requirements

- Python 3.9+
- PyQt6 (Qt 6.4 or later) — installed automatically as a dependency
- PyYAML — installed automatically as a dependency, used for the optional
  text-to-speech templates file
- A display environment (X11 / `DISPLAY` variable set)

This does work with ssh forwarded X11 connections.

> **Qt6 note.** The GUI was migrated from PyQt5 to PyQt6; there is no longer any
> Qt5 dependency. PyQt6 6.10 and later require Python 3.10+, so on Python 3.9
> pip resolves to PyQt6 6.9.1 (verified on manylinux) — that is fine, since the
> code uses no API introduced after 6.4. On Linux, Qt6 needs the
> usual X11 client libraries (`libxkbcommon-x11`, `libEGL`, `xcb-cursor`); on
> RHEL/AlmaLinux install `libxkbcommon-x11 xcb-util-cursor mesa-libEGL`.

> **Text-to-speech note.** `QTextToSpeech` ships inside the `PyQt6` wheel
> itself — no extra pip package is needed. The Qt plugin still needs a
> working platform speech backend at the OS level: macOS (`AVSpeechSynthesizer`)
> and Windows (SAPI) have one built in; on Linux install `speech-dispatcher`
> or `flite` (e.g. `apt install speech-dispatcher` / `dnf install flite`).
> Without one, TTS degrades to silence with a warning in the log — see
> *Text-to-speech* below.

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

## Single instance and troubleshooting

Only one listener can own the UDP port at a time. The port is bound **before**
the PID file is written, so port ownership — not the PID file — is what decides
which process is the live listener:

- Starting a second listener exits immediately with status **3** and an
  explanatory message. It will not sit there with a dead listener thread.
- `start_daq_alert.sh` checks the PID file *and* probes the port, so it also
  detects a listener started by hand or one whose PID file was deleted.
- `stop_daq_alert.sh` falls back to the process holding the UDP port when the
  PID file is missing, so an orphaned listener can still be stopped. It only
  ever stops this application — an unrelated process holding the port is left
  alone.

To see who currently owns the port:

```bash
lsof -nP -iUDP:37020
```

## Service discovery

When the optional `mu2edaq-discovery` package is installed, the listener answers
DISCOVER requests with its version information, so you can audit what is
deployed on each node without logging in:

```bash
mu2edaq-discover --filter app=bigredbox --json
```

```json
{
  "app": "bigredbox",
  "name": "Big Red Box Alerts",
  "port": 37020,
  "scheme": "udp",
  "version": "2.0.0",
  "meta": {
    "version": "2.0.0",
    "qt": "6.11.0",
    "pyqt": "6.11.0",
    "python": "3.12.1",
    "udp_port": "37020"
  }
}
```

The package version is reported both as the announcement's `version` field and
inside `meta`; `meta` additionally carries the Qt, PyQt and Python runtime
versions and the UDP port actually in use. Discovery remains entirely optional —
without the package the listener runs normally and simply does not announce.

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
| `src/mu2edaq_bigredbox/config.py` | Shared constants (`BROADCAST_PORT`, `MESSAGE_RATE_LIMIT`, `MAX_ALERT_WINDOWS`, log/PID paths, `TTS_*`) |
| `src/mu2edaq_bigredbox/tts.py` | Text-to-speech: `QTextToSpeech` wrapper, YAML template loading/rendering |
| `daq_alert.py`, `demo_sender.py` | Root-level compatibility shims for running from a checkout |
| `config/tts_templates.yaml` | Example/default text-to-speech templates |
| `man/man1/` | Man pages for both console scripts |
| `tests/test_packaging.py` | pytest checks for the package build and the UDP payload |
| `tests/test_gui.py` | Headless PyQt6 widget tests (offscreen platform) |
| `tests/test_tts.py` | Text-to-speech template rendering and `TTSSpeaker` tests (fake engine, no real audio) |
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
| `LOG_FILE` | `/tmp/daq_alert.log` | Daemon log path (overridden by `DAQ_ALERT_LOG_FILE`) |
| `PID_FILE` | `/tmp/daq_alert.pid` | Daemon PID file path (overridden by `DAQ_ALERT_PID_FILE`) |
| `TTS_ENABLED` | `True` | Whether alerts are read aloud (overridden by `DAQ_ALERT_TTS_ENABLED`) |
| `TTS_RATE` | `None` (engine default) | Speech rate, -1.0 to 1.0 (overridden by `DAQ_ALERT_TTS_RATE`) |
| `TTS_VOLUME` | `None` (engine default) | Speech volume, 0.0 to 1.0 (overridden by `DAQ_ALERT_TTS_VOLUME`) |
| `TTS_VOICE` | `None` (engine default) | Voice name substring match (overridden by `DAQ_ALERT_TTS_VOICE`) |
| `TTS_ENGINE` | `None` (auto) | Force a specific Qt TTS plugin (overridden by `DAQ_ALERT_TTS_ENGINE`) |
| `TTS_TEMPLATE_FILE` | `config/tts_templates.yaml` | Spoken-text templates (overridden by `DAQ_ALERT_TTS_TEMPLATE_FILE`) |

## Pausing alerts

Ticking **Pause** on any alert window stops the application processing incoming
alerts entirely: no new windows open, and no open window updates. Alerts that
arrive while paused are dropped, not queued — each one is recorded in
`/tmp/daq_alert.log` so nothing is lost silently:

```
2026-07-22 12:41:02,113 [INFO] Paused; dropping message: {'system_id': ...}
```

Pause is **global, not per-window**: it is the operator saying "stop
interrupting me", so ticking it on one window suppresses alerts for all of
them. Processing resumes as soon as no open window has Pause ticked — untick
it, or close the paused window.

## Text-to-speech

Each accepted alert (after the pause and rate-limit checks) is read aloud via
Qt's `QTextToSpeech`, using a template chosen by the alert's `system_id`.
Templates live in a YAML file, `config/tts_templates.yaml` by default
(override with `DAQ_ALERT_TTS_TEMPLATE_FILE`):

```yaml
default: "Critical error on {system_id}. {message}"
"DAQ-NODE-*": "Attention. Node {system_id} reports a critical error. {message}"
"CFO*": "Central fanout controller {system_id} has a critical error. {message}"
```

Patterns are `fnmatch` globs, matched in file order — first match wins. The
`default` key is used when nothing else matches. `{system_id}`, `{timestamp}`,
and `{message}` are filled in from the alert payload. A missing template
file, missing PyYAML, malformed YAML, or a malformed template string (a bad
placeholder) all fall back to the listener's built-in default template with a
warning in the log — they never stop an alert from being spoken or the
listener from starting.

Each alert window also has a **Mute Audio** box, independent of Pause: while
ticked it silences speech only — the window itself still opens and updates
normally. Like Pause, muting is global across open windows and resumes as
soon as no open window has it ticked.

Rate, volume, voice, and which Qt speech plugin to use are all configured via
the `DAQ_ALERT_TTS_*` environment variables in *Environment overrides* below;
there is no command-line flag for any of it (see the Configuration table
above for the matching `config.py` constants).

### Environment overrides

| Variable | Overrides | Notes |
|---|---|---|
| `CRS_PORT_UDP` | `BROADCAST_PORT` | Exported by the control room's `crs-app`. A blank, non-numeric or out-of-range value falls back to 37020 with a warning rather than failing to start |
| `DAQ_ALERT_LOG_FILE` | `LOG_FILE` | Falls back to stderr if the file cannot be opened |
| `DAQ_ALERT_PID_FILE` | `PID_FILE` | The listener keeps running if it cannot be written |
| `DAQ_ALERT_TTS_ENABLED` | `TTS_ENABLED` | 1/0, true/false, yes/no, on/off (case-insensitive); unrecognized falls back to `True` |
| `DAQ_ALERT_TTS_RATE` | `TTS_RATE` | Out-of-range or non-numeric falls back to the engine default |
| `DAQ_ALERT_TTS_VOLUME` | `TTS_VOLUME` | Out-of-range or non-numeric falls back to the engine default |
| `DAQ_ALERT_TTS_VOICE` | `TTS_VOICE` | No match found falls back to the engine's default voice |
| `DAQ_ALERT_TTS_ENGINE` | `TTS_ENGINE` | An unsupported plugin name disables TTS rather than crashing |
| `DAQ_ALERT_TTS_TEMPLATE_FILE` | `TTS_TEMPLATE_FILE` | Missing/unreadable/malformed falls back to the built-in default template |

The default `/tmp` paths are shared by every user on a machine, so the first
operator to start the listener owns them. On a node where more than one person
runs it, point these at your own paths:

```bash
DAQ_ALERT_LOG_FILE=~/daq_alert.log DAQ_ALERT_PID_FILE=~/daq_alert.pid mu2edaq-bigredbox
```

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
