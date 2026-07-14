from __future__ import annotations

import os
from dataclasses import dataclass, field
from threading import Event, RLock
from types import MappingProxyType
from typing import Any

from ..flow.loader import compile_flow, load_raw_flow
from ..flow.models import CompiledFlow
from ..infrastructure.paths import logical_abs_path, resolve_config_relative_path
from ..infrastructure.scaling import ScaleHelper
from ..input.base import BaseInput


@dataclass(slots=True)
class RuntimeContext:
    config_dir: str | os.PathLike
    scale_helper: ScaleHelper
    input: BaseInput
    print_log: bool = False
    stop_event: Event | None = None
    state: dict[str, Any] = field(default_factory=dict)
    compiled_flows: dict[str, CompiledFlow] = field(default_factory=dict)
    image_cache: dict[str, Any] = field(default_factory=dict)
    resource_cache: dict[str, Any] = field(default_factory=dict)
    _cache_lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.config_dir = logical_abs_path(self.config_dir).resolve()
        if self.stop_event is None:
            self.stop_event = Event()

    def set_input(self, input_obj: BaseInput) -> None:
        self.input = input_obj

    def _flow_cache_key(self, file_name: str) -> str:
        resolved_path = resolve_config_relative_path(
            self.config_dir,
            file_name,
            allowed_suffixes=(".csv",),
        )
        relative_name = resolved_path.relative_to(self.config_dir).as_posix()
        return os.path.normcase(relative_name)

    def get_compiled_flow(self, file_name: str = "main.csv") -> CompiledFlow:
        cache_key = self._flow_cache_key(file_name)
        with self._cache_lock:
            compiled = self.compiled_flows.get(cache_key)
            if compiled is not None:
                return compiled

        raw_flow = load_raw_flow(self.config_dir, file_name)
        with self._cache_lock:
            compiled = self.compiled_flows.get(cache_key)
            if compiled is None:
                compiled = compile_flow(raw_flow, self.scale_helper)
                self.compiled_flows[cache_key] = compiled
            return compiled

    def get_image(self, relative_path: str | os.PathLike):
        resolved_path = resolve_config_relative_path(self.config_dir, relative_path)
        cache_key = os.path.normcase(os.fspath(resolved_path))
        with self._cache_lock:
            if cache_key not in self.image_cache:
                self.image_cache[cache_key] = self.scale_helper.getScaleImg(resolved_path)
            return self.image_cache[cache_key]

    def get_resources(self, file_name: str, required: bool = False) -> dict[str, Any]:
        from ..scripting.resources import _resolve_resource_path, build_resource_specs

        resource_path = _resolve_resource_path(os.fspath(self.config_dir), file_name)
        if not resource_path.exists():
            if required:
                raise FileNotFoundError(f"未找到资源文件: {resource_path}")
            return {}

        relative_name = resource_path.relative_to(self.config_dir).as_posix()
        cache_key = os.path.normcase(relative_name)
        with self._cache_lock:
            cached = self.resource_cache.get(cache_key)
            if cached is not None:
                return dict(cached)

        compiled_flow = self.get_compiled_flow(relative_name)
        resources = MappingProxyType(build_resource_specs(compiled_flow, relative_name))
        with self._cache_lock:
            cached = self.resource_cache.setdefault(cache_key, resources)
            return dict(cached)

    def reset_business_state(self) -> None:
        self.state = {}
