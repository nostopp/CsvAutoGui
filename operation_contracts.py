from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


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
    SCRIPT = "script"
    RESOURCE = "resource"
    NOTIFY = "notify"
    JUMP = "jmp"


class OperationCategory(StrEnum):
    MOUSE = "mouse"
    KEYBOARD = "keyboard"
    RECOGNITION = "recognition"
    CONTROL_FLOW = "control_flow"
    SCRIPT = "script"
    RESOURCE = "resource"
    NOTIFICATION = "notification"


class ParamKind(StrEnum):
    MOUSE_BUTTON = "mouse_button"
    COORDINATE_PAIR = "coordinate_pair"
    KEY = "key"
    TEXT = "text"
    RECOGNITION_BRANCH = "recognition_branch"
    SCRIPT_REFERENCE = "script_reference"
    RESOURCE_DECLARATION = "resource_declaration"
    JUMP_TARGET = "jump_target"


class OperationField(StrEnum):
    PARAM = "param_text"
    WAIT = "wait_value"
    WAIT_RANDOM = "wait_random"
    SEARCH_TARGET = "search_target"
    REGION = "region_text"
    CONFIDENCE = "confidence_text"
    RETRY = "retry_value"
    RETRY_RANDOM = "retry_random"
    RANGE_RANDOM = "pic_range_random"
    MOVE_TIME = "move_time"
    JUMP_MARK = "jump_mark"
    DISABLE_GRAYSCALE = "disable_grayscale"
    NOTE = "note"
    BRANCH = "branch"


@dataclass(frozen=True, slots=True)
class OperationContract:
    operation: OperationType
    category: OperationCategory
    param_kind: ParamKind
    param_required: bool
    allowed_in_normal_flow: bool
    allowed_in_resource_flow: bool
    supports_branch: bool
    supported_fields: frozenset[OperationField]
    default_confidence: float | None = None


_COMMON_FIELDS = frozenset(
    {
        OperationField.PARAM,
        OperationField.WAIT,
        OperationField.WAIT_RANDOM,
        OperationField.MOVE_TIME,
        OperationField.JUMP_MARK,
        OperationField.NOTE,
    }
)
_RECOGNITION_FIELDS = _COMMON_FIELDS | frozenset(
    {
        OperationField.SEARCH_TARGET,
        OperationField.REGION,
        OperationField.CONFIDENCE,
        OperationField.RETRY,
        OperationField.RETRY_RANDOM,
        OperationField.RANGE_RANDOM,
        OperationField.BRANCH,
    }
)


def _contract(
    operation: OperationType,
    category: OperationCategory,
    param_kind: ParamKind,
    *,
    param_required: bool,
    normal: bool = True,
    resource: bool = False,
    branch: bool = False,
    fields: frozenset[OperationField] = _COMMON_FIELDS,
    confidence: float | None = None,
) -> OperationContract:
    return OperationContract(
        operation=operation,
        category=category,
        param_kind=param_kind,
        param_required=param_required,
        allowed_in_normal_flow=normal,
        allowed_in_resource_flow=resource,
        supports_branch=branch,
        supported_fields=fields,
        default_confidence=confidence,
    )


