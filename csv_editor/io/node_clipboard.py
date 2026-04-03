from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from csv_editor.domain.enums import BranchMode, BranchTrigger, OperationType
from csv_editor.domain.models import BranchConfig, FlowDocument, OperationNode

CLIPBOARD_MIME_TYPE = "application/x-csvautogui-nodes"
CLIPBOARD_TEXT_PREFIX = "CsvAutoGuiNodes:"
CLIPBOARD_VERSION = 1


@dataclass(slots=True)
class NodeClipboardPayload:
    source_root: str
    source_flow: str
    nodes: list[OperationNode]
    version: int = CLIPBOARD_VERSION


def build_clipboard_payload(root_path: Path, flow_name: str, nodes: list[OperationNode]) -> NodeClipboardPayload:
    return NodeClipboardPayload(
        source_root=str(root_path),
        source_flow=flow_name,
        nodes=[node.clone() for node in nodes],
    )


def serialize_clipboard_payload(payload: NodeClipboardPayload) -> str:
    data = {
        "version": payload.version,
        "source_root": payload.source_root,
        "source_flow": payload.source_flow,
        "nodes": [_node_to_dict(node) for node in payload.nodes],
    }
    return json.dumps(data, ensure_ascii=False)


def deserialize_clipboard_payload(text: str) -> NodeClipboardPayload | None:
    if not text:
        return None
    if text.startswith(CLIPBOARD_TEXT_PREFIX):
        text = text[len(CLIPBOARD_TEXT_PREFIX) :]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict) or data.get("version") != CLIPBOARD_VERSION:
        return None

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list):
        return None

    nodes: list[OperationNode] = []
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            return None
        nodes.append(_node_from_dict(raw_node))

    return NodeClipboardPayload(
        version=CLIPBOARD_VERSION,
        source_root=str(data.get("source_root", "")),
        source_flow=str(data.get("source_flow", "")),
        nodes=nodes,
    )


def clone_nodes_for_paste(nodes: list[OperationNode], target_flow: FlowDocument) -> tuple[list[OperationNode], dict[str, str]]:
    cloned_nodes = [node.clone() for node in nodes]
    existing_marks = {node.jump_mark.strip() for node in target_flow.nodes if node.jump_mark.strip()}
    used_marks = set(existing_marks)
    renamed_marks: dict[str, str] = {}

    for node in cloned_nodes:
        node.node_id = uuid4().hex
        node.index = 0
        mark = node.jump_mark.strip()
        if not mark:
            continue
        unique_mark = _build_unique_mark(mark, used_marks)
        used_marks.add(unique_mark)
        node.jump_mark = unique_mark
        if unique_mark != mark:
            renamed_marks[mark] = unique_mark

    if renamed_marks:
        for node in cloned_nodes:
            if node.operation == OperationType.JUMP.value:
                target = node.param_text.strip()
                if target in renamed_marks:
                    node.param_text = renamed_marks[target]
            if node.branch.mode is BranchMode.JUMP_PAIR:
                primary = node.branch.primary_target.strip()
                secondary = node.branch.secondary_target.strip()
                if primary in renamed_marks:
                    node.branch.primary_target = renamed_marks[primary]
                if secondary in renamed_marks:
                    node.branch.secondary_target = renamed_marks[secondary]

    return cloned_nodes, renamed_marks


def _build_unique_mark(mark: str, used_marks: set[str]) -> str:
    candidate = mark
    suffix = 1
    while candidate in used_marks:
        candidate = f"{mark}_copy{suffix}"
        suffix += 1
    return candidate


def _node_to_dict(node: OperationNode) -> dict[str, object]:
    return {
        "node_id": node.node_id,
        "index": node.index,
        "operation": node.operation,
        "param_text": node.param_text,
        "wait_value": node.wait_value,
        "wait_random": node.wait_random,
        "search_target": node.search_target,
        "region_text": node.region_text,
        "confidence_text": node.confidence_text,
        "retry_value": node.retry_value,
        "retry_random": node.retry_random,
        "pic_range_random": node.pic_range_random,
        "move_time": node.move_time,
        "jump_mark": node.jump_mark,
        "disable_grayscale": node.disable_grayscale,
        "note": node.note,
        "raw_extra": node.raw_extra,
        "branch": {
            "trigger": node.branch.trigger.value,
            "mode": node.branch.mode.value,
            "primary_target": node.branch.primary_target,
            "secondary_target": node.branch.secondary_target,
        },
    }


def _node_from_dict(data: dict[str, object]) -> OperationNode:
    raw_branch = data.get("branch")
    branch_data = raw_branch if isinstance(raw_branch, dict) else {}
    raw_extra = data.get("raw_extra")
    parsed_extra = raw_extra if isinstance(raw_extra, dict) else {}
    return OperationNode(
        operation=str(data.get("operation", "")),
        node_id=str(data.get("node_id", "")) or uuid4().hex,
        index=_safe_int(data.get("index")),
        param_text=str(data.get("param_text", "")),
        wait_value=str(data.get("wait_value", "")),
        wait_random=str(data.get("wait_random", "")),
        search_target=str(data.get("search_target", "")),
        region_text=str(data.get("region_text", "")),
        confidence_text=str(data.get("confidence_text", "")),
        retry_value=str(data.get("retry_value", "")),
        retry_random=str(data.get("retry_random", "")),
        pic_range_random=bool(data.get("pic_range_random", False)),
        move_time=str(data.get("move_time", "")),
        jump_mark=str(data.get("jump_mark", "")),
        disable_grayscale=bool(data.get("disable_grayscale", False)),
        note=str(data.get("note", "")),
        raw_extra={str(key): str(value) for key, value in parsed_extra.items()},
        branch=BranchConfig(
            trigger=_parse_branch_trigger(branch_data.get("trigger")),
            mode=_parse_branch_mode(branch_data.get("mode")),
            primary_target=str(branch_data.get("primary_target", "")),
            secondary_target=str(branch_data.get("secondary_target", "")),
        ),
    )


def _parse_branch_trigger(value: object) -> BranchTrigger:
    try:
        return BranchTrigger(str(value))
    except ValueError:
        return BranchTrigger.NONE


def _parse_branch_mode(value: object) -> BranchMode:
    try:
        return BranchMode(str(value))
    except ValueError:
        return BranchMode.NONE


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
