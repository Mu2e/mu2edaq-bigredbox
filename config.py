"""
Shared configuration for the DAQ Alert system.
"""

import os

# PID file location for daemon management
PID_FILE = "/tmp/daq_alert.pid"

# Log file location
LOG_FILE = "/tmp/daq_alert.log"

# Maximum rate in Hz at which incoming messages are accepted 
# Messages arriving faster than this are silently dropped.
MESSAGE_RATE_LIMIT = 10.0

# Maximum number of alert windows that may be open simultaneously.
# Each time a message is received a new window is openned up to 
# this limit, after which the messages go to the most recently
# opened (and unpaused) window.
MAX_ALERT_WINDOWS = 2

# UDP broadcast port for alert messages.
# CRS_PORT_UDP is exported by the control room's crs-app launcher.
BROADCAST_PORT = int(os.environ.get("CRS_PORT_UDP", 37020))

