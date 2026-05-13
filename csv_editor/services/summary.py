from __future__ import annotations

from csv_editor.domain.enums import BranchMode, BranchTrigger, OperationType
from csv_editor.domain.models import OperationNode

_FIELD_LABELS: dict[str, str] = {
    "param_text": "操作参数",
    "wait_value": "完成后等待时间",
    "wait_random": "等待随机时间",
    "search_target": "图片/OCR 目标",
    "region_text": "图片/OCR 坐标范围",
    "confidence_text": "图片/OCR 置信度",
    "retry_value": "未找到图片/OCR 重试时间",
    "retry_random": "重试随机时间",
    "pic_range_random": "图片/OCR 定位移动随机",
    "move_time": "移动操作用时",
    "jump_mark": "跳转标记",
    "disable_grayscale": "图片不使用灰度匹配",
    "note": "备注",
    "branch.trigger": "分支触发条件",
    "branch.mode": "分支模式",
    "branch.primary_target": "分支主目标",
    "branch.secondary_target": "分支次目标",
}

_HELPERS: dict[str, dict[str, object]] = {
    "capture_point": {
        "label": "拾取屏幕坐标点",
        "capability": "capture_point",
        "target_fields": ("param_text",),
    },
    "capture_image_region": {
        "label": "框选区域并保存图片",
        "capability": "capture_region",
        "target_fields": ("search_target", "region_text"),
    },
    "capture_ocr_region": {
        "label": "框选区域并提取 OCR 候选",
        "capability": "capture_region",
        "target_fields": ("search_target", "region_text"),
    },
    "select_ocr_candidate": {
        "label": "从 OCR 候选中选择文本",
        "capability": "capture_region",
        "target_fields": ("search_target",),
    },
}

_COMMON_FIELDS = ("wait_value", "wait_random", "jump_mark", "note")
_VISUAL_FIELDS = (
    "search_target",
    "region_text",
    "confidence_text",
    "retry_value",
    "retry_random",
    "pic_range_random",
    "move_time",
    "jump_mark",
    "note",
    "branch.trigger",
    "branch.mode",
    "branch.primary_target",
    "branch.secondary_target",
)

_OPERATION_METADATA: dict[str, dict[str, object]] = {
    OperationType.CLICK.value: {
        "label": "鼠标点击",
        "category": "mouse",
        "category_label": "鼠标",
        "visible_fields": ("param_text", "wait", "jump_mark", "note"),
        "allowed_helpers": (),
    },
    OperationType.MOUSE_DOWN.value: {
        "label": "鼠标按下",
        "category": "mouse",
        "category_label": "鼠标",
        "visible_fields": ("param_text", "wait", "jump_mark", "note"),
        "allowed_helpers": (),
    },
    OperationType.MOUSE_UP.value: {
        "label": "鼠标松开",
        "category": "mouse",
        "category_label": "鼠标",
        "visible_fields": ("param_text", "wait", "jump_mark", "note"),
        "allowed_helpers": (),
    },
    OperationType.MOVE_REL.value: {
        "label": "相对移动",
        "category": "mouse",
        "category_label": "鼠标",
        "visible_fields": ("param_text", "wait", "move_time", "jump_mark", "note"),
        "allowed_helpers": (),
    },
    OperationType.MOVE_TO.value: {
        "label": "绝对移动",
        "category": "mouse",
        "category_label": "鼠标",
        "visible_fields": ("param_text", "wait", "move_time", "jump_mark", "note"),
        "allowed_helpers": ("capture_point",),
    },
    OperationType.PRESS.value: {
        "label": "按键",
        "category": "keyboard",
        "category_label": "键盘",
        "visible_fields": ("param_text", "wait", "jump_mark", "note"),
        "allowed_helpers": (),
    },
    OperationType.KEY_DOWN.value: {
        "label": "按键按下",
        "category": "keyboard",
        "category_label": "键盘",
        "visible_fields": ("param_text", "wait", "jump_mark", "note"),
        "allowed_helpers": (),
    },
    OperationType.KEY_UP.value: {
        "label": "按键松开",
        "category": "keyboard",
        "category_label": "键盘",
        "visible_fields": ("param_text", "wait", "jump_mark", "note"),
        "allowed_helpers": (),
    },
    OperationType.WRITE.value: {
        "label": "输入文本",
        "category": "keyboard",
        "category_label": "键盘",
        "visible_fields": ("param_text", "wait", "jump_mark", "note"),
        "allowed_helpers": (),
    },
    OperationType.PIC.value: {
        "label": "识图",
        "category": "visual",
        "category_label": "识别",
        "visible_fields": (
            "wait",
            "search_target",
            "region_text",
            "confidence_text",
            "retry",
            "pic_range_random",
            "move_time",
            "jump_mark",
            "disable_grayscale",
            "note",
            "branch",
        ),
        "allowed_helpers": ("capture_image_region",),
    },
    OperationType.OCR.value: {
        "label": "OCR 识别",
        "category": "visual",
        "category_label": "识别",
        "visible_fields": (
            "wait",
            "search_target",
            "region_text",
            "confidence_text",
            "retry",
            "pic_range_random",
            "move_time",
            "jump_mark",
            "note",
            "branch",
        ),
        "allowed_helpers": ("capture_ocr_region", "select_ocr_candidate"),
    },
    OperationType.NOTIFY.value: {
        "label": "通知",
        "category": "system",
        "category_label": "系统",
        "visible_fields": ("param_text", "wait", "jump_mark", "note"),
        "allowed_helpers": (),
    },
    OperationType.JUMP.value: {
        "label": "跳转",
        "category": "flow",
        "category_label": "流程",
        "visible_fields": ("param_text", "jump_mark", "note"),
        "allowed_helpers": (),
    },
}


