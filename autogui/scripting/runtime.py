import hashlib
import importlib.util
import os
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pyautogui
from operation_contracts import OperationType, require_operation_contract

from ..infrastructure import log
from ..infrastructure.paths import resolve_config_relative_path
from ..runtime.context import RuntimeContext
from ..vision.ocr import OCR
from .resources import ResourceSpec


_script_cache: dict[str, ModuleType] = {}
OperationDict = dict[str, Any]
JumpResolver = Callable[[int | str], int]
SubflowStarter = Callable[[str], None]
PIC_DEFAULT_CONFIDENCE = require_operation_contract(OperationType.PIC).default_confidence
OCR_DEFAULT_CONFIDENCE = require_operation_contract(OperationType.OCR).default_confidence


def clear_script_cache() -> None:
    _script_cache.clear()


def _parse_script_target(operate_param: object) -> tuple[str, str | None, bool]:
    if isinstance(operate_param, tuple):
        parts = tuple(str(part).strip() for part in operate_param)
    else:
        parts = ()

    if len(parts) < 1 or len(parts) > 2:
        raise ValueError("script 节点参数错误，应为 script.py 或 script.py;xxx_resource.csv")

    script_name = parts[0]
    if not script_name or not script_name.endswith(".py"):
        raise ValueError(f"script 节点脚本文件必须是 .py: {script_name}")

    if len(parts) == 2:
        resource_name = parts[1]
        if not resource_name or not resource_name.endswith("_resource.csv"):
            raise ValueError(f"script 节点资源文件必须以 _resource.csv 结尾: {resource_name}")
        return script_name, resource_name, True

    resource_name = f"{Path(script_name).stem}_resource.csv"
    return script_name, resource_name, False


def _load_script_module(script_path: Path) -> ModuleType:
    cache_key = os.fspath(script_path)
    if cache_key in _script_cache:
        return _script_cache[cache_key]

    module_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()
    module_name = f"autogui_script_{module_hash}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载脚本模块: {script_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_func = getattr(module, "run", None)
    if not callable(run_func):
        raise AttributeError(f"脚本缺少固定入口 run(ctx): {script_path.name}")

    _script_cache[cache_key] = module
    return module


