#!/usr/bin/env bash
#
# start-mu2edaq-bigredbox.sh - standardized Mu2e control-room start script.
#
# Launched by the control room as `crs-app start bigredbox`, which exports
# CRS_PORT_UDP from apps.yaml. daq_alert.py honors CRS_PORT_UDP as the UDP
# broadcast port (see config.py). Starts the listener in the background; the
# app writes /tmp/daq_alert.pid.
#
# Port precedence: CRS_PORT_UDP env > built-in default (37020, matching apps.yaml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export CRS_PORT_UDP="${CRS_PORT_UDP:-37020}"
export DISPLAY="${DISPLAY:-:0}"
PID_FILE="/tmp/daq_alert.pid"
LOG_FILE="/tmp/daq_alert.log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "DAQ Alert listener already running (PID $(cat "$PID_FILE"))."
  exit 0
fi
rm -f "$PID_FILE"

PY=python3
[[ -x ./venv/bin/python ]] && PY=./venv/bin/python

# The pid file only knows about listeners this script started. A listener
# launched by hand, or one orphaned when the pid file was deleted, is invisible
# to the check above -- but it still owns the UDP port. Ask the port itself,
# which is the authoritative answer. (The app repeats this check when it binds,
# so the small race between here and launch is covered.)
if ! "$PY" - "$CRS_PORT_UDP" <<'PYEOF'
import socket, sys
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind(("", int(sys.argv[1])))
except OSError:
    sys.exit(1)
finally:
    sock.close()
PYEOF
then
  echo "error: UDP port $CRS_PORT_UDP is already in use -- a DAQ Alert listener" >&2
  echo "       is already running (its pid file may have been removed)." >&2
  if command -v lsof >/dev/null 2>&1; then
    echo "       holder:" >&2
    lsof -nP -iUDP:"$CRS_PORT_UDP" >&2 || true
  fi
  echo "       stop it with ./stop-mu2edaq-bigredbox.sh, or kill the pid above." >&2
  exit 1
fi

# Prefer the installed console-script entry point; fall back to the checkout
# shim when the package has not been installed (see bootstrap.sh).
if [[ -x ./venv/bin/mu2edaq-bigredbox ]]; then
  LAUNCH=(./venv/bin/mu2edaq-bigredbox)
elif command -v mu2edaq-bigredbox >/dev/null 2>&1; then
  LAUNCH=(mu2edaq-bigredbox)
else
  LAUNCH=("$PY" "$SCRIPT_DIR/daq_alert.py")
fi

echo "Starting Big Red Box / DAQ Alert listener (udp=$CRS_PORT_UDP)"
nohup "${LAUNCH[@]}" >> "$LOG_FILE" 2>&1 &
bgpid=$!
sleep 1
if ! kill -0 "$bgpid" 2>/dev/null; then
  echo "error: DAQ Alert listener failed to start; see $LOG_FILE" >&2
  tail -n 3 "$LOG_FILE" >&2 2>/dev/null || true
  exit 1
fi
echo "DAQ Alert listener started (PID $bgpid); log: $LOG_FILE"
