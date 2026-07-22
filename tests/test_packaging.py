"""Smoke tests for the mu2edaq-bigredbox package build.

These deliberately avoid importing mu2edaq_bigredbox.daq_alert, which pulls in
PyQt5 and needs a display; the GUI is exercised manually with
mu2edaq-bigredbox-send.
"""

import json
import socket

import pytest

import mu2edaq_bigredbox
from mu2edaq_bigredbox import config, demo_sender


def test_version_is_exposed():
    assert mu2edaq_bigredbox.__version__


def test_default_broadcast_port():
    assert isinstance(config.BROADCAST_PORT, int)
    assert 0 < config.BROADCAST_PORT < 65536


def test_port_honours_crs_port_udp(monkeypatch):
    import importlib

    monkeypatch.setenv("CRS_PORT_UDP", "37031")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.BROADCAST_PORT == 37031
    finally:
        monkeypatch.delenv("CRS_PORT_UDP", raising=False)
        importlib.reload(config)


def test_send_alert_emits_expected_payload():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rx:
        rx.bind(("127.0.0.1", 0))
        rx.settimeout(2.0)
        port = rx.getsockname()[1]

        demo_sender.send_alert("DAQ-NODE-TEST", "unit test alert",
                               broadcast_ip="127.0.0.1", port=port)

        data, _ = rx.recvfrom(4096)

    payload = json.loads(data.decode("utf-8"))
    assert payload["system_id"] == "DAQ-NODE-TEST"
    assert payload["message"] == "unit test alert"
    assert payload["timestamp"]


@pytest.mark.parametrize("script", ["mu2edaq-bigredbox", "mu2edaq-bigredbox-send"])
def test_console_scripts_are_registered(script):
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover - Python < 3.8
        pytest.skip("importlib.metadata unavailable")

    eps = entry_points()
    # Python 3.9 returns a dict; 3.10+ supports select().
    console = eps.select(group="console_scripts") if hasattr(eps, "select") \
        else eps.get("console_scripts", [])
    assert script in {ep.name for ep in console}
