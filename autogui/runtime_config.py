import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_STALL_TIMEOUT_SECONDS = 90.0
DEFAULT_STALL_NON_PROGRESS_OPS = 60
DEFAULT_RECOVERY_LIMIT = -1


@dataclass(frozen=True)
class WatchdogSettings:
    stall_timeout_seconds: float
    stall_non_progress_ops: int
    recovery_limit: int


@dataclass(frozen=True)
class WatchdogThresholds:
    stall_timeout_seconds: float
    stall_non_progress_ops: int


class RuntimeConfigResolver:
    def __init__(self, config_dir: str):
        self._config_dir = Path(config_dir)
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

    def _load_runtime_json(self) -> dict:
        if not self.recovery_enabled:
            return {}

        runtime_path = self.runtime_json_path
        if not runtime_path.exists():
            return {}

        with runtime_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)

        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError(f"runtime.json 必须是对象: {runtime_path}")

        return data

    def _get_section(self, name: str) -> dict:
        section = self._data.get(name, {})
        if section is None:
            return {}
        if not isinstance(section, dict):
            raise ValueError(f"runtime.json 中 {name} 必须是对象")
        return section

    def get_watchdog_value(self, field: str):
        watchdog = self._get_section("watchdog")
        if field in watchdog:
            return watchdog[field]
        return self._default_value(field)

    def get_recovery_watchdog_value(self, field: str):
        recovery_watchdog = self._get_section("recovery_watchdog")
        if field in recovery_watchdog:
            return recovery_watchdog[field]
        return self.get_watchdog_value(field)

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
