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
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QLinearGradient, QPainter, QPalette, QBrush

from config import BROADCAST_PORT, PID_FILE, LOG_FILE


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

        value_lbl = QLabel(value)
        value_lbl.setFont(QFont("Arial", 17))
        value_lbl.setStyleSheet(f"color: {CLR_TEXT}; background: transparent;")
        value_lbl.setWordWrap(True)
        value_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout.addWidget(label)
        layout.addWidget(value_lbl)


# ── Alert window ───────────────────────────────────────────────────────────────
class AlertWindow(QWidget):
    """Modern dark alert window displayed when a critical message arrives."""

    def __init__(self, message_data: dict):
        super().__init__()
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
        body_layout.addWidget(FieldRow("System ID",    system_id))
        body_layout.addWidget(self._divider())
        body_layout.addWidget(FieldRow("Timestamp",    timestamp))
        body_layout.addWidget(self._divider())
        body_layout.addWidget(FieldRow("Error Message", message))
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
        footer_layout.addStretch()
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

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Space):
            self.close()


# ── Application controller ─────────────────────────────────────────────────────
class DAQAlertApp:
    """Manages the Qt event loop and the UDP listener thread."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self._windows: list = []   # keep references so windows aren't GC'd

        self.listener = UDPListenerThread(port=BROADCAST_PORT)
        self.listener.message_received.connect(self._show_alert)
        self.listener.start()

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
        log.info("Displaying alert: %s", message_data)
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
