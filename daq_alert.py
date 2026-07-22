#!/usr/bin/env python3
"""
Backwards-compatible launcher for the DAQ alert listener.

The application now lives in the installed package
``mu2edaq_bigredbox`` (entry point ``mu2edaq-bigredbox``); this shim keeps
``python3 daq_alert.py`` working from a plain checkout, with or without the
package installed.
"""

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from mu2edaq_bigredbox.daq_alert import main  # noqa: E402

if __name__ == "__main__":
    main()
