from dataclasses import dataclass
from pathlib import Path

from ..flow.models import CompiledFlow
from ..infrastructure.paths import resolve_config_relative_path


@dataclass(frozen=True)
class ResourceSpec:
    kind: str
    name: str
    search_target: str | None = None
    region: tuple[int, int, int, int] | None = None
    confidence: float | None = None
    jump_target: int | str | None = None
    disable_grayscale: bool = False


def _resolve_resource_path(config_path: str, file_name: str) -> Path:
    try:
        return resolve_config_relative_path(config_path, file_name)
    except ValueError as exc:
        path = Path(file_name)
        if path.is_absolute() or path.drive:
            raise ValueError(f"资源文件只支持相对配置目录路径: {file_name}") from exc
        raise ValueError(f"资源文件路径超出配置目录: {file_name}") from exc


def _parse_jump_target(value: str) -> int | str:
    try:
        return int(value)
    except Exception:
        return value


def build_resource_specs(
    compiled_flow: CompiledFlow,
    file_name: str | None = None,
) -> dict[str, ResourceSpec]:
    resource_name = file_name or compiled_flow.file_name
    resources: dict[str, ResourceSpec] = {}
    for index, operation in compiled_flow.operations_by_index.items():
        if operation.operation != "resource":
            raise ValueError(f"{resource_name} 第 {index} 行不是 resource 节点")

        operate_param = operation.operate_param
        if not isinstance(operate_param, tuple) or len(operate_param) != 2:
            raise ValueError(f"{resource_name} 第 {index} 行 resource 参数错误")

        kind, alias = operate_param
        if kind not in ("pic", "ocr", "jmp") or not alias:
            raise ValueError(f"{resource_name} 第 {index} 行 resource 参数错误")
        if alias in resources:
            raise ValueError(f"{resource_name} 中存在重复资源变量名: {alias}")

        if kind == "jmp":
            jump_target = operation.jump_mark
            if jump_target is None or jump_target == "":
                raise ValueError(f"{resource_name} 第 {index} 行 jmp 资源缺少跳转目标")
            resources[alias] = ResourceSpec(
                kind,
                alias,
                jump_target=_parse_jump_target(jump_target),
            )
            continue

        search_target = operation.search_target
        if search_target is None or search_target == "":
            raise ValueError(f"{resource_name} 第 {index} 行 {kind} 资源缺少目标名称")

        resources[alias] = ResourceSpec(
            kind,
            alias,
            search_target=search_target,
            region=operation.region,
            confidence=operation.confidence,
            disable_grayscale=operation.disable_grayscale,
        )
    return resources
