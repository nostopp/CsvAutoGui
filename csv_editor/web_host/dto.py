from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from csv_editor.domain.enums import BranchMode, BranchTrigger, ValidationSeverity
from csv_editor.domain.models import BranchConfig, EditorDocument, EditorState, FlowDocument, OperationNode, ValidationIssue
from csv_editor.io.node_clipboard import NodeClipboardPayload

JsonDict = dict[str, object]
ApiResultDTO = JsonDict
BootstrapDTO = JsonDict
BranchConfigDTO = JsonDict
OperationNodeDTO = JsonDict
FlowDocumentDTO = JsonDict
EditorDocumentDTO = JsonDict
ValidationIssueDTO = JsonDict
ExternalFlowSummaryDTO = JsonDict
ImportNodesInputDTO = JsonDict
NodeClipboardPayloadDTO = JsonDict
SaveDocumentInputDTO = JsonDict
SaveDocumentResultDTO = JsonDict
UnusedImageDTO = JsonDict


def branch_config_to_dict(branch: BranchConfig) -> JsonDict:
    return {
        "trigger": branch.trigger.value,
        "mode": branch.mode.value,
        "primary_target": branch.primary_target,
        "secondary_target": branch.secondary_target,
    }


def branch_config_from_dict(payload: object) -> BranchConfig:
    data = _as_mapping(payload)
    return BranchConfig(
        trigger=_parse_branch_trigger(data.get("trigger")),
        mode=_parse_branch_mode(data.get("mode")),
        primary_target=_as_str(data.get("primary_target")),
        secondary_target=_as_str(data.get("secondary_target")),
    )


def operation_node_to_dict(node: OperationNode) -> JsonDict:
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
        "branch": branch_config_to_dict(node.branch),
        "raw_extra": {str(key): str(value) for key, value in node.raw_extra.items()},
    }


def operation_node_from_dict(payload: object) -> OperationNode:
    data = _as_mapping(payload)
    raw_extra = _as_mapping(data.get("raw_extra"))
    return OperationNode(
        operation=_as_str(data.get("operation")),
        node_id=_as_str(data.get("node_id")),
        index=_as_int(data.get("index")),
        param_text=_as_str(data.get("param_text")),
        wait_value=_as_str(data.get("wait_value")),
        wait_random=_as_str(data.get("wait_random")),
        search_target=_as_str(data.get("search_target")),
        region_text=_as_str(data.get("region_text")),
        confidence_text=_as_str(data.get("confidence_text")),
        retry_value=_as_str(data.get("retry_value")),
        retry_random=_as_str(data.get("retry_random")),
        pic_range_random=_as_bool(data.get("pic_range_random")),
        move_time=_as_str(data.get("move_time")),
        jump_mark=_as_str(data.get("jump_mark")),
        disable_grayscale=_as_bool(data.get("disable_grayscale")),
        note=_as_str(data.get("note")),
        branch=branch_config_from_dict(data.get("branch")),
        raw_extra={str(key): _as_str(value) for key, value in raw_extra.items()},
    )


def flow_document_to_dict(flow: FlowDocument) -> JsonDict:
    return {
        "filename": flow.filename,
        "nodes": [operation_node_to_dict(node) for node in flow.nodes],
    }


def flow_document_from_dict(payload: object) -> FlowDocument:
    data = _as_mapping(payload)
    nodes = [operation_node_from_dict(item) for item in _as_sequence(data.get("nodes"))]
    flow = FlowDocument(filename=_as_str(data.get("filename")), nodes=nodes)
    flow.reindex()
    return flow


def editor_state_to_dict(state: EditorState) -> JsonDict:
    return {
        "selected_flow": state.selected_flow,
        "selected_node_id": state.selected_node_id,
    }


def editor_state_from_dict(payload: object) -> EditorState:
    data = _as_mapping(payload)
    selected_node = data.get("selected_node_id")
    return EditorState(
        selected_flow=_as_str(data.get("selected_flow"), "main.csv"),
        selected_node_id=_as_str(selected_node) if selected_node is not None else None,
    )


def editor_document_to_dict(document: EditorDocument) -> JsonDict:
    return {
        "root_path": str(document.root_path),
        "flows": [flow_document_to_dict(flow) for flow in document.flows],
        "state": editor_state_to_dict(document.state),
    }


def editor_document_from_dict(payload: object) -> EditorDocument:
    data = _as_mapping(payload)
    flows = [flow_document_from_dict(item) for item in _as_sequence(data.get("flows"))]
    document = EditorDocument(
        root_path=Path(_as_str(data.get("root_path"))),
        flows=flows,
        state=editor_state_from_dict(data.get("state")),
    )
    document.ensure_main_first()
    return document


def validation_issue_to_dict(issue: ValidationIssue) -> JsonDict:
    return {
        "severity": _validation_severity_to_str(issue.severity),
        "flow_name": issue.flow_name,
        "node_id": issue.node_id,
        "message": issue.message,
    }


def external_flow_summary_to_dict(root_path: Path, flow: FlowDocument) -> JsonDict:
    return {
        "root_path": str(root_path),
        "flow_name": flow.filename,
        "node_count": len(flow.nodes),
    }


def unused_image_to_dict(root_path: Path, image_name: str) -> JsonDict:
    return {
        "image_name": image_name,
        "image_path": str(root_path / image_name),
    }


def node_clipboard_payload_to_dict(payload: NodeClipboardPayload) -> JsonDict:
    return {
        "version": payload.version,
        "source_root": payload.source_root,
        "source_flow": payload.source_flow,
        "nodes": [operation_node_to_dict(node) for node in payload.nodes],
    }


def node_clipboard_payload_from_dict(payload: object) -> NodeClipboardPayload:
    data = _as_mapping(payload)
    nodes = [operation_node_from_dict(item) for item in _as_sequence(data.get("nodes"))]
    return NodeClipboardPayload(
        version=_as_int(data.get("version"), 1),
        source_root=_as_str(data.get("source_root")),
        source_flow=_as_str(data.get("source_flow")),
        nodes=nodes,
    )


def save_document_result_to_dict(document: EditorDocument) -> JsonDict:
    return {
        "document": editor_document_to_dict(document),
    }


def _validation_severity_to_str(severity: ValidationSeverity) -> str:
    if severity in {ValidationSeverity.ERROR, ValidationSeverity.WARNING}:
        return severity.value
    return "info"


def _parse_branch_trigger(value: object) -> BranchTrigger:
    try:
        return BranchTrigger(_as_str(value))
    except ValueError:
        return BranchTrigger.NONE


def _parse_branch_mode(value: object) -> BranchMode:
    try:
        return BranchMode(_as_str(value))
    except ValueError:
        return BranchMode.NONE


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: object) -> list[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _as_str(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