def build_operation_metadata() -> dict[str, object]:
    operations = {
        operation: {
            "label": str(metadata["label"]),
            "category": str(metadata["category"]),
            "category_label": str(metadata["category_label"]),
            "visible_fields": list(metadata["visible_fields"]),
            "allowed_helpers": list(metadata["allowed_helpers"]),
        }
        for operation, metadata in _OPERATION_METADATA.items()
    }
    fields = {field_key: {"label": label} for field_key, label in _FIELD_LABELS.items()}
    helpers = {
        helper_key: {
            "label": str(helper["label"]),
            "capability": str(helper["capability"]),
            "target_fields": list(helper["target_fields"]),
        }
        for helper_key, helper in _HELPERS.items()
    }
    return {
        "version": 1,
        "fields": fields,
        "helpers": helpers,
        "operations": operations,
    }


def build_node_row_view(node: OperationNode) -> dict[str, object]:
    operation_metadata = _OPERATION_METADATA.get(node.operation)
    operation_label = str(operation_metadata["label"]) if operation_metadata else (node.operation or "未知操作")
    category = str(operation_metadata["category"]) if operation_metadata else "unknown"
    category_label = str(operation_metadata["category_label"]) if operation_metadata else "未知"
    branch_text = _branch_text(node)
    summary = _summary_text(node)
    secondary_text = _secondary_text(node, branch_text)

    search_parts = [
        node.operation,
        operation_label,
        category_label,
        summary,
        secondary_text,
        branch_text,
        _locator_text(node),
        node.region_text.strip(),
        node.note.strip(),
        node.jump_mark.strip(),
    ]
    search_text = " ".join(part for part in search_parts if part and part != "-")

    return {
        "operation_label": operation_label,
        "category": category,
        "category_label": category_label,
        "summary": summary,
        "secondary_text": secondary_text,
        "locator_text": _locator_text(node),
        "region_text": node.region_text.strip() or "-",
        "timing_text": _timing_text(node),
        "branch_text": branch_text,
        "search_text": search_text,
    }


def summarize_node(node: OperationNode) -> str:
    return str(build_node_row_view(node)["summary"])


