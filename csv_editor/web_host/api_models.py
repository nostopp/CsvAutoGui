from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

JsonDict = dict[str, object]
T = TypeVar("T")


@dataclass(slots=True)
class ApiError:
    code: str
    message: str
    details: JsonDict | None = None

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(slots=True)
class ApiResult(Generic[T]):
    ok: bool
    data: T | None = None
    error: ApiError | None = None

    @classmethod
    def success(cls, data: T) -> "ApiResult[T]":
        return cls(ok=True, data=data)

    @classmethod
    def failure(
        cls,
        code: str,
        message: str,
        details: JsonDict | None = None,
    ) -> "ApiResult[object]":
        return cls(ok=False, error=ApiError(code=code, message=message, details=details))

    def to_dict(self) -> JsonDict:
        if self.ok:
            return {
                "ok": True,
                "data": self.data,
            }
        return {
            "ok": False,
            "error": self.error.to_dict() if self.error else {"code": "unknown_error", "message": "Unknown error"},
        }
