from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from csv_editor.domain.models import OperationNode


class WidgetKind(StrEnum):
    LINE_EDIT = "line_edit"
    CHECKBOX = "checkbox"
    COMBO = "combo"


@dataclass(frozen=True, slots=True)
class FieldBinding:
    field_name: str
    label: str
    widget_kind: WidgetKind
    getter: Callable[[OperationNode], object]
    normalizer: Callable[[object], object]
    expandable: bool = False


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _boolean(value: object) -> bool:
    return bool(value)


def _binding(
    field_name: str,
    label: str,
    widget_kind: WidgetKind = WidgetKind.LINE_EDIT,
    *,
    expandable: bool = False,
) -> FieldBinding:
    normalizer = _boolean if widget_kind is WidgetKind.CHECKBOX else _text
    return FieldBinding(
        field_name=field_name,
        label=label,
        widget_kind=widget_kind,
        getter=lambda node, name=field_name: getattr(node, name),
        normalizer=normalizer,
        expandable=expandable,
    )


FIELD_BINDINGS: Mapping[str, FieldBinding] = MappingProxyType(
    {
        "operation": _binding("operation", "操作类型", WidgetKind.COMBO),
        "param_text": _binding("param_text", "参数"),
        "wait_value": _binding("wait_value", "等待时间"),
        "wait_random": _binding("wait_random", "等待随机"),
        "move_time": _binding("move_time", "移动用时"),
        "note": _binding("note", "备注", expandable=True),
        "search_target": _binding("search_target", "识别目标", expandable=True),
        "region_text": _binding("region_text", "搜索区域", expandable=True),
        "confidence_text": _binding("confidence_text", "置信度"),
        "retry_value": _binding("retry_value", "重试时间"),
        "retry_random": _binding("retry_random", "重试随机"),
        "jump_mark": _binding("jump_mark", "跳转标记", expandable=True),
        "pic_range_random": _binding(
            "pic_range_random",
            "随机命中位置",
            WidgetKind.CHECKBOX,
        ),
        "disable_grayscale": _binding(
            "disable_grayscale",
            "禁用灰度匹配",
            WidgetKind.CHECKBOX,
        ),
    }
)


def get_field_binding(field_name: str) -> FieldBinding:
    return FIELD_BINDINGS[field_name]


def build_changed_fields(
    node: OperationNode,
    values: Mapping[str, object],
) -> dict[str, object]:
    changed_fields: dict[str, object] = {}
    for field_name, raw_value in values.items():
        binding = get_field_binding(field_name)
        normalized = binding.normalizer(raw_value)
        if normalized != binding.getter(node):
            changed_fields[field_name] = normalized
    return changed_fields
