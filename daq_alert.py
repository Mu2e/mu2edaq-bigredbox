#!/usr/bin/env python3
"""
DAQ Alert Listener - Listens for broadcast critical error messages and
displays a prominent alert window via PyQt5.

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

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect,
    QScrollArea, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QLinearGradient, QPainter, QPalette, QBrush

from config import BROADCAST_PORT, PID_FILE, LOG_FILE, MESSAGE_RATE_LIMIT, MAX_ALERT_WINDOWS


logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


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


# ── Clickable label ────────────────────────────────────────────────────────────
class ClickableLabel(QLabel):
    """A QLabel that emits clicked() when left-clicked."""

    clicked = pyqtSignal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ── UDP listener thread ────────────────────────────────────────────────────────
class UDPListenerThread(QThread):
    """Background thread that listens for UDP broadcast messages."""

    message_received = pyqtSignal(dict)

    def __init__(self, port: int = BROADCAST_PORT):
        super().__init__()
        self.port = port
        self._running = True

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
            sock.bind(("", self.port))
            log.info("Listening for broadcast messages on port %d", self.port)
        except OSError as exc:
            log.error("Failed to bind UDP socket: %s", exc)
            return

        while self._running:
            try:
                data, addr = sock.recvfrom(65535)
                log.info("Received message from %s", addr)
                try:
                    payload = json.loads(data.decode("utf-8"))
                    self.message_received.emit(payload)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    log.warning("Could not parse message from %s: %s", addr, exc)
            except socket.timeout:
                continue
            except OSError as exc:
                if self._running:
                    log.error("Socket error: %s", exc)
                break

        sock.close()
        log.info("UDP listener stopped")

    def stop(self):
        self._running = False
        self.wait(3000)


# ── Gradient banner widget ─────────────────────────────────────────────────────
class RedBanner(QWidget):
    """Top banner: left-to-right red gradient with the alert title."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(40, 0, 40, 0)
        layout.setSpacing(22)

        icon = QLabel("⬛")          # placeholder; replaced by paintEvent gradient
        icon_lbl = QLabel("⚠")
        icon_lbl.setFont(QFont("Arial", 36, QFont.Bold))
        icon_lbl.setStyleSheet(f"color: {CLR_AMBER}; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignVCenter)

        title = QLabel("CRITICAL DAQ ERROR")
        title.setFont(QFont("Arial", 34, QFont.Bold))
        title.setStyleSheet(
            f"color: {CLR_TEXT}; background: transparent; letter-spacing: 6px;"
        )
        title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        layout.addWidget(icon_lbl)
        layout.addWidget(title, stretch=1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
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
        label.setFont(QFont("Courier New", 10, QFont.Bold))
        label.setStyleSheet(f"color: {CLR_MUTED}; letter-spacing: 3px; background: transparent;")

        self.value_label = QLabel(value)
        self.value_label.setFont(QFont("Arial", 17))
        self.value_label.setStyleSheet(f"color: {CLR_TEXT}; background: transparent;")
        self.value_label.setWordWrap(True)
        self.value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

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
        system_id = data.get("system_id", "UNKNOWN")
        timestamp = data.get("timestamp", "UNKNOWN")
        message   = data.get("message",   "(no message text)")

        self.setWindowTitle("CRITICAL DAQ ERROR")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
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
        self._counter_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self._counter_lbl.setToolTip("Click to view error history")
        self._counter_lbl.clicked.connect(self._show_history)

        btn = QPushButton("ACKNOWLEDGE")
        btn.setFont(QFont("Arial", 14, QFont.Bold))
        btn.setFixedSize(200, 46)
        btn.setCursor(Qt.PointingHandCursor)
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
        d.setFrameShape(QFrame.HLine)
        d.setFixedHeight(1)
        d.setStyleSheet(f"background: {CLR_DIVIDER}; border: none;")
        return d

    def _center_on_screen(self):
        from PyQt5.QtWidgets import QDesktopWidget
        geo = self.frameGeometry()
        geo.moveCenter(QDesktopWidget().availableGeometry().center())
        self.move(geo.topLeft())

    @property
    def is_paused(self) -> bool:
        return self._pause_cb.isChecked()

    def update_message(self, data: dict):
        """Replace displayed fields with new message data and increment the counter."""
        self._history.append(data)
        self._system_id_row.value_label.setText(data.get("system_id", "UNKNOWN"))
        self._timestamp_row.value_label.setText(data.get("timestamp", "UNKNOWN"))
        self._message_row.value_label.setText(data.get("message", "(no message text)"))
        self._error_count += 1
        self._counter_lbl.setText(f"Errors Received:  {self._error_count}")
        # Refresh the open history dialog if it is visible
        if self._history_dialog is not None:
            self._history_dialog.close()
            self._open_history_dialog()
        self.raise_()
        self.activateWindow()

    def _show_history(self):
        if self._history_dialog is not None:
            self._history_dialog.raise_()
            self._history_dialog.activateWindow()
            return
        self._open_history_dialog()

    def _open_history_dialog(self):
        self._history_dialog = HistoryDialog(self._history, parent=self)
        self._history_dialog.destroyed.connect(lambda: setattr(self, "_history_dialog", None))
        self._history_dialog.show()
        self._history_dialog.raise_()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Space):
            self.close()


# ── History dialog ─────────────────────────────────────────────────────────────
class HistoryDialog(QWidget):
    """Scrollable list of all messages received by one AlertWindow."""

    def __init__(self, history: list, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle(f"Error History  —  {len(history)} message(s)")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
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
        title_lbl = QLabel(f"Error History  —  {len(history)} message(s)")
        title_lbl.setFont(QFont("Arial", 15, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {CLR_TEXT}; background: transparent;")
        hdr_layout.addWidget(title_lbl)
        layout.addWidget(header)

        # Scrollable entries (newest first)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {CLR_BG}; }}")

        container = QWidget()
        container.setStyleSheet(f"background: {CLR_BG};")
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(32, 24, 32, 24)
        c_layout.setSpacing(12)

        for idx, msg in enumerate(reversed(history), 1):
            c_layout.addWidget(self._make_entry(len(history) - idx + 1, msg))

        c_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _make_entry(self, index: int, data: dict) -> QWidget:
        entry = QWidget()
        entry.setStyleSheet(
            f"background: {CLR_PANEL}; border-radius: 4px; border: 1px solid {CLR_DIVIDER};"
        )
        e_layout = QVBoxLayout(entry)
        e_layout.setContentsMargins(20, 14, 20, 14)
        e_layout.setSpacing(8)

        num_lbl = QLabel(f"#{index}")
        num_lbl.setFont(QFont("Courier New", 10, QFont.Bold))
        num_lbl.setStyleSheet(f"color: {CLR_RED}; background: transparent; letter-spacing: 2px;")
        e_layout.addWidget(num_lbl)

        for field, key in (("System ID", "system_id"), ("Timestamp", "timestamp"), ("Message", "message")):
            row = QHBoxLayout()
            row.setSpacing(12)
            lbl = QLabel(field.upper())
            lbl.setFont(QFont("Courier New", 9, QFont.Bold))
            lbl.setStyleSheet(f"color: {CLR_MUTED}; background: transparent; letter-spacing: 2px;")
            lbl.setFixedWidth(110)
            lbl.setAlignment(Qt.AlignTop)
            val = QLabel(data.get(key, "UNKNOWN"))
            val.setFont(QFont("Arial", 13))
            val.setStyleSheet(f"color: {CLR_TEXT}; background: transparent;")
            val.setWordWrap(True)
            row.addWidget(lbl)
            row.addWidget(val, stretch=1)
            e_layout.addLayout(row)

        return entry

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return):
            self.close()


# ── Application controller ─────────────────────────────────────────────────────
class DAQAlertApp:
    """Manages the Qt event loop and the UDP listener thread."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self._windows: list = []   # keep references so windows aren't GC'd
        self._last_accepted_time: float = 0.0

        self.listener = UDPListenerThread(port=BROADCAST_PORT)
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
                                        port=BROADCAST_PORT, scheme="udp")
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
        with open(PID_FILE, "w") as fh:
            fh.write(str(os.getpid()))

    def _show_alert(self, message_data: dict):
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
            # Find the most recently opened window that is not paused
            for window in reversed(self._windows):
                if not window.is_paused:
                    window.update_message(message_data)
                    log.info("Max windows reached; updated existing window")
                    return
            log.info("All windows paused; dropping message")
            return

        window = AlertWindow(message_data)
        self._windows.append(window)
        # Remove from list when the window is closed so memory isn't leaked
        window.destroyed.connect(lambda: self._windows.remove(window) if window in self._windows else None)
        window.show()
        window.raise_()
        window.activateWindow()

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

    def run(self) -> int:
        exit_code = self.app.exec_()
        self._shutdown()
        return exit_code


def main():
    app = DAQAlertApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
