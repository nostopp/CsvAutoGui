from __future__ import annotations

import csv
import os
from pathlib import Path
from threading import RLock

from operation_contracts import ParamKind, get_operation_contract

from csv_schema import (
    COL_CONFIDENCE,
    COL_DISABLE_GRAYSCALE,
    COL_INDEX,
    COL_JUMP_MARK,
    COL_MOVE_TIME,
    COL_NOTE,
    COL_OPERATION,
    COL_PARAM,
    COL_RANGE_RANDOM,
    COL_REGION,
    COL_RETRY,
    COL_SEARCH_TARGET,
    COL_WAIT,
)

from ..infrastructure.paths import logical_abs_path, resolve_config_relative_path
from ..infrastructure.scaling import ScaleHelper
from .models import CompiledFlow, CompiledOperation, RawFlow, RawOperation


def _optional_text(row: dict[str, str | None], key: str) -> str | None:
    value = row.get(key)
    return value if value else None


def _resolve_flow_path(
    config_dir: str | os.PathLike,
    file_name: str | os.PathLike,
    *,
    must_exist: bool = True,
) -> tuple[Path, Path, str]:
    resolved_config_dir = logical_abs_path(config_dir).resolve()
    resolved_path = resolve_config_relative_path(
        resolved_config_dir,
        file_name,
        must_exist=must_exist,
        allowed_suffixes=(".csv",),
    )
    normalized_file_name = resolved_path.relative_to(resolved_config_dir).as_posix()
    return resolved_config_dir, resolved_path, normalized_file_name


def read_raw_flow(
    config_dir: str | os.PathLike,
    file_name: str | os.PathLike = "main.csv",
) -> RawFlow:
    resolved_config_dir, resolved_path, normalized_file_name = _resolve_flow_path(
        config_dir,
        file_name,
    )
    operations: dict[int, RawOperation] = {}
    with resolved_path.open(mode="r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            index = int(row[COL_INDEX])
            operations[index] = RawOperation(
                index=index,
                operation=row[COL_OPERATION],
                param_text=_optional_text(row, COL_PARAM),
                wait_text=_optional_text(row, COL_WAIT),
                search_target=_optional_text(row, COL_SEARCH_TARGET),
                region_text=_optional_text(row, COL_REGION),
                confidence_text=_optional_text(row, COL_CONFIDENCE),
                retry_text=_optional_text(row, COL_RETRY),
                range_random_text=_optional_text(row, COL_RANGE_RANDOM),
                move_time_text=_optional_text(row, COL_MOVE_TIME),
                jump_mark=_optional_text(row, COL_JUMP_MARK),
                disable_grayscale_text=_optional_text(
                    row,
                    COL_DISABLE_GRAYSCALE,
                ),
                note=_optional_text(row, COL_NOTE),
            )
    return RawFlow(
        config_dir=resolved_config_dir,
        file_name=normalized_file_name,
        operations=tuple(operations.values()),
    )


class RawFlowCache:
    def __init__(self) -> None:
        self._flows: dict[tuple[str, str], RawFlow] = {}
        self._lock = RLock()

    def get(
        self,
        config_dir: str | os.PathLike,
        file_name: str | os.PathLike = "main.csv",
    ) -> RawFlow:
        resolved_config_dir, _, normalized_file_name = _resolve_flow_path(
            config_dir,
            file_name,
            must_exist=False,
        )
        cache_key = (
            os.path.normcase(os.fspath(resolved_config_dir)),
            os.path.normcase(normalized_file_name),
        )
        with self._lock:
            cached = self._flows.get(cache_key)
            if cached is not None:
                return cached
            raw_flow = read_raw_flow(resolved_config_dir, normalized_file_name)
            self._flows[cache_key] = raw_flow
            return raw_flow

    def clear(self) -> None:
        with self._lock:
            self._flows.clear()


raw_flow_cache = RawFlowCache()


def load_raw_flow(
    config_dir: str | os.PathLike,
    file_name: str | os.PathLike = "main.csv",
) -> RawFlow:
    return raw_flow_cache.get(config_dir, file_name)


def clear_raw_flow_cache() -> None:
    raw_flow_cache.clear()


def parse_operation_param(
    param: str,
    operation: str,
    scale_helper: ScaleHelper,
):
    contract = get_operation_contract(operation)
    if contract is None:
        return None

    if contract.param_kind in {
        ParamKind.MOUSE_BUTTON,
        ParamKind.KEY,
        ParamKind.TEXT,
    }:
        return param
    if contract.param_kind is ParamKind.JUMP_TARGET:
        try:
            return int(param)
        except Exception:
            return param
    if contract.param_kind is ParamKind.RECOGNITION_BRANCH:
        parts: list[object] = param.split(";")
        if len(parts) == 3:
            for index in (1, 2):
                try:
                    parts[index] = int(parts[index])
                except Exception:
                    pass
        return tuple(parts)
    if contract.param_kind in {
        ParamKind.SCRIPT_REFERENCE,
        ParamKind.RESOURCE_DECLARATION,
    }:
        return tuple(part.strip() for part in param.split(";"))
    if contract.param_kind is ParamKind.COORDINATE_PAIR:
        parts = param.split(";")
        return (
            scale_helper.getScaleInt(int(parts[0])),
            scale_helper.getScaleInt(int(parts[1])),
        )
    return None


def _parse_timing(value: str | None) -> tuple[float | None, float | None]:
    if value is None:
        return None, None
    if ";" not in value:
        return float(value), None
    parts = value.split(";")
    return float(parts[0]), float(parts[1])


def compile_flow(raw_flow: RawFlow, scale_helper: ScaleHelper) -> CompiledFlow:
    operations: list[CompiledOperation] = []
    for raw in raw_flow.operations:
        wait, wait_random = _parse_timing(raw.wait_text)
        retry, retry_random = _parse_timing(raw.retry_text)
        region = None
        if raw.region_text is not None:
            parts = raw.region_text.split(";")
            region = scale_helper.getScaleRegion(
                (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
            )
        operations.append(
            CompiledOperation(
                index=raw.index,
                operation=raw.operation,
                operate_param=(
                    None
                    if raw.param_text is None
                    else parse_operation_param(
                        raw.param_text,
                        raw.operation,
                        scale_helper,
                    )
                ),
                wait=wait,
                wait_random=wait_random,
                search_target=raw.search_target,
                region=region,
                confidence=(
                    None
                    if raw.confidence_text is None
                    else float(raw.confidence_text)
                ),
                retry=retry,
                retry_random=retry_random,
                range_random=(
                    raw.range_random_text is not None
                    and int(raw.range_random_text) == 1
                ),
                move_time=(
                    None
                    if raw.move_time_text is None
                    else float(raw.move_time_text)
                ),
                jump_mark=raw.jump_mark,
                disable_grayscale=(
                    raw.disable_grayscale_text is not None
                    and int(raw.disable_grayscale_text) == 1
                ),
                note=raw.note,
            )
        )
    return CompiledFlow(raw_flow.file_name, tuple(operations))
