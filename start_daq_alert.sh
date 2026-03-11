#!/usr/bin/env bash
# start_daq_alert.sh — Start the DAQ Alert listener in the background.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="/tmp/daq_alert.pid"
LOG_FILE="/tmp/daq_alert.log"

# ---- Check if already running -----------------------------------------------
if [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
        echo "DAQ Alert listener is already running (PID: $PID)."
        echo "Use stop_daq_alert.sh to stop it first."
        exit 1
    else
        echo "Stale PID file found — removing."
        rm -f "$PID_FILE"
    fi
fi

# ---- Ensure a DISPLAY is available ------------------------------------------
export DISPLAY="${DISPLAY:-:0}"

# ---- Start the application ---------------------------------------------------
nohup python3 "$SCRIPT_DIR/daq_alert.py" >> "$LOG_FILE" 2>&1 &
BGPID=$!

# Give the process a moment to start and verify it is alive
sleep 1
if ! kill -0 "$BGPID" 2>/dev/null; then
    echo "ERROR: DAQ Alert listener failed to start. Check $LOG_FILE for details."
    exit 1
fi

echo "DAQ Alert listener started (PID: $BGPID)."
echo "Log file : $LOG_FILE"
