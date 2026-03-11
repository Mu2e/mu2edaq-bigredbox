"""
Shared configuration for the DAQ Alert system.
"""

# UDP broadcast port for alert messages
BROADCAST_PORT = 37020

# PID file location for daemon management
PID_FILE = "/tmp/daq_alert.pid"

# Log file location
LOG_FILE = "/tmp/daq_alert.log"

# Maximum rate at which incoming messages are accepted (messages per second).
# Messages arriving faster than this are silently dropped.
MESSAGE_RATE_LIMIT = 10.0

# Maximum number of alert windows that may be open simultaneously.
# When the cap is reached, new messages update the most recently opened
# unpaused window instead of opening a new one.
MAX_ALERT_WINDOWS = 2
