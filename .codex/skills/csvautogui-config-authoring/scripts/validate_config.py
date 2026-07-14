#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[4]
if os.fspath(REPO_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(REPO_ROOT))

from autogui.infrastructure.paths import resolve_config_relative_path
from autogui.runtime.config import RuntimeConfigResolver
from csv_editor.domain.models import EditorDocument, FlowDocument
from csv_editor.io.csv_codec import (
    CsvEditorCodec,
    infer_default_resource_filename,
    is_resource_flow_filename,
    parse_resource_param,
    parse_script_param,
)
from csv_editor.services.validation import validate_document, validate_flow
from csv_schema import (
    COL_DISABLE_GRAYSCALE,
    COL_INDEX,
    COL_JUMP_MARK,
    COL_OPERATION,
    COL_PARAM,
    COL_RANGE_RANDOM,
    COL_SEARCH_TARGET,
    CSV_COLUMNS,
)
from operation_contracts import OperationType, is_terminal_jump_target


PHASE_FINAL = "final"
PHASE_RESOURCES = "resources"
PHASE_RUNTIME = "runtime"
CANONICAL_SCRIPT_MODULE = "autogui.scripting.runtime"
FORBIDDEN_SCRIPT_MODULES = {
    "autogui.script_runtime",
    "autogui.flow.parser",
}
FORBIDDEN_SCRIPT_NAMES = {"GetCsv", "csvDataDict"}
FORBIDDEN_SCRIPT_CALLS = {"ScriptContext", "execute_script_node"}


@dataclass(frozen=True, slots=True)
class ReportIssue:
    severity: str
    location: str
    message: str


