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
