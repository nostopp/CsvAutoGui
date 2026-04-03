from __future__ import annotations

from csv_editor.domain.enums import BranchMode, OperationType
from csv_editor.domain.models import OperationNode


def summarize_node(node: OperationNode) -> str:
    operation = node.operation
    if operation == OperationType.CLICK.value:
        return f"点击鼠标 {node.param_text or 'left'}"
    if operation == OperationType.MOUSE_DOWN.value:
        return f"按下鼠标 {node.param_text or 'left'}"
    if operation == OperationType.MOUSE_UP.value:
        return f"松开鼠标 {node.param_text or 'left'}"
    if operation == OperationType.MOVE_REL.value:
        return f"相对移动 {node.param_text or '(未设置)'}"
    if operation == OperationType.MOVE_TO.value:
        return f"绝对移动 {node.param_text or '(未设置)'}"
    if operation == OperationType.PRESS.value:
        return f"按键 {node.param_text or '(未设置)'}"
    if operation == OperationType.KEY_DOWN.value:
        return f"按下键 {node.param_text or '(未设置)'}"
    if operation == OperationType.KEY_UP.value:
        return f"松开键 {node.param_text or '(未设置)'}"
    if operation == OperationType.WRITE.value:
        return f"输入文本 {node.param_text or '(未设置)'}"
    if operation == OperationType.NOTIFY.value:
        return f"通知 {node.param_text or '(空)'}"
    if operation == OperationType.JUMP.value:
        return f"跳转到 {node.param_text or '(未设置)'}"
    if operation == OperationType.PIC.value:
        return _summarize_detect("图片", node)
    if operation == OperationType.OCR.value:
        return _summarize_detect("OCR", node)
    return f"未知操作 {operation or '(空)'}"


def _summarize_detect(label: str, node: OperationNode) -> str:
    target = node.search_target or "(未设置)"
    if not node.branch.is_enabled:
        return f"{label}识别 {target}"

    if node.branch.mode is BranchMode.SUBFLOW:
        return f"{label}判断 {target} -> {node.branch.trigger.value} 执行 {node.branch.primary_target}"

    return (
        f"{label}判断 {target} -> {node.branch.trigger.value} 时到 {node.branch.primary_target}，"
        f"否则到 {node.branch.secondary_target or '(未设置)'}"
    )
