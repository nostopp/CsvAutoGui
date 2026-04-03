from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .enums import BranchMode, BranchTrigger, OperationType, ValidationSeverity


@dataclass(slots=True)
class BranchConfig:
    trigger: BranchTrigger = BranchTrigger.NONE
    mode: BranchMode = BranchMode.NONE
    primary_target: str = ""
    secondary_target: str = ""

    @property
    def is_enabled(self) -> bool:
        return self.trigger is not BranchTrigger.NONE and self.mode is not BranchMode.NONE

    def clone(self) -> "BranchConfig":
        return BranchConfig(
            trigger=self.trigger,
            mode=self.mode,
            primary_target=self.primary_target,
            secondary_target=self.secondary_target,
        )


@dataclass(slots=True)
class OperationNode:
    operation: str
    node_id: str = field(default_factory=lambda: uuid4().hex)
    index: int = 0
    param_text: str = ""
    wait_value: str = ""
    wait_random: str = ""
    search_target: str = ""
    region_text: str = ""
    confidence_text: str = ""
    retry_value: str = ""
    retry_random: str = ""
    pic_range_random: bool = False
    move_time: str = ""
    jump_mark: str = ""
    disable_grayscale: bool = False
    note: str = ""
    branch: BranchConfig = field(default_factory=BranchConfig)
    raw_extra: dict[str, str] = field(default_factory=dict)

    @property
    def operation_type(self) -> OperationType | None:
        try:
            return OperationType(self.operation)
        except ValueError:
            return None

    def clone(self) -> "OperationNode":
        return OperationNode(
            operation=self.operation,
            node_id=self.node_id,
            index=self.index,
            param_text=self.param_text,
            wait_value=self.wait_value,
            wait_random=self.wait_random,
            search_target=self.search_target,
            region_text=self.region_text,
            confidence_text=self.confidence_text,
            retry_value=self.retry_value,
            retry_random=self.retry_random,
            pic_range_random=self.pic_range_random,
            move_time=self.move_time,
            jump_mark=self.jump_mark,
            disable_grayscale=self.disable_grayscale,
            note=self.note,
            branch=self.branch.clone(),
            raw_extra=dict(self.raw_extra),
        )

    def apply_from(self, other: "OperationNode") -> None:
        self.operation = other.operation
        self.param_text = other.param_text
        self.wait_value = other.wait_value
        self.wait_random = other.wait_random
        self.search_target = other.search_target
        self.region_text = other.region_text
        self.confidence_text = other.confidence_text
        self.retry_value = other.retry_value
        self.retry_random = other.retry_random
        self.pic_range_random = other.pic_range_random
        self.move_time = other.move_time
        self.jump_mark = other.jump_mark
        self.disable_grayscale = other.disable_grayscale
        self.note = other.note
        self.branch = other.branch.clone()
        self.raw_extra = dict(other.raw_extra)


@dataclass(slots=True)
class FlowDocument:
    filename: str
    nodes: list[OperationNode] = field(default_factory=list)

    def reindex(self) -> None:
        for i, node in enumerate(self.nodes, start=1):
            node.index = i

    def get_node(self, node_id: str) -> OperationNode | None:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def jump_marks(self) -> dict[str, int]:
        return {node.jump_mark: node.index for node in self.nodes if node.jump_mark}


@dataclass(slots=True)
class EditorState:
    selected_flow: str = "main.csv"
    selected_node_id: str | None = None


@dataclass(slots=True)
class EditorDocument:
    root_path: Path
    flows: list[FlowDocument] = field(default_factory=list)
    state: EditorState = field(default_factory=EditorState)

    def get_flow(self, filename: str) -> FlowDocument | None:
        for flow in self.flows:
            if flow.filename == filename:
                return flow
        return None

    def ensure_main_first(self) -> None:
        self.flows.sort(key=lambda flow: (flow.filename != "main.csv", flow.filename.lower()))

    def iter_flow_filenames(self) -> Iterable[str]:
        for flow in self.flows:
            yield flow.filename


@dataclass(slots=True)
class ValidationIssue:
    severity: ValidationSeverity
    flow_name: str
    node_id: str | None
    message: str
