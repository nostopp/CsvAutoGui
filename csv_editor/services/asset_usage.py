from __future__ import annotations

from pathlib import Path

from csv_editor.domain.enums import OperationType
from csv_editor.domain.models import EditorDocument

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def find_unused_images(document: EditorDocument) -> list[str]:
    used_images: set[str] = set()
    for flow in document.flows:
        for node in flow.nodes:
            if node.operation == OperationType.PIC.value and node.search_target.strip():
                used_images.add(node.search_target.strip())

    unused: list[str] = []
    for path in sorted(document.root_path.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if path.name not in used_images:
            unused.append(path.name)
    return unused
