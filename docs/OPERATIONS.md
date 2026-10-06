# mu2edaq-bigredbox — operations

For a DAQ expert installing, running or debugging the Big Red Box listener.
*Verified* means reproduced on 2026-10-06 in an `almalinux:9` container
(Python 3.9.25, PyQt6 6.10.2 / Qt 6.10.0) or on macOS with the checkout venv.
The review's completion pass re-checked the test count (110 passed, macOS),
the Linux `SO_REUSEADDR` co-bind, the C sender's address handling, and the
`libpulse.so.0` dependency (read from the PyQt6-Qt6 wheel's ELF headers).

Installation is covered by §1 below together with `README.md` and `BUILD.md`;
there is no separate `INSTALL.md`.

## 1. Install

```bash
cd ~/mu2edaq-main/mu2edaq-bigredbox
./bootstrap.sh            # venv/, pip install -e . ; --dev adds pytest, pytest-qt, build
```

`bootstrap.sh` installs `../mu2edaq-discovery` editable when the sibling
checkout exists, otherwise tries GitHub, otherwise continues without discovery.
It installs the package with `pip install -e .`, which uses `pyproject.toml`
and works. **Do not use `pip install -r requirements.txt`**: line 10 names
`mu2edaq-discovery`, which is not on PyPI, and pip aborts the whole file
(*verified*: "No matching distribution found for mu2edaq-discovery"; staged as
DISC-016 by the discovery review).

### System packages on EL9 (AlmaLinux 9)

| Package | Why | Without it |
|---|---|---|
| `libxkbcommon-x11 xcb-util-cursor mesa-libEGL` (+ the other `xcb-util-*`) | Qt xcb platform plugin | Qt aborts at startup |
| **`pulseaudio-libs`** | `libpulse.so.0`, needed to import `PyQt6.QtMultimedia` and `PyQt6.QtTextToSpeech` | **the listener does not start**: `ImportError: libpulse.so.0` at import, even with `DAQ_ALERT_TTS_ENABLED=0` (*verified*; BRB-001). Desktop installs normally have it; minimal server installs do not. |
| `speech-dispatcher` or `flite` | an OS speech engine for the default `qt` TTS backend | starts and alerts visually; log says "Text-to-speech engine None failed to initialize; TTS disabled" (*verified*) |

The README's dnf line omits `pulseaudio-libs`.

### PyQt6 version on Python 3.9

`PyQt6>=6.4` is not pinned. On 2026-10-06 pip on Python 3.9.25 resolved
**PyQt6 6.10.2** and reported that 6.11.0 requires Python ≥ 3.10. README,
BUILD.md and CLAUDE.md say Python 3.9 resolves to 6.9.1; that is out of date. A
fresh install therefore gets whatever the newest 3.9-compatible PyQt6 is on that
day.

### Sender libraries (optional)

```bash
cmake -S libs -B libs/build && cmake --build libs/build -j
cmake --install libs/build --prefix /opt/mu2edaq     # libdaq_alert.a, libdaq_alert_cpp.a, headers, examples, Python module
pip install libs/python                             # Python library only
```

Builds cleanly with Apple clang (this review). `example-sender-c/-cpp` use
`getopt_long` and do not build with MSVC.

## 2. Start, stop, status

Canonical scripts are `start-mu2edaq-bigredbox.sh` / `stop-mu2edaq-bigredbox.sh`
(`mu2edaq-controlroom-setup/config/apps.yaml:40-41`). `start_daq_alert.sh` and
`stop_daq_alert.sh` are git symlinks to them (mode 120000), not copies.

| Action | Command |
|---|---|
| Start (control room) | `crs-app start bigredbox` |
| Start (by hand) | `./start-mu2edaq-bigredbox.sh` |
| Foreground | `DISPLAY=:0 venv/bin/mu2edaq-bigredbox` |
| Stop | `./stop-mu2edaq-bigredbox.sh` |
| Send a test alert | `venv/bin/mu2edaq-bigredbox-send --system-id TEST --message "test, please acknowledge"` |
| Who owns the port | `ss -ulpn 'sport = :37020'` or `lsof -nP -iUDP:37020` |
| Discovery | `mu2edaq-discover --filter app=bigredbox --json` |
| Log | `tail -f /tmp/daq_alert.log` |

**Start script** (`start-mu2edaq-bigredbox.sh`): `cd` to the checkout; export
`CRS_PORT_UDP` (default 37020) and `DISPLAY` (default `:0`); exit 0 if the PID in
`/tmp/daq_alert.pid` is alive; probe the port by binding it; pick
`venv/bin/mu2edaq-bigredbox`, else `mu2edaq-bigredbox` on `PATH`, else
`python3 daq_alert.py`; `nohup` it with output appended to `/tmp/daq_alert.log`;
after 1 s, fail with the last three log lines if the process is gone.

The start script ignores `DAQ_ALERT_PID_FILE` and `DAQ_ALERT_LOG_FILE`: it
always checks `/tmp/daq_alert.pid` and appends to `/tmp/daq_alert.log`, while the
listener it launches writes wherever those variables point (BRB-012). If you set
them, pass the PID file to the stop script explicitly.

**Stop script**: PID from `$1` or `/tmp/daq_alert.pid`; if there is no PID
file, fall back to the `lsof` holder of `CRS_PORT_UDP` whose command line
matches `mu2edaq[-_]bigredbox|daq_alert`; SIGTERM, wait `CRS_STOP_TIMEOUT`
(10 s), SIGKILL, remove the PID file.

## 3. Display requirements

`QApplication` is constructed before anything else
(`src/mu2edaq_bigredbox/daq_alert.py:605`), so a display problem aborts before
the port is bound or the PID file is written.

| Situation | Result |
|---|---|
| `DISPLAY` unset, no `QT_QPA_PLATFORM` | Qt: "could not connect to display … no Qt platform plugin could be initialized"; **SIGABRT, exit 134**, possible core file (*verified*) |
| `DISPLAY=:0` with no X server or no X authority for this user | same, exit 134 (*verified*). The start script defaults `DISPLAY=:0`, so on a host whose console session is `:1` or a VNC display it targets the wrong display. |
| `ssh -X` | works (README) |
| `QT_QPA_PLATFORM=offscreen` | runs headless; windows are invisible. Used by the tests. Never in production. |

The start script reports the abort ("failed to start; see /tmp/daq_alert.log").

`mu2edaq-controlroom-setup/config/apps.yaml:44` assigns the Big Red Box to two
sessions, `shift-main` and `shift-aux`, which that package documents as
displays `:1` and `:2` of the same host and account (`mu2e-mgr-01`,
`mu2eshift`); its own docs say `shift-aux` is not currently active. If both are
started, the second start finds the first listener's live PID in the shared
`/tmp/daq_alert.pid` and exits 0 without starting a listener on its display.
Not filed: it depends on a deployment choice this review cannot see.

## 4. Speech

Default backend `qt`. For Polly: `pip install '.[aws]'`, AWS credentials for the
user that runs the listener, network access to the Polly endpoint, then
`DAQ_ALERT_TTS_BACKEND=aws`. DAQ hosts on the private network normally have no
route to AWS; each Polly failure is logged and the next alert retries. There is
no fallback from `aws` to `qt`.

Speech is per accepted alert, before the window-cap check. A new Qt utterance
interrupts the previous one. The Polly backend queues synthesis requests
without a bound (`tts.py:160`) and each finished clip pre-empts the one playing
(`tts.py:247-257`), so after a burst the speaker emits late, mutually
interrupting clips for stale alerts until the queue drains.
**Mute Audio** on any window silences both backends.

Templates: `config/tts_templates.yaml` relative to the working directory
(`man 5 tts_templates.yaml`). The start script `cd`s to the checkout, so it is
found; a hand-started entry point in another directory silently falls back to
`"Critical error on {system_id}. {message}"`.

## 5. Failure modes

| Situation | Behaviour | What to do |
|---|---|---|
| Second listener on the same Linux host | Binds successfully (`SO_REUSEADDR`), so the "exit 3 / port in use" path and the start script's port probe never fire on Linux. Both listeners open windows and speak for every broadcast; a unicast alert goes only to the newer one; the PID file now names the newer one (*verified*; BRB-002). | `ss -ulpn 'sport = :37020'`; stop extras by PID. |
| Same on macOS | second instance exits 3 as documented (*verified*) | — |
| Alert flood (> 10/s from anywhere) | Only the first datagram per 100 ms is accepted; genuine alerts are mostly dropped; each datagram is logged at INFO, so `/tmp` fills (BRB-003) | Find the source in the log (`Received message from (ip, port)`), fix or firewall it. |
| Pause ticked and forgotten | every alert dropped (logged) until it is unticked or that window is closed; no timeout | Close the window. |
| `/tmp/daq_alert.log` owned by another user | logs to stderr instead (closed #13) | set `DAQ_ALERT_LOG_FILE` |
| `/tmp/daq_alert.pid` owned by another user | runs without a PID file; stop script falls back to the port holder | set `DAQ_ALERT_PID_FILE` |
| `CRS_PORT_UDP` blank or invalid | 37020 with a warning (closed #12) | — |
| Sender and listener on different subnets | limited broadcast `255.255.255.255` never crosses a router | send unicast to the listener host |
| C sender given a bad `--ip` | silently broadcasts locally and reports success (BRB-006) | check the address |
| Alert text contains `<` followed by an HTML tag name | the window renders it as rich text and drops the text between the brackets; speech is complete (BRB-011) | avoid `<` in senders' messages |

## 6. Tests

```bash
./bootstrap.sh --dev && QT_QPA_PLATFORM=offscreen venv/bin/pytest -q
```

| Platform | Result |
|---|---|
| macOS, Python 3.12, PyQt6 6.11 | 110 passed |
| AlmaLinux 9, Python 3.9.25, PyQt6 6.10.2, with `pulseaudio-libs` | 106 passed, 2 skipped, **2 failed**: `test_listener_raises_when_port_is_busy`, `test_second_instance_exits_with_port_in_use_status` (BRB-002) |
| AlmaLinux 9 without `pulseaudio-libs` | `test_gui.py` and `test_tts.py` fail at collection with `ImportError: libpulse.so.0` |

There is no CI (BRB-007), which is why the Linux failures were not noticed.