class ScriptContext:
    def __init__(
        self,
        runtime_context: RuntimeContext,
        node: OperationDict,
        resources: dict[str, ResourceSpec],
        jump_resolver: JumpResolver,
        subflow_starter: SubflowStarter,
    ) -> None:
        self.config_dir = os.fspath(runtime_context.config_dir)
        self.node = node
        self.input = runtime_context.input
        self.scale_helper = runtime_context.scale_helper
        self.log = log
        self.state = runtime_context.state
        self.resources = resources
        self._jump_resolver = jump_resolver
        self._subflow_starter = subflow_starter
        self._runtime_context = runtime_context
        self._config_dir_path = runtime_context.config_dir

    def _report_observation(self, detail: str) -> None:
        self.input.record_observation(detail, source="script_ctx")

    def resolve_path(self, path: str) -> Path:
        return resolve_config_relative_path(self.config_dir, path)

    def get_resource(self, name: str) -> ResourceSpec:
        if name not in self.resources:
            raise KeyError(f"未找到资源变量: {name}")
        return self.resources[name]

    def get_jump_target(self, name: str) -> int | str:
        resource = self.get_resource(name)
        if resource.kind != "jmp":
            raise ValueError(f"资源 {name} 不是 jmp 类型")
        return resource.jump_target

    def resolve_jump_target(self, target: int | str) -> int:
        return self._jump_resolver(target)

    def start_subflow(self, file_name: str) -> None:
        relative_path = self.resolve_path(file_name).relative_to(self._config_dir_path).as_posix()
        self._subflow_starter(relative_path)

    def _load_image(self, name: str):
        return self._runtime_context.get_image(name)

    def find_image(self, resource: str | None = None, name: str | None = None, region=None, confidence: float | None = None, grayscale=None):
        self._report_observation("find_image")
        resource_spec = self.get_resource(resource) if resource is not None else None
        if resource_spec is not None and resource_spec.kind != "pic":
            raise ValueError(f"资源 {resource} 不是 pic 类型")

        search_name = name if name is not None else None if resource_spec is None else resource_spec.search_target
        if not search_name:
            raise ValueError("find_image 需要 resource 或 name")

        search_region = region if region is not None else None if resource_spec is None else resource_spec.region
        search_confidence = confidence if confidence is not None else PIC_DEFAULT_CONFIDENCE if resource_spec is None or resource_spec.confidence is None else resource_spec.confidence
        search_grayscale = grayscale if grayscale is not None else False if resource_spec is not None and resource_spec.disable_grayscale else None
        image = self._load_image(search_name)

        try:
            center = self.input.locateCenterOnScreen(
                image,
                confidence=search_confidence,
                region=search_region,
                grayscale=search_grayscale,
            )
        except pyautogui.ImageNotFoundException:
            return None

        if center is None:
            return None

        return SimpleNamespace(
            x=center.x,
            y=center.y,
            center_x=center.x,
            center_y=center.y,
            width=image.shape[1],
            height=image.shape[0],
            confidence=getattr(self.input, "_last_locate_confidence", None),
        )

    def find_text(self, resource: str | None = None, text: str | None = None, region=None, confidence: float | None = None):
        self._report_observation("find_text")
        resource_spec = self.get_resource(resource) if resource is not None else None
        if resource_spec is not None and resource_spec.kind != "ocr":
            raise ValueError(f"资源 {resource} 不是 ocr 类型")

        search_text = text if text is not None else None if resource_spec is None else resource_spec.search_target
        if not search_text:
            raise ValueError("find_text 需要 resource 或 text")

        search_region = region if region is not None else None if resource_spec is None else resource_spec.region
        search_confidence = confidence if confidence is not None else OCR_DEFAULT_CONFIDENCE if resource_spec is None or resource_spec.confidence is None else resource_spec.confidence
        x_center, y_center, width, height = OCR(search_text, self.input, search_region, search_confidence)
        if x_center is None or y_center is None:
            return None

        return SimpleNamespace(
            x=x_center,
            y=y_center,
            center_x=x_center,
            center_y=y_center,
            width=width,
            height=height,
            confidence=search_confidence,
        )

    def screenshot(self, region=None):
        image = self.input.screenShot()
        if region is None:
            return image

        converted_region = self.input.convertFindRegion(region)
        return image[
            converted_region[1] : converted_region[1] + converted_region[3],
            converted_region[0] : converted_region[0] + converted_region[2],
        ]

    def sleep(self, seconds: float) -> None:
        self._report_observation("sleep")
        time.sleep(seconds)


class ScriptBase:
    def __init__(self, ctx: ScriptContext) -> None:
        self.ctx = ctx

    def jump(self, target: int | str):
        resolved_target = self.ctx.resolve_jump_target(target)
        return None, lambda _: resolved_target, None

    def jump_resource(self, name: str):
        return self.jump(self.ctx.get_jump_target(name))

    def next_step(self):
        return None, None, None

    def start_subflow(self, file_name: str):
        self.ctx.start_subflow(file_name)
        return self.next_step()


def execute_script_node(
    operation: OperationDict,
    runtime_context: RuntimeContext,
    jump_resolver: JumpResolver,
    subflow_starter: SubflowStarter,
):
    script_name, resource_name, explicit_resource = _parse_script_target(operation.get("operate_param"))
    script_path = resolve_config_relative_path(runtime_context.config_dir, script_name)

    try:
        module = _load_script_module(script_path)
        resources = runtime_context.get_resources(resource_name, explicit_resource)
        ctx = ScriptContext(
            runtime_context,
            operation,
            resources,
            jump_resolver,
            subflow_starter,
        )
        if runtime_context.print_log:
            resource_text = resource_name if resources or explicit_resource else "无"
            log.debug(f"执行脚本 {script_name}, 资源文件: {resource_text}")

        result = module.run(ctx)
    except Exception:
        log.error(f"执行脚本 {script_path.name} 失败\n{traceback.format_exc()}")
        raise

    if result is None:
        return None, None, None

    if not isinstance(result, tuple) or len(result) != 3:
        raise TypeError(f"脚本 {script_path.name} 返回值必须是长度为 3 的元组")

    return result
