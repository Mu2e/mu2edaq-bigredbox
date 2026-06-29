#!/usr/bin/env bash
#
# stop-mu2edaq-bigredbox.sh - standardized Mu2e control-room stop script.
# Launched as `crs-app stop bigredbox`. Stops the DAQ Alert listener via its
# pid file (SIGTERM then SIGKILL after a timeout).
set -euo pipefail

PID_FILE="${1:-/tmp/daq_alert.pid}"
TIMEOUT="${CRS_STOP_TIMEOUT:-10}"

if [[ ! -f "$PID_FILE" ]]; then
  echo "DAQ Alert listener not running (no pid file: $PID_FILE)"
  exit 0
fi
pid="$(cat "$PID_FILE")"
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