def _summary_text(node: OperationNode) -> str:
    operation = node.operation
    if operation == OperationType.CLICK.value:
        return f"点击鼠标 {_default_text(node.param_text, 'left')}"
    if operation == OperationType.MOUSE_DOWN.value:
        return f"按下鼠标 {_default_text(node.param_text, 'left')}"
    if operation == OperationType.MOUSE_UP.value:
        return f"松开鼠标 {_default_text(node.param_text, 'left')}"
    if operation == OperationType.MOVE_REL.value:
        return f"相对移动 {_default_text(node.param_text, '(未设置)')}"
    if operation == OperationType.MOVE_TO.value:
        return f"绝对移动 {_default_text(node.param_text, '(未设置)')}"
    if operation == OperationType.PRESS.value:
        return f"按键 {_default_text(node.param_text, '(未设置)')}"
    if operation == OperationType.KEY_DOWN.value:
        return f"按下键 {_default_text(node.param_text, '(未设置)')}"
    if operation == OperationType.KEY_UP.value:
        return f"松开键 {_default_text(node.param_text, '(未设置)')}"
    if operation == OperationType.WRITE.value:
        return f"输入文本 {_default_text(node.param_text, '(空)')}"
    if operation == OperationType.NOTIFY.value:
        return f"通知 {_default_text(node.param_text, '(空)')}"
    if operation == OperationType.JUMP.value:
        return f"跳转到 {_default_text(node.param_text, '(未设置)')}"
    if operation == OperationType.PIC.value:
        return f"识图 {_default_text(node.search_target, '(未设置)')}"
    if operation == OperationType.OCR.value:
        return f"OCR 识别 {_default_text(node.search_target, '(未设置)')}"
    return f"未知操作 {_default_text(node.operation, '(空)')}"


def _secondary_text(node: OperationNode, branch_text: str) -> str:
    if node.note.strip():
        return node.note.strip()
    if node.jump_mark.strip():
        return f"标记 {node.jump_mark.strip()}"
    if node.confidence_text.strip():
        return f"置信度 {node.confidence_text.strip()}"
    if branch_text != "-":
        return branch_text
    return "-"


def _locator_text(node: OperationNode) -> str:
    if node.operation == OperationType.JUMP.value:
        return _default_text(node.param_text, "(未设置)")

    if node.operation in {OperationType.PIC.value, OperationType.OCR.value} and node.branch.is_enabled:
        if node.branch.mode is BranchMode.JUMP_PAIR:
            exist_target, not_exist_target = _branch_jump_pair_targets(node)
            return f"exist-> {exist_target} · notExist-> {not_exist_target}"
        if node.branch.mode is BranchMode.SUBFLOW:
            subflow_target = _default_text(node.branch.primary_target, "(未设置)")
            return f"启动 {subflow_target}"

    if node.search_target.strip():
        return node.search_target.strip()
    if node.param_text.strip():
        return node.param_text.strip()
    return "(未设置)"


def _timing_text(node: OperationNode) -> str:
    wait_text = _pair_text(node.wait_value, node.wait_random)
    if node.operation in {OperationType.PIC.value, OperationType.OCR.value}:
        retry_text = _pair_text(node.retry_value, node.retry_random)
        return f"等待 {wait_text} · 重试 {retry_text}"
    return f"等待 {wait_text}"


def _branch_text(node: OperationNode) -> str:
    if not node.branch.is_enabled:
        return "-"

    trigger_text = _trigger_text(node.branch.trigger)
    primary_target = _default_text(node.branch.primary_target, "(未设置)")
    secondary_target = _default_text(node.branch.secondary_target, "(未设置)")

    if node.branch.mode is BranchMode.SUBFLOW:
        return f"{trigger_text}执行子流程 {primary_target}"
    if node.branch.mode is BranchMode.JUMP_PAIR:
        return f"{trigger_text}跳转 {primary_target}，否则跳转 {secondary_target}"
    return f"{trigger_text} -> {primary_target}"


def _branch_jump_pair_targets(node: OperationNode) -> tuple[str, str]:
    primary_target = _default_text(node.branch.primary_target, "(未设置)")
    secondary_target = _default_text(node.branch.secondary_target, "(未设置)")
    if node.branch.trigger is BranchTrigger.NOT_EXIST:
        return secondary_target, primary_target
    return primary_target, secondary_target


def _trigger_text(trigger: BranchTrigger) -> str:
    if trigger is BranchTrigger.EXIST:
        return "存在时"
    if trigger is BranchTrigger.NOT_EXIST:
        return "不存在时"
    return "命中时"


def _pair_text(first: str, second: str) -> str:
    first = first.strip()
    second = second.strip()
    if first and second:
        return f"{first};{second}"
    if first:
        return first
    return "-"


def _default_text(value: str, default: str) -> str:
    value = value.strip()
    return value or default
