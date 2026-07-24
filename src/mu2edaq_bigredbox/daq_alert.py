#!/usr/bin/env python3
"""
DAQ Alert Listener - Listens for broadcast critical error messages and
displays a prominent alert window via PyQt6.

Compatible with Python 3.9+
"""

import sys
import json
import socket
import signal
import os
import logging
import time
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect,
    QScrollArea, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QT_VERSION_STR, PYQT_VERSION_STR
from PyQt6.QtGui import QFont, QColor, QLinearGradient, QPainter, QBrush

from . import __version__
from .config import BROADCAST_PORT, PID_FILE, LOG_FILE, MESSAGE_RATE_LIMIT, MAX_ALERT_WINDOWS


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

try:
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                        format=_LOG_FORMAT)
    _log_fallback = None
except OSError as _exc:
    # The default log path lives in /tmp and is shared by every user on the
    # machine, so it is routinely owned by whoever started the listener first.
    # Losing the log must not stop DAQ alerting: fall back to stderr and say
    # why, rather than dying at import with a bare PermissionError.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format=_LOG_FORMAT)
    _log_fallback = _exc

log = logging.getLogger(__name__)

if _log_fallback is not None:
    log.warning("Cannot write %s (%s); logging to stderr instead. "
                "Set DAQ_ALERT_LOG_FILE to choose another path.",
                LOG_FILE, _log_fallback)


# Exit status used when the UDP port is already taken, i.e. another listener
# is running.  Distinct from 1 so the control room can tell the two apart.
EXIT_PORT_IN_USE = 3

PORT_CHECK_HINT = "lsof -nP -iUDP:%d" % BROADCAST_PORT


# ── Colours & typography ───────────────────────────────────────────────────────
CLR_BG          = "#0D0D0D"   # near-black background
CLR_PANEL       = "#1A1A1A"   # card surface
CLR_RED         = "#E82020"   # primary red
CLR_RED_DARK    = "#A01010"   # darker red for gradient
CLR_RED_GLOW    = "#FF3333"   # glow / highlight
CLR_AMBER       = "#FFB800"   # warning amber for the icon
CLR_TEXT        = "#FFFFFF"   # primary text
CLR_MUTED       = "#8A8A8A"   # secondary label text
CLR_DIVIDER     = "#2E2E2E"   # subtle divider
CLR_BTN_BG      = "#E82020"
CLR_BTN_HOVER   = "#FF3A3A"
CLR_BTN_PRESS   = "#B01818"


# ── Discovery metadata ─────────────────────────────────────────────────────────
def discovery_metadata() -> dict:
    """Extra version detail reported in reply to a discovery DISCOVER request.

    The package version itself is sent as the announcement's `version` field;
    this fills the `meta` map with the runtime versions an operator needs when
    a node misbehaves.  Values are kept short: mu2edaq-discovery caps a
    datagram at 1400 bytes.
    """
    return {
        "version": __version__,
        "qt": QT_VERSION_STR,
        "pyqt": PYQT_VERSION_STR,
        "python": "%d.%d.%d" % sys.version_info[:3],
        "udp_port": str(BROADCAST_PORT),
    }


# ── Payload field access ───────────────────────────────────────────────────────
def field_text(data: dict, key: str, default: str) -> str:
    """Return ``data[key]`` as text that Qt will accept.

    dict.get() only substitutes the default when the key is *absent*, so a
    sender that puts a number or a nested object in `message` hands a non-str
    straight to QLabel, which raises TypeError.  Inside a slot PyQt6 turns that
    into qFatal() and the application dies.  Showing a stringified value is
    always better than losing the alert window.
    """
    value = data.get(key, default)
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


# ── Clickable label ────────────────────────────────────────────────────────────
class ClickableLabel(QLabel):
    """A QLabel that emits clicked() when left-clicked."""

    clicked = pyqtSignal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ── UDP listener thread ────────────────────────────────────────────────────────
