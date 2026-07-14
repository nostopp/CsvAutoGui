from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Collection


class ChangeImpact(StrEnum):
    DISPLAY_ONLY = "display_only"
    NODE_VALIDATION = "node_validation"
    REFERENCE_GRAPH = "reference_graph"
    FLOW_STRUCTURE = "flow_structure"
    DOCUMENT_STRUCTURE = "document_structure"


@dataclass(frozen=True, slots=True)
class EditorChangeSet:
    impact: ChangeImpact
    flow_name: str | None = None
    node_ids: frozenset[str] = frozenset()
    changed_fields: frozenset[str] = frozenset()
    selected_node_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_ids", frozenset(self.node_ids))
        object.__setattr__(self, "changed_fields", frozenset(self.changed_fields))


_DISPLAY_ONLY_FIELDS = frozenset({"note"})
_NODE_VALIDATION_FIELDS = frozenset(
    {
        "wait_value",
        "wait_random",
        "move_time",
        "search_target",
        "region_text",
        "confidence_text",
        "retry_value",
        "retry_random",
        "pic_range_random",
        "disable_grayscale",
        "raw_extra",
    }
)
_REFERENCE_GRAPH_FIELDS = frozenset(
    {
        "operation",
        "jump_mark",
        "branch.trigger",
        "branch.mode",
        "branch.primary_target",
        "branch.secondary_target",
    }
)
_REFERENCE_PARAM_OPERATIONS = frozenset({"jmp", "script", "resource"})


def change_impact_for_fields(
    changed_fields: Collection[str],
    *,
    operation: str | None = None,
) -> ChangeImpact:
    fields = frozenset(changed_fields)
    unknown_fields = fields - (
        _DISPLAY_ONLY_FIELDS
        | _NODE_VALIDATION_FIELDS
        | _REFERENCE_GRAPH_FIELDS
        | {"param_text"}
    )
    if unknown_fields:
        names = ", ".join(sorted(unknown_fields))
        raise ValueError(f"未定义字段影响级别: {names}")

    if fields & _REFERENCE_GRAPH_FIELDS:
        return ChangeImpact.REFERENCE_GRAPH
    if "param_text" in fields and operation in _REFERENCE_PARAM_OPERATIONS:
        return ChangeImpact.REFERENCE_GRAPH
    if fields & (_NODE_VALIDATION_FIELDS | {"param_text"}):
        return ChangeImpact.NODE_VALIDATION
    return ChangeImpact.DISPLAY_ONLY
