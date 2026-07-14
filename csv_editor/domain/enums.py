from __future__ import annotations

from enum import StrEnum


class BranchMode(StrEnum):
    NONE = "none"
    SUBFLOW = "subflow"
    JUMP_PAIR = "jump_pair"


class BranchTrigger(StrEnum):
    NONE = "none"
    EXIST = "exist"
    NOT_EXIST = "notExist"


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
