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

echo "Starting Big Red Box / DAQ Alert listener (udp=$CRS_PORT_UDP)"
nohup "$PY" "$SCRIPT_DIR/daq_alert.py" >> "$LOG_FILE" 2>&1 &
bgpid=$!
sleep 1
if ! kill -0 "$bgpid" 2>/dev/null; then
  echo "error: DAQ Alert listener failed to start; see $LOG_FILE" >&2
  exit 1
fi
echo "DAQ Alert listener started (PID $bgpid); log: $LOG_FILE"
