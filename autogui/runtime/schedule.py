from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import TIMEOUT_MAX, Event

from ..infrastructure import log


@dataclass(frozen=True)
class DurationSpec:
    minutes: float
    random_minutes: float = 0.0

    def sample_seconds(self) -> float:
        extra = random.random() * self.random_minutes if self.random_minutes else 0.0
        return (self.minutes + extra) * 60.0


@dataclass(frozen=True)
class RunPauseSettings:
    run: DurationSpec
    pause: DurationSpec


def _parse_duration(value: str, label: str) -> DurationSpec:
    parts = value.split(";")
    try:
        if len(parts) not in (1, 2):
            raise ValueError
        minutes = float(parts[0].strip())
        extra = float(parts[1].strip()) if len(parts) == 2 else 0.0
        if minutes <= 0 or extra < 0 or not math.isfinite((minutes + extra) * 60.0):
            raise ValueError
    except (ValueError, OverflowError):
        raise ValueError(
            f"{label}必须为正数或 正数;非负随机增量（分钟），且数值必须有限: {value!r}"
        ) from None
    return DurationSpec(minutes, extra)


def parse_run_pause_settings(run_duration: str | None, pause_duration: str | None) -> RunPauseSettings | None:
    run_text = (run_duration or "").strip()
    pause_text = (pause_duration or "").strip()
    if not run_text or not pause_text:
        return None
    return RunPauseSettings(
        _parse_duration(run_text, "运行时长"),
        _parse_duration(pause_text, "暂停时长"),
    )


class RunPauseSchedule:
    """One instance's schedule; only the outer main flow calls before_main_entry."""

    def __init__(
        self,
        settings: RunPauseSettings,
        status_callback: Callable[[str], None] | None = None,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self._status_callback = status_callback
        self._time_fn = time_fn
        self._run_deadline: float | None = None
        self._paused_seconds = 0.0
        self._pause_started_at: float | None = None

    def active_time(self) -> float:
        # Watchdogs share this clock so a planned pause preserves prior stall evidence.
        now = self._time_fn() if self._pause_started_at is None else self._pause_started_at
        return now - self._paused_seconds

    def _start_run(self) -> None:
        seconds = self.settings.run.sample_seconds()
        self._run_deadline = self._time_fn() + seconds
        log.info(f"计划暂停：本轮运行时长 {seconds / 60:.4f} 分钟，到期后在 main.csv 第一条节点前暂停")

    def before_main_entry(self, stop_event: Event) -> bool:
        if stop_event.is_set():
            return False
        if self._run_deadline is None:
            self._start_run()
            return True
        if self._time_fn() < self._run_deadline:
            return True

        seconds = self.settings.pause.sample_seconds()
        log.info(f"计划暂停：已到 main.csv 入口，暂停 {seconds / 60:.4f} 分钟")
        self._pause_started_at = self._time_fn()
        deadline = self._pause_started_at + seconds
        try:
            if self._status_callback is not None:
                self._status_callback("已暂停")
            while not stop_event.is_set():
                remaining = deadline - self._time_fn()
                if remaining <= 0:
                    break
                if stop_event.wait(min(remaining, TIMEOUT_MAX)):
                    break
        finally:
            self._paused_seconds += self._time_fn() - self._pause_started_at
            self._pause_started_at = None

        if stop_event.is_set():
            log.info("计划暂停期间收到停止信号，终止实例")
            return False
        log.info("计划暂停结束，从 main.csv 第一条节点继续运行")
        self._start_run()
        if self._status_callback is not None:
            self._status_callback("运行中")
        return True
