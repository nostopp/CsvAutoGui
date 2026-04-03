from __future__ import annotations

from pathlib import Path

from csv_editor.domain.enums import OperationType, ValidationSeverity
from csv_editor.domain.models import EditorDocument, FlowDocument, OperationNode, ValidationIssue


def validate_document(document: EditorDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for flow in document.flows:
        issues.extend(validate_flow(document.root_path, flow))
    return issues


def validate_flow(root_path: Path, flow: FlowDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_marks: set[str] = set()
    jump_marks: set[str] = {node.jump_mark for node in flow.nodes if node.jump_mark}

    for expected_index, node in enumerate(flow.nodes, start=1):
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
            continue

        if node.jump_mark:
            if node.jump_mark in seen_marks:
                issues.append(_issue(flow, node, f"跳转标记重复: {node.jump_mark}"))
            seen_marks.add(node.jump_mark)

        if node.operation not in {item.value for item in OperationType}:
            issues.append(_issue(flow, node, f"不支持的操作类型: {node.operation}"))
            continue

        if node.operation in {OperationType.MOVE_REL.value, OperationType.MOVE_TO.value} and not _is_pair_int(node.param_text):
            issues.append(_issue(flow, node, "移动操作参数必须为 x;y"))

        if node.operation in {
            OperationType.PRESS.value,
            OperationType.KEY_DOWN.value,
            OperationType.KEY_UP.value,
            OperationType.WRITE.value,
            OperationType.NOTIFY.value,
            OperationType.JUMP.value,
        } and not node.param_text.strip():
            issues.append(_issue(flow, node, "当前操作需要操作参数"))

        if node.operation == OperationType.JUMP.value and node.param_text.strip():
            if not _is_jump_target(node.param_text, jump_marks):
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        flow_name=flow.filename,
                        node_id=node.node_id,
                        message=f"跳转目标可能不存在: {node.param_text}",
                    )
                )

        if node.operation in {OperationType.PIC.value, OperationType.OCR.value}:
            if not node.search_target.strip():
                issues.append(_issue(flow, node, "识别节点需要图片或 OCR 目标"))
            if node.region_text and not _is_region(node.region_text):
                issues.append(_issue(flow, node, "识别区域必须为 x;y;w;h"))
            if node.confidence_text:
                if not _is_float(node.confidence_text):
                    issues.append(_issue(flow, node, "置信度必须是数字"))
                else:
                    confidence = float(node.confidence_text)
                    if confidence < 0 or confidence > 1:
                        issues.append(_issue(flow, node, "置信度必须在 0 到 1 之间"))
            if node.retry_value and not _is_float(node.retry_value):
                issues.append(_issue(flow, node, "重试时间必须是数字"))
            if node.retry_random and not _is_float(node.retry_random):
                issues.append(_issue(flow, node, "重试随机时间必须是数字"))
            if node.operation == OperationType.PIC.value and node.search_target.strip():
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

        if node.wait_value and not _is_float(node.wait_value):
            issues.append(_issue(flow, node, "等待时间必须是数字"))
        if node.wait_random and not _is_float(node.wait_random):
            issues.append(_issue(flow, node, "等待随机时间必须是数字"))
        if node.move_time and not _is_float(node.move_time):
            issues.append(_issue(flow, node, "移动用时必须是数字"))

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
    try:
        int(text)
        return True
    except ValueError:
        return False
