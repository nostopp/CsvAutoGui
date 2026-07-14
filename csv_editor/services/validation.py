from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from operation_contracts import (
    OperationCategory,
    OperationContract,
    OperationField,
    OperationType,
    ParamKind,
    get_operation_contract,
    is_terminal_jump_target,
)

from autogui.infrastructure.paths import resolve_config_relative_path
from csv_editor.domain.enums import ValidationSeverity
from csv_editor.domain.models import EditorDocument, FlowDocument, OperationNode, ValidationIssue
from csv_editor.io.csv_codec import is_resource_flow_filename, parse_resource_param, parse_script_param


def validate_document(document: EditorDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    flow_lookup = {flow.filename: flow for flow in document.flows}
    for flow in document.flows:
        issues.extend(validate_flow(document.root_path, flow, flow_lookup))
    return issues


def validate_flow(root_path: Path, flow: FlowDocument, flow_lookup: dict[str, FlowDocument] | None = None) -> list[ValidationIssue]:
    context = _build_flow_validation_context(root_path, flow, flow_lookup)
    issues: list[ValidationIssue] = []
    for node in flow.nodes:
        issues.extend(_validate_node_with_context(context, node))
    return issues


def validate_node(
    root_path: Path,
    flow: FlowDocument,
    node: OperationNode,
    flow_lookup: dict[str, FlowDocument] | None = None,
) -> list[ValidationIssue]:
    if all(candidate is not node for candidate in flow.nodes):
        raise ValueError(f"节点不属于流程 {flow.filename}: {node.node_id}")
    context = _build_flow_validation_context(root_path, flow, flow_lookup)
    return _validate_node_with_context(context, node)


@dataclass(frozen=True, slots=True)
class _FlowValidationContext:
    root_path: Path
    flow: FlowDocument
    flow_lookup: dict[str, FlowDocument]
    is_resource_flow: bool
    expected_indexes: dict[int, int]
    jump_marks: set[str]
    first_jump_mark_nodes: dict[str, int]
    first_resource_alias_nodes: dict[str, int]


def _build_flow_validation_context(
    root_path: Path,
    flow: FlowDocument,
    flow_lookup: dict[str, FlowDocument] | None,
) -> _FlowValidationContext:
    is_resource_flow = is_resource_flow_filename(flow.filename)
    first_jump_mark_nodes: dict[str, int] = {}
    first_resource_alias_nodes: dict[str, int] = {}
    for node in flow.nodes:
        if node.jump_mark and not is_resource_flow:
            first_jump_mark_nodes.setdefault(node.jump_mark, id(node))
        if is_resource_flow and node.operation == OperationType.RESOURCE.value:
            parsed = parse_resource_param(node.param_text.strip())
            if parsed is not None:
                first_resource_alias_nodes.setdefault(parsed[1], id(node))
    return _FlowValidationContext(
        root_path=root_path,
        flow=flow,
        flow_lookup=flow_lookup or {},
        is_resource_flow=is_resource_flow,
        expected_indexes={id(node): index for index, node in enumerate(flow.nodes, start=1)},
        jump_marks=set(first_jump_mark_nodes),
        first_jump_mark_nodes=first_jump_mark_nodes,
        first_resource_alias_nodes=first_resource_alias_nodes,
    )


def _validate_node_with_context(
    context: _FlowValidationContext,
    node: OperationNode,
) -> list[ValidationIssue]:
    flow = context.flow
    issues: list[ValidationIssue] = []
    expected_index = context.expected_indexes[id(node)]
    if node.index != expected_index:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                flow_name=flow.filename,
                node_id=node.node_id,
                message=f"序号 {node.index} 将在保存时重排为 {expected_index}",
            )
        )

    if not node.operation:
        issues.append(_issue(flow, node, "操作不能为空"))
        return issues

    if (
        node.jump_mark
        and not context.is_resource_flow
        and context.first_jump_mark_nodes.get(node.jump_mark) != id(node)
    ):
        issues.append(_issue(flow, node, f"跳转标记重复: {node.jump_mark}"))

    contract = get_operation_contract(node.operation)
    if contract is None:
        issues.append(_issue(flow, node, f"不支持的操作类型: {node.operation}"))
        return issues

    if context.is_resource_flow:
        if not contract.allowed_in_resource_flow:
            issues.append(_issue(flow, node, "资源文件中只允许使用 resource 节点"))
        else:
            parsed = parse_resource_param(node.param_text.strip())
            duplicate_alias = (
                parsed is not None
                and context.first_resource_alias_nodes.get(parsed[1]) != id(node)
            )
            issues.extend(
                _validate_resource_node(
                    context.root_path,
                    flow,
                    node,
                    duplicate_alias=duplicate_alias,
                )
            )
        return issues

    if not contract.allowed_in_normal_flow:
        issues.append(_issue(flow, node, "普通流程中不能使用 resource 节点"))

    issues.extend(validate_node_fields(flow, node, contract))
    issues.extend(
        validate_node_assets(
            context.root_path,
            flow,
            node,
            contract,
            context.flow_lookup,
        )
    )
    issues.extend(
        _validate_node_references(
            context.root_path,
            flow,
            node,
            contract,
            context.jump_marks,
        )
    )
    issues.extend(validate_node_timing_fields(flow, node))
    return issues


