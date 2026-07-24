#!/usr/bin/env bash
#
# stop-mu2edaq-bigredbox.sh - standardized Mu2e control-room stop script.
# Launched as `crs-app stop bigredbox`. Stops the DAQ Alert listener via its
# pid file (SIGTERM then SIGKILL after a timeout).
set -euo pipefail

PID_FILE="${1:-/tmp/daq_alert.pid}"
TIMEOUT="${CRS_STOP_TIMEOUT:-10}"
PORT="${CRS_PORT_UDP:-37020}"

# A listener started by hand, or one whose pid file was deleted, still owns the
# UDP port. Fall back to the port holder so such an orphan can still be stopped
# -- otherwise the start script refuses to start (port busy) and this script
# refuses to stop (no pid file), leaving no way out but a manual kill.
find_orphan() {
  command -v lsof >/dev/null 2>&1 || return 1
  local candidate
  for candidate in $(lsof -t -nP -iUDP:"$PORT" 2>/dev/null); do
    # Only ever stop our own application, never an unrelated port holder.
    if ps -p "$candidate" -o command= 2>/dev/null |
         grep -qE 'mu2edaq[-_]bigredbox|daq_alert'; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if [[ ! -f "$PID_FILE" ]]; then
  if orphan="$(find_orphan)"; then
    echo "No pid file ($PID_FILE), but a DAQ Alert listener holds UDP $PORT (pid $orphan)."
    pid="$orphan"
  else
    echo "DAQ Alert listener not running (no pid file: $PID_FILE)"
    exit 0
  fi
else
  pid="$(cat "$PID_FILE")"
fi
if ! kill -0 "$pid" 2>/dev/null; then
  echo "DAQ Alert listener not running (stale pid $pid); cleaning up"
  rm -f "$PID_FILE"
  exit 0
fi

echo "Stopping DAQ Alert listener (pid $pid)..."
kill -TERM "$pid" 2>/dev/null || true
for ((i = 0; i < TIMEOUT; i++)); do
  kill -0 "$pid" 2>/dev/null || break
  sleep 1
done
if kill -0 "$pid" 2>/dev/null; then
  echo "did not exit within ${TIMEOUT}s; sending SIGKILL"
  kill -KILL "$pid" 2>/dev/null || true
  sleep 1
fi
rm -f "$PID_FILE"
echo "DAQ Alert listener stopped"
