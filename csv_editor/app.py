from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .main_window import EditorMainWindow


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CsvAutoGui visual CSV editor")
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="Optional config folder to open on startup",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app = QApplication(sys.argv if argv is None else ["csv_editor", *argv])
    window = EditorMainWindow()
    if args.config:
        window.open_config_folder(Path(args.config))
    window.show()
    return app.exec()
