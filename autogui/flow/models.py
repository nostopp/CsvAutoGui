from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class RawOperation:
    index: int
    operation: str
    param_text: str | None = None
    wait_text: str | None = None
    search_target: str | None = None
    region_text: str | None = None
    confidence_text: str | None = None
    retry_text: str | None = None
    range_random_text: str | None = None
    move_time_text: str | None = None
    jump_mark: str | None = None
    disable_grayscale_text: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class RawFlow:
    config_dir: Path
    file_name: str
    operations: tuple[RawOperation, ...]


@dataclass(frozen=True, slots=True)
class CompiledOperation:
    index: int
    operation: str
    operate_param: object | None = None
    wait: float | None = None
    wait_random: float | None = None
    search_target: str | None = None
    region: tuple[int, int, int, int] | None = None
    confidence: float | None = None
    retry: float | None = None
    retry_random: float | None = None
    range_random: bool = False
    move_time: float | None = None
    jump_mark: str | None = None
    disable_grayscale: bool = False
    note: str | None = None

    def to_script_node_dict(self) -> dict[str, object]:
        operation: dict[str, object] = {
            "index": self.index,
            "operate": self.operation,
        }
        if self.operate_param is not None:
            operation["operate_param"] = self.operate_param
        if self.wait is not None:
            operation["wait"] = self.wait
        if self.wait_random is not None:
            operation["wait_random"] = self.wait_random
        if self.search_target is not None:
            operation["search_pic"] = self.search_target
        if self.region is not None:
            operation["pic_region"] = self.region
        if self.confidence is not None:
            operation["confidence"] = self.confidence
        if self.retry is not None:
            operation["pic_retry_time"] = self.retry
        if self.retry_random is not None:
            operation["pic_retry_time_random"] = self.retry_random
        if self.range_random:
            operation["pic_range_random"] = True
        if self.move_time is not None:
            operation["move_time"] = self.move_time
        if self.jump_mark is not None:
            operation["jump_mark"] = self.jump_mark
        if self.disable_grayscale:
            operation["disable_grayscale"] = True
        return operation

@dataclass(frozen=True, slots=True)
class CompiledFlow:
    file_name: str
    operations: tuple[CompiledOperation, ...]
    operations_by_index: Mapping[int, CompiledOperation] = field(init=False, repr=False)
    jump_marks: Mapping[str, int] = field(init=False)

    def __post_init__(self) -> None:
        operations_by_index = {operation.index: operation for operation in self.operations}
        jump_marks = {
            operation.jump_mark: operation.index
            for operation in self.operations
            if operation.jump_mark is not None
        }
        object.__setattr__(
            self,
            "operations_by_index",
            MappingProxyType(operations_by_index),
        )
        object.__setattr__(self, "jump_marks", MappingProxyType(jump_marks))

    def __len__(self) -> int:
        return len(self.operations_by_index)
