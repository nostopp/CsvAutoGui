from __future__ import annotations

import json
from pathlib import Path

from csv_editor.domain.models import EditorState


class EditorStateRepository:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def load(self, root_path: Path) -> EditorState:
        if not self.enabled:
            return EditorState()

        state_path = root_path / ".csv_editor_state.json"
        if not state_path.exists():
            return EditorState()

        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return EditorState()

        return EditorState(
            selected_flow=str(data.get("selected_flow", "main.csv")),
            selected_node_id=data.get("selected_node_id"),
        )

    def save(self, root_path: Path, state: EditorState) -> None:
        if not self.enabled:
            return

        state_path = root_path / ".csv_editor_state.json"
        payload = {
            "selected_flow": state.selected_flow,
            "selected_node_id": state.selected_node_id,
        }
        state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
