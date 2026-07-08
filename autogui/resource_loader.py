import os
from dataclasses import dataclass
from pathlib import Path

from .config_paths import logical_abs_path
from .parser import GetCsv
from .scaleHelper import ScaleHelper


@dataclass(frozen=True)
class ResourceSpec:
    kind: str
    name: str
    search_target: str | None = None
    region: tuple[int, int, int, int] | None = None
    confidence: float | None = None
    jump_target: int | str | None = None
    disable_grayscale: bool = False


_resource_cache: dict[str, dict[str, ResourceSpec]] = {}


def clear_resource_cache():
    _resource_cache.clear()


def _resolve_resource_path(config_path: str, file_name: str) -> Path:
    path = Path(file_name)
    if path.is_absolute():
        raise ValueError(f"资源文件只支持相对配置目录路径: {file_name}")

    base_dir = logical_abs_path(config_path)
    resolved_path = logical_abs_path(path, base_dir)
    try:
        resolved_path.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError(f"资源文件路径超出配置目录: {file_name}") from exc
    try:
        resolved_path.resolve().relative_to(base_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"资源文件路径超出配置目录: {file_name}") from exc
    return resolved_path


def _parse_jump_target(value: str) -> int | str:
    try:
        return int(value)
    except Exception:
        return value


def load_resource_file(
    config_path: str,
    scale_helper: ScaleHelper,
    file_name: str,
    required: bool = False,
) -> dict[str, ResourceSpec]:
    resource_path = _resolve_resource_path(config_path, file_name)
    if not resource_path.exists():
        if required:
            raise FileNotFoundError(f"未找到资源文件: {resource_path}")
        return {}

    cache_key = os.fspath(resource_path)
    if cache_key in _resource_cache:
        return _resource_cache[cache_key]

    csv_data = GetCsv(config_path, scale_helper, file_name)
    resources: dict[str, ResourceSpec] = {}
    for index, operation in csv_data.items():
        if operation.get("operate") != "resource":
            raise ValueError(f"{file_name} 第 {index} 行不是 resource 节点")

        operate_param = operation.get("operate_param")
        if not isinstance(operate_param, tuple) or len(operate_param) != 2:
            raise ValueError(f"{file_name} 第 {index} 行 resource 参数错误")

        kind, alias = operate_param
        if kind not in ("pic", "ocr", "jmp") or not alias:
            raise ValueError(f"{file_name} 第 {index} 行 resource 参数错误")
        if alias in resources:
            raise ValueError(f"{file_name} 中存在重复资源变量名: {alias}")

        if kind == "jmp":
            jump_target = operation.get("jump_mark")
            if jump_target is None or jump_target == "":
                raise ValueError(f"{file_name} 第 {index} 行 jmp 资源缺少跳转目标")
            resources[alias] = ResourceSpec(kind, alias, jump_target=_parse_jump_target(jump_target))
            continue

        search_target = operation.get("search_pic")
        if search_target is None or search_target == "":
            raise ValueError(f"{file_name} 第 {index} 行 {kind} 资源缺少目标名称")

        resources[alias] = ResourceSpec(
            kind,
            alias,
            search_target=search_target,
            region=operation.get("pic_region"),
            confidence=operation.get("confidence"),
            disable_grayscale="disable_grayscale" in operation,
        )

    _resource_cache[cache_key] = resources
    return resources
