"""
Shared configuration for the DAQ Alert system.

Every value below can be overridden from the environment.  Parsing is
deliberately forgiving: this module is imported before logging is configured,
so a bad value must fall back to the default with a warning rather than raise
and leave the operator with a bare traceback.
"""

import logging
import os

log = logging.getLogger(__name__)

DEFAULT_PORT = 37020
DEFAULT_PID_FILE = "/tmp/daq_alert.pid"
DEFAULT_LOG_FILE = "/tmp/daq_alert.log"


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


def _bool(value, default, source):
    """Parse a boolean override, falling back to `default` if it is unusable.

    Accepts 1/0, true/false, yes/no, on/off (case-insensitive). Anything
    else falls back to `default` with a warning, per this module's
    never-raise contract.
    """
    if value is None or str(value).strip() == "":
        return default
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    log.warning("%s=%r is not a recognized boolean; using default %r",
                source, value, default)
    return default


def _float(value, default, lo, hi, source):
    """Parse a float override within [lo, hi], falling back to `default`.

    Returns `default` (never raises) for a missing, non-numeric, or
    out-of-range value, with a warning explaining why.
    """
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = float(str(value).strip())
    except ValueError:
        log.warning("%s=%r is not a number; using default %r",
                    source, value, default)
        return default
    if not lo <= parsed <= hi:
        log.warning("%s=%r is out of range (%s-%s); using default %r",
                    source, value, lo, hi, default)
        return default
    return parsed


def _choice(value, default, choices, source):
    """Parse a case-insensitive enum value, falling back to `default`.

    `choices` is compared case-insensitively but the matching entry from
    `choices` (not the raw input) is returned, so callers get a normalized
    value. An unrecognized value falls back to `default` with a warning,
    per this module's never-raise contract.
    """
    if value is None or str(value).strip() == "":
        return default
    text = str(value).strip().lower()
    for choice in choices:
        if text == choice.lower():
            return choice
    log.warning("%s=%r is not one of %s; using default %r",
                source, value, choices, default)
    return default


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


# ── Text-to-speech ──────────────────────────────────────────────────────────
# Whether alerts are read aloud via Qt's QTextToSpeech. Override with
# DAQ_ALERT_TTS_ENABLED. Disabled here still lets the app run with no speech
# engine at all -- the engine is also independently best-effort at startup,
# so a platform with no working speech plugin degrades the same way.
TTS_ENABLED = _bool(os.environ.get("DAQ_ALERT_TTS_ENABLED"), True,
                     "DAQ_ALERT_TTS_ENABLED")

# Speech rate, QTextToSpeech.setRate() range: -1.0 (slowest) to 1.0
# (fastest), 0.0 is normal speed. None leaves the engine's own default.
# Override with DAQ_ALERT_TTS_RATE.
TTS_RATE = _float(os.environ.get("DAQ_ALERT_TTS_RATE"), None, -1.0, 1.0,
                   "DAQ_ALERT_TTS_RATE")

# Speech volume, QTextToSpeech.setVolume() range: 0.0 to 1.0. None leaves
# the engine's own default. Override with DAQ_ALERT_TTS_VOLUME.
TTS_VOLUME = _float(os.environ.get("DAQ_ALERT_TTS_VOLUME"), None, 0.0, 1.0,
                     "DAQ_ALERT_TTS_VOLUME")

# Case-insensitive substring match against QVoice.name() among
# QTextToSpeech.availableVoices(). None leaves the engine's default voice.
# Override with DAQ_ALERT_TTS_VOICE.
TTS_VOICE = _path("DAQ_ALERT_TTS_VOICE", None)

# Force a specific Qt text-to-speech plugin (e.g. "speechd" or "flite" on
# Linux, "sapi" on Windows, "darwin" on macOS) when more than one is
# available. None lets Qt auto-pick. Override with DAQ_ALERT_TTS_ENGINE.
TTS_ENGINE = _path("DAQ_ALERT_TTS_ENGINE", None)

# YAML file mapping system_id glob patterns to spoken-text templates (plus
# an optional "default" key). Missing, unreadable, or malformed files fall
# back to DEFAULT_TTS_TEMPLATE below. Override with
# DAQ_ALERT_TTS_TEMPLATE_FILE.
TTS_TEMPLATE_FILE = _path("DAQ_ALERT_TTS_TEMPLATE_FILE",
                           "config/tts_templates.yaml")

# Built-in fallback spoken-text template, used whenever no template file is
# configured/loadable or no template matches a given system_id.
DEFAULT_TTS_TEMPLATE = "Critical error on {system_id}. {message}"

# Which engine reads alerts aloud: the local Qt QTextToSpeech plugin, or AWS
# Polly (requires the "aws" extra -- `pip install .[aws]` -- and network
# access; degrades to silence with a warning if unavailable). Override with
# DAQ_ALERT_TTS_BACKEND. An unrecognized value falls back to "qt".
TTS_BACKEND = _choice(os.environ.get("DAQ_ALERT_TTS_BACKEND"), "qt",
                      ("qt", "aws"), "DAQ_ALERT_TTS_BACKEND")

# AWS Polly voice ID (e.g. "Joanna", "Matthew"). Override with
# DAQ_ALERT_TTS_AWS_VOICE. Only used when TTS_BACKEND is "aws".
TTS_AWS_VOICE = _path("DAQ_ALERT_TTS_AWS_VOICE", "Joanna")

# AWS Polly engine tier: "standard", "neural", or "generative" -- a voice
# quality/cost axis, unrelated to TTS_ENGINE above (which selects a Qt
# platform plugin). Override with DAQ_ALERT_TTS_AWS_ENGINE.
TTS_AWS_ENGINE = _path("DAQ_ALERT_TTS_AWS_ENGINE", "neural")

# AWS region for the Polly client. None lets boto3 resolve it from the
# environment or ~/.aws/config. Override with DAQ_ALERT_TTS_AWS_REGION.
TTS_AWS_REGION = _path("DAQ_ALERT_TTS_AWS_REGION", None)

# Named AWS profile (from ~/.aws/credentials / ~/.aws/config) to use for the
# Polly client. None uses boto3's default credential chain. Override with
# DAQ_ALERT_TTS_AWS_PROFILE.
TTS_AWS_PROFILE = _path("DAQ_ALERT_TTS_AWS_PROFILE", None)
