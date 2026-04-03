from __future__ import annotations

import datetime
from pathlib import Path

from PIL import Image


def build_capture_filename(left: int, top: int, width: int, height: int) -> str:
    timestamp = datetime.datetime.now().strftime("%m%d%H%M%S")
    return f"{timestamp}_{left};{top};{width};{height}.png"


def save_capture_image(root_path: Path, image: Image.Image, left: int, top: int, width: int, height: int) -> str:
    filename = build_capture_filename(left, top, width, height)
    out_path = root_path / filename
    counter = 1
    while out_path.exists():
        out_path = root_path / f"{out_path.stem}_{counter}.png"
        counter += 1
    image.save(out_path)
    return out_path.name
