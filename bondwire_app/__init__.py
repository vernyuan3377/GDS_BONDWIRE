"""Interactive Altium/GDS bond-wire planning tool."""

import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if VENDOR.exists() and str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

__version__ = "0.1.0"
