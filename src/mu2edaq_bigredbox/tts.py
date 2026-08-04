"""
Text-to-speech alert reading via Qt's QTextToSpeech, and the YAML-backed
template rendering that produces the text it speaks.

Compatible with Python 3.9+
"""

import fnmatch
import logging

from PyQt6.QtTextToSpeech import QTextToSpeech

from .config import DEFAULT_TTS_TEMPLATE

log = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None


class TTSSpeaker:
    """Speaks alert text aloud via one QTextToSpeech instance.

    Must be constructed after a QApplication exists and used only from the
    GUI thread -- QTextToSpeech is asynchronous via the Qt event loop, so
    say() never blocks and no background thread is needed here (unlike a
    blocking engine such as pyttsx3).

    Construction, and every property set on the engine, is best-effort: a
    missing speech plugin, a bad engine/voice name, or an out-of-range rate
    or volume must never stop the app from starting or crash it, mirroring
    the discovery responder's degrade-gracefully pattern in daq_alert.py.
    """

    def __init__(self, enabled, rate=None, volume=None, voice=None,
                 engine_name=None):
        self._engine = None
        self._available = False
        if not enabled:
            return

        try:
            self._engine = (QTextToSpeech(engine_name) if engine_name
                             else QTextToSpeech())
        except Exception as exc:
            log.warning("Could not create text-to-speech engine; TTS "
                        "disabled (%s)", exc)
            self._engine = None
            return

        self._engine.stateChanged.connect(self._on_state_changed)

        # A bad engine name fails synchronously (state is already Error
        # right after construction) rather than emitting stateChanged,
        # since we only just connected to it -- check both.
        if self._engine.state() == QTextToSpeech.State.Error:
            log.warning("Text-to-speech engine %r failed to initialize; "
                        "TTS disabled", engine_name)
            self._engine = None
            return

        if rate is not None:
            try:
                self._engine.setRate(rate)
            except Exception:
                log.warning("Could not set TTS rate %r; using engine "
                            "default", rate)

        if volume is not None:
            try:
                self._engine.setVolume(volume)
            except Exception:
                log.warning("Could not set TTS volume %r; using engine "
                            "default", volume)

        if voice:
            self._select_voice(voice)

        self._available = True

    def _select_voice(self, name_substring):
        needle = name_substring.strip().lower()
        try:
            voices = self._engine.availableVoices()
        except Exception:
            log.warning("Could not list TTS voices; using engine default "
                        "voice")
            return
        for candidate in voices:
            if needle in candidate.name().lower():
                try:
                    self._engine.setVoice(candidate)
                except Exception:
                    log.warning("Could not select TTS voice %r; using "
                                "engine default", name_substring)
                return
        log.warning("No TTS voice matching %r found; using engine default",
                    name_substring)

    def _on_state_changed(self, state):
        """Qt slot; must never raise. Disables further speech on error."""
        if state == QTextToSpeech.State.Error:
            if self._available:
                log.warning("Text-to-speech engine entered an error state; "
                            "disabling further speech")
            self._available = False

    def speak(self, text):
        if not self._available or not text:
            return
        try:
            self._engine.say(text)
        except Exception:
            log.exception("Text-to-speech engine failed to speak; "
                          "continuing")

    def stop(self):
        """Cut off any in-progress speech. Best-effort; runs at shutdown."""
        if self._engine is None:
            return
        try:
            self._engine.stop()
        except Exception:
            log.warning("Error stopping text-to-speech engine", exc_info=True)


def _text(value, default):
    """Coerce a payload field to text `.format()` will accept.

    Mirrors daq_alert.field_text()'s handling of non-str/None payload
    fields without importing daq_alert (which imports this module to
    dispatch speech -- importing back would be circular).
    """
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def load_templates(path):
    """Load a YAML {system_id_glob: template} map, never raising.

    Returns {} for any problem -- missing PyYAML, missing/unreadable file,
    a parse error, a non-mapping top level, or non-string keys/values --
    so the caller always has a safe (empty) map to fall back from onto
    DEFAULT_TTS_TEMPLATE.
    """
    if not path:
        return {}
    if yaml is None:
        log.warning("PyYAML is not installed; ignoring TTS template file %s",
                    path)
        return {}
    try:
        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        log.warning("Could not read TTS template file %s: %s", path, exc)
        return {}
    except yaml.YAMLError as exc:
        log.warning("Could not parse TTS template file %s: %s", path, exc)
        return {}

    if data is None:
        return {}
    if not isinstance(data, dict):
        log.warning("TTS template file %s must contain a mapping; "
                    "ignoring it", path)
        return {}

    templates = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            log.warning("Ignoring non-string TTS template entry %r: %r",
                        key, value)
            continue
        templates[key] = value
    return templates


def render_template(data, templates):
    """Render the spoken text for one alert payload.

    Matches data["system_id"] against `templates` keys as fnmatch glob
    patterns (first match in file order wins), falling back to a
    "default" key, falling back to DEFAULT_TTS_TEMPLATE. A malformed
    custom template (bad placeholder) falls back the same way rather
    than raising.
    """
    system_id = _text(data.get("system_id"), "UNKNOWN")
    fields = {
        "system_id": system_id,
        "timestamp": _text(data.get("timestamp"), "UNKNOWN"),
        "message": _text(data.get("message"), "(no message text)"),
    }

    template = templates.get("default")
    for pattern, candidate in templates.items():
        if pattern == "default":
            continue
        if fnmatch.fnmatch(system_id, pattern):
            template = candidate
            break

    if template is None:
        template = DEFAULT_TTS_TEMPLATE

    try:
        return template.format(**fields)
    except (KeyError, IndexError, ValueError) as exc:
        log.warning("Malformed TTS template %r (%s); using default "
                    "template", template, exc)
        return DEFAULT_TTS_TEMPLATE.format(**fields)
