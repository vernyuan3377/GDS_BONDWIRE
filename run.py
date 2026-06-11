from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

from PyQt5.QtWidgets import QApplication

from bondwire_app.main_window import MainWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Altium/GDS BondWire planning tool")
    parser.add_argument("--pcb", help="Altium PcbLib path")
    parser.add_argument("--gds", help="GDSII path")
    parser.add_argument("--project", help="BondWire JSON project path")
    parser.add_argument("--export-pdf", help="Load inputs, export PDF, and exit")
    return parser.parse_args()


def load_requested_inputs(window: MainWindow, args: argparse.Namespace) -> None:
    if args.project:
        window.open_project(args.project)
        return
    if args.pcb and Path(args.pcb).exists():
        window.load_pcblib_file(str(args.pcb))
    if args.gds and Path(args.gds).exists():
        window.load_gds_file(str(args.gds))


def main() -> int:
    args = parse_args()
    app = QApplication(sys.argv)
    window = MainWindow()

    load_requested_inputs(window, args)

    if args.export_pdf:
        window.export_pdf(args.export_pdf)
        return 0

    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
