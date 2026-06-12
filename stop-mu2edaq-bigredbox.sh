#!/usr/bin/env bash
# stop_daq_alert.sh — Stop the DAQ Alert listener.

set -euo pipefail

PID_FILE="/tmp/daq_alert.pid"

if [[ ! -f "$PID_FILE" ]]; then
    echo "DAQ Alert listener is not running (no PID file at $PID_FILE)."
    exit 1
fi

PID="$(cat "$PID_FILE")"

if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "DAQ Alert listener stopped (PID: $PID)."
    rm -f "$PID_FILE"
else
    echo "Process $PID is not running (stale PID file — cleaning up)."
    rm -f "$PID_FILE"
    exit 1
fi