def validate_node_fields(
    flow: FlowDocument,
    node: OperationNode,
    contract: OperationContract,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if (
        contract.param_kind is ParamKind.COORDINATE_PAIR
        and not _is_pair_int(node.param_text)
    ):
        issues.append(_issue(flow, node, "移动操作参数必须为 x;y"))

    if (
        contract.param_required
        and contract.param_kind in {ParamKind.KEY, ParamKind.TEXT, ParamKind.JUMP_TARGET}
        and not node.param_text.strip()
    ):
        issues.append(_issue(flow, node, "当前操作需要操作参数"))

    if contract.category is not OperationCategory.RECOGNITION:
        return issues

    fields = contract.supported_fields
    if OperationField.SEARCH_TARGET in fields and not node.search_target.strip():
        issues.append(_issue(flow, node, "识别节点需要图片或 OCR 目标"))
    if (
        OperationField.REGION in fields
        and node.region_text
        and not _is_region(node.region_text)
    ):
        issues.append(_issue(flow, node, "识别区域必须为 x;y;w;h"))
    if OperationField.CONFIDENCE in fields and node.confidence_text:
        if not _is_float(node.confidence_text):
            issues.append(_issue(flow, node, "置信度必须是数字"))
        else:
            confidence = float(node.confidence_text)
            if confidence < 0 or confidence > 1:
                issues.append(_issue(flow, node, "置信度必须在 0 到 1 之间"))
    if (
        OperationField.RETRY in fields
        and node.retry_value
        and not _is_float(node.retry_value)
    ):
        issues.append(_issue(flow, node, "重试时间必须是数字"))
    if (
        OperationField.RETRY_RANDOM in fields
        and node.retry_random
        and not _is_float(node.retry_random)
    ):
        issues.append(_issue(flow, node, "重试随机时间必须是数字"))
    return issues


def validate_node_assets(
    root_path: Path,
    flow: FlowDocument,
    node: OperationNode,
    contract: OperationContract,
    flow_lookup: dict[str, FlowDocument],
) -> list[ValidationIssue]:
    if contract.param_kind is ParamKind.SCRIPT_REFERENCE:
        return _validate_script_node(root_path, flow, node, flow_lookup)

    if contract.operation is not OperationType.PIC or not node.search_target.strip():
        return []
    asset_path = root_path / node.search_target.strip()
    if asset_path.exists():
        return []
    return [
        ValidationIssue(
            severity=ValidationSeverity.WARNING,
            flow_name=flow.filename,
            node_id=node.node_id,
            message=f"图片素材不存在: {node.search_target}",
        )
    ]


def validate_flow_references(
    root_path: Path,
    flow: FlowDocument,
    node: OperationNode,
    contract: OperationContract,
    jump_marks: set[str],
) -> list[ValidationIssue]:
    return _validate_node_references(
        root_path,
        flow,
        node,
        contract,
        jump_marks,
    )


def _validate_node_references(
    root_path: Path,
    flow: FlowDocument,
    node: OperationNode,
    contract: OperationContract,
    jump_marks: set[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if (
        contract.param_kind is ParamKind.JUMP_TARGET
        and node.param_text.strip()
        and not _is_jump_target(node.param_text, jump_marks)
    ):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                flow_name=flow.filename,
                node_id=node.node_id,
                message=f"跳转目标可能不存在: {node.param_text}",
            )
        )

    if not contract.supports_branch:
        return issues
    if node.branch.is_enabled and not node.branch.primary_target.strip():
        issues.append(_issue(flow, node, "分支目标不能为空"))
    if node.branch.mode.value == "subflow" and node.branch.primary_target.strip():
        subflow_path = root_path / node.branch.primary_target.strip()
        if not subflow_path.exists():
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    flow_name=flow.filename,
                    node_id=node.node_id,
                    message=f"子流程文件不存在: {node.branch.primary_target}",
                )
            )
        elif is_resource_flow_filename(node.branch.primary_target.strip()):
            issues.append(_issue(flow, node, "资源文件不能作为子流程执行"))
    if node.branch.mode.value == "jump_pair" and node.branch.primary_target.strip():
        if not _is_jump_target(node.branch.primary_target, jump_marks):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    flow_name=flow.filename,
                    node_id=node.node_id,
                    message=f"分支主跳转目标可能不存在: {node.branch.primary_target}",
                )
            )
    if node.branch.mode.value == "jump_pair" and not node.branch.secondary_target.strip():
        issues.append(_issue(flow, node, "双跳转分支需要第二目标"))
    if node.branch.mode.value == "jump_pair" and node.branch.secondary_target.strip():
        if not _is_jump_target(node.branch.secondary_target, jump_marks):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    flow_name=flow.filename,
                    node_id=node.node_id,
                    message=f"分支次跳转目标可能不存在: {node.branch.secondary_target}",
                )
            )
    return issues


