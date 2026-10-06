# mu2edaq-bigredbox — interfaces

The UDP alert datagram is a public interface with three language bindings and
an external caller (`mu2edaq-file-reaper`). This document is its specification
as implemented on `mu2e-sept-mega-review` (package 2.0.0, sender libraries
1.0.0).

1. [Alert datagram](#1-alert-datagram)
2. [What the listener does with a datagram](#2-what-the-listener-does-with-a-datagram)
3. [Sender bindings and byte-level comparison](#3-sender-bindings-and-byte-level-comparison)
4. [Service discovery](#4-service-discovery)
5. [Environment, files, exit status](#5-environment-files-exit-status)
6. [Review facts verified and questions settled](#6-review-facts-verified-and-questions-settled)

---

## 1. Alert datagram

### 1.1 Transport

| Property | Value | Source |
|---|---|---|
| Port | 37020/udp | `src/mu2edaq_bigredbox/config.py:15`; `libs/c/include/daq_alert.h:11` |
| Port override (listener) | `CRS_PORT_UDP` | `config.py:130` |
| Family | IPv4 only | `daq_alert.py:150` |
| Listener bind | `("", port)` = `0.0.0.0`, `SO_REUSEADDR`, `SO_BROADCAST` | `daq_alert.py:150-155` |
| Default destination (all senders) | `255.255.255.255` (limited broadcast: local segment only, never routed) | `daq_alert.h:14`, `_sender.py:10`, `demo_sender.py:21` |
| Unicast | accepted; send to the listener host's address | — |
| Receive size | `recvfrom(65535)` | `daq_alert.py:164` |

Directed broadcast (`x.y.z.255`) reaches another subnet only if the routers
forward directed broadcasts, which is normally disabled. A listener on a
different segment from the sender needs unicast.

### 1.2 Payload

One UTF-8 JSON object:

```json
{"system_id": "DAQ-NODE-01", "timestamp": "2026-10-06T14:17:46", "message": "Readout buffer overflow"}
```

| Key | Producers write | Listener uses |
|---|---|---|
| `system_id` | caller string | displayed; selects the TTS template by `fnmatch` glob; default `UNKNOWN` |
| `timestamp` | sender **local time**, no zone, seconds precision, `YYYY-MM-DDTHH:MM:SS` | displayed verbatim; default `UNKNOWN`; never parsed |
| `message` | caller string | displayed and spoken; default `(no message text)` |

**Versioning: none.** There is no version, type or schema field; the format is
identified only by the port. Extra keys are ignored. Because the listener
validates nothing beyond "is a JSON object", *any* JSON object on 37020,
including `{}`, raises a Big Red Box with `UNKNOWN` fields. A future v2 should
add a `"v"` key and the listener should ignore objects without `system_id`.

**Timestamps are local time without an offset** in all three bindings
(`libs/c/src/daq_alert.c:56-64` uses `localtime_r`; Python uses naive
`datetime.now()`). Alerts from hosts in different zones, or around a DST change,
are not comparable. Nothing parses the field today.

**Rendering: Qt rich text.** The window's value labels keep Qt's default
`AutoText` format, so a field that `Qt.mightBeRichText()` accepts is rendered as
HTML. Measured with PyQt6 6.11: `"a < b and c > d"` and `"rate < b and c > d"`
are detected as rich text and display as `a d` / `rate d`; `"buffer <b>full</b>"`
displays bold. Strings such as `"<ROC 3> link down"` or `"rate < 5 Hz"` are not
detected and display verbatim. Senders should avoid `<` in `message` until
BRB-011 is fixed. Speech uses the raw string.

**Authentication: none.** See ARCHITECTURE.md, "The unauthenticated broadcast".

### 1.3 Size

| Producer | Limit | Behaviour over the limit |
|---|---|---|
| C / C++ | each field, after escaping, at most 2041 bytes (2048-byte buffer `char esc[PAYLOAD_MAX/2]` with a 7-byte guard, `daq_alert.c:33,80-84`); whole payload < 4096 (`:86-91`) | returns `DAQ_ALERT_ERR_FORMAT` / throws `AlertError`; nothing sent. Measured: 2041-byte ASCII message accepted, 2042 rejected. |
| Python (both) | none in code; the OS rejects > 65507 bytes with `OSError` (`EMSGSIZE`) | raises |
| Listener | 65535 read; no length check | an over-MTU datagram arrives as IP fragments; a lost fragment drops the whole alert silently |

Keep `message` under about 1 kB: it is shown in a word-wrapped label and read
aloud in full by the TTS engine.

## 2. What the listener does with a datagram

| Input | Result | Source |
|---|---|---|
| not UTF-8, or not JSON | warning, dropped | `daq_alert.py:166-170` |
| JSON but not an object | warning, dropped | `:176-179` (fix for closed #8) |
| object with non-string fields | coerced with `str()`; `null` → default | `field_text`, `:100-114` (fix for closed #9) |
| any object, while any window has **Pause** ticked | logged and **dropped** (not queued) | `:718-720` |
| any object, < 100 ms after the last accepted one | logged and **dropped** | `:723-731` |
| otherwise | spoken (unless Mute), then new window or update of the newest of ≤ 2 windows | `:733-755` |

Every received datagram is logged at INFO (`"Received message from …"`, `:165`),
and each throttled or paused one again with its full payload, to
`/tmp/daq_alert.log`, which is never rotated.

## 3. Sender bindings and byte-level comparison

### 3.1 C — `libdaq_alert.a` (`libs/c/include/daq_alert.h`)

```c
#define DAQ_ALERT_PORT 37020
#define DAQ_ALERT_BROADCAST_IP "255.255.255.255"
typedef enum { DAQ_ALERT_OK = 0, DAQ_ALERT_ERR_SOCKET = -1,
               DAQ_ALERT_ERR_SEND = -2, DAQ_ALERT_ERR_FORMAT = -3 } DaqAlertResult;
DaqAlertResult daq_alert_send(const char *system_id, const char *message,
                              const char *broadcast_ip /* NULL or "" → default */,
                              uint16_t port            /* 0 → default */);
const char *daq_alert_strerror(DaqAlertResult result);
```

- One socket per call, `SO_BROADCAST` set (result unchecked), `sendto`, close.
  On Windows, `WSAStartup`/`WSACleanup` per call.
- The destination is parsed with `inet_addr()` (`daq_alert.c:114`). An
  unparseable string returns `INADDR_NONE`, which is `255.255.255.255`, so a
  typo or a host name silently becomes a limited broadcast and the call returns
  `DAQ_ALERT_OK`. Measured: `example-sender-c -i not.an.ip` exits 0 and the
  datagram arrives as a broadcast (BRB-006). Host names are not supported.
- `system_id` or `message` `NULL` is dereferenced (no check).
- Thread-safe (no shared state).

### 3.2 C++ — `libdaq_alert_cpp.a` (`libs/cpp/include/daq_alert.hpp`)

```cpp
namespace mu2e { namespace daq {
class AlertError : public std::runtime_error { using std::runtime_error::runtime_error; };
class AlertSender {
public:
  explicit AlertSender(std::string broadcast_ip = "255.255.255.255", uint16_t port = 37020);
  void send(const std::string& system_id, const std::string& message) const;   // throws AlertError
  static void send_once(const std::string& system_id, const std::string& message,
                        const std::string& broadcast_ip = "255.255.255.255", uint16_t port = 37020);
  const std::string& broadcast_ip() const;  uint16_t port() const;
};
}}
```

Every call goes through `daq_alert_send()` (`libs/cpp/src/daq_alert.cpp:20-27`),
so behaviour and bytes are the C library's. Strings with embedded NUL are
truncated at the NUL.

### 3.3 Python — `daq_alert` (`libs/python/daq_alert/_sender.py`)

```python
DEFAULT_PORT = 37020; DEFAULT_BROADCAST_IP = "255.255.255.255"
send_alert(system_id: str, message: str,
           broadcast_ip: str = DEFAULT_BROADCAST_IP, port: int = DEFAULT_PORT) -> None   # raises OSError
class AlertSender:
    def __init__(self, broadcast_ip=DEFAULT_BROADCAST_IP, port=DEFAULT_PORT): ...
    def send(self, system_id: str, message: str) -> None
```

Install with `pip install libs/python` (distribution `daq-alert`) or via the
CMake install. The listener package's `mu2edaq_bigredbox.demo_sender.send_alert`
has the same signature and produces the same bytes; it defaults the port to
`CRS_PORT_UDP` when set.

The keyword is **`broadcast_ip`**. `mu2edaq-file-reaper` calls
`send_alert(..., ip=..., port=...)`
(`mu2edaq-file-reaper/src/mu2edaq_file_reaper/notify/channels.py:151`), which
raises `TypeError` whenever this library is importable in the reaper's
environment; its `except ImportError` does not catch it, so the reaper records
the channel as failed and never reaches its raw-JSON fallback. That defect is
in the caller and is staged once, by the file-reaper review, as **FR-011**
(`mu2edaq-file-reaper/docs/ISSUES-PENDING.md`); this review verified it
(`TypeError: send_alert() got an unexpected keyword argument 'ip'`) and did not
stage a second copy.

### 3.4 Byte-for-byte comparison

Method: built `libs/` with CMake (Apple clang), then sent the same alert
through `example-sender-c`, `example-sender-cpp`, `example-sender-py` (the
`daq_alert` library) and `mu2edaq-bigredbox-send` to a capture socket on
127.0.0.1, masking only the timestamp value.

```
case plain
  C    len= 97 {"system_id":"DAQ-NODE-01","timestamp":"<TS>","message":"Readout buffer overflow"}
  C++  len= 97 (identical to C)
  Py   len=102 {"system_id": "DAQ-NODE-01", "timestamp": "<TS>", "message": "Readout buffer overflow"}
  Py   len=102 (mu2edaq-bigredbox-send, identical to the daq_alert library)
case escapes  (system_id 'NODE "q"\', message with \n \t \r \b \f 0x01 0x1f 0x7f)
  C    ..."message":"l1\nl2\tT\rR\u0008B\u000cF\u0001\u001f<0x7f>DEL"
  Py   ..."message": "l1\nl2\tT\rR\bB\fF\u0001\u001f\u007fDEL"
case utf8  (system_id "trk-µ", message "ΔT → 5 µs")
  C    raw UTF-8 bytes
  Py   µ, Δ, → escapes
case 2100-byte message
  C, C++  rejected (DAQ_ALERT_ERR_FORMAT), nothing sent, exit 1
  Py      sent, 2179 bytes
-> in every sendable case: 2 distinct byte strings (C = C++, Py = Py), 1 decoded JSON object
```

| Aspect | C / C++ | Python (both) |
|---|---|---|
| Key order | system_id, timestamp, message | same |
| Separators | none | `", "` and `": "` |
| `\b`, `\f` | `\u0008`, `\u000c` | `\b`, `\f` |
| Other C0 controls | `\u00XX` | `\u00XX` |
| DEL 0x7F | raw | `\u007f` |
| Non-ASCII | raw UTF-8 | `\uXXXX` (`ensure_ascii`) |
| Invalid UTF-8 in input | passed through; the listener then drops the datagram as undecodable | impossible (`str`) |
| Timestamp | local, `%Y-%m-%dT%H:%M:%S` | local, `isoformat(timespec="seconds")`, same shape |
| Max field size | ~2 kB escaped | ~64 kB total |
| Bad address | silently broadcast | `OSError`/`gaierror` |

Repeated in the review's completion pass (macOS, `libs/` rebuilt with Apple
clang in a scratch directory): same four cases, same result. Datagram lengths
with the timestamp masked were C = C++ = 82 bytes and Python = Python = 86 bytes
for the plain case; the 2100-byte message was rejected by C and C++ (exit 1,
nothing on the wire) and sent by both Python senders. `example-sender-c -i
not.an.ip` exited 0 and the datagram arrived at a `0.0.0.0` listener as a
broadcast, while the Python library raised `socket.gaierror` for the same
address.

**Verdict:** the bindings agree on the decoded object for every input the C
library accepts, and the listener only ever decodes, so they are
interchangeable today. They are not byte-identical, and they disagree on size
limits and invalid-address handling. Anyone adding a receiver that is not a
JSON parser (a `grep` on a packet capture, a fixed-offset parser) must not
assume one encoding.

## 4. Service discovery

With `mu2edaq_discovery` importable (`daq_alert.py:633-642`):

| Field | Value |
|---|---|
| `name` / `app` | `Big Red Box Alerts` / `bigredbox` |
| `scheme` / `port` | `udp` / `BROADCAST_PORT` |
| `version` | `__version__` (2.0.0) |
| `meta` | `version`, `qt`, `pyqt`, `python`, `udp_port`; all `str` (`daq_alert.py:82-96`) |

All `meta` values are strings, as `mu2edaq-discovery/doc/INTERFACES.md` §6
requires (`QT_VERSION_STR` and `PYQT_VERSION_STR` are strings; the port is
wrapped in `str()`).

## 5. Environment, files, exit status

| Variable | Effect |
|---|---|
| `CRS_PORT_UDP` | listener port and `mu2edaq-bigredbox-send` default port; blank/invalid → 37020 with a warning |
| `DAQ_ALERT_LOG_FILE` | default `/tmp/daq_alert.log`; unwritable → stderr |
| `DAQ_ALERT_PID_FILE` | default `/tmp/daq_alert.pid`; unwritable → run without it |
| `DAQ_ALERT_TTS_ENABLED` | default on |
| `DAQ_ALERT_TTS_BACKEND` | `qt` (default) or `aws` |
| `DAQ_ALERT_TTS_RATE`, `_VOLUME`, `_VOICE`, `_ENGINE` | Qt backend only |
| `DAQ_ALERT_TTS_AWS_VOICE`, `_AWS_ENGINE`, `_AWS_REGION`, `_AWS_PROFILE` | Polly backend only |
| `DAQ_ALERT_TTS_TEMPLATE_FILE` | default `config/tts_templates.yaml`, relative to cwd |
| `DISPLAY` / `QT_QPA_PLATFORM` | Qt platform selection; the start script defaults `DISPLAY=:0` |

Listener exit status: 0 normal; 1 Python exception at import (for example
`libpulse.so.0` missing); **3** UDP port in use (macOS only in practice; see
BRB-002); **134** (SIGABRT) when Qt cannot open a display.

Man pages: `mu2edaq-bigredbox(1)`, `mu2edaq-bigredbox-send(1)`,
`start-mu2edaq-bigredbox.sh(1)`, `stop-mu2edaq-bigredbox.sh(1)`, `bootstrap.sh(1)`,
`libdaq_alert(3)`, `libdaq_alert_cpp(3)`, `daq_alert(3)`, `tts_templates.yaml(5)`,
`mu2edaq-bigredbox-api(7)`; the example senders' pages stay next to their
sources under `libs/examples/*/`, where CMake installs them from. Only
`mu2edaq-bigredbox.1` and `mu2edaq-bigredbox-send.1` are listed in
`pyproject.toml`'s `data-files`, so `pip install` installs only those two
(BRB-010).

---

## 6. Review facts verified and questions settled

| Claim or question | Result | Evidence |
|---|---|---|
| UDP broadcast on 37020 | **Confirmed.** Listener binds `0.0.0.0:37020`; every sender defaults to `255.255.255.255:37020` | `config.py:15`; `daq_alert.h:11,14`; `_sender.py:9-10`; `demo_sender.py:21` |
| Confirmed caller: `mu2edaq-file-reaper`, default-off, critical only | **Confirmed.** `bigredbox:` channel with `enabled: false`, `min_severity: critical`, `port: 37020`, no `ip:` key (so `255.255.255.255`) | `mu2edaq-file-reaper/config/mu2edaq-file-reaper.yaml:147-151`; `notify/channels.py:148-160` |
| Two script pairs: duplicates? | **No.** `start_daq_alert.sh` and `stop_daq_alert.sh` are mode `120000` in `git ls-files -s`, i.e. symlinks to `start-mu2edaq-bigredbox.sh` / `stop-mu2edaq-bigredbox.sh`. Not filed | `git ls-files -s` |
| Do the C, C++ and Python senders emit identical bytes? | **C and C++ yes; C vs Python no.** C++ calls the C function, so their bytes are identical; the two Python implementations are identical to each other. C and Python differ in separators, escaping of `\b`/`\f`/DEL/non-ASCII, and size and address handling, but decode to the same object | §3.4 |
| Unauthenticated broadcast: accepted risk or defect? | **Accepted design risk for spoofing; defect for suppression.** A spoofed alert costs a click on a closed network, and authentication would defeat the one-call, receiver-agnostic sender model. The global first-come 100 ms limiter lets any >10 Hz source starve genuine alerts, which breaks the box's only promise; that is BRB-003 (S3) and needs no authentication to fix | `ARCHITECTURE.md`, "The unauthenticated broadcast"; `daq_alert.py:723-731` |
| DISC-016: `requirements.txt:10` names `mu2edaq-discovery` bare | **Confirmed, and a regression.** `45805cc` removed the line on 2026-07-24; merge `6ed76a5` (main into QT6-Migration) reintroduced it and PR #15 (`c557be3`) brought it back to `main`. Staged once, as DISC-016 in `mu2edaq-discovery/doc/ISSUES-PENDING.md`; not restaged here | `git show <rev>:requirements.txt` for each revision |
| Discovery `meta` values are strings (§9.5) | **Confirmed.** `version`, `qt`, `pyqt` are `str`; `python` is `"%d.%d.%d" % ...`; `udp_port` is `str(BROADCAST_PORT)` | `daq_alert.py:90-96` |
| 110 tests, no CI | **Confirmed.** `110 passed` on macOS / Python 3.12 / PyQt6 6.11; no `.github/` | `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q` |
| libpulse is a hard runtime dependency (BRB-001) | **Confirmed independently.** In the `PyQt6-Qt6` 6.10.2 `manylinux_2_34_x86_64` wheel, `libQt6Multimedia.so.6` has `DT_NEEDED libpulse.so.0` and `libQt6TextToSpeech.so.6` needs `libQt6Multimedia.so.6`; `tts.py:16-17` imports both at module scope | ELF dynamic section read from the wheel |
| `SO_REUSEADDR` co-bind on Linux (BRB-002) | **Confirmed independently.** In an `almalinux:9` container the second bind succeeds and a unicast datagram goes to the second socket only; on macOS the second bind fails with `EADDRINUSE` | socket probe with the listener's exact options |
| PyQt6 6.9.1 on Python 3.9 (README) | **Contradicted.** PyPI `requires_python` is `>=3.9` for 6.9.1, 6.10.0 and 6.10.2 and `>=3.10` for 6.11.0, so Python 3.9 resolves 6.10.x (BRB-009) | PyPI JSON API |
