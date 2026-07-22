"""GUI smoke tests for the PyQt6 alert windows.

These run against the Qt "offscreen" platform plugin so they work on a headless
machine (CI, a node without DISPLAY).  Their main job is to catch the runtime
failures that the Qt5 -> Qt6 port can introduce: PyQt6 requires fully scoped
enums (Qt.AlignmentFlag.AlignLeft rather than Qt.AlignLeft), so a missed enum
raises AttributeError only when the widget is actually constructed.
"""

import os

import pytest

# Must be set before QApplication is created by the qapp fixture.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6", reason="PyQt6 is required for the GUI tests")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import mu2edaq_bigredbox  # noqa: E402
from mu2edaq_bigredbox.daq_alert import (  # noqa: E402
    AlertWindow,
    ClickableLabel,
    FieldRow,
    HistoryDialog,
    RedBanner,
    UDPListenerThread,
    discovery_metadata,
)

MESSAGE = {
    "system_id": "DAQ-NODE-01",
    "timestamp": "2026-07-22T09:15:00",
    "message": "Critical error in the data acquisition pipeline.",
}


@pytest.fixture
def app():
    """A QApplication shared by the tests in this module."""
    instance = QApplication.instance() or QApplication([])
    yield instance
    instance.processEvents()


def test_red_banner_constructs(app, qtbot):
    banner = RedBanner()
    qtbot.addWidget(banner)
    assert banner.height() == 110


def test_field_row_shows_value(app, qtbot):
    row = FieldRow("System ID", "DAQ-NODE-01")
    qtbot.addWidget(row)
    assert row.value_label.text() == "DAQ-NODE-01"


def test_clickable_label_emits_on_left_click(app, qtbot):
    label = ClickableLabel("click me")
    qtbot.addWidget(label)
    with qtbot.waitSignal(label.clicked, timeout=1000):
        qtbot.mouseClick(label, Qt.MouseButton.LeftButton)


def test_alert_window_builds_and_populates(app, qtbot):
    window = AlertWindow(MESSAGE)
    qtbot.addWidget(window)

    assert window.windowTitle() == "CRITICAL DAQ ERROR"
    assert window._system_id_row.value_label.text() == "DAQ-NODE-01"
    assert window._message_row.value_label.text() == MESSAGE["message"]
    assert window.is_paused is False
    # Window flags survive the Qt6 scoped-enum port.
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_alert_window_update_increments_counter(app, qtbot):
    window = AlertWindow(MESSAGE)
    qtbot.addWidget(window)

    window.update_message({**MESSAGE, "system_id": "DAQ-NODE-07"})

    assert window._system_id_row.value_label.text() == "DAQ-NODE-07"
    assert "2" in window._counter_lbl.text()
    assert len(window._history) == 2


def test_alert_window_pause_checkbox(app, qtbot):
    window = AlertWindow(MESSAGE)
    qtbot.addWidget(window)

    window._pause_cb.setChecked(True)
    assert window.is_paused is True


def test_history_dialog_lists_entries(app, qtbot):
    dialog = HistoryDialog([MESSAGE, {**MESSAGE, "system_id": "DAQ-NODE-02"}])
    qtbot.addWidget(dialog)
    assert "2 message(s)" in dialog.windowTitle()


def test_escape_closes_alert_window(app, qtbot):
    window = AlertWindow(MESSAGE)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    qtbot.keyClick(window, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=2000)


def test_discovery_metadata_reports_versions():
    """The DISCOVER reply carries the package and Qt runtime versions."""
    meta = discovery_metadata()

    assert meta["version"] == mu2edaq_bigredbox.__version__
    assert meta["qt"].startswith("6.")      # Qt6 after the PyQt5 migration
    assert meta["pyqt"].startswith("6.")
    assert meta["python"].count(".") == 2
    assert meta["udp_port"].isdigit()


def test_discovery_metadata_fits_in_a_datagram():
    """mu2edaq-discovery caps an announcement at 1400 bytes."""
    import json

    assert len(json.dumps(discovery_metadata()).encode("utf-8")) < 400
    assert all(isinstance(v, str) for v in discovery_metadata().values())


def test_listener_thread_start_stop(app):
    """The QThread subclass starts and stops cleanly under Qt6."""
    thread = UDPListenerThread(port=0)
    thread.start()
    thread.stop()
    assert not thread.isRunning()


def test_listener_raises_when_port_is_busy(app):
    """A second listener must fail loudly, not run without a socket.

    Regression test: the bind used to happen inside run(), so a port clash only
    produced a log line and left the application alive but deaf.
    """
    import socket

    holder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("", 0))
    port = holder.getsockname()[1]
    try:
        with pytest.raises(OSError):
            UDPListenerThread(port=port)
    finally:
        holder.close()

    # The failed attempt must not have leaked a bound socket: the port is free.
    probe = UDPListenerThread(port=port)
    probe.stop()


def test_second_instance_exits_with_port_in_use_status(tmp_path):
    """End-to-end: launching a second listener exits EXIT_PORT_IN_USE (3)."""
    import socket
    import subprocess
    import sys as _sys

    from mu2edaq_bigredbox.daq_alert import EXIT_PORT_IN_USE

    holder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("", 0))
    port = holder.getsockname()[1]

    env = dict(os.environ,
               CRS_PORT_UDP=str(port),
               QT_QPA_PLATFORM="offscreen")
    try:
        result = subprocess.run(
            [_sys.executable, "-m", "mu2edaq_bigredbox"],
            env=env, capture_output=True, text=True, timeout=60,
        )
    finally:
        holder.close()

    assert result.returncode == EXIT_PORT_IN_USE, result.stderr
    assert "already running" in result.stderr
