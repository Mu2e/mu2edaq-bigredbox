"""Tests for text-to-speech alert reading (mu2edaq_bigredbox.tts).

TTSSpeaker tests use a fake QTextToSpeech stand-in rather than a real
platform speech engine, so they run deterministically without requiring a
working speech plugin (e.g. speech-dispatcher/flite) to be installed in CI.
render_template()/load_templates() need no Qt object at all, but the module
under test imports PyQt6.QtTextToSpeech at import time, so this file follows
test_gui.py's offscreen-platform / importorskip pattern.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6", reason="PyQt6 is required for the TTS tests")

from PyQt6.QtTextToSpeech import QTextToSpeech as _RealQTextToSpeech  # noqa: E402

from mu2edaq_bigredbox import config, tts  # noqa: E402

MESSAGE = {
    "system_id": "DAQ-NODE-01",
    "timestamp": "2026-07-22T09:15:00",
    "message": "Buffer overflow",
}


# ── render_template() ────────────────────────────────────────────────────────

def test_render_template_falls_back_to_default_template():
    text = tts.render_template(MESSAGE, {})
    assert text == config.DEFAULT_TTS_TEMPLATE.format(**MESSAGE)


def test_render_template_matches_glob_pattern():
    templates = {"DAQ-NODE-*": "Node {system_id} down: {message}"}
    text = tts.render_template(MESSAGE, templates)
    assert text == "Node DAQ-NODE-01 down: Buffer overflow"


def test_render_template_falls_back_to_configured_default_key():
    templates = {"default": "Generic alert: {message}", "OTHER-*": "unused"}
    text = tts.render_template(MESSAGE, templates)
    assert text == "Generic alert: Buffer overflow"


def test_render_template_survives_malformed_custom_template():
    """A bad placeholder in an operator-supplied template must not raise."""
    templates = {"DAQ-NODE-*": "Bad template {not_a_field}"}
    text = tts.render_template(MESSAGE, templates)
    assert text == config.DEFAULT_TTS_TEMPLATE.format(**MESSAGE)


def test_render_template_coerces_non_string_fields():
    data = {"system_id": 42, "timestamp": None, "message": ["oops"]}
    text = tts.render_template(data, {})
    assert "42" in text
    assert "['oops']" in text


# ── load_templates() ─────────────────────────────────────────────────────────

def test_load_templates_missing_file_returns_empty(tmp_path):
    assert tts.load_templates(str(tmp_path / "missing.yaml")) == {}


def test_load_templates_blank_path_returns_empty():
    assert tts.load_templates(None) == {}
    assert tts.load_templates("") == {}


def test_load_templates_malformed_yaml_returns_empty(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("default: [unterminated")
    assert tts.load_templates(str(bad)) == {}


def test_load_templates_non_mapping_top_level_returns_empty(tmp_path):
    f = tmp_path / "list.yaml"
    f.write_text("- a\n- b\n")
    assert tts.load_templates(str(f)) == {}


def test_load_templates_skips_non_string_entries(tmp_path):
    f = tmp_path / "mixed.yaml"
    f.write_text('default: "ok"\nbad_key: 5\n123: "also bad"\n')
    assert tts.load_templates(str(f)) == {"default": "ok"}


def test_load_templates_without_pyyaml_returns_empty(tmp_path, monkeypatch):
    f = tmp_path / "templates.yaml"
    f.write_text('default: "ok"\n')
    monkeypatch.setattr(tts, "yaml", None)
    assert tts.load_templates(str(f)) == {}


@pytest.mark.skipif(getattr(os, "geteuid", lambda: 1)() == 0,
                    reason="root bypasses file permissions")
def test_load_templates_unreadable_file_returns_empty(tmp_path):
    f = tmp_path / "locked.yaml"
    f.write_text('default: "ok"\n')
    f.chmod(0o000)
    try:
        assert tts.load_templates(str(f)) == {}
    finally:
        f.chmod(0o644)


# ── TTSSpeaker (fake QTextToSpeech, no real speech engine) ──────────────────

class _FakeSignal:
    """Minimal stand-in for a pyqtSignal: connect() + emit()."""

    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class _FakeVoice:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


def _make_fake_engine(fail_construct=False, initial_state=None):
    """Build a fake QTextToSpeech class configured for one test scenario."""
    state_cls = _RealQTextToSpeech.State
    start_state = initial_state if initial_state is not None else state_cls.Ready

    class _FakeQTextToSpeech:
        State = state_cls
        instances = []

        def __init__(self, engine_name=None):
            if fail_construct:
                raise RuntimeError("boom")
            self.engine_name = engine_name
            self.stateChanged = _FakeSignal()
            self._state = start_state
            self._voices = [_FakeVoice("Alex"), _FakeVoice("Victoria")]
            self.said = []
            self.stopped = False
            self.rate = None
            self.volume = None
            self.voice_set = None
            _FakeQTextToSpeech.instances.append(self)

        def state(self):
            return self._state

        def setRate(self, rate):
            self.rate = rate

        def setVolume(self, volume):
            self.volume = volume

        def availableVoices(self):
            return self._voices

        def setVoice(self, voice):
            self.voice_set = voice

        def say(self, text):
            self.said.append(text)

        def stop(self):
            self.stopped = True

    return _FakeQTextToSpeech


def test_speaker_disabled_creates_no_engine(monkeypatch):
    fake_cls = _make_fake_engine()
    monkeypatch.setattr(tts, "QTextToSpeech", fake_cls)

    speaker = tts.TTSSpeaker(enabled=False)

    assert speaker._available is False
    assert fake_cls.instances == []
    speaker.speak("should not raise")   # no-op, must not raise
    speaker.stop()                      # no-op, must not raise


def test_speaker_available_when_engine_ready(monkeypatch):
    fake_cls = _make_fake_engine()
    monkeypatch.setattr(tts, "QTextToSpeech", fake_cls)

    speaker = tts.TTSSpeaker(enabled=True, rate=0.5, volume=0.8, voice="alex")

    assert speaker._available is True
    engine = fake_cls.instances[0]
    assert engine.rate == 0.5
    assert engine.volume == 0.8
    assert engine.voice_set.name() == "Alex"   # case-insensitive substring

    speaker.speak("hello")
    assert engine.said == ["hello"]

    speaker.stop()
    assert engine.stopped is True


def test_speaker_construction_failure_is_not_fatal(monkeypatch):
    fake_cls = _make_fake_engine(fail_construct=True)
    monkeypatch.setattr(tts, "QTextToSpeech", fake_cls)

    speaker = tts.TTSSpeaker(enabled=True)

    assert speaker._available is False
    speaker.speak("no engine")   # must not raise
    speaker.stop()               # must not raise


def test_speaker_bad_engine_name_is_not_fatal(monkeypatch):
    """A bad engine name fails synchronously (state is Error right away)."""
    fake_cls = _make_fake_engine(initial_state=_RealQTextToSpeech.State.Error)
    monkeypatch.setattr(tts, "QTextToSpeech", fake_cls)

    speaker = tts.TTSSpeaker(enabled=True, engine_name="doesnotexist")

    assert speaker._available is False
    speaker.speak("dropped")   # must not raise


def test_speaker_disables_on_async_error(monkeypatch):
    """A later stateChanged(Error) -- e.g. the plugin crashes -- disables speech."""
    fake_cls = _make_fake_engine()
    monkeypatch.setattr(tts, "QTextToSpeech", fake_cls)

    speaker = tts.TTSSpeaker(enabled=True)
    assert speaker._available is True
    engine = fake_cls.instances[0]

    engine.stateChanged.emit(_RealQTextToSpeech.State.Error)

    assert speaker._available is False
    speaker.speak("should be dropped")
    assert engine.said == []


def test_speaker_unknown_voice_keeps_engine_default(monkeypatch):
    fake_cls = _make_fake_engine()
    monkeypatch.setattr(tts, "QTextToSpeech", fake_cls)

    speaker = tts.TTSSpeaker(enabled=True, voice="does-not-exist")

    engine = fake_cls.instances[0]
    assert engine.voice_set is None
    assert speaker._available is True   # a missing voice is not fatal


# ── AWSPollySpeaker / _PollySynthesisThread (fake boto3 + QtMultimedia) ─────

class _FakeAudioStream:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data


class _FakePollyClient:
    """Stand-in for a boto3 Polly client -- no real network call."""

    def __init__(self, fail=False, fail_message="boom"):
        self.fail = fail
        self.fail_message = fail_message
        self.calls = []

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError(self.fail_message)
        return {"AudioStream": _FakeAudioStream(b"fake-mp3-bytes")}


class _FakeBoto3:
    """Stand-in for the boto3 module used by tts.py."""

    def __init__(self, client):
        self._client = client
        self.session_profile = None
        self.last_region = None

    def client(self, service_name, region_name=None):
        self.last_region = region_name
        return self._client

    def Session(self, profile_name=None):
        self.session_profile = profile_name
        return self   # Session.client() has the same shape as boto3.client()


class _FakeAudioOutput:
    def __init__(self):
        pass


class _FakeMediaPlayer:
    instances = []

    def __init__(self):
        self.errorOccurred = _FakeSignal()
        self.audio_output = None
        self.source_device = None
        self.played = False
        self.stopped = False
        _FakeMediaPlayer.instances.append(self)

    def setAudioOutput(self, output):
        self.audio_output = output

    def setSourceDevice(self, device):
        self.source_device = device

    def play(self):
        self.played = True
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_polly_thread_emits_synthesized_audio(qtbot):
    client = _FakePollyClient()
    thread = tts._PollySynthesisThread(client, voice="Joanna", engine="neural")
    thread.start()
    try:
        with qtbot.waitSignal(thread.synthesized, timeout=2000) as blocker:
            thread.speak("hello")
        assert blocker.args == [b"fake-mp3-bytes"]
        assert client.calls[-1] == {
            "Text": "hello", "OutputFormat": "mp3",
            "VoiceId": "Joanna", "Engine": "neural",
        }
    finally:
        thread.stop()


def test_polly_thread_emits_failed_on_exception(qtbot):
    client = _FakePollyClient(fail=True, fail_message="throttled")
    thread = tts._PollySynthesisThread(client, voice="Joanna", engine="neural")
    thread.start()
    try:
        with qtbot.waitSignal(thread.failed, timeout=2000) as blocker:
            thread.speak("hello")
        assert "throttled" in blocker.args[0]
    finally:
        thread.stop()


def test_polly_thread_survives_repeated_failures(qtbot):
    """A failed synthesis must not kill the worker thread."""
    client = _FakePollyClient(fail=True)
    thread = tts._PollySynthesisThread(client, voice="Joanna", engine="neural")
    thread.start()
    try:
        with qtbot.waitSignal(thread.failed, timeout=2000):
            thread.speak("first")
        client.fail = False
        with qtbot.waitSignal(thread.synthesized, timeout=2000):
            thread.speak("second")
    finally:
        thread.stop()


def test_polly_thread_stop_joins_cleanly(qtbot):
    client = _FakePollyClient()
    thread = tts._PollySynthesisThread(client, voice="Joanna", engine="neural")
    thread.start()
    thread.stop()
    assert thread.isRunning() is False


def test_polly_speaker_disabled_creates_no_client(monkeypatch):
    monkeypatch.setattr(tts, "boto3", _FakeBoto3(_FakePollyClient()))
    monkeypatch.setattr(tts, "QMediaPlayer", _FakeMediaPlayer)
    monkeypatch.setattr(tts, "QAudioOutput", _FakeAudioOutput)

    speaker = tts.AWSPollySpeaker(enabled=False)

    assert speaker._available is False
    speaker.speak("should not raise")
    speaker.stop()


def test_polly_speaker_without_boto3_is_unavailable(monkeypatch):
    monkeypatch.setattr(tts, "boto3", None)
    monkeypatch.setattr(tts, "QMediaPlayer", _FakeMediaPlayer)
    monkeypatch.setattr(tts, "QAudioOutput", _FakeAudioOutput)

    speaker = tts.AWSPollySpeaker(enabled=True)

    assert speaker._available is False
    speaker.speak("no boto3")   # must not raise
    speaker.stop()


def test_polly_speaker_client_construction_failure_is_not_fatal(monkeypatch):
    class _BrokenBoto3:
        def client(self, *a, **k):
            raise RuntimeError("no region")

    monkeypatch.setattr(tts, "boto3", _BrokenBoto3())
    monkeypatch.setattr(tts, "QMediaPlayer", _FakeMediaPlayer)
    monkeypatch.setattr(tts, "QAudioOutput", _FakeAudioOutput)

    speaker = tts.AWSPollySpeaker(enabled=True)

    assert speaker._available is False
    speaker.speak("no client")   # must not raise
    speaker.stop()


def test_polly_speaker_speaks_and_plays_audio(qtbot, monkeypatch):
    fake_client = _FakePollyClient()
    fake_boto3 = _FakeBoto3(fake_client)
    monkeypatch.setattr(tts, "boto3", fake_boto3)
    monkeypatch.setattr(tts, "QMediaPlayer", _FakeMediaPlayer)
    monkeypatch.setattr(tts, "QAudioOutput", _FakeAudioOutput)

    speaker = tts.AWSPollySpeaker(enabled=True, voice="Joanna", engine="neural",
                                   region="us-west-2")
    assert speaker._available is True
    assert fake_boto3.last_region == "us-west-2"

    speaker.speak("hello from polly")

    qtbot.waitUntil(lambda: _FakeMediaPlayer.instances[-1].played, timeout=2000)
    player = _FakeMediaPlayer.instances[-1]
    assert player.source_device is not None

    speaker.stop()
    assert player.stopped is True


def test_polly_speaker_uses_named_profile(monkeypatch):
    fake_client = _FakePollyClient()
    fake_boto3 = _FakeBoto3(fake_client)
    monkeypatch.setattr(tts, "boto3", fake_boto3)
    monkeypatch.setattr(tts, "QMediaPlayer", _FakeMediaPlayer)
    monkeypatch.setattr(tts, "QAudioOutput", _FakeAudioOutput)

    speaker = tts.AWSPollySpeaker(enabled=True, profile="andrew")

    assert speaker._available is True
    assert fake_boto3.session_profile == "andrew"
    speaker.stop()


# ── create_speaker() ─────────────────────────────────────────────────────────

def test_create_speaker_qt_backend(monkeypatch):
    monkeypatch.setattr(tts, "QTextToSpeech", _make_fake_engine())
    speaker = tts.create_speaker("qt", enabled=True)
    assert isinstance(speaker, tts.TTSSpeaker)


def test_create_speaker_aws_backend(monkeypatch):
    monkeypatch.setattr(tts, "boto3", _FakeBoto3(_FakePollyClient()))
    monkeypatch.setattr(tts, "QMediaPlayer", _FakeMediaPlayer)
    monkeypatch.setattr(tts, "QAudioOutput", _FakeAudioOutput)

    speaker = tts.create_speaker("aws", enabled=True, aws_voice="Joanna",
                                  aws_engine="neural")

    assert isinstance(speaker, tts.AWSPollySpeaker)
    speaker.stop()


def test_create_speaker_unknown_backend_falls_back_to_qt(monkeypatch):
    """config._choice() already restricts TTS_BACKEND, so this is defensive."""
    monkeypatch.setattr(tts, "QTextToSpeech", _make_fake_engine())
    speaker = tts.create_speaker("something-else", enabled=True)
    assert isinstance(speaker, tts.TTSSpeaker)
