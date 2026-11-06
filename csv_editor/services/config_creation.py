"""Validate and create a new configuration without touching the active document."""
from __future__ import annotations

import json
import math
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autogui.infrastructure.paths import display_config_path, logical_abs_path
from autogui.runtime.schedule import parse_run_pause_settings
from csv_editor.domain.models import FlowDocument
from csv_editor.io.csv_codec import CsvEditorCodec
from run_parameters import default_run_parameters


@dataclass(frozen=True)
class ConfigCreationPlan:
    target: Path
    parameters: dict[str, Any]


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON 不允许非有限数值：{value}")


def prepare_config_creation(
    parent: Path, name: str, source_json: Path | None = None,
) -> ConfigCreationPlan:
    parent = logical_abs_path(parent)
    if not parent.is_dir():
        raise ValueError("请选择一个已存在的存放目录。")
    if (not name or name in {".", ".."} or name != name.strip()
            or name.endswith(".") or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
            or Path(name).is_reserved()):
        raise ValueError("配置名称必须是有效的 Windows 目录名，不能包含路径分隔符或首尾空格。")
    if name.casefold() == "runtime":
        raise ValueError("请使用其他配置名称：runtime.json 是 watchdog 和通知策略的保留文件名。")
    target = parent / name
    if target.exists() or target.is_symlink():
        raise ValueError(f"目标已存在，请修改配置名称：{target}")

    parameters = default_run_parameters()
    if source_json is not None:
        try:
            with source_json.open(encoding="utf-8-sig") as handle:
                source = json.load(handle, parse_constant=_reject_json_constant)
        except (OSError, ValueError) as exc:
            raise ValueError(f"无法读取来源 JSON：{exc}") from exc
        if (not isinstance(source, dict) or not parameters.keys() & source.keys()
                or {"watchdog", "on_stall_unresolved", "notification"} & source.keys()):
            raise ValueError("请选择 Manager 保存的运行参数 JSON，不能使用 runtime.json 或其他 JSON。")
        # Retain template extensions as well as known fields; only config is replaced.
        parameters.update(source)
        for key, default in default_run_parameters().items():
            value = parameters[key]
            if key == "config":
                continue
            if isinstance(default, bool):
                valid = isinstance(value, bool)
            elif key == "scale":
                try:
                    valid = (type(value) in (int, float) and math.isfinite(value) and value > 0)
                except OverflowError:
                    valid = False
            elif key == "title":
                valid = value is None or isinstance(value, str)
            else:
                valid = isinstance(value, str)
            if not valid:
                raise ValueError(f"来源 JSON 中的 {key} 字段类型或取值无效。")
        parse_run_pause_settings(parameters["run_duration"], parameters["pause_duration"])
    parameters["config"] = display_config_path(target)
    return ConfigCreationPlan(target, parameters)


def create_config(plan: ConfigCreationPlan, codec: CsvEditorCodec) -> Path:
    """Stage both files, then publish the directory. Existing targets are never merged."""
    if plan.target.exists() or plan.target.is_symlink():
        raise ValueError(f"目标已存在，请修改配置名称：{plan.target}")
    # tempfile.mkdtemp/TemporaryDirectory use mode 0o700 on Windows: an
    # elevated editor would pass administrator-only ACLs on to the final config.
    # A normal sibling mkdir inherits the same permissions as the target parent.
    staged = plan.target.parent / f".csvautogui-{uuid.uuid4().hex}"
    staged.mkdir()
    try:
        codec.save_flow(staged / "main.csv", FlowDocument(filename="main.csv"))
        with (staged / f"{plan.target.name}.json").open("x", encoding="utf-8") as handle:
            json.dump(plan.parameters, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        # On Windows rename fails if the destination exists, including empty directories.
        staged.rename(plan.target)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return plan.target
