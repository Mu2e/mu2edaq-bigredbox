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


class _StubApp:
    """DAQAlertApp's alert-dispatch logic without a QApplication or a socket.

    _show_alert only touches _windows and the throttle state, so binding the
    real methods to a stub lets the pause semantics be tested directly.
    """

    def __init__(self):
        from mu2edaq_bigredbox.daq_alert import DAQAlertApp
        self._windows = []
        self._last_accepted_time = 0.0
        self._show_alert = DAQAlertApp._show_alert.__get__(self)
        self._cls = DAQAlertApp

    @property
    def is_paused(self):
        from mu2edaq_bigredbox.daq_alert import DAQAlertApp
        return DAQAlertApp.is_paused.fget(self)


@pytest.fixture
def dispatcher(app, qtbot):
    stub = _StubApp()
    yield stub
    for window in list(stub._windows):
        qtbot.addWidget(window)


def _send(dispatcher, message=None):
    """Deliver an alert, clearing the rate limiter first."""
    dispatcher._last_accepted_time = 0.0
    dispatcher._show_alert(message or MESSAGE)


def test_pause_blocks_new_windows(dispatcher):
    """Regression for #10: a paused window must stop new windows opening."""
    _send(dispatcher)
    assert len(dispatcher._windows) == 1
    dispatcher._windows[0]._pause_cb.setChecked(True)

    _send(dispatcher, {**MESSAGE, "message": "arrived while paused"})

    assert len(dispatcher._windows) == 1, "a new window opened while paused"


def test_pause_blocks_updates_to_existing_windows(dispatcher):
    """Pause stops processing entirely, not just window creation."""
    _send(dispatcher)
    window = dispatcher._windows[0]
    window._pause_cb.setChecked(True)
    counter_before = window._counter_lbl.text()

    _send(dispatcher, {**MESSAGE, "message": "arrived while paused"})

    assert window._counter_lbl.text() == counter_before
    assert window._message_row.value_label.text() == MESSAGE["message"]
    assert len(window._history) == 1


def test_pause_is_global_across_windows(dispatcher):
    """Pausing any one window suppresses alerts for all of them."""
    _send(dispatcher)
    _send(dispatcher, {**MESSAGE, "message": "second"})
    assert len(dispatcher._windows) == 2

    dispatcher._windows[0]._pause_cb.setChecked(True)   # pause only the first
    assert dispatcher.is_paused is True

    _send(dispatcher, {**MESSAGE, "message": "should be suppressed"})

    assert dispatcher._windows[1]._message_row.value_label.text() == "second"


def test_unpausing_resumes_processing(dispatcher):
    _send(dispatcher)
    window = dispatcher._windows[0]
    window._pause_cb.setChecked(True)
    _send(dispatcher, {**MESSAGE, "message": "suppressed"})
    assert len(dispatcher._windows) == 1

    window._pause_cb.setChecked(False)
    _send(dispatcher, {**MESSAGE, "message": "after resuming"})

    assert len(dispatcher._windows) == 2
    assert dispatcher.is_paused is False


def test_closing_the_paused_window_resumes_processing(dispatcher, app):
    """Pause must not outlive the window that set it."""
    _send(dispatcher)
    window = dispatcher._windows[0]
    window._pause_cb.setChecked(True)
    assert dispatcher.is_paused is True

    dispatcher._windows.remove(window)   # what the destroyed handler does
    assert dispatcher.is_paused is False

    _send(dispatcher, {**MESSAGE, "message": "after the paused window closed"})
    assert len(dispatcher._windows) == 1


def test_listener_ignores_malformed_payloads(app, qtbot):
    """Regression for #8: a bad datagram must not kill the listener.

    json.loads returns str/int/list/None for well-formed JSON that is not an
    object; emitting one on pyqtSignal(dict) raised TypeError inside run(),
    which PyQt6 escalated to qFatal() -- the whole process aborted (SIGABRT).
    """
    import json as _json
    import socket

    thread = UDPListenerThread(port=0)
    port = thread._sock.getsockname()[1]
    received = []
    thread.message_received.connect(received.append)
    thread.start()

    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    hostile = [
        b'"just a string"',     # JSON string
        b"12345",               # JSON number
        b"[1, 2, 3]",           # JSON array
        b"null",                # JSON null
        b"true",                # JSON bool
        b"not json at all",     # invalid JSON
        b"\xff\xfe\x00",        # invalid UTF-8
    ]
    try:
        for raw in hostile:
            sender.sendto(raw, ("127.0.0.1", port))
        # A valid alert sent afterwards must still arrive, proving the thread
        # survived every one of the payloads above.
        sender.sendto(_json.dumps(MESSAGE).encode("utf-8"), ("127.0.0.1", port))
        qtbot.waitUntil(lambda: bool(received), timeout=5000)
    finally:
        sender.close()
        thread.stop()

    assert received == [MESSAGE]


@pytest.mark.parametrize("payload, expected_message", [
    ({"system_id": "A", "timestamp": "T", "message": 12345}, "12345"),
    ({"system_id": "A", "timestamp": "T", "message": {"k": "v"}}, "{'k': 'v'}"),
    ({"system_id": "A", "timestamp": "T", "message": ["a", "b"]}, "['a', 'b']"),
    ({"system_id": "A", "timestamp": "T", "message": None}, "(no message text)"),
    ({"system_id": "A", "timestamp": "T"}, "(no message text)"),
])
def test_alert_window_survives_non_string_fields(app, qtbot, payload, expected_message):
    """Regression for #9: non-string fields used to abort the process."""
    window = AlertWindow(payload)
    qtbot.addWidget(window)
    assert window._message_row.value_label.text() == expected_message


def test_update_message_survives_non_string_fields(app, qtbot):
    """#9 also reached QLabel.setText() via update_message()."""
    window = AlertWindow(MESSAGE)
    qtbot.addWidget(window)

    window.update_message({"system_id": 7, "timestamp": 1.5, "message": None})

    assert window._system_id_row.value_label.text() == "7"
    assert window._timestamp_row.value_label.text() == "1.5"
    assert window._message_row.value_label.text() == "(no message text)"


def test_history_dialog_survives_non_string_fields(app, qtbot):
    """#9 reached a third call site: the history entry labels."""
    dialog = HistoryDialog([{"system_id": 7, "timestamp": None, "message": {"k": 1}}])
    qtbot.addWidget(dialog)
    assert "1 message(s)" in dialog.windowTitle()


def test_field_text_coercion():
    from mu2edaq_bigredbox.daq_alert import field_text

    assert field_text({"k": "text"}, "k", "d") == "text"
    assert field_text({"k": 42}, "k", "d") == "42"
    assert field_text({"k": None}, "k", "d") == "d"      # null -> default
    assert field_text({}, "k", "d") == "d"               # absent -> default
    assert field_text({"k": ""}, "k", "d") == ""         # empty string kept


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
