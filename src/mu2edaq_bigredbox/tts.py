"""
Text-to-speech alert reading, and the YAML-backed template rendering that
produces the text spoken. Two interchangeable backends are available,
selected via create_speaker(): the local Qt QTextToSpeech engine
(TTSSpeaker), and AWS Polly (AWSPollySpeaker), played back through
QtMultimedia.

Compatible with Python 3.9+
"""

import fnmatch
import logging
import queue

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QThread, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtTextToSpeech import QTextToSpeech

from .config import DEFAULT_TTS_TEMPLATE

log = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None

try:
    import boto3
except ImportError:
    boto3 = None


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


class _PollySynthesisThread(QThread):
    """Background thread that turns queued text into AWS Polly audio bytes.

    AWS Polly's synthesize_speech() is a blocking HTTP call with no async
    API available here, so it runs the same way UDPListenerThread runs its
    blocking recvfrom() loop (daq_alert.py): a persistent daemon thread
    bounded by a queue.get() timeout so stop() can return promptly, with
    results handed back to the GUI thread via a signal -- PyQt marshals a
    signal emitted from a QThread.run() to whichever thread the connected
    slot lives on automatically, the same mechanism message_received uses.
    """

    synthesized = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, client, voice, engine):
        super().__init__()
        self._client = client
        self._voice = voice
        self._engine = engine
        self._queue = queue.Queue()
        self._running = True

    def speak(self, text):
        self._queue.put(text)

    def run(self):
        while self._running:
            try:
                text = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if text is None:
                break
            try:
                response = self._client.synthesize_speech(
                    Text=text, OutputFormat="mp3", VoiceId=self._voice,
                    Engine=self._engine)
                audio = response["AudioStream"].read()
            except Exception as exc:
                # A single failed synthesis (throttling, a transient
                # network blip) must not kill the thread -- the next
                # alert deserves its own attempt.
                self.failed.emit(str(exc))
                continue
            self.synthesized.emit(audio)

    def stop(self):
        self._running = False
        self._queue.put(None)
        self.wait(3000)


class AWSPollySpeaker:
    """Speaks alert text aloud via AWS Polly, played back through QtMultimedia.

    Text synthesis is a blocking network call, so it runs on a background
    _PollySynthesisThread; QMediaPlayer/QAudioOutput/QBuffer must be
    constructed and driven from the GUI thread, so the synthesized-audio
    signal is handled by a slot here rather than inside the worker thread.

    Unlike TTSSpeaker, a failure speaking one alert does not permanently
    disable the speaker: AWS errors are frequently transient (network
    blips, throttling) or externally fixable (an IAM policy corrected)
    without restarting this app, so each speak() call is independently
    best-effort. Only a missing boto3 install or a client that cannot be
    constructed at all (e.g. no resolvable region) disables it for good.
    """

    def __init__(self, enabled, voice="Joanna", engine="neural", region=None,
                 profile=None):
        self._worker = None
        self._player = None
        self._audio_output = None
        self._buffer = None
        self._available = False
        if not enabled:
            return

        if boto3 is None:
            log.warning("boto3 is not installed; AWS Polly TTS disabled "
                        "(pip install '.[aws]')")
            return

        try:
            if profile:
                session = boto3.Session(profile_name=profile)
                client = session.client("polly", region_name=region)
            else:
                client = boto3.client("polly", region_name=region)
        except Exception as exc:
            log.warning("Could not create AWS Polly client; TTS disabled "
                        "(%s)", exc)
            return

        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._player.errorOccurred.connect(self._on_player_error)

        self._worker = _PollySynthesisThread(client, voice, engine)
        self._worker.synthesized.connect(self._play)
        self._worker.failed.connect(self._on_synthesis_failed)
        self._worker.start()

        self._available = True

    def _play(self, audio_bytes):
        """Qt slot; runs on the GUI thread. A new alert pre-empts playback
        of whatever the previous one was still speaking."""
        if self._player is None:
            return
        self._player.stop()
        self._buffer = QBuffer()
        self._buffer.setData(QByteArray(audio_bytes))
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._player.setSourceDevice(self._buffer)
        self._player.play()

    def _on_synthesis_failed(self, message):
        """Qt slot; must never raise."""
        log.warning("AWS Polly speech synthesis failed; skipping this "
                    "alert (%s)", message)

    def _on_player_error(self, error, error_string):
        """Qt slot; must never raise."""
        log.warning("AWS Polly playback error: %s", error_string)

    def speak(self, text):
        if not self._available or not text:
            return
        self._worker.speak(text)

    def stop(self):
        """Cut off any in-progress speech. Best-effort; runs at shutdown."""
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                log.warning("Error stopping Polly playback", exc_info=True)
        if self._worker is not None:
            try:
                self._worker.stop()
            except Exception:
                log.warning("Error stopping Polly synthesis thread",
                            exc_info=True)


def create_speaker(backend, *, enabled, rate=None, volume=None, voice=None,
                    engine_name=None, aws_voice=None, aws_engine=None,
                    aws_region=None, aws_profile=None):
    """Construct the configured TTS backend. Never raises.

    backend == "aws" builds an AWSPollySpeaker; anything else (including
    the expected "qt") builds a TTSSpeaker -- config.py's _choice() already
    guarantees backend is one of ("qt", "aws"), so the fallback branch here
    is defensive, not a path exercised in practice.
    """
    if backend == "aws":
        return AWSPollySpeaker(enabled, voice=aws_voice, engine=aws_engine,
                                region=aws_region, profile=aws_profile)
    return TTSSpeaker(enabled, rate=rate, volume=volume, voice=voice,
                       engine_name=engine_name)


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