class UDPListenerThread(QThread):
    """Background thread that listens for UDP broadcast messages.

    The socket is bound in the constructor, on the calling thread, so a port
    conflict raises OSError immediately.  Binding inside run() instead would
    only log the failure from a background thread and leave the application
    running with a dead listener — a Big Red Box that can never turn red.
    """

    message_received = pyqtSignal(dict)

    def __init__(self, port: int = BROADCAST_PORT):
        super().__init__()
        self.port = port
        self._running = True

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.settimeout(1.0)
        try:
            self._sock.bind(("", port))
        except OSError:
            self._sock.close()
            raise
        log.info("Listening for broadcast messages on port %d", self.port)

    def run(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(65535)
                log.info("Received message from %s", addr)
                try:
                    payload = json.loads(data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    log.warning("Could not parse message from %s: %s", addr, exc)
                    continue
                # json.loads happily returns str/int/list/None for well-formed
                # JSON that is not an object.  message_received is
                # pyqtSignal(dict), and emitting the wrong type raises
                # TypeError here — which PyQt6 escalates to qFatal(), killing
                # the process.  A bad datagram must never do that.
                if not isinstance(payload, dict):
                    log.warning("Ignoring non-object payload from %s: %r",
                                addr, payload)
                    continue
                self.message_received.emit(payload)
            except socket.timeout:
                continue
            except OSError as exc:
                if self._running:
                    log.error("Socket error: %s", exc)
                break
            except Exception:
                # Last line of defence: an exception escaping run() aborts the
                # whole application under PyQt6, taking DAQ alerting with it.
                # Losing one datagram is always preferable.
                log.exception("Unexpected error handling a datagram; ignoring it")

        self._sock.close()
        log.info("UDP listener stopped")

    def stop(self):
        self._running = False
        self.wait(3000)
        # If the thread was never started, run() never closed the socket.
        self._sock.close()


# ── Gradient banner widget ─────────────────────────────────────────────────────
class RedBanner(QWidget):
    """Top banner: left-to-right red gradient with the alert title."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(40, 0, 40, 0)
        layout.setSpacing(22)

        icon = QLabel("⬛")          # placeholder; replaced by paintEvent gradient
        icon_lbl = QLabel("⚠")
        icon_lbl.setFont(QFont("Arial", 36, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color: {CLR_AMBER}; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        title = QLabel("CRITICAL DAQ ERROR")
        title.setFont(QFont("Arial", 34, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color: {CLR_TEXT}; background: transparent; letter-spacing: 6px;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(icon_lbl)
        layout.addWidget(title, stretch=1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0.0, QColor(CLR_RED))
        gradient.setColorAt(0.6, QColor(CLR_RED_DARK))
        gradient.setColorAt(1.0, QColor(CLR_PANEL))
        painter.fillRect(self.rect(), QBrush(gradient))
        super().paintEvent(event)


# ── Field row ──────────────────────────────────────────────────────────────────
class FieldRow(QWidget):
    """A label + value pair used in the detail section."""

    def __init__(self, field: str, value: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(field.upper())
        label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {CLR_MUTED}; letter-spacing: 3px; background: transparent;")

        self.value_label = QLabel(value)
        self.value_label.setFont(QFont("Arial", 17))
        self.value_label.setStyleSheet(f"color: {CLR_TEXT}; background: transparent;")
        self.value_label.setWordWrap(True)
        self.value_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout.addWidget(label)
        layout.addWidget(self.value_label)


# ── Alert window ───────────────────────────────────────────────────────────────
class AlertWindow(QWidget):
    """Modern dark alert window displayed when a critical message arrives."""

    def __init__(self, message_data: dict):
        super().__init__()
        self._error_count = 0
        self._history: list = []
        self._history_dialog = None
        self._build_ui(message_data)

    def _build_ui(self, data: dict):
        system_id = field_text(data, "system_id", "UNKNOWN")
        timestamp = field_text(data, "timestamp", "UNKNOWN")
        message   = field_text(data, "message",   "(no message text)")

        self.setWindowTitle("CRITICAL DAQ ERROR")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(860, 530)
        self.setStyleSheet(f"background-color: {CLR_BG};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Red gradient banner ──
        banner = RedBanner()
        outer.addWidget(banner)

        # ── Card body ──
        body = QWidget()
        body.setStyleSheet(f"""
            QWidget {{
                background-color: {CLR_PANEL};
                border-left: 1px solid {CLR_DIVIDER};
                border-right: 1px solid {CLR_DIVIDER};
            }}
        """)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(48, 36, 48, 36)
        body_layout.setSpacing(22)

        # Top thin red accent line
        accent = QFrame()
        accent.setFixedHeight(3)
        accent.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                             f"stop:0 {CLR_RED_GLOW}, stop:0.5 {CLR_RED}, stop:1 transparent);"
                             f"border: none;")
        body_layout.addWidget(accent)
        body_layout.addSpacing(8)

        # Detail fields
        self._system_id_row  = FieldRow("System ID",    system_id)
        self._timestamp_row  = FieldRow("Timestamp",    timestamp)
        self._message_row    = FieldRow("Error Message", message)
        body_layout.addWidget(self._system_id_row)
        body_layout.addWidget(self._divider())
        body_layout.addWidget(self._timestamp_row)
        body_layout.addWidget(self._divider())
        body_layout.addWidget(self._message_row)
        body_layout.addStretch(1)

        outer.addWidget(body, stretch=1)

        # ── Footer ──
        footer = QWidget()
        footer.setFixedHeight(90)
        footer.setStyleSheet(f"background-color: {CLR_BG};")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(48, 0, 48, 0)

        hint = QLabel("Press  Enter / Esc  or click to dismiss")
        hint.setFont(QFont("Arial", 11))
        hint.setStyleSheet(f"color: {CLR_MUTED}; background: transparent;")

        self._pause_cb = QCheckBox("Pause")
        self._pause_cb.setFont(QFont("Arial", 11))
        self._pause_cb.setToolTip(
            "Suppress all incoming alerts while ticked — no new windows open "
            "and no existing window updates. Untick, or close this window, to "
            "resume."
        )
        self._pause_cb.setStyleSheet(f"""
            QCheckBox {{
                color: {CLR_MUTED};
                background: transparent;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {CLR_MUTED};
                border-radius: 3px;
                background: transparent;
            }}
            QCheckBox::indicator:checked {{
                background-color: {CLR_RED};
                border-color: {CLR_RED};
            }}
        """)

        self._history.append(data)
        self._error_count += 1
        self._counter_lbl = ClickableLabel(f"Errors Received:  {self._error_count}")
        self._counter_lbl.setFont(QFont("Arial", 11))
        self._counter_lbl.setStyleSheet(
            f"color: {CLR_MUTED}; background: transparent; text-decoration: underline;"
        )
        self._counter_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._counter_lbl.setToolTip("Click to view error history")
        self._counter_lbl.clicked.connect(self._show_history)

        btn = QPushButton("ACKNOWLEDGE")
        btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        btn.setFixedSize(200, 46)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CLR_BTN_BG};
                color: {CLR_TEXT};
                border: none;
                border-radius: 4px;
                letter-spacing: 2px;
            }}
            QPushButton:hover  {{ background-color: {CLR_BTN_HOVER}; }}
            QPushButton:pressed {{ background-color: {CLR_BTN_PRESS}; }}
        """)

        # Drop-shadow on button
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(CLR_RED_GLOW))
        shadow.setOffset(0, 0)
        btn.setGraphicsEffect(shadow)

        btn.clicked.connect(self.close)
        footer_layout.addWidget(hint)
        footer_layout.addSpacing(24)
        footer_layout.addWidget(self._pause_cb)
        footer_layout.addStretch()
        footer_layout.addWidget(self._counter_lbl)
        footer_layout.addSpacing(32)
        footer_layout.addWidget(btn)

        outer.addWidget(footer)

        self._center_on_screen()

    @staticmethod
    def _divider() -> QFrame:
        d = QFrame()
        d.setFrameShape(QFrame.Shape.HLine)
        d.setFixedHeight(1)
        d.setStyleSheet(f"background: {CLR_DIVIDER}; border: none;")
        return d

    def _center_on_screen(self):
        # QDesktopWidget was removed in Qt6; use the screen this window is on,
        # falling back to the primary screen before the window is shown.
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        geo = self.frameGeometry()
        geo.moveCenter(screen.availableGeometry().center())
        self.move(geo.topLeft())

    @property
    def is_paused(self) -> bool:
        return self._pause_cb.isChecked()

    def update_message(self, data: dict):
        """Replace displayed fields with new message data and increment the counter."""
        self._history.append(data)
        self._system_id_row.value_label.setText(field_text(data, "system_id", "UNKNOWN"))
        self._timestamp_row.value_label.setText(field_text(data, "timestamp", "UNKNOWN"))
        self._message_row.value_label.setText(
            field_text(data, "message", "(no message text)"))
        self._error_count += 1
        self._counter_lbl.setText(f"Errors Received:  {self._error_count}")
        # Update the open history dialog in place if it is visible
        if self._history_dialog is not None:
            self._history_dialog.refresh(self._history)
        self.raise_()
        self.activateWindow()

    def _show_history(self):
        if self._history_dialog is not None:
            self._history_dialog.raise_()
            self._history_dialog.activateWindow()
            return
        self._open_history_dialog()

    def _open_history_dialog(self):
        dialog = HistoryDialog(self._history, parent=self)
        self._history_dialog = dialog
        # Clear the reference only if it still points at *this* dialog: widget
        # deletion is deferred, so a stale destroyed signal must not wipe out a
        # newer dialog. Bound as a default argument so the slot never touches a
        # cleared closure cell.
        dialog.destroyed.connect(lambda *_, d=dialog: self._forget_history_dialog(d))
        dialog.show()
        dialog.raise_()

    def _forget_history_dialog(self, dialog):
        """Runs as a Qt slot during widget destruction; must never raise."""
        if self._history_dialog is dialog:
            self._history_dialog = None

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.close()