class ConfigValidator:
    def __init__(
        self,
        config_dir: Path,
        *,
        phase: str,
        manifest: str | None,
    ) -> None:
        self.config_dir = config_dir.resolve()
        self.phase = phase
        self.manifest = manifest
        self.issues: list[ReportIssue] = []
        self._issue_keys: set[tuple[str, str, str]] = set()

    def validate(self) -> bool:
        if not self.config_dir.exists():
            self._add("ERROR", os.fspath(self.config_dir), "配置目录不存在")
            return False
        if not self.config_dir.is_dir():
            self._add("ERROR", os.fspath(self.config_dir), "目标路径不是目录")
            return False

        if self.phase == PHASE_RESOURCES:
            self._validate_resource_phase()
        elif self.phase == PHASE_RUNTIME:
            self._validate_runtime_config()
        else:
            self._validate_final_phase()
        return not self.issues

    def _validate_resource_phase(self) -> None:
        if not self.manifest:
            self._add(
                "ERROR",
                self._display(self.config_dir),
                "resources 阶段必须通过 --manifest 指定编写清单",
            )
            return

        try:
            manifest_path = resolve_config_relative_path(
                self.config_dir,
                self.manifest,
                must_exist=True,
                allowed_suffixes=("_resource.csv",),
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            self._add("ERROR", self.manifest, str(exc))
            return

        self._validate_csv_shape(manifest_path)
        flow = self._load_flow(manifest_path)
        if flow is None:
            return

        self._add_editor_issues(
            validate_flow(self.config_dir, flow, {flow.filename: flow}),
            [flow],
        )
        self._validate_authoring_manifest(flow)

    def _validate_final_phase(self) -> None:
        csv_paths = self._discover_csv_paths()
        if not (self.config_dir / "main.csv").is_file():
            self._add("ERROR", "main.csv", "最终配置缺少入口文件 main.csv")

        for csv_path in csv_paths:
            self._validate_csv_shape(csv_path)

        document = self._load_document(csv_paths)
        if document is not None:
            self._add_editor_issues(validate_document(document), document.flows)
            self._validate_flow_contracts(document)
            self._validate_scripts_and_resource_lifecycle(document)

        self._validate_runtime_config()

    def _discover_csv_paths(self) -> list[Path]:
        paths: list[Path] = []
        for csv_path in sorted(
            self.config_dir.rglob("*.csv"),
            key=lambda path: path.relative_to(self.config_dir).as_posix().casefold(),
        ):
            relative_path = csv_path.relative_to(self.config_dir).as_posix()
            try:
                resolved_path = resolve_config_relative_path(
                    self.config_dir,
                    relative_path,
                    must_exist=True,
                    allowed_suffixes=(".csv",),
                )
            except (FileNotFoundError, OSError, ValueError) as exc:
                self._add("ERROR", relative_path, str(exc))
                continue
            paths.append(resolved_path)
        return paths

    def _load_document(self, csv_paths: list[Path]) -> EditorDocument | None:
        flows: list[FlowDocument] = []
        for csv_path in csv_paths:
            flow = self._load_flow(csv_path)
            if flow is not None:
                flows.append(flow)
        document = EditorDocument(root_path=self.config_dir, flows=flows)
        document.ensure_main_first()
        return document

    def _load_flow(self, csv_path: Path) -> FlowDocument | None:
        relative_name = csv_path.relative_to(self.config_dir).as_posix()
        try:
            flow = CsvEditorCodec().load_flow(csv_path)
        except (OSError, UnicodeError, csv.Error, ValueError) as exc:
            self._add("ERROR", relative_name, f"CSV 解析失败: {exc}")
            return None
        flow.filename = relative_name
        return flow

    def _validate_csv_shape(self, csv_path: Path) -> None:
        location = self._display(csv_path)
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, None)
        except (OSError, UnicodeError, csv.Error) as exc:
            self._add("ERROR", location, f"无法读取 CSV: {exc}")
            return

        if header is None:
            self._add("ERROR", location, "CSV 文件为空")
            return

        if header != CSV_COLUMNS:
            missing = [name for name in CSV_COLUMNS if name not in header]
            unexpected = [name for name in header if name not in CSV_COLUMNS]
            details: list[str] = []
            if missing:
                details.append(f"缺少列: {', '.join(missing)}")
            if unexpected:
                details.append(f"未知列: {', '.join(unexpected)}")
            if not details:
                details.append("列顺序与 csv_schema.py 不一致")
            self._add("ERROR", location, "；".join(details))

        if COL_INDEX not in header:
            return

        seen_indexes: set[int] = set()
        numeric_jump_targets: list[tuple[str, str, int]] = []
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row_number, row in enumerate(reader, start=1):
                    raw_index = (row.get(COL_INDEX) or "").strip()
                    row_location = f"{location}:{row_number}"
                    self._validate_raw_csv_row(row, row_location)
                    self._collect_numeric_jump_targets(
                        row,
                        row_location,
                        numeric_jump_targets,
                    )
                    try:
                        index = int(raw_index)
                    except ValueError:
                        self._add("ERROR", row_location, f"序号不是整数: {raw_index or '<空>'}")
                        continue
                    if index in seen_indexes:
                        self._add("ERROR", row_location, f"序号重复: {index}")
                    seen_indexes.add(index)
        except (OSError, UnicodeError, csv.Error) as exc:
            self._add("ERROR", location, f"无法校验 CSV 序号: {exc}")
            return

        for target_location, label, target in numeric_jump_targets:
            if is_terminal_jump_target(target):
                continue
            if target not in seen_indexes:
                self._add(
                    "ERROR",
                    target_location,
                    f"{label}序号不存在: {target}",
                )

    def _validate_raw_csv_row(
        self,
        row: dict[str | None, str | list[str] | None],
        location: str,
    ) -> None:
        operation = str(row.get(COL_OPERATION) or "")
        if operation != operation.strip():
            self._add("ERROR", location, "操作名称不能包含首尾空格")

        jump_mark = str(row.get(COL_JUMP_MARK) or "")
        if jump_mark != jump_mark.strip():
            self._add("ERROR", location, "跳转标记不能包含首尾空格")

        for column in (COL_RANGE_RANDOM, COL_DISABLE_GRAYSCALE):
            raw_value = str(row.get(column) or "")
            if raw_value not in {"", "0", "1"}:
                self._add(
                    "ERROR",
                    location,
                    f"{column} 只能为空、0 或 1，实际为: {raw_value}",
                )

        param_text = str(row.get(COL_PARAM) or "")
        if operation in {
            OperationType.PIC.value,
            OperationType.OCR.value,
            OperationType.JUMP.value,
        } and param_text != param_text.strip():
            self._add("ERROR", location, "识别或跳转参数不能包含首尾空格")

        search_target = str(row.get(COL_SEARCH_TARGET) or "")
        is_picture_path = operation == OperationType.PIC.value
        if operation == OperationType.RESOURCE.value:
            parsed_resource = parse_resource_param(param_text.strip())
            is_picture_path = parsed_resource is not None and parsed_resource[0] == "pic"
        if is_picture_path and search_target != search_target.strip():
            self._add("ERROR", location, "图片文件名不能包含首尾空格")

    @staticmethod
    def _collect_numeric_jump_targets(
        row: dict[str | None, str | list[str] | None],
        location: str,
        targets: list[tuple[str, str, int]],
    ) -> None:
        operation = str(row.get(COL_OPERATION) or "").strip()
        param_text = str(row.get(COL_PARAM) or "").strip()
        if operation == OperationType.JUMP.value:
            try:
                targets.append((location, "跳转目标", int(param_text)))
            except ValueError:
                pass
            return

        if operation not in {OperationType.PIC.value, OperationType.OCR.value}:
            return
        parts = param_text.split(";")
        if len(parts) != 3 or parts[0] not in {"exist", "notExist"}:
            return
        for label, raw_target in zip(
            ("分支主跳转目标", "分支次跳转目标"),
            parts[1:],
            strict=True,
        ):
            try:
                targets.append((location, label, int(raw_target)))
            except ValueError:
                pass

    def _add_editor_issues(
        self,
        editor_issues,
        flows: list[FlowDocument],
    ) -> None:
        node_indexes = {
            (flow.filename, node.node_id): node.index
            for flow in flows
            for node in flow.nodes
        }
        for issue in editor_issues:
            location = issue.flow_name
            if issue.node_id is not None:
                index = node_indexes.get((issue.flow_name, issue.node_id))
                if index is not None:
                    location = f"{location}:{index}"
            self._add(issue.severity.value.upper(), location, issue.message)

    def _validate_authoring_manifest(self, flow: FlowDocument) -> None:
        for node in flow.nodes:
            location = f"{flow.filename}:{node.index}"
            if node.operation != OperationType.RESOURCE.value:
                continue
            parsed = parse_resource_param(node.param_text.strip())
            if parsed is None:
                continue
            kind, _ = parsed
            if kind == "jmp":
                self._add("ERROR", location, "编写清单不允许 jmp 资源")
                continue
            if kind not in {"pic", "ocr"}:
                self._add("ERROR", location, f"编写清单不支持资源类型: {kind}")
                continue
            if not node.region_text.strip():
                self._add("ERROR", location, "编写清单中的 pic/ocr 必须填写识别区域")
            if kind == "pic" and node.search_target.strip():
                self._validate_picture_path(node.search_target, location)

    def _validate_flow_contracts(self, document: EditorDocument) -> None:
        for flow in document.flows:
            for node in flow.nodes:
                location = f"{flow.filename}:{node.index}"
                if node.operation == OperationType.PIC.value and node.search_target.strip():
                    self._validate_picture_path(node.search_target, location)

                if node.operation == OperationType.RESOURCE.value:
                    parsed = parse_resource_param(node.param_text.strip())
                    if parsed is not None and parsed[0] == "pic" and node.search_target.strip():
                        self._validate_picture_path(node.search_target, location)

                if node.operation not in {OperationType.PIC.value, OperationType.OCR.value}:
                    continue

                if node.branch.is_enabled:
                    if node.branch.mode.value == "subflow":
                        self._validate_subflow_path(node.branch.primary_target, location)
                elif node.param_text.strip():
                    self._add(
                        "ERROR",
                        location,
                        "识别节点操作参数必须为空、exist;file.csv、notExist;file.csv，或合法三段式双跳转",
                    )

    def _validate_picture_path(self, target: str, location: str) -> None:
        try:
            picture_path = resolve_config_relative_path(
                self.config_dir,
                target,
                must_exist=False,
            )
        except (OSError, ValueError) as exc:
            self._add("ERROR", location, f"图片路径无效: {exc}")
            return
        if picture_path.exists() and not picture_path.is_file():
            self._add("ERROR", location, f"图片路径不是文件: {target}")

    def _validate_subflow_path(self, target: str, location: str) -> None:
        if not target.strip():
            return
        try:
            subflow_path = resolve_config_relative_path(
                self.config_dir,
                target,
                must_exist=False,
                allowed_suffixes=(".csv",),
            )
        except (OSError, ValueError) as exc:
            self._add("ERROR", location, f"子流程路径无效: {exc}")
            return
        if subflow_path.exists() and not subflow_path.is_file():
            self._add("ERROR", location, f"子流程路径不是文件: {target}")

    def _validate_scripts_and_resource_lifecycle(
        self,
        document: EditorDocument,
    ) -> None:
        script_paths: dict[str, Path] = {}
        referenced_resources: set[str] = set()

        for flow in document.flows:
            if is_resource_flow_filename(flow.filename):
                continue
            for node in flow.nodes:
                if node.operation != OperationType.SCRIPT.value:
                    continue
                parsed = parse_script_param(node.param_text.strip())
                if parsed is None:
                    continue
                location = f"{flow.filename}:{node.index}"
                script_name, explicit_resource = parsed
                if script_name.lower().endswith(".py") and not script_name.endswith(".py"):
                    self._add("ERROR", location, "script 文件后缀必须严格使用小写 .py")
                script_path = self._resolve_reference(
                    script_name,
                    location,
                    label="脚本",
                    allowed_suffixes=(".py",),
                )
                if script_path is not None:
                    key = script_path.relative_to(self.config_dir).as_posix().casefold()
                    script_paths.setdefault(key, script_path)

                if explicit_resource is not None:
                    if (
                        explicit_resource.lower().endswith("_resource.csv")
                        and not explicit_resource.endswith("_resource.csv")
                    ):
                        self._add(
                            "ERROR",
                            location,
                            "显式资源文件后缀必须严格使用小写 _resource.csv",
                        )
                    resource_path = self._resolve_reference(
                        explicit_resource,
                        location,
                        label="显式资源文件",
                        allowed_suffixes=("_resource.csv",),
                    )
                    if resource_path is not None:
                        referenced_resources.add(
                            resource_path.relative_to(self.config_dir).as_posix().casefold()
                        )
                    continue

                default_name = infer_default_resource_filename(script_name)
                default_path = self.config_dir / default_name
                if default_path.is_file():
                    referenced_resources.add(default_name.casefold())

        for script_path in script_paths.values():
            self._validate_script_file(script_path)

        for flow in document.flows:
            if not is_resource_flow_filename(flow.filename):
                continue
            if flow.filename.casefold() not in referenced_resources:
                self._add(
                    "ERROR",
                    flow.filename,
                    "资源文件未被任何 script 显式引用，也不是已引用脚本的同名默认资源；请转换用途或清理阶段性清单",
                )

    def _resolve_reference(
        self,
        reference: str,
        location: str,
        *,
        label: str,
        allowed_suffixes: tuple[str, ...],
    ) -> Path | None:
        try:
            resolved_path = resolve_config_relative_path(
                self.config_dir,
                reference,
                must_exist=False,
                allowed_suffixes=allowed_suffixes,
            )
        except (OSError, ValueError):
            return None
        if resolved_path.exists() and not resolved_path.is_file():
            self._add("ERROR", location, f"{label}路径不是文件: {reference}")
            return None
        return resolved_path if resolved_path.exists() else None

    def _validate_script_file(self, script_path: Path) -> None:
        script_name = script_path.relative_to(self.config_dir).as_posix()
        try:
            with tokenize.open(script_path) as handle:
                source = handle.read()
            tree = ast.parse(source, filename=os.fspath(script_path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            self._add("ERROR", script_name, f"脚本无法解析: {exc}")
            return

        run_functions = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run"
        ]
        if len(run_functions) != 1:
            self._add(
                "ERROR",
                script_name,
                f"脚本必须且只能提供一个顶层 run(ctx)，当前数量: {len(run_functions)}",
            )
        elif isinstance(run_functions[0], ast.AsyncFunctionDef):
            self._add("ERROR", script_name, "脚本入口 run(ctx) 不能是 async 函数")
        elif not self._is_run_ctx_signature(run_functions[0]):
            self._add("ERROR", script_name, "脚本入口签名必须严格为 run(ctx)")

        canonical_module_aliases = {CANONICAL_SCRIPT_MODULE}
        autogui_root_aliases: set[str] = set()
        forbidden_call_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_alias = alias.asname or alias.name
                    if alias.name == "autogui":
                        autogui_root_aliases.add(module_alias)
                    if alias.name == CANONICAL_SCRIPT_MODULE:
                        canonical_module_aliases.add(module_alias)
                    if self._is_forbidden_module(alias.name):
                        self._add(
                            "ERROR",
                            script_name,
                            f"禁止导入旧模块: {alias.name}",
                        )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                module_is_forbidden = self._is_forbidden_module(module_name)
                if module_is_forbidden:
                    self._add(
                        "ERROR",
                        script_name,
                        f"禁止导入旧模块: {module_name}",
                    )
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    imported_path = f"{module_name}.{alias.name}".strip(".")
                    imported_path_is_forbidden = self._is_forbidden_module(imported_path)
                    if imported_path_is_forbidden and not module_is_forbidden:
                        self._add(
                            "ERROR",
                            script_name,
                            f"禁止导入旧模块: {imported_path}",
                        )
                    if alias.name == "ScriptBase":
                        if (
                            module_name != CANONICAL_SCRIPT_MODULE
                            and not module_is_forbidden
                            and not imported_path_is_forbidden
                        ):
                            self._add(
                                "ERROR",
                                script_name,
                                f"ScriptBase 必须从 {CANONICAL_SCRIPT_MODULE} 导入",
                            )
                    if (
                        module_name.startswith("autogui")
                        and alias.name in FORBIDDEN_SCRIPT_NAMES
                        and not module_is_forbidden
                    ):
                        self._add(
                            "ERROR",
                            script_name,
                            f"禁止导入旧入口: {alias.name}",
                        )
                    if module_name.startswith("autogui") and alias.name in FORBIDDEN_SCRIPT_CALLS:
                        forbidden_call_aliases.add(local_name)
                        self._add(
                            "ERROR",
                            script_name,
                            f"禁止导入框架内部入口: {alias.name}",
                        )

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                attribute_path = self._attribute_path(node)
                forbidden_module = self._forbidden_module_from_path(
                    attribute_path,
                    autogui_root_aliases,
                )
                if forbidden_module is not None:
                    self._add(
                        "ERROR",
                        script_name,
                        f"禁止使用旧模块: {forbidden_module}",
                    )
            if isinstance(node, ast.Call):
                call_path = self._attribute_path(node.func)
                if call_path in forbidden_call_aliases:
                    self._add("ERROR", script_name, f"禁止直接调用: {call_path}")
                    continue
                for member in FORBIDDEN_SCRIPT_CALLS:
                    if self._is_module_member(
                        call_path,
                        canonical_module_aliases,
                        member,
                    ):
                        self._add("ERROR", script_name, f"禁止直接调用: {member}")

    @staticmethod
    def _is_run_ctx_signature(function: ast.FunctionDef) -> bool:
        arguments = function.args
        positional = [*arguments.posonlyargs, *arguments.args]
        return (
            len(positional) == 1
            and positional[0].arg == "ctx"
            and not arguments.defaults
            and arguments.vararg is None
            and not arguments.kwonlyargs
            and arguments.kwarg is None
        )

    @staticmethod
    def _attribute_path(expression: ast.expr) -> str | None:
        if isinstance(expression, ast.Name):
            return expression.id
        if isinstance(expression, ast.Attribute):
            parent = ConfigValidator._attribute_path(expression.value)
            if parent:
                return f"{parent}.{expression.attr}"
            return expression.attr
        return None

    @staticmethod
    def _is_module_member(
        expression_path: str | None,
        module_aliases: set[str],
        member: str,
    ) -> bool:
        if expression_path is None:
            return False
        return any(
            expression_path == f"{module_alias}.{member}"
            for module_alias in module_aliases
        )

    @staticmethod
    def _forbidden_module_from_path(
        expression_path: str | None,
        autogui_aliases: set[str],
    ) -> str | None:
        if expression_path is None:
            return None
        for autogui_alias in autogui_aliases:
            for forbidden_module in FORBIDDEN_SCRIPT_MODULES:
                relative_module = forbidden_module.removeprefix("autogui")
                alias_path = f"{autogui_alias}{relative_module}"
                if (
                    expression_path == alias_path
                    or expression_path.startswith(f"{alias_path}.")
                ):
                    return forbidden_module
        return None

    @staticmethod
    def _is_forbidden_module(module_name: str) -> bool:
        return any(
            module_name == forbidden or module_name.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_SCRIPT_MODULES
        )

    def _validate_runtime_config(self) -> None:
        config_root = self._runtime_config_root()
        try:
            resolver = RuntimeConfigResolver(
                os.fspath(self.config_dir),
                config_root=config_root,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._add(
                "ERROR",
                self._display(self.config_dir / "runtime.json"),
                f"无法加载层级 runtime.json: {exc}",
            )
            return

        runtime_schema = self._load_runtime_schema()
        if runtime_schema is not None:
            for runtime_path in resolver.runtime_json_paths:
                self._validate_runtime_schema(runtime_path, runtime_schema)

        checks: tuple[tuple[str, Callable[[], object]], ...] = (
            ("watchdog.mode", resolver.get_watchdog_mode),
            ("watchdog", resolver.get_watchdog_settings),
            ("watchdog.recovery_watchdog", resolver.get_recovery_watchdog_thresholds),
            ("on_stall_unresolved", resolver.get_unresolved_stall_policy),
            ("notification", resolver.get_notification_settings),
        )
        for label, check in checks:
            try:
                check()
            except (TypeError, ValueError) as exc:
                self._add("ERROR", label, str(exc))

    def _runtime_config_root(self) -> Path:
        repository_config_root = (REPO_ROOT / "config").resolve()
        if self.config_dir.is_relative_to(repository_config_root):
            return repository_config_root
        return self.config_dir

    def _load_runtime_schema(self) -> dict | None:
        schema_path = REPO_ROOT / "config" / "example" / "runtime.json"
        try:
            with schema_path.open("r", encoding="utf-8") as handle:
                schema = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self._add(
                "ERROR",
                self._display(schema_path),
                f"无法读取 runtime.json 权威示例: {exc}",
            )
            return None
        if not isinstance(schema, dict):
            self._add(
                "ERROR",
                self._display(schema_path),
                "runtime.json 权威示例的根节点必须是对象",
            )
            return None
        return schema

    def _validate_runtime_schema(
        self,
        runtime_path: Path,
        schema: dict,
    ) -> None:
        location = self._display(runtime_path)
        try:
            with runtime_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self._add("ERROR", location, f"JSON 解析失败: {exc}")
            return

        if data is None:
            return
        if not isinstance(data, dict):
            self._add("ERROR", location, "runtime.json 根节点必须是对象或 null")
            return
        self._validate_runtime_object(data, schema, location, root=True)

    def _validate_runtime_object(
        self,
        value: dict,
        schema: dict,
        location: str,
        *,
        root: bool = False,
    ) -> None:
        for key in sorted(set(value) - set(schema)):
            if root and key == "recovery_watchdog":
                self._add(
                    "ERROR",
                    location,
                    "recovery_watchdog 不能位于顶层，必须放在 watchdog.recovery_watchdog",
                )
            else:
                self._add("ERROR", location, f"不支持的 runtime.json 字段: {key}")

        for key in sorted(set(value) & set(schema)):
            expected_value = schema[key]
            actual_value = value[key]
            if actual_value is None:
                continue
            child_location = f"{location}:{key}"
            if isinstance(expected_value, dict):
                if not isinstance(actual_value, dict):
                    self._add("ERROR", child_location, "字段必须是对象或 null")
                    continue
                self._validate_runtime_object(
                    actual_value,
                    expected_value,
                    child_location,
                )
                continue
            if isinstance(expected_value, list):
                if not isinstance(actual_value, list):
                    self._add("ERROR", child_location, "字段必须是数组或 null")
                continue
            if isinstance(actual_value, (dict, list)):
                self._add("ERROR", child_location, "字段必须是标量或 null")

    def _add(self, severity: str, location: str, message: str) -> None:
        issue_key = (severity, location, message)
        if issue_key in self._issue_keys:
            return
        self._issue_keys.add(issue_key)
        self.issues.append(ReportIssue(severity, location, message))

    @staticmethod
    def _display(path: Path) -> str:
        try:
            return path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return os.fspath(path.resolve())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="只读校验 CsvAutoGui 配置、编写资源清单或 runtime.json",
    )
    parser.add_argument("config_dir", type=Path, help="目标配置目录")
    parser.add_argument(
        "--phase",
        choices=(PHASE_FINAL, PHASE_RESOURCES, PHASE_RUNTIME),
        default=PHASE_FINAL,
        help="final 校验完整配置；resources 校验阶段性资源清单；runtime 只校验层级运行参数",
    )
    parser.add_argument(
        "--manifest",
        help="resources 阶段要校验的 *_resource.csv，相对目标配置目录",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validator = ConfigValidator(
        args.config_dir,
        phase=args.phase,
        manifest=args.manifest,
    )
    passed = validator.validate()

    for issue in validator.issues:
        print(f"[{issue.severity}] {issue.location} - {issue.message}")

    errors = sum(issue.severity == "ERROR" for issue in validator.issues)
    warnings = sum(issue.severity == "WARNING" for issue in validator.issues)
    if passed:
        print(
            f"[OK] {validator.config_dir} ({validator.phase}) 校验通过："
            "0 error, 0 warning"
        )
        return 0

    print(
        f"[FAIL] {validator.config_dir} ({validator.phase}) 校验失败："
        f"{errors} error, {warnings} warning"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
