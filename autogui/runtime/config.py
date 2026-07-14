import json
import os
from dataclasses import dataclass
from pathlib import Path

from ..infrastructure.paths import normalize_config_dir, normalize_config_root


DEFAULT_STALL_TIMEOUT_SECONDS = 90.0
DEFAULT_STALL_NON_PROGRESS_OPS = 60
DEFAULT_RECOVERY_LIMIT = -1
DEFAULT_WATCHDOG_MODE = "auto"


@dataclass(frozen=True)
class WatchdogSettings:
    stall_timeout_seconds: float
    stall_non_progress_ops: int
    recovery_limit: int


@dataclass(frozen=True)
class WatchdogThresholds:
    stall_timeout_seconds: float
    stall_non_progress_ops: int


@dataclass(frozen=True)
class NotificationRouteSettings:
    local_notify: bool
    remote_notify: bool


@dataclass(frozen=True)
class RemoteNotificationSettings:
    enabled: bool
    sendkey: str | None


@dataclass(frozen=True)
class NotificationSettings:
    notify_operation: NotificationRouteSettings
    remote: RemoteNotificationSettings


class RuntimeConfigResolver:
    def __init__(self, config_dir: str, config_root: str | Path | None = None):
        configured_root = normalize_config_root(config_root)
        self._config_dir = normalize_config_dir(config_dir, configured_root)
        if self._config_dir.is_relative_to(configured_root):
            self._config_root = configured_root
        else:
            self._config_root = self._config_dir
        self._data = self._load_runtime_json()

    @property
    def recovery_csv_path(self) -> Path:
        return self._config_dir / "recovery.csv"

    @property
    def recovery_enabled(self) -> bool:
        return self.recovery_csv_path.exists()

    @property
    def runtime_json_path(self) -> Path:
        return self._config_dir / "runtime.json"

    @property
    def runtime_json_paths(self) -> list[Path]:
        return self._get_runtime_json_paths()

    @property
    def config_root(self) -> Path:
        return self._config_root

    def _get_runtime_json_paths(self) -> list[Path]:
        runtime_paths: list[Path] = []
        current = self._config_dir
        while True:
            runtime_path = current / "runtime.json"
            if runtime_path.exists():
                runtime_paths.append(runtime_path)

            if current == self._config_root:
                break

            parent = current.parent
            if parent == current:
                break
            current = parent

        runtime_paths.reverse()
        return runtime_paths

    def _load_runtime_json(self) -> dict:
        merged: dict = {}
        for runtime_path in self.runtime_json_paths:
            with runtime_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)

            if data is None:
                continue
            if not isinstance(data, dict):
                raise ValueError(f"runtime.json 必须是对象: {runtime_path}")

            merged = self._merge_dicts(merged, data)

        return merged

    @classmethod
    def _merge_dicts(cls, base: dict, override: dict) -> dict:
        merged = dict(base)
        for key, value in override.items():
            base_value = merged.get(key)
            if isinstance(base_value, dict) and isinstance(value, dict):
                merged[key] = cls._merge_dicts(base_value, value)
            else:
                merged[key] = value
        return merged

    def _get_section(self, name: str) -> dict:
        section = self._data.get(name, {})
        if section is None:
            return {}
        if not isinstance(section, dict):
            raise ValueError(f"runtime.json 中 {name} 必须是对象")
        return section

    def _get_watchdog_section(self) -> dict:
        return self._get_section("watchdog")

    def _get_recovery_watchdog_section(self) -> dict:
        watchdog = self._get_watchdog_section()
        nested = watchdog.get("recovery_watchdog")
        if nested is None:
            return {}
        if not isinstance(nested, dict):
            raise ValueError("runtime.json 中 watchdog.recovery_watchdog 必须是对象")
        return nested

    @staticmethod
    def _get_subsection(section: dict, name: str) -> dict:
        child = section.get(name, {})
        if child is None:
            return {}
        if not isinstance(child, dict):
            raise ValueError(f"runtime.json 中 {name} 必须是对象")
        return child

    def get_watchdog_value(self, field: str):
        watchdog = self._get_watchdog_section()
        if field in watchdog:
            return watchdog[field]
        return self._default_value(field)

    def get_recovery_watchdog_value(self, field: str):
        recovery_watchdog = self._get_recovery_watchdog_section()
        if field in recovery_watchdog:
            return recovery_watchdog[field]
        return self.get_watchdog_value(field)

    def get_watchdog_mode(self) -> str:
        return self._coerce_watchdog_mode(self.get_watchdog_value("mode"))

    def should_enable_watchdog(self) -> bool:
        mode = self.get_watchdog_mode()
        if mode == "off":
            return False
        if mode == "on":
            return True
        if self.recovery_enabled:
            return True
        return self.get_unresolved_stall_policy().remote_notify

    def get_unresolved_stall_policy(self) -> NotificationRouteSettings:
        section = self._get_section("on_stall_unresolved")
        return NotificationRouteSettings(
            local_notify=self._coerce_bool(section.get("local_notify", False)),
            remote_notify=self._coerce_bool(section.get("remote_notify", False)),
        )

    def get_notification_settings(self) -> NotificationSettings:
        notification = self._get_section("notification")
        notify_operation = self._get_subsection(notification, "notify_operation")
        remote = self._get_subsection(notification, "remote")
        sendkey = self._resolve_string_or_env(
            remote.get("sendkey"),
            remote.get("sendkey_env"),
        )
        return NotificationSettings(
            notify_operation=NotificationRouteSettings(
                local_notify=self._coerce_bool(notify_operation.get("local_notify", True)),
                remote_notify=self._coerce_bool(notify_operation.get("remote_notify", False)),
            ),
            remote=RemoteNotificationSettings(
                enabled=self._coerce_bool(remote.get("enabled", False)),
                sendkey=sendkey,
            ),
        )

    def get_watchdog_settings(self) -> WatchdogSettings:
        return WatchdogSettings(
            stall_timeout_seconds=self._coerce_timeout(self.get_watchdog_value("stall_timeout_seconds")),
            stall_non_progress_ops=self._coerce_non_progress_ops(self.get_watchdog_value("stall_non_progress_ops")),
            recovery_limit=self._coerce_recovery_limit(self.get_watchdog_value("recovery_limit")),
        )

    def get_recovery_watchdog_thresholds(self) -> WatchdogThresholds:
        return WatchdogThresholds(
            stall_timeout_seconds=self._coerce_timeout(self.get_recovery_watchdog_value("stall_timeout_seconds")),
            stall_non_progress_ops=self._coerce_non_progress_ops(self.get_recovery_watchdog_value("stall_non_progress_ops")),
        )

    def _default_value(self, field: str):
        defaults = {
            "stall_timeout_seconds": DEFAULT_STALL_TIMEOUT_SECONDS,
            "stall_non_progress_ops": DEFAULT_STALL_NON_PROGRESS_OPS,
            "recovery_limit": DEFAULT_RECOVERY_LIMIT,
            "mode": DEFAULT_WATCHDOG_MODE,
        }
        if field not in defaults:
            raise KeyError(f"未知 watchdog 配置字段: {field}")
        return defaults[field]

    @staticmethod
    def _coerce_timeout(value) -> float:
        coerced = float(value)
        if coerced <= 0:
            raise ValueError("stall_timeout_seconds 必须大于 0")
        return coerced

    @staticmethod
    def _coerce_non_progress_ops(value) -> int:
        coerced = int(value)
        if coerced <= 0:
            raise ValueError("stall_non_progress_ops 必须大于 0")
        return coerced

    @staticmethod
    def _coerce_recovery_limit(value) -> int:
        return int(value)

    @staticmethod
    def _coerce_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "on", "yes"}:
                return True
            if normalized in {"false", "0", "off", "no"}:
                return False
        raise ValueError("布尔配置必须是 true/false，或等价的 on/off、yes/no、1/0")

    @staticmethod
    def _coerce_watchdog_mode(value) -> str:
        mode = str(value).strip().lower()
        if mode not in {"off", "auto", "on"}:
            raise ValueError("watchdog.mode 必须是 off、auto 或 on")
        return mode

    @staticmethod
    def _resolve_string_or_env(value, env_name) -> str | None:
        if value is not None:
            text = str(value).strip()
            if text:
                return text
        if env_name is None:
            return None
        env_key = str(env_name).strip()
        if not env_key:
            return None
        env_value = os.getenv(env_key)
        if env_value is None:
            return None
        env_value = env_value.strip()
        return env_value or None
