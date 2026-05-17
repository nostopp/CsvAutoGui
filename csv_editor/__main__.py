from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from csv_editor.app import main
else:
    from .app import main


if __name__ == "__main__":
    raise SystemExit(main())
