from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from csv_editor import __version__

from .bridge import EditorBridgeApi


@dataclass(slots=True)
class HostConfig:
    initial_root_path: Path | None = None
    webui_url: str | None = None
    debug: bool = False
    width: int = 1440
    height: int = 920
    title: str = "CsvAutoGui Editor"


class WebHostApp:
    def __init__(self, config: HostConfig) -> None:
        self._config = config

    def run(self) -> int:
        try:
            import webview
        except ImportError as exc:
            sys.stderr.write("pywebview is required to start the web host.\n")
            sys.stderr.write(f"{exc}\n")
            return 1

        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True

        frontend_entry = self._resolve_frontend_entry()
        bridge = EditorBridgeApi(
            initial_root_path=self._config.initial_root_path,
            app_name=self._config.title,
            app_version=__version__,
            frontend_entry=frontend_entry,
        )

        window_options = self._build_window_options(frontend_entry)
        window = webview.create_window(
            self._config.title,
            js_api=bridge,
            width=self._config.width,
            height=self._config.height,
            min_size=(1024, 720),
            **window_options,
        )
        bridge.set_window(window)
        webview.start(debug=self._config.debug)
        return 0

    def _resolve_frontend_entry(self) -> str | None:
        configured = self._config.webui_url or os.environ.get("CSV_EDITOR_WEBUI_URL")
        if configured:
            return configured

        base_dir = Path(__file__).resolve().parents[1]
        candidates = [
            base_dir / "webui" / "dist" / "index.html",
            base_dir / "webui" / "index.html",
            base_dir / "webui" / "build" / "index.html",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve().as_uri()
        return None

    def _build_window_options(self, frontend_entry: str | None) -> dict[str, Any]:
        if frontend_entry:
            return {
                "url": frontend_entry,
                "frameless": True,
                "easy_drag": False,
                "shadow": True,
                "background_color": "#DDE4EC",
            }
        return {
            "html": _placeholder_html(self._config.title, self._config.initial_root_path),
            "frameless": True,
            "easy_drag": False,
            "shadow": True,
            "background_color": "#DDE4EC",
        }


def _placeholder_html(title: str, initial_root_path: Path | None) -> str:
    initial_path_text = str(initial_root_path) if initial_root_path else "(not set)"
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: "Segoe UI", sans-serif;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: linear-gradient(160deg, #f6efe1, #d6e4ff);
        color: #1a2333;
      }}
      main {{
        width: min(720px, calc(100vw - 48px));
        padding: 32px;
        border-radius: 24px;
        background: rgba(255, 255, 255, 0.88);
        box-shadow: 0 24px 80px rgba(26, 35, 51, 0.18);
      }}
      h1 {{
        margin: 0 0 12px;
        font-size: 28px;
      }}
      p {{
        margin: 0 0 12px;
        line-height: 1.6;
      }}
      code {{
        font-family: Consolas, monospace;
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>Web host is ready</h1>
      <p>The pywebview shell started, but no bundled web UI was found yet.</p>
      <p>Initial config path: <code>{initial_path_text}</code></p>
      <p>Set <code>CSV_EDITOR_WEBUI_URL</code> or run <code>npm run build</code> in <code>csv_editor/webui</code> to attach the frontend.</p>
    </main>
  </body>
</html>
"""
