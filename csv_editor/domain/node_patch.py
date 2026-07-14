from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .enums import BranchMode, BranchTrigger
from .models import OperationNode


@dataclass(frozen=True, slots=True)
class NodePatch:
    node_id: str
    changed_fields: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "changed_fields",
            MappingProxyType(dict(self.changed_fields)),
        )


def apply_node_patch(node: OperationNode, patch: NodePatch) -> None:
    if node.node_id != patch.node_id:
        raise ValueError("NodePatch.node_id 与目标节点不一致")

    branch_fields = {
        "branch.trigger": "trigger",
        "branch.mode": "mode",
        "branch.primary_target": "primary_target",
        "branch.secondary_target": "secondary_target",
    }
    for field_name in patch.changed_fields:
        if field_name in branch_fields:
            continue
        if not hasattr(node, field_name):
            raise AttributeError(f"OperationNode 不存在字段: {field_name}")

    for field_name, value in patch.changed_fields.items():
        branch_attribute = branch_fields.get(field_name)
        if branch_attribute is None:
            setattr(node, field_name, value)
            continue
        if branch_attribute == "trigger" and not isinstance(value, BranchTrigger):
            value = BranchTrigger(value)
        elif branch_attribute == "mode" and not isinstance(value, BranchMode):
            value = BranchMode(value)
        setattr(node.branch, branch_attribute, value)
