from __future__ import annotations

import queue
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LogEvent:
    instance_id: int
    text: str


@dataclass(frozen=True, slots=True)
class InstanceStatusEvent:
    instance_id: int
    status: str


@dataclass(frozen=True, slots=True)
class DrainedLogEvent:
    event: LogEvent
    removed_text: str | None = None


class InstanceLogBuffer:
    def __init__(self, max_entries: int = 5000) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries 必须大于 0")
        self.max_entries = max_entries
        self._entries: deque[str] = deque()

    def append(self, text: str) -> str | None:
        removed_text = None
        if len(self._entries) >= self.max_entries:
            removed_text = self._entries.popleft()
        self._entries.append(text)
        return removed_text

    def snapshot(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


def normalize_log_message(message: str) -> str:
    normalized = str(message)
    level_markers = (
        "[DEBUG]",
        "[INFO]",
        "[WARNING]",
        "[WARN]",
        "[ERROR]",
        "[TRACE]",
    )
    marker_positions = [
        normalized.find(marker)
        for marker in level_markers
        if marker in normalized
    ]
    if marker_positions:
        normalized = normalized[min(marker_positions):]
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def log_tag_for_message(message: str) -> str:
    upper = message.upper()
    if "[ERROR]" in upper or "异常" in message or "失败" in message:
        return "error"
    if (
        "[WARNING]" in upper
        or "[WARN]" in upper
        or "警告" in message
    ):
        return "warn"
    if "[DEBUG]" in upper:
        return "debug"
    if "成功" in message or "完成" in message:
        return "success"
    if "启动" in message or "停止" in message or "重启" in message:
        return "meta"
    return "info"


def drain_log_events(
    event_queue: queue.SimpleQueue[LogEvent],
    buffers: Mapping[int, InstanceLogBuffer],
    *,
    max_events: int,
    accepting: bool = True,
) -> tuple[DrainedLogEvent, ...]:
    if max_events <= 0:
        raise ValueError("max_events 必须大于 0")

    drained: list[DrainedLogEvent] = []
    for _ in range(max_events):
        try:
            event = event_queue.get_nowait()
        except queue.Empty:
            break

        if not accepting:
            continue
        buffer = buffers.get(event.instance_id)
        if buffer is None:
            continue
        drained.append(
            DrainedLogEvent(
                event=event,
                removed_text=buffer.append(event.text),
            )
        )
    return tuple(drained)