# ── History dialog ─────────────────────────────────────────────────────────────
class HistoryDialog(QWidget):
    """Scrollable list of all messages received by one AlertWindow."""

    def __init__(self, history: list, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(f"Error History  —  {len(history)} message(s)")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(720, 520)
        self.setStyleSheet(f"background-color: {CLR_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(64)
        header.setStyleSheet(f"background-color: {CLR_PANEL}; border-bottom: 1px solid {CLR_DIVIDER};")
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(32, 0, 32, 0)
        self._title_lbl = QLabel()
        self._title_lbl.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {CLR_TEXT}; background: transparent;")
        hdr_layout.addWidget(self._title_lbl)
        layout.addWidget(header)

        # Scrollable entries (newest first)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {CLR_BG}; }}")

        container = QWidget()
        container.setStyleSheet(f"background: {CLR_BG};")
        self._entry_layout = QVBoxLayout(container)
        self._entry_layout.setContentsMargins(32, 24, 32, 24)
        self._entry_layout.setSpacing(12)
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self.refresh(history)

    def refresh(self, history: list):
        """Rebuild the entry list in place for an updated history.

        Updating the open dialog avoids closing and reopening it, which reset
        the window position and scroll offset — and raced with the old
        dialog's destroyed signal, clearing the reference to the new one.
        """
        title = f"Error History  —  {len(history)} message(s)"
        self.setWindowTitle(title)
        self._title_lbl.setText(title)

        while self._entry_layout.count():
            item = self._entry_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for idx, msg in enumerate(reversed(history), 1):
            self._entry_layout.addWidget(
                self._make_entry(len(history) - idx + 1, msg))
        self._entry_layout.addStretch()

    def _make_entry(self, index: int, data: dict) -> QWidget:
        entry = QWidget()
        entry.setStyleSheet(
            f"background: {CLR_PANEL}; border-radius: 4px; border: 1px solid {CLR_DIVIDER};"
        )
        e_layout = QVBoxLayout(entry)
        e_layout.setContentsMargins(20, 14, 20, 14)
        e_layout.setSpacing(8)

        num_lbl = QLabel(f"#{index}")
        num_lbl.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        num_lbl.setStyleSheet(f"color: {CLR_RED}; background: transparent; letter-spacing: 2px;")
        e_layout.addWidget(num_lbl)

        for field, key in (("System ID", "system_id"), ("Timestamp", "timestamp"), ("Message", "message")):
            row = QHBoxLayout()
            row.setSpacing(12)
            lbl = QLabel(field.upper())
            lbl.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {CLR_MUTED}; background: transparent; letter-spacing: 2px;")
            lbl.setFixedWidth(110)
            lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
            val = QLabel(field_text(data, key, "UNKNOWN"))
            val.setFont(QFont("Arial", 13))
            val.setStyleSheet(f"color: {CLR_TEXT}; background: transparent;")
            val.setWordWrap(True)
            row.addWidget(lbl)
            row.addWidget(val, stretch=1)
            e_layout.addLayout(row)

        return entry

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return):
            self.close()


# ── Application controller ─────────────────────────────────────────────────────
class DAQAlertApp:
    """Manages the Qt event loop and the UDP listener thread."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self._windows: list = []   # keep references so windows aren't GC'd
        self._last_accepted_time: float = 0.0

        # Bind before anything else claims to be running.  A busy port means
        # another listener already owns it, so refuse to start a second one
        # rather than sitting here unable to receive alerts.
        try:
            self.listener = UDPListenerThread(port=BROADCAST_PORT)
        except OSError as exc:
            log.critical("Cannot listen on UDP port %d: %s", BROADCAST_PORT, exc)
            log.critical("A DAQ Alert listener is probably already running; "
                         "not starting a second one.")
            print("error: cannot listen on UDP port %d: %s" % (BROADCAST_PORT, exc),
                  file=sys.stderr)
            print("error: a DAQ Alert listener is probably already running "
                  "(check with: %s)" % PORT_CHECK_HINT, file=sys.stderr)
            raise SystemExit(EXIT_PORT_IN_USE)

        self.listener.message_received.connect(self._show_alert)
        self.listener.start()

        # Mu2e DAQ service discovery: advertise the UDP alert port so the app
        # appears in mu2edaq-discover scans and the control room browser.
        # Best-effort so a missing package never blocks startup.
        self._responder = None
        try:
            from mu2edaq_discovery import Responder
            self._responder = Responder(name="Big Red Box Alerts",
                                        app="bigredbox",
                                        port=BROADCAST_PORT, scheme="udp",
                                        version=__version__,
                                        meta=discovery_metadata())
            self._responder.start()
        except Exception as exc:
            log.warning("Discovery responder not started: %s", exc)

        # Allow Python signal handlers to fire inside the Qt event loop
        self._signal_timer = QTimer()
        self._signal_timer.setInterval(500)
        self._signal_timer.timeout.connect(lambda: None)
        self._signal_timer.start()

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT,  self._handle_signal)

        self._write_pid()
        log.info("DAQ Alert application started (PID %d)", os.getpid())

    def _write_pid(self):
        """Record the pid, but never let a bookkeeping file stop alerting.

        We already own the UDP port by this point, so this process *is* the
        listener.  If the pid file is unwritable (typically another operator's
        file in /tmp) carry on without it: stop-mu2edaq-bigredbox.sh falls back
        to the process holding the port, so the daemon can still be stopped.
        """
        try:
            with open(PID_FILE, "w") as fh:
                fh.write(str(os.getpid()))
        except OSError as exc:
            log.error("Cannot write pid file %s (%s); continuing without it. "
                      "Set DAQ_ALERT_PID_FILE to choose another path.",
                      PID_FILE, exc)
            print("warning: cannot write pid file %s: %s" % (PID_FILE, exc),
                  file=sys.stderr)

    @property
    def is_paused(self) -> bool:
        """True while any open alert window has Pause ticked.

        Pause is deliberately global rather than per-window: ticking it on one
        window is the operator saying "stop interrupting me", so it must also
        keep new windows from opening.
        """
        return any(window.is_paused for window in self._windows)

    def _show_alert(self, message_data: dict):
        # ── Pause ─────────────────────────────────────────────────────────────
        # Checked before the throttle so a paused period does not consume the
        # rate-limit budget of the first alert that arrives after resuming.
        if self.is_paused:
            log.info("Paused; dropping message: %s", message_data)
            return

        # ── Throttle ──────────────────────────────────────────────────────────
        now = time.monotonic()
        min_interval = 1.0 / MESSAGE_RATE_LIMIT
        if now - self._last_accepted_time < min_interval:
            log.info(
                "Throttling message (rate limit %.1f msg/s): %s",
                MESSAGE_RATE_LIMIT, message_data,
            )
            return
        self._last_accepted_time = now

        log.info("Displaying alert: %s", message_data)

        # ── Window cap ────────────────────────────────────────────────────────
        if len(self._windows) >= MAX_ALERT_WINDOWS:
            # Nothing is paused (checked above), so update the newest window.
            self._windows[-1].update_message(message_data)
            log.info("Max windows reached; updated existing window")
            return

        window = AlertWindow(message_data)
        self._windows.append(window)
        # Remove from the list once the window is destroyed so it can be freed
        # and so a paused window stops suppressing alerts when it closes.
        #
        # The window is bound as a default argument rather than captured as a
        # free variable: when the widget is destroyed during garbage collection
        # this frame's cell may already have been cleared, and the resulting
        # NameError inside a slot is fatal under PyQt6.
        window.destroyed.connect(lambda *_, w=window: self._forget_window(w))
        window.show()
        window.raise_()
        window.activateWindow()

    def _forget_window(self, window):
        """Drop a destroyed window. Must never raise: it runs as a Qt slot."""
        try:
            self._windows.remove(window)
        except ValueError:
            pass

    def _handle_signal(self, signum, frame):
        log.info("Received signal %d, shutting down", signum)
        self._shutdown()

    def _shutdown(self):
        self.listener.stop()
        if self._responder is not None:
            self._responder.stop()
        self._remove_pid()
        self.app.quit()

    def _remove_pid(self):
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        except OSError as exc:
            # Runs during shutdown; a permission problem here must not turn a
            # clean exit into a traceback.
            log.warning("Could not remove pid file %s: %s", PID_FILE, exc)

    def run(self) -> int:
        exit_code = self.app.exec()
        self._shutdown()
        return exit_code


def main():
    app = DAQAlertApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
