"""Shared pytest configuration.

Forces Qt's offscreen platform plugin before any Qt import so the GUI tests
run on machines without a DISPLAY.  Set QT_QPA_PLATFORM yourself (e.g. to
"xcb" or "cocoa") if you want to watch the windows while testing.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
