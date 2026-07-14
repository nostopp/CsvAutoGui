from __future__ import annotations

from operation_contracts import OperationType

from csv_editor.domain.models import EditorDocument
from csv_editor.io.csv_codec import parse_resource_param

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def find_unused_images(document: EditorDocument) -> list[str]:
    used_images: set[str] = set()
    for flow in document.flows:
        for node in flow.nodes:
            if node.operation == OperationType.PIC.value and node.search_target.strip():
                used_images.add(node.search_target.strip())
                continue
            if node.operation != OperationType.RESOURCE.value or not node.search_target.strip():
                continue
            parsed = parse_resource_param(node.param_text.strip())
            if parsed is not None and parsed[0] == "pic":
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
