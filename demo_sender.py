#!/usr/bin/env python3
"""
Backwards-compatible launcher for the test alert sender.

The utility now lives in the installed package ``mu2edaq_bigredbox``
(entry point ``mu2edaq-bigredbox-send``); this shim keeps
``python3 demo_sender.py`` working from a plain checkout.
"""

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from mu2edaq_bigredbox.demo_sender import main, send_alert  # noqa: E402,F401

if __name__ == "__main__":
    main()