OPERATION_CONTRACTS: Mapping[OperationType, OperationContract] = MappingProxyType(
    {
        OperationType.CLICK: _contract(
            OperationType.CLICK,
            OperationCategory.MOUSE,
            ParamKind.MOUSE_BUTTON,
            param_required=False,
        ),
        OperationType.MOUSE_DOWN: _contract(
            OperationType.MOUSE_DOWN,
            OperationCategory.MOUSE,
            ParamKind.MOUSE_BUTTON,
            param_required=False,
        ),
        OperationType.MOUSE_UP: _contract(
            OperationType.MOUSE_UP,
            OperationCategory.MOUSE,
            ParamKind.MOUSE_BUTTON,
            param_required=False,
        ),
        OperationType.MOVE_REL: _contract(
            OperationType.MOVE_REL,
            OperationCategory.MOUSE,
            ParamKind.COORDINATE_PAIR,
            param_required=True,
        ),
        OperationType.MOVE_TO: _contract(
            OperationType.MOVE_TO,
            OperationCategory.MOUSE,
            ParamKind.COORDINATE_PAIR,
            param_required=True,
        ),
        OperationType.PRESS: _contract(
            OperationType.PRESS,
            OperationCategory.KEYBOARD,
            ParamKind.KEY,
            param_required=True,
        ),
        OperationType.KEY_DOWN: _contract(
            OperationType.KEY_DOWN,
            OperationCategory.KEYBOARD,
            ParamKind.KEY,
            param_required=True,
        ),
        OperationType.KEY_UP: _contract(
            OperationType.KEY_UP,
            OperationCategory.KEYBOARD,
            ParamKind.KEY,
            param_required=True,
        ),
        OperationType.WRITE: _contract(
            OperationType.WRITE,
            OperationCategory.KEYBOARD,
            ParamKind.TEXT,
            param_required=True,
        ),
        OperationType.PIC: _contract(
            OperationType.PIC,
            OperationCategory.RECOGNITION,
            ParamKind.RECOGNITION_BRANCH,
            param_required=False,
            branch=True,
            fields=_RECOGNITION_FIELDS | {OperationField.DISABLE_GRAYSCALE},
            confidence=0.8,
        ),
        OperationType.OCR: _contract(
            OperationType.OCR,
            OperationCategory.RECOGNITION,
            ParamKind.RECOGNITION_BRANCH,
            param_required=False,
            branch=True,
            fields=_RECOGNITION_FIELDS,
            confidence=0.9,
        ),
        OperationType.SCRIPT: _contract(
            OperationType.SCRIPT,
            OperationCategory.SCRIPT,
            ParamKind.SCRIPT_REFERENCE,
            param_required=True,
        ),
        OperationType.RESOURCE: _contract(
            OperationType.RESOURCE,
            OperationCategory.RESOURCE,
            ParamKind.RESOURCE_DECLARATION,
            param_required=True,
            normal=False,
            resource=True,
            fields=frozenset(
                {
                    OperationField.PARAM,
                    OperationField.SEARCH_TARGET,
                    OperationField.REGION,
                    OperationField.CONFIDENCE,
                    OperationField.JUMP_MARK,
                    OperationField.DISABLE_GRAYSCALE,
                    OperationField.NOTE,
                }
            ),
        ),
        OperationType.NOTIFY: _contract(
            OperationType.NOTIFY,
            OperationCategory.NOTIFICATION,
            ParamKind.TEXT,
            param_required=True,
        ),
        OperationType.JUMP: _contract(
            OperationType.JUMP,
            OperationCategory.CONTROL_FLOW,
            ParamKind.JUMP_TARGET,
            param_required=True,
        ),
    }
)


def get_operation_contract(
    value: str | OperationType,
) -> OperationContract | None:
    try:
        operation = value if isinstance(value, OperationType) else OperationType(value)
    except (TypeError, ValueError):
        return None
    return OPERATION_CONTRACTS.get(operation)


def require_operation_contract(
    value: str | OperationType,
) -> OperationContract:
    contract = get_operation_contract(value)
    if contract is None:
        raise ValueError(f"不支持的操作类型: {value}")
    return contract


def iter_operation_contracts(
    *,
    normal_flow: bool | None = None,
    resource_flow: bool | None = None,
) -> tuple[OperationContract, ...]:
    return tuple(
        contract
        for contract in OPERATION_CONTRACTS.values()
        if (
            normal_flow is None
            or contract.allowed_in_normal_flow is normal_flow
        )
        and (
            resource_flow is None
            or contract.allowed_in_resource_flow is resource_flow
        )
    )
