"""
mu2edaq-bigredbox -- Mu2e DAQ "Big Red Box" alert listener.

Listens for JSON critical-error alerts broadcast over UDP and displays a
prominent PyQt6 alert window.  Compatible with Python 3.9+.

Entry points installed by this package:

    mu2edaq-bigredbox        -- run the alert listener (see daq_alert.main)
    mu2edaq-bigredbox-send   -- send a test alert  (see demo_sender.main)
"""

__version__ = "2.0.0"

__all__ = ["__version__"]
