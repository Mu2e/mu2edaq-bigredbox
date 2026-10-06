# Staged issues — mu2edaq-bigredbox

Findings from the September 2026 DAQ mega-review (`mu2e-sept-mega-review`),
2026-10-06. Target repository: `Mu2e/mu2edaq-bigredbox` (public, issues
enabled) unless an entry says otherwise.

**Why staged.** Contract §9.1: no GitHub write is attempted in this review.
Each entry is the issue body verbatim with its fingerprint.

**Dedup.** `gh issue list -R Mu2e/mu2edaq-bigredbox --state all` returned 9
issues, all closed, none carrying a mega-review fingerprint (#1–#3 features,
#8–#13 robustness fixes that this review confirmed are in the code). No overlap
with the entries below.

**Already staged elsewhere, not restaged here:**

- `requirements.txt:10` naming `mu2edaq-discovery` bare is already staged as
  **DISC-016** in `mu2edaq-discovery/doc/ISSUES-PENDING.md` (routed to this
  repository, fingerprint `b7cc489a`). Verified on this branch; it is a
  regression: `45805cc` fixed it, merge `6ed76a5` reintroduced it, PR #15
  (`c557be3`) carried it to `main`.
- `mu2edaq-file-reaper`'s Big Red Box channel calling `send_alert(..., ip=...)`
  against this library's `broadcast_ip` keyword is already staged as
  **FR-011** in `mu2edaq-file-reaper/docs/ISSUES-PENDING.md`. Verified here.

IDs BRB-004 and BRB-005 were used for those two in the draft and are retired.

10 entries: 1 × S2, 5 × S3, 4 × S4. BRB-011 and BRB-012 were added in the
review's completion pass; the rest were re-checked against the source then.

Reproduction environments for *verified* items: `almalinux:9` container,
Python 3.9.25, PyQt6 6.10.2 (Qt 6.10.0) installed by pip from `pyproject.toml`;
macOS with the checkout venv (Python 3.12, PyQt6 6.11).

---

## BRB-001

**Title:** `[tts] module-level QtMultimedia import makes libpulse a hard dependency; the listener cannot start without it even with TTS disabled`

**Severity:** S2 — production breakage or silent wrong behaviour; workaround exists
**Category:** bug
**Location:** `src/mu2edaq_bigredbox/tts.py:16`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`tts.py` imports `PyQt6.QtMultimedia` and `PyQt6.QtTextToSpeech` at module
scope, and `daq_alert.py:33` imports `tts` unconditionally. On Linux both Qt
modules need `libpulse.so.0`. Where it is missing, the import raises and the
alert listener exits before creating a window or binding the port.
`DAQ_ALERT_TTS_ENABLED=0` does not help, because the import happens first.

## Evidence
```
$ sed -n 15,17p src/mu2edaq_bigredbox/tts.py
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QThread, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtTextToSpeech import QTextToSpeech
```
AlmaLinux 9, X11 libraries from the README installed, `pulseaudio-libs` not:
```
$ DAQ_ALERT_TTS_ENABLED=0 QT_QPA_PLATFORM=offscreen python3 -m mu2edaq_bigredbox
  File ".../daq_alert.py", line 33, in <module>
    from .tts import create_speaker, load_templates, render_template
  File ".../tts.py", line 16, in <module>
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
ImportError: libpulse.so.0: cannot open shared object file: No such file or directory
exit=1
```
After `dnf install pulseaudio-libs` the same command starts normally.

## Why it matters
TTS is documented in README, man page and code comments as best-effort: "no
working speech plugin/backend on this platform must never block startup".
Since `058fd2d` (2026-08-04) an optional speech feature is a hard runtime
dependency of the critical-alert path. On a minimal EL9 install without
`pulseaudio-libs`, for example a server node used over `ssh -X`, the Big Red Box
cannot start at all. Desktop installs normally have the library, so the
control-room consoles are probably unaffected; this was not checked on a real
console. The README's `dnf install` line does not list `pulseaudio-libs`.

## Suggested fix
Import `QtMultimedia` and `QtTextToSpeech` lazily inside `TTSSpeaker` /
`AWSPollySpeaker` (or inside `create_speaker`) within `try/except ImportError`,
returning a no-op speaker on failure, so `daq_alert.py` imports only
QtWidgets/QtCore/QtGui. Add `pulseaudio-libs` to the README's EL9 package list
for when speech is wanted. Add a test that stubs out `PyQt6.QtMultimedia` and
checks the listener still starts.

## Related
- BRB-007 (no CI to catch platform-specific import failures)

<!-- mega-review-fingerprint: cb1187ee -->

---

## BRB-002

**Title:** `[listener] SO_REUSEADDR defeats the single-instance guard on Linux; a second listener co-binds 37020`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `src/mu2edaq_bigredbox/daq_alert.py:151`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
The listener relies on `bind()` failing to detect a running instance and exit
with status 3. It sets `SO_REUSEADDR` before binding. On Linux, two UDP sockets
that both set `SO_REUSEADDR` may bind the same address and port, so the second
listener starts normally. The start script's port probe also sets
`SO_REUSEADDR` (`start-mu2edaq-bigredbox.sh:38`) and therefore always reports
the port free while a listener is running. The behaviour holds on macOS, where
the tests were written.

## Evidence
```
$ sed -n 150,155p src/mu2edaq_bigredbox/daq_alert.py
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.settimeout(1.0)
        try:
            self._sock.bind(("", port))
```
Socket probe with exactly these calls:
```
Darwin 25.6.0   case1 both-REUSEADDR second bind: failed [Errno 48] Address already in use
Linux (AL9)     case1 both-REUSEADDR second bind: SUCCEEDED
                  unicast copy received by b only;  broadcast copy received by a and b
                case2 start-script probe bind: SUCCEEDED (probe reports port free)
```
Real listener on AlmaLinux 9: second `python -m mu2edaq_bigredbox` on the same
port is still running when `timeout 4` kills it (exit 124), not exit 3. The
package's own tests fail on AlmaLinux 9:
```
FAILED tests/test_gui.py::test_listener_raises_when_port_is_busy - Failed: DID NOT RAISE <class 'OSError'>
FAILED tests/test_gui.py::test_second_instance_exits_with_port_in_use_status
2 failed, 106 passed, 2 skipped
```

## Why it matters
On the production OS the documented invariant ("only one listener can own the
port; a second exits with status 3") is false. A listener started by hand or
over `ssh -X` next to the control-room one doubles every window and every
spoken alert, overwrites `/tmp/daq_alert.pid` so the stop script stops only the
newer one, and receives every unicast alert in place of the original. Unicast
is the only way to reach a listener on another subnet. The Windows branch
`origin/windows-compat` (`d314369`, unmerged) already switches to
`SO_EXCLUSIVEADDRUSE` for the same reason on Windows.

## Suggested fix
Do not set `SO_REUSEADDR` on the listener socket. UDP has no TIME_WAIT, so it
buys nothing, and broadcast reception does not need it. Use
`SO_EXCLUSIVEADDRUSE` on Windows (merge `d314369`). Drop `SO_REUSEADDR` from the
start script's probe. Fix the two tests so the holder socket does not set
`SO_REUSEADDR`, and run them on Linux in CI.

## Related
- Mu2e/mu2edaq-heartbeatmonitor: HBM-003 (same `SO_REUSEADDR` pattern)
- BRB-007

<!-- mega-review-fingerprint: 265cbb00 -->

---

## BRB-003

**Title:** `[security] unauthenticated broadcast plus a global first-come rate limit lets any VLAN host suppress genuine alerts`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `src/mu2edaq_bigredbox/daq_alert.py:723`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
Any host that can reach UDP 37020 can raise a Big Red Box. There is no
authentication, no source check and no schema check (any JSON object,
including `{}`, raises a window). On its own that is an accepted design risk
for a closed DAQ network: a spoofed alert costs an operator one click, the
window is 860×530 and there are never more than two. The defect is that the
only flood protection is a single global, source-blind limiter. It accepts the
first datagram after each 100 ms window and drops everything else. A host or
runaway sender emitting more than 10 datagrams/s therefore suppresses genuine
alerts from every other source. Every datagram, accepted or dropped, is
written to `/tmp/daq_alert.log` at INFO with its payload, and per-window
history grows without bound.

## Evidence
```
$ sed -n 723,731p src/mu2edaq_bigredbox/daq_alert.py
        now = time.monotonic()
        min_interval = 1.0 / MESSAGE_RATE_LIMIT
        if now - self._last_accepted_time < min_interval:
            log.info(
                "Throttling message (rate limit %.1f msg/s): %s",
                MESSAGE_RATE_LIMIT, message_data,
            )
            return
        self._last_accepted_time = now
$ grep -n 'log.info("Received message' src/mu2edaq_bigredbox/daq_alert.py
165:                log.info("Received message from %s", addr)
```
For a flood at rate R, a genuine alert is accepted only if it is the first
arrival after the window reopens: P ≈ 1/(1 + 0.1·R), about 1 % at 1 kHz. If
accepted, it is overwritten in the newest window by the next accepted flood
datagram 100 ms later (`:737-741`). At 1 kHz with roughly 200-byte log lines
the log grows by about 0.4 MB/s into `/tmp`, which is never rotated.

## Why it matters
The Big Red Box makes one promise: a critical alert reaches a human. A looping
sender (a crash-restart cycle that calls `daq_alert_send` on start) or any
compromised or misconfigured host on the VLAN breaks that promise silently, and
fills `/tmp` on the control-room host. Nothing in the README or man page
describes the trust model or this failure mode.

## Suggested fix
Authentication is not required. Rate-limit per source address and per
`system_id` instead of globally, and never drop the first alert from a
`system_id` not seen recently; coalesce suppressed alerts into a counter shown
in the window ("47 more from 10.226.9.21"). Rate-limit the per-datagram log
lines and use a `RotatingFileHandler`. Cap `_history` (e.g. 1000). Ignore
objects without `system_id` and `message`. Optionally add a configurable source
CIDR allowlist. Document the trust model in the README.

## Related
- BRB-002

<!-- mega-review-fingerprint: ccbe910b -->

---

## BRB-006

**Title:** `[libs] C sender silently turns an invalid address into 255.255.255.255 and caps fields at about 2 kB while Python does not`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `libs/c/src/daq_alert.c:114`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`daq_alert_send()` parses the destination with `inet_addr()`. For any string it
cannot parse (a typo, a host name), `inet_addr()` returns `INADDR_NONE`, whose
bit pattern is `255.255.255.255`. The call then sends a local limited broadcast
and returns `DAQ_ALERT_OK`. The C and C++ bindings also reject any field longer
than 2041 escaped bytes, while both Python senders accept up to about 64 kB.
`NULL` `system_id` or `message` is dereferenced.

## Evidence
```
$ sed -n 114p libs/c/src/daq_alert.c
    addr.sin_addr.s_addr = inet_addr(broadcast_ip);
$ example-sender-c -i not.an.ip -p <port>      # listener bound to 0.0.0.0:<port>
Alert sent.                                    # rc 0
  datagram arrived from ('131.225.169.89', 53223) => sent to limited broadcast
$ for n in 2041 2042; do example-sender-c -m "$(head -c $n /dev/zero | tr '\0' x)" ...; done
msg=2041: ok
msg=2042: REJECTED      (error: Payload too large or format error)
```
The Python senders sent the same 2100-byte message (2179-byte datagram).

## Why it matters
A sender configured with a directed broadcast for another subnet, or a host
name, gets a success code while its alert never reaches that subnet. That is
the failure a Big Red Box sender can least afford. The differing size limits
mean the same alert succeeds from Python and fails from C/C++.

## Suggested fix
Use `inet_pton(AF_INET, ...)` and return a new `DAQ_ALERT_ERR_ADDRESS` on
failure (or resolve with `getaddrinfo`). Check `setsockopt(SO_BROADCAST)`.
Return `DAQ_ALERT_ERR_FORMAT` for `NULL` arguments. Document one maximum
message size for all bindings (about 1 kB is plenty), and enforce it in the
Python library too.

## Related
- `docs/INTERFACES.md` §3.4 (byte-level comparison)

<!-- mega-review-fingerprint: 486a7a78 -->

---

## BRB-007

**Title:** `[ci] 110 tests and no CI; two single-instance tests fail on Linux`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** enhancement
**Location:** `tests/test_gui.py:150`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
The package has 110 pytest cases (`test_gui.py`, `test_tts.py`,
`test_packaging.py`) and no `.github/workflows/`. The suite passes on macOS and
has two failures on AlmaLinux 9, the production OS. On an EL9 host without
`pulseaudio-libs`, two of the three modules cannot be collected. The C/C++
sender libraries have no tests.

## Evidence
```
macOS, Python 3.12:      110 passed
AlmaLinux 9, Py 3.9.25:  2 failed, 106 passed, 2 skipped
AlmaLinux 9, no libpulse: ERROR tests/test_gui.py / tests/test_tts.py (ImportError: libpulse.so.0)
$ ls .github 2>&1
ls: .github: No such file or directory
```

## Why it matters
BRB-001 and BRB-002 are both visible to a Linux CI run of the existing suite.
Without CI they shipped.

## Suggested fix
GitHub Actions on `ubuntu-latest` with Python 3.9 and a Rocky/Alma 9 container
job: install the EL9 X11 and `pulseaudio-libs` packages, run
`QT_QPA_PLATFORM=offscreen pytest`, and build `libs/` with CMake. Add a
C-vs-Python payload equivalence test (decode both and compare).

## Related
- BRB-001, BRB-002

<!-- mega-review-fingerprint: cdc9320c -->

---

## BRB-008

**Title:** `[config] TTS template path is relative to the working directory and a miss is silent`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** bug
**Location:** `src/mu2edaq_bigredbox/config.py:166`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`TTS_TEMPLATE_FILE` defaults to the relative path `config/tts_templates.yaml`,
and `load_templates()` returns `{}` on `FileNotFoundError` without logging. The
start script `cd`s to the checkout, so the file is found there. An installed
`mu2edaq-bigredbox` entry point started from any other directory silently uses
the built-in template. The wheel does not ship the YAML.

## Evidence
```
$ sed -n 166,167p src/mu2edaq_bigredbox/config.py
TTS_TEMPLATE_FILE = _path("DAQ_ALERT_TTS_TEMPLATE_FILE",
                           "config/tts_templates.yaml")
$ sed -n 336,337p src/mu2edaq_bigredbox/tts.py
    except FileNotFoundError:
        return {}
```

## Why it matters
Operators customise spoken text in the YAML and hear the default phrasing with
no log line saying why. Cosmetic: the alert is still shown and spoken.

## Suggested fix
Resolve the default relative to the package or checkout (as
`heartbeat_monitor.py` does with its search list), and log at INFO which
template file was loaded or that none was found.

## Related
- none

<!-- mega-review-fingerprint: f7f342fb -->

---

## BRB-009

**Title:** `[docs] README, CLAUDE.md and man page describe single-instance and PyQt6 behaviour that is false on AlmaLinux 9`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** documentation
**Location:** `README.md:118`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
README "Single instance and troubleshooting", CLAUDE.md "Single-instance
invariant" and the man page's SINGLE INSTANCE / EXIT STATUS 3 describe behaviour
that holds on macOS only (BRB-002). README, BUILD.md and CLAUDE.md state that
Python 3.9 resolves to PyQt6 6.9.1; on 2026-10-06 pip resolved 6.10.2 (6.11
requires 3.10). README and CLAUDE.md present `start_daq_alert.sh` as the
launcher, while the control room uses `start-mu2edaq-bigredbox.sh` (the former
is a symlink). README says TTS failures "never stop … the listener from
starting" (false without libpulse, BRB-001). The README's EL9 package list omits
`pulseaudio-libs`. `docs/SOLUTIONS_pause_checkbox_does_not_s.md` is a tracked
empty file.

## Evidence
```
$ grep -n '6.9.1' README.md BUILD.md CLAUDE.md
README.md:46:> pip resolves to PyQt6 6.9.1 (verified on manylinux) — that is fine, since the
BUILD.md:34:PyQt6 6.9.1. That is supported — the code uses no API newer than Qt 6.4. If an
CLAUDE.md:21:PyQt6 6.9.1; keep to APIs available in Qt 6.4.
$ python3 -m pip install -e '.[dev]' && python3 -c "import PyQt6.QtCore as c; print(c.PYQT_VERSION_STR)"   # AL9, Py 3.9.25
6.10.2
$ git ls-files -s start_daq_alert.sh
120000 ... start_daq_alert.sh
```

## Why it matters
Operators troubleshooting a duplicate window, or a listener that will not
start, are told the opposite of what happens.

## Suggested fix
Correct the README/CLAUDE.md/BUILD.md statements as listed, name the canonical
scripts, add `pulseaudio-libs` to the EL9 package list, delete the empty file.
The man page has been corrected in this review.

## Related
- BRB-001, BRB-002

<!-- mega-review-fingerprint: 246c0dd0 -->

---

## BRB-010

**Title:** `[packaging] repo-root daq_alert.py shadows the daq_alert sender package; example man pages live outside man/`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** bug
**Location:** `daq_alert.py:1`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
The repository root has `daq_alert.py`, a backwards-compatibility launcher for
the listener. The Python sender library is also a top-level module named
`daq_alert` (`libs/python/daq_alert/`). Any Python process whose `sys.path[0]`
is the checkout root (`python3 -c ...` or `python3 -m ...` run from there, or a
script placed there) imports the listener shim instead of the sender, and that
pulls in PyQt6. The three example-sender man pages sit beside their sources,
outside the `man/manN/` layout, because `libs/examples/*/CMakeLists.txt`
installs them from there (their headers were brought to the house format in
this review). `pyproject.toml`'s `data-files` lists only
`man/man1/mu2edaq-bigredbox.1` and `man/man1/mu2edaq-bigredbox-send.1`, so a
`pip install` does not install the script, library, template and API pages
under `man/`.

## Evidence
```
$ ls daq_alert.py libs/python/daq_alert/__init__.py
daq_alert.py  libs/python/daq_alert/__init__.py
$ grep -n 'install(FILES' libs/examples/example-sender-c/CMakeLists.txt
5:install(FILES example-sender-c.1 DESTINATION ${CMAKE_INSTALL_MANDIR}/man1)
$ sed -n 48,51p pyproject.toml
data-files = { "share/man/man1" = [
    "man/man1/mu2edaq-bigredbox.1",
    "man/man1/mu2edaq-bigredbox-send.1",
] }
```

## Why it matters
A confusing import failure for a developer testing the sender from the
checkout root. Note that `mu2edaq-file-reaper` imports `daq_alert` by that
name. The man-page placement is cosmetic.

## Suggested fix
Rename the shim (e.g. `run_bigredbox.py`) or the library module
(`mu2edaq_daq_alert`); keep a one-release alias. Move the example pages to
`man/man1/` and update the three `install(FILES ...)` paths in the same commit.
Add the `man/man3`, `man/man5` and `man/man7` pages and the script pages to
`data-files`.

## Related
- FR-011 (Mu2e/mu2edaq-file-reaper): imports `daq_alert` by that name

<!-- mega-review-fingerprint: ec4b7d58 -->

---

## BRB-011

**Title:** `[gui] alert text is rendered as Qt rich text, so a message containing <tag loses text in the window`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `src/mu2edaq_bigredbox/daq_alert.py:259`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
Every payload field is shown in a `QLabel` created with the default
`Qt.TextFormat.AutoText` (`FieldRow.value_label` at `:259`, updated at
`:458-461`; history entries at `:585`). Qt then renders any string that
`Qt.mightBeRichText()` accepts as HTML. A `<` followed by a tag name opens a
tag and the text up to the next `>` disappears from the window; markup in the
payload (`<b>`, `<font size=1>`, `<p>`) is applied. The spoken text is built
from the raw string and is complete, so window and speech disagree.

## Evidence
```
$ sed -n 259p src/mu2edaq_bigredbox/daq_alert.py
        self.value_label = QLabel(value)
$ grep -n 'setTextFormat' src/mu2edaq_bigredbox/daq_alert.py
(no output)
```
PyQt6 6.11, `Qt.mightBeRichText(s)` and the text Qt displays for it:
```
'rate < b and c > d'                     rich=True   shown: 'rate d'
'buffer <b>full</b>'                     rich=True   shown: 'buffer full' (bold)
'<p>Run 1234 stopped</p><font size=1>x'  rich=True   shown in two blocks, last one tiny
'<ROC 3> link down'                      rich=False  shown verbatim
'rate < 5 Hz and occupancy > 90%'        rich=False  shown verbatim
```

## Why it matters
The window is the record an operator reads and acknowledges. A genuine alert
whose message happens to contain `< b`, `< p`, `< a`, `< i` and so on loses
words without any sign that it did. A sender can also make text tiny or
invisible, which matters because senders are unauthenticated (BRB-003). Rated
S3 rather than S4 because it silently alters the content of a critical alert;
no occurrence in production is known.

## Suggested fix
Call `setTextFormat(Qt.TextFormat.PlainText)` on every label that shows payload
data (`FieldRow.value_label` and the history `val` labels). Add a test that
`"a < b and c > d"` is displayed unchanged.

## Related
- BRB-003

<!-- mega-review-fingerprint: e15c16a7 -->

---

## BRB-012

**Title:** `[scripts] start/stop scripts hard-code /tmp/daq_alert.pid and .log and ignore DAQ_ALERT_PID_FILE / DAQ_ALERT_LOG_FILE`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** bug
**Location:** `start-mu2edaq-bigredbox.sh:18`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
The listener reads `DAQ_ALERT_PID_FILE` and `DAQ_ALERT_LOG_FILE`
(`src/mu2edaq_bigredbox/config.py:112,115`), and its comments tell a second
operator on the same node to set them. The start script ignores both: it checks
`/tmp/daq_alert.pid` for a running listener and appends the listener's output
to `/tmp/daq_alert.log`. The stop script defaults to `/tmp/daq_alert.pid`.

## Evidence
```
$ sed -n 18,19p start-mu2edaq-bigredbox.sh
PID_FILE="/tmp/daq_alert.pid"
LOG_FILE="/tmp/daq_alert.log"
$ sed -n 8p stop-mu2edaq-bigredbox.sh
PID_FILE="${1:-/tmp/daq_alert.pid}"
$ sed -n 110,115p src/mu2edaq_bigredbox/config.py
# Override with DAQ_ALERT_PID_FILE; the default is shared by every user on the
# machine, so a second operator on the same node should point this elsewhere.
PID_FILE = _path("DAQ_ALERT_PID_FILE", DEFAULT_PID_FILE)
```

## Why it matters
With the variables set, the start script's already-running check looks at the
wrong file, and on Linux its port probe also passes (BRB-002), so a second
start launches a second listener; the stop script, run without an argument,
reports "not running" unless its `lsof` fallback finds the process. Startup
errors go to `/tmp/daq_alert.log` while the application log goes elsewhere.
Workaround: pass the PID file to the stop script. Hence S4.

## Suggested fix
In both scripts use `PID_FILE="${DAQ_ALERT_PID_FILE:-/tmp/daq_alert.pid}"` and
`LOG_FILE="${DAQ_ALERT_LOG_FILE:-/tmp/daq_alert.log}"` (keeping `$1` as the
stop script's override).

## Related
- BRB-002

<!-- mega-review-fingerprint: 8ef4dc99 -->
