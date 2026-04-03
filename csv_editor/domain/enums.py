from __future__ import annotations

from enum import StrEnum


class OperationType(StrEnum):
    CLICK = "click"
    MOUSE_DOWN = "mDown"
    MOUSE_UP = "mUp"
    MOVE_REL = "mMove"
    MOVE_TO = "mMoveTo"
    PRESS = "press"
    KEY_DOWN = "kDown"
    KEY_UP = "kUp"
    WRITE = "write"
    PIC = "pic"
    OCR = "ocr"
    NOTIFY = "notify"
    JUMP = "jmp"


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