def validate_node_timing_fields(
    flow: FlowDocument,
    node: OperationNode,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if node.wait_value and not _is_float(node.wait_value):
        issues.append(_issue(flow, node, "等待时间必须是数字"))
    if node.wait_random and not _is_float(node.wait_random):
        issues.append(_issue(flow, node, "等待随机时间必须是数字"))
    if node.move_time and not _is_float(node.move_time):
        issues.append(_issue(flow, node, "移动用时必须是数字"))
    return issues


def _validate_script_node(
    root_path: Path,
    flow: FlowDocument,
    node: OperationNode,
    flow_lookup: dict[str, FlowDocument],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    parsed = parse_script_param(node.param_text.strip())
    if parsed is None:
        issues.append(_issue(flow, node, "script 参数必须为 script.py 或 script.py;name_resource.csv"))
        return issues

    script_filename, explicit_resource = parsed
    if not _is_safe_relative_path(root_path, script_filename):
        issues.append(_issue(flow, node, "script 文件必须位于当前配置目录内"))
    if not script_filename.lower().endswith(".py"):
        issues.append(_issue(flow, node, "script 文件必须以 .py 结尾"))
    elif not (root_path / script_filename).exists():
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                flow_name=flow.filename,
                node_id=node.node_id,
                message=f"脚本文件不存在: {script_filename}",
            )
        )

    if explicit_resource is None:
        return issues

    if not _is_safe_relative_path(root_path, explicit_resource):
        issues.append(_issue(flow, node, "显式资源文件必须位于当前配置目录内"))

    if not is_resource_flow_filename(explicit_resource):
        issues.append(_issue(flow, node, "显式资源文件必须以 _resource.csv 结尾"))
        return issues

    resource_path = root_path / explicit_resource
    if not resource_path.exists():
        issues.append(_issue(flow, node, f"显式资源文件不存在: {explicit_resource}"))
        return issues

    resource_flow = flow_lookup.get(explicit_resource)
    if resource_flow is not None and not is_resource_flow_filename(resource_flow.filename):
        issues.append(_issue(flow, node, f"显式资源文件命名不合法: {explicit_resource}"))
    return issues


def _validate_resource_node(
    root_path: Path,
    flow: FlowDocument,
    node: OperationNode,
    *,
    duplicate_alias: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    parsed = parse_resource_param(node.param_text.strip())
    if parsed is None:
        issues.append(_issue(flow, node, "resource 参数必须为 pic;alias、ocr;alias 或 jmp;alias"))
        return issues

    kind, alias = parsed
    if duplicate_alias:
        issues.append(_issue(flow, node, f"资源变量名重复: {alias}"))

    if kind in {"pic", "ocr"}:
        if not node.search_target.strip():
            issues.append(_issue(flow, node, "资源节点需要图片文件或 OCR 文本"))
        if node.region_text and not _is_region(node.region_text):
            issues.append(_issue(flow, node, "识别区域必须为 x;y;w;h"))
        if node.confidence_text:
            if not _is_float(node.confidence_text):
                issues.append(_issue(flow, node, "置信度必须是数字"))
            else:
                confidence = float(node.confidence_text)
                if confidence < 0 or confidence > 1:
                    issues.append(_issue(flow, node, "置信度必须在 0 到 1 之间"))
        if kind == "pic" and node.search_target.strip():
            asset_path = root_path / node.search_target.strip()
            if not asset_path.exists():
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        flow_name=flow.filename,
                        node_id=node.node_id,
                        message=f"图片素材不存在: {node.search_target}",
                    )
                )

    if kind == "jmp" and not node.jump_mark.strip():
        issues.append(_issue(flow, node, "jmp 资源需要填写跳转标记"))

    return issues


def _issue(flow: FlowDocument, node: OperationNode, message: str) -> ValidationIssue:
    return ValidationIssue(
        severity=ValidationSeverity.ERROR,
        flow_name=flow.filename,
        node_id=node.node_id,
        message=message,
    )


def _is_float(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _is_pair_int(text: str) -> bool:
    parts = [item.strip() for item in text.split(";")]
    if len(parts) != 2:
        return False
    try:
        int(parts[0])
        int(parts[1])
        return True
    except ValueError:
        return False


def _is_region(text: str) -> bool:
    parts = [item.strip() for item in text.split(";")]
    if len(parts) != 4:
        return False
    try:
        for item in parts:
            int(item)
        return True
    except ValueError:
        return False


def _is_jump_target(text: str, jump_marks: set[str]) -> bool:
    text = text.strip()
    if not text:
        return False
    if text in jump_marks:
        return True
    if is_terminal_jump_target(text):
        return True
    try:
        int(text)
        return True
    except ValueError:
        return False


def _is_safe_relative_path(root_path: Path, text: str) -> bool:
    if not text.strip():
        return False
    try:
        resolve_config_relative_path(root_path, text)
    except ValueError:
        return False
    return True
