"""Cross-platform / Windows compatibility tests.

Added in the windows-compat sweep. These lock in the fixes that let the alert
daemon and its launch scripts work on Windows as well as POSIX:

* config paths default under the platform temp dir (not a hard-coded /tmp),
* the environment overrides still win (and blank overrides fall back), and
* every standardized control-room shell script ships a PowerShell port.
"""
import importlib
import os
import socket
import tempfile
from pathlib import Path

import mu2edaq_bigredbox.config as config

REPO = Path(__file__).resolve().parent.parent


def test_default_paths_live_under_platform_tempdir():
    tmp = tempfile.gettempdir()
    assert config.DEFAULT_PID_FILE == os.path.join(tmp, "daq_alert.pid")
    assert config.DEFAULT_LOG_FILE == os.path.join(tmp, "daq_alert.log")


def test_no_hardcoded_posix_tmp_default():
    # On Windows tempfile.gettempdir() is %TEMP%, never "/tmp"; guard against a
    # regression that reintroduces a literal POSIX path.
    if os.name == "nt":
        assert not config.DEFAULT_PID_FILE.startswith("/tmp")
        assert not config.DEFAULT_LOG_FILE.startswith("/tmp")


def test_pid_and_log_env_overrides_win(monkeypatch):
    pid = os.path.join(tempfile.gettempdir(), "custom_bb.pid")
    log = os.path.join(tempfile.gettempdir(), "custom_bb.log")
    monkeypatch.setenv("DAQ_ALERT_PID_FILE", pid)
    monkeypatch.setenv("DAQ_ALERT_LOG_FILE", log)
    reloaded = importlib.reload(config)
    try:
        assert reloaded.PID_FILE == pid
        assert reloaded.LOG_FILE == log
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_blank_env_override_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("DAQ_ALERT_PID_FILE", "   ")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.PID_FILE == reloaded.DEFAULT_PID_FILE
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_exclusive_bind_option_is_available_where_expected():
    # The listener uses SO_EXCLUSIVEADDRUSE on Windows so a second bind raises;
    # on POSIX it uses SO_REUSEADDR. Assert the option the platform relies on
    # actually exists in the socket module.
    if os.name == "nt":
        assert hasattr(socket, "SO_EXCLUSIVEADDRUSE")
    else:
        assert hasattr(socket, "SO_REUSEADDR")


def test_every_control_room_shell_script_has_a_powershell_port():
    for stem in ("bootstrap", "start-mu2edaq-bigredbox", "stop-mu2edaq-bigredbox"):
        assert (REPO / f"{stem}.sh").is_file(), f"missing shell script: {stem}.sh"
        assert (REPO / f"{stem}.ps1").is_file(), f"missing PowerShell port: {stem}.ps1"
