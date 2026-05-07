from __future__ import annotations

import argparse
from pathlib import Path

from .web_host import HostConfig, WebHostApp


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CsvAutoGui visual CSV editor")
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="Optional config folder to open on startup",
    )
    parser.add_argument(
        "--webui-url",
        type=str,
        default=None,
        help="Optional web UI URL or file URI to load in the desktop host",
    )
    parser.add_argument(
        "--debug-webview",
        action="store_true",
        help="Enable pywebview debug mode",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config).expanduser() if args.config else None
    host = WebHostApp(
        HostConfig(
            initial_root_path=config_path,
            webui_url=args.webui_url,
            debug=args.debug_webview,
        )
    )
    return host.run()
