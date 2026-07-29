"""
Shared configuration for the DAQ Alert system.

Every value below can be overridden from the environment.  Parsing is
deliberately forgiving: this module is imported before logging is configured,
so a bad value must fall back to the default with a warning rather than raise
and leave the operator with a bare traceback.
"""

import logging
import os
import tempfile

log = logging.getLogger(__name__)

DEFAULT_PORT = 37020
# Use the platform temp dir so the defaults are valid on every OS. On POSIX
# gettempdir() is normally "/tmp" (honouring $TMPDIR), preserving the previous
# behaviour; on Windows it resolves to %TEMP% instead of a nonexistent /tmp.
_TMPDIR = tempfile.gettempdir()
DEFAULT_PID_FILE = os.path.join(_TMPDIR, "daq_alert.pid")
DEFAULT_LOG_FILE = os.path.join(_TMPDIR, "daq_alert.log")


def _port(value, default=DEFAULT_PORT, source="CRS_PORT_UDP"):
    """Parse a UDP port, falling back to `default` if it is unusable.

    os.environ.get(key, default) only substitutes when the variable is *unset*.
    The control room's crs-app exports CRS_PORT_UDP from apps.yaml, and a blank
    key there exports an empty string -- a present value that int() rejects.
    """
    if value is None or str(value).strip() == "":
        return default
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        log.warning("%s=%r is not a number; using default port %d",
                    source, value, default)
        return default
    if not 0 < port < 65536:
        log.warning("%s=%r is out of range (1-65535); using default port %d",
                    source, value, default)
        return default
    return port


def _path(env_var, default):
    """Return an overridable file path, ignoring a blank override."""
    value = os.environ.get(env_var)
    if value is None or value.strip() == "":
        return default
    return value


# PID file location for daemon management.
# Override with DAQ_ALERT_PID_FILE; the default is shared by every user on the
# machine, so a second operator on the same node should point this elsewhere.
PID_FILE = _path("DAQ_ALERT_PID_FILE", DEFAULT_PID_FILE)

# Log file location.  Override with DAQ_ALERT_LOG_FILE.
LOG_FILE = _path("DAQ_ALERT_LOG_FILE", DEFAULT_LOG_FILE)

# Maximum rate in Hz at which incoming messages are accepted
# Messages arriving faster than this are silently dropped.
MESSAGE_RATE_LIMIT = 10.0

# Maximum number of alert windows that may be open simultaneously.
# Each time a message is received a new window is openned up to
# this limit, after which the messages go to the most recently
# opened window.
MAX_ALERT_WINDOWS = 2

# UDP broadcast port for alert messages.
# CRS_PORT_UDP (exported by the control room's crs-app from apps.yaml) takes
# precedence over this default when set.
BROADCAST_PORT = _port(os.environ.get("CRS_PORT_UDP"))
