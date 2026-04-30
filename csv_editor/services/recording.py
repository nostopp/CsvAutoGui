from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from PySide6.QtCore import QObject, Signal

from csv_editor.domain.enums import BranchMode, BranchTrigger, OperationType
from csv_editor.domain.models import BranchConfig, FlowDocument, OperationNode

STOP_HOTKEY = "shift+x"
SHIFT_KEY_NAMES = {"shift", "left shift", "right shift"}
STOP_HOTKEY_KEYS = SHIFT_KEY_NAMES | {"x"}
MERGE_THRESHOLD_SECONDS = 0.5
HOTKEY_STRIP_WINDOW_SECONDS = 0.6
VISUAL_MARK_WAIT_SECONDS = {
    "ocr": "0.5",
    "pic": "0.3",
}
VISUAL_MARK_CONFIDENCE = {
    "ocr": "0.9",
    "pic": "0.8",
}


class VisualMarkKind:
    OCR = "ocr"
    PIC = "pic"


class VisualMarkAction:
    WAIT_EXIST = "wait_exist"
    WAIT_NOT_EXIST = "wait_not_exist"
    LOCATE = "locate"


@dataclass(slots=True)
class VisibleWindowInfo:
    hwnd: int
    title: str
    process_name: str
    class_name: str

    @property
    def display_text(self) -> str:
        extras = [item for item in (self.process_name, str(self.hwnd), self.class_name) if item]
        if not extras:
            return self.title
        return f"{self.title} | {' | '.join(extras)}"


@dataclass(slots=True)
class RawRecordedEvent:
    operation: str
    value: str
    timestamp: float
    x: int | None = None
    y: int | None = None
    screen_x: int | None = None
    screen_y: int | None = None


@dataclass(slots=True)
class VisualMarkEvent:
    kind: str
    action: str
    search_target: str
    region_text: str
    timestamp: float
    note: str = ""


RecordedEvent = RawRecordedEvent | VisualMarkEvent


@dataclass(slots=True)
class NodeGroup:
    nodes: list[OperationNode]
    start_time: float
    end_time: float


class RecordingService(QObject):
    stop_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._keyboard_module: Any | None = None
        self._mouse_module: Any | None = None
        self._events: list[RecordedEvent] = []
        self._lock = Lock()
        self._recording = False
        self._stop_pending = False
        self._capture_paused = False
        self._suppress_events_until = 0.0
        self._ignored_screen_rects: list[tuple[int, int, int, int]] = []
        self._pressed_keys: set[str] = set()
        self._target_window: VisibleWindowInfo | None = None
        self._match_child_window = False
        self._keyboard_hook = None
        self._mouse_hook = None
        self._stop_hotkey_time: float | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    def set_target_window(self, window_info: VisibleWindowInfo | None, match_child_window: bool = False) -> None:
        self._target_window = window_info
        self._match_child_window = match_child_window

    def set_capture_paused(self, paused: bool) -> None:
        self._capture_paused = paused

    def suppress_events_for(self, seconds: float) -> None:
        self._suppress_events_until = max(self._suppress_events_until, time.time() + max(0.0, seconds))

    def set_ignored_screen_rects(self, rects: list[tuple[int, int, int, int]]) -> None:
        self._ignored_screen_rects = list(rects)

    def add_visual_mark(
        self,
        kind: str,
        action: str,
        search_target: str,
        region_text: str,
        note: str = "",
        timestamp: float | None = None,
    ) -> None:
        if kind not in {VisualMarkKind.OCR, VisualMarkKind.PIC}:
            raise ValueError(f"Unsupported visual mark kind: {kind}")
        if action not in {VisualMarkAction.WAIT_EXIST, VisualMarkAction.WAIT_NOT_EXIST, VisualMarkAction.LOCATE}:
            raise ValueError(f"Unsupported visual mark action: {action}")
        self._append_event(
            VisualMarkEvent(
                kind=kind,
                action=action,
                search_target=search_target,
                region_text=region_text,
                timestamp=time.time() if timestamp is None else timestamp,
                note=note,
            )
        )

    def start(self) -> None:
        if self._recording:
            return

        self._ensure_dependencies()
        if self._target_window:
            if not self._is_window_handle_valid(self._target_window.hwnd):
                raise RuntimeError(f"目标窗口已失效：{self._target_window.display_text}")

        with self._lock:
            self._events = []
        self._stop_hotkey_time = None
        self._stop_pending = False
        self._capture_paused = False
        self._suppress_events_until = 0.0
        self._ignored_screen_rects = []
        self._pressed_keys.clear()

        self._keyboard_hook = self._keyboard_module.hook(self._on_keyboard_event)
        self._mouse_hook = self._mouse_module.hook(self._on_mouse_event)
        self._recording = True

    def stop(self) -> list[OperationNode]:
        if not self._recording:
            return self.build_nodes()

        self._recording = False
        self._stop_pending = False
        self._capture_paused = False
        self._ignored_screen_rects = []
        self._pressed_keys.clear()

        try:
            if self._keyboard_hook is not None:
                self._keyboard_module.unhook(self._keyboard_hook)
        finally:
            self._keyboard_hook = None

        try:
            if self._mouse_hook is not None:
                self._mouse_module.unhook(self._mouse_hook)
        finally:
            self._mouse_hook = None

        self._strip_stop_hotkey_events()
        return self.build_nodes()

    def build_nodes(self) -> list[OperationNode]:
        with self._lock:
            events = sorted(self._events, key=lambda item: item.timestamp)

        groups: list[NodeGroup] = []
        pending_locator: VisualMarkEvent | None = None
        visual_mark_counter = 1
        index = 0
        while index < len(events):
            event = events[index]
            next_event = events[index + 1] if index + 1 < len(events) else None

            if isinstance(event, VisualMarkEvent):
                mark_node = self._build_visual_mark_node(event, visual_mark_counter)
                visual_mark_counter += 1
                groups.append(
                    NodeGroup(
                        nodes=[mark_node],
                        start_time=event.timestamp,
                        end_time=event.timestamp,
                    )
                )
                pending_locator = event if event.action == VisualMarkAction.LOCATE else None
                index += 1
                continue

            next_raw_event = next_event if isinstance(next_event, RawRecordedEvent) else None

            if event.operation == OperationType.MOUSE_DOWN.value:
                if self._can_merge_mouse_click(event, next_raw_event):
                    click_nodes = self._build_mouse_position_nodes(event, pending_locator)
                    click_nodes.append(self._build_node(OperationType.CLICK.value, event.value))
                    groups.append(
                        NodeGroup(
                            nodes=click_nodes,
                            start_time=event.timestamp,
                            end_time=next_raw_event.timestamp,
                        )
                    )
                    pending_locator = None
                    index += 2
                    continue

                mouse_down_nodes = self._build_mouse_position_nodes(event, pending_locator)
                mouse_down_nodes.append(self._build_node(OperationType.MOUSE_DOWN.value, event.value))
                groups.append(
                    NodeGroup(
                        nodes=mouse_down_nodes,
                        start_time=event.timestamp,
                        end_time=event.timestamp,
                    )
                )
                pending_locator = None
                index += 1
                continue

            if event.operation == OperationType.MOUSE_UP.value:
                groups.append(
                    NodeGroup(
                        nodes=[
                            self._build_move_to_node(event),
                            self._build_node(OperationType.MOUSE_UP.value, event.value),
                        ],
                        start_time=event.timestamp,
                        end_time=event.timestamp,
                    )
                )
                index += 1
                continue

            if event.operation == OperationType.KEY_DOWN.value:
                if self._can_merge_key_press(event, next_raw_event):
                    groups.append(
                        NodeGroup(
                            nodes=[self._build_node(OperationType.PRESS.value, event.value)],
                            start_time=event.timestamp,
                            end_time=next_raw_event.timestamp,
                        )
                    )
                    index += 2
                    continue

                groups.append(
                    NodeGroup(
                        nodes=[self._build_node(OperationType.KEY_DOWN.value, event.value)],
                        start_time=event.timestamp,
                        end_time=event.timestamp,
                    )
                )
                index += 1
                continue

            if event.operation == OperationType.KEY_UP.value:
                groups.append(
                    NodeGroup(
                        nodes=[self._build_node(OperationType.KEY_UP.value, event.value)],
                        start_time=event.timestamp,
                        end_time=event.timestamp,
                    )
                )
                index += 1
                continue

            index += 1

        for current_group, next_group in zip(groups, groups[1:]):
            wait_seconds = max(0.0, next_group.start_time - current_group.end_time)
            if not current_group.nodes[-1].wait_value:
                current_group.nodes[-1].wait_value = self._format_wait(wait_seconds)

        nodes: list[OperationNode] = []
        for group in groups:
            nodes.extend(group.nodes)

        self._resolve_visual_wait_marks(nodes)
        flow = FlowDocument(filename="recording", nodes=nodes)
        flow.reindex()
        return flow.nodes

    def _on_stop_hotkey(self) -> None:
        if not self._recording or self._stop_pending:
            return
        self._stop_pending = True
        self._stop_hotkey_time = time.time()
        self.stop_requested.emit()

    def _on_keyboard_event(self, event) -> None:
        if not self._recording or self._capture_paused or self._is_temporarily_suppressed():
            return

        event_type = getattr(event, "event_type", "")
        if event_type not in {"down", "up"}:
            return

        key_name = self._normalize_key_name(getattr(event, "name", ""))
        if not key_name:
            return

        if event_type == "down":
            self._pressed_keys.add(key_name)
        else:
            self._pressed_keys.discard(key_name)

        if self._is_stop_hotkey_event(key_name, event_type):
            self._on_stop_hotkey()
            return

        if self._stop_pending and key_name in STOP_HOTKEY_KEYS:
            return

        operation = OperationType.KEY_DOWN.value if event_type == "down" else OperationType.KEY_UP.value
        self._append_event(
            RawRecordedEvent(
                operation=operation,
                value=key_name,
                timestamp=time.time(),
            )
        )

    def _on_mouse_event(self, event) -> None:
        if not self._recording or self._capture_paused or self._is_temporarily_suppressed():
            return

        event_type = getattr(event, "event_type", "")
        if event_type not in {"down", "up"}:
            return

        button = self._normalize_mouse_button(getattr(event, "button", ""))
        if not button:
            return

        mouse_position = self._extract_mouse_position(event)
        if mouse_position is None:
            return
        mouse_x, mouse_y = mouse_position
        if self._is_ignored_screen_position(mouse_x, mouse_y):
            return

        operation = OperationType.MOUSE_DOWN.value if event_type == "down" else OperationType.MOUSE_UP.value
        transformed_x, transformed_y = self._transform_mouse_position(mouse_x, mouse_y)
        self._append_event(
            RawRecordedEvent(
                operation=operation,
                value=button,
                timestamp=time.time(),
                x=transformed_x,
                y=transformed_y,
                screen_x=mouse_x,
                screen_y=mouse_y,
            )
        )

    def _append_event(self, event: RecordedEvent) -> None:
        with self._lock:
            self._events.append(event)

    def _ensure_dependencies(self) -> None:
        if self._keyboard_module is not None and self._mouse_module is not None:
            return

        try:
            import keyboard as keyboard_module
            import mouse as mouse_module
        except ModuleNotFoundError as exc:
            raise RuntimeError("缺少录制依赖，请先安装 keyboard 和 mouse。") from exc

        self._keyboard_module = keyboard_module
        self._mouse_module = mouse_module

    def _strip_stop_hotkey_events(self) -> None:
        if self._stop_hotkey_time is None:
            return

        cutoff = self._stop_hotkey_time - HOTKEY_STRIP_WINDOW_SECONDS
        with self._lock:
            while self._events:
                event = self._events[-1]
                if (
                    isinstance(event, RawRecordedEvent)
                    and
                    event.operation in {OperationType.KEY_DOWN.value, OperationType.KEY_UP.value}
                    and event.value in STOP_HOTKEY_KEYS
                    and event.timestamp >= cutoff
                ):
                    self._events.pop()
                    continue
                break

    def _is_stop_hotkey_event(self, key_name: str, event_type: str) -> bool:
        if self._stop_pending:
            return False

        if event_type != "down":
            return False

        if key_name == "x":
            return any(shift_key in self._pressed_keys for shift_key in SHIFT_KEY_NAMES)

        if key_name in SHIFT_KEY_NAMES:
            return "x" in self._pressed_keys

        return False

    @staticmethod
    def _build_move_to_node(event: RawRecordedEvent) -> OperationNode:
        x = event.x if event.x is not None else 0
        y = event.y if event.y is not None else 0
        return OperationNode(operation=OperationType.MOVE_TO.value, param_text=f"{x};{y}")

    @staticmethod
    def _build_move_rel_node(delta_x: int, delta_y: int) -> OperationNode:
        return OperationNode(operation=OperationType.MOVE_REL.value, param_text=f"{delta_x};{delta_y}")

    @staticmethod
    def _build_node(operation: str, param_text: str) -> OperationNode:
        return OperationNode(operation=operation, param_text=param_text)

    def _build_mouse_position_nodes(self, event: RawRecordedEvent, locator: VisualMarkEvent | None) -> list[OperationNode]:
        if locator is None:
            return [self._build_move_to_node(event)]

        bounds = self._parse_region(locator.region_text)
        if bounds is None or event.screen_x is None or event.screen_y is None:
            return [self._build_move_to_node(event)]

        left, top, width, height = bounds
        if self._point_in_region(event.screen_x, event.screen_y, bounds):
            return []

        center_x = left + width // 2
        center_y = top + height // 2
        return [self._build_move_rel_node(event.screen_x - center_x, event.screen_y - center_y)]

    def _build_visual_mark_node(self, mark: VisualMarkEvent, counter: int) -> OperationNode:
        node = OperationNode(
            operation=mark.kind,
            search_target=mark.search_target,
            region_text=mark.region_text,
            confidence_text=VISUAL_MARK_CONFIDENCE.get(mark.kind, ""),
            note=mark.note,
        )
        if mark.action == VisualMarkAction.LOCATE:
            if mark.kind == VisualMarkKind.PIC:
                node.pic_range_random = True
            return node

        self_mark = f"rec_wait_{counter:03d}"
        next_mark = f"{self_mark}_done"
        trigger = BranchTrigger.EXIST if mark.action == VisualMarkAction.WAIT_EXIST else BranchTrigger.NOT_EXIST
        node.wait_value = VISUAL_MARK_WAIT_SECONDS.get(mark.kind, "0.3")
        node.jump_mark = self_mark
        node.branch = BranchConfig(
            trigger=trigger,
            mode=BranchMode.JUMP_PAIR,
            primary_target=next_mark,
            secondary_target=self_mark,
        )
        node.raw_extra["recording_wait_done_mark"] = next_mark
        return node

    @staticmethod
    def _resolve_visual_wait_marks(nodes: list[OperationNode]) -> None:
        for index, node in enumerate(nodes):
            done_mark = node.raw_extra.pop("recording_wait_done_mark", "")
            if not done_mark or index + 1 >= len(nodes):
                continue
            next_node = nodes[index + 1]
            if next_node.jump_mark.strip():
                node.branch.primary_target = next_node.jump_mark.strip()
                continue
            next_node.jump_mark = done_mark

    @staticmethod
    def _parse_region(region_text: str) -> tuple[int, int, int, int] | None:
        parts = region_text.split(";")
        if len(parts) != 4:
            return None
        try:
            left, top, width, height = (int(part.strip()) for part in parts)
        except ValueError:
            return None
        if width <= 0 or height <= 0:
            return None
        return left, top, width, height

    @staticmethod
    def _point_in_region(x: int, y: int, bounds: tuple[int, int, int, int]) -> bool:
        left, top, width, height = bounds
        return left <= x <= left + width and top <= y <= top + height

    def _is_ignored_screen_position(self, x: int, y: int) -> bool:
        for left, top, width, height in self._ignored_screen_rects:
            if width <= 0 or height <= 0:
                continue
            if left <= x <= left + width and top <= y <= top + height:
                return True
        return False

    def _is_temporarily_suppressed(self) -> bool:
        return time.time() < self._suppress_events_until

    @staticmethod
    def _normalize_key_name(name: object) -> str:
        return str(name or "").strip().lower()

    @staticmethod
    def _normalize_mouse_button(button: object) -> str:
        return str(button or "").strip().lower()

    def _extract_mouse_position(self, event) -> tuple[int, int] | None:
        x = getattr(event, "x", None)
        y = getattr(event, "y", None)
        try:
            return int(x), int(y)
        except (TypeError, ValueError):
            pass

        if self._mouse_module is None:
            return None

        try:
            x, y = self._mouse_module.get_position()
            return int(x), int(y)
        except Exception:
            return None

    def _transform_mouse_position(self, mouse_x: int, mouse_y: int) -> tuple[int, int]:
        if not self._target_window:
            return mouse_x, mouse_y

        hwnd = self._target_window.hwnd
        if not self._is_window_handle_valid(hwnd):
            return mouse_x, mouse_y

        screen_point = (mouse_x, mouse_y)
        if self._match_child_window:
            matched_hwnd = self._find_window_at_screen_pos(hwnd, screen_point)
            if matched_hwnd and matched_hwnd != hwnd:
                child_rect = self._get_window_rect(matched_hwnd)
                if child_rect is not None:
                    child_left, child_top, _, _ = child_rect
                    return mouse_x - child_left, mouse_y - child_top

        rect = self._get_window_rect(hwnd)
        if rect is None:
            return mouse_x, mouse_y

        left, top, right, bottom = rect
        width = right - left
        height = bottom - top
        screen_size = self._get_screen_size()
        is_fullscreen = screen_size == (width, height)
        if not is_fullscreen:
            left += 8
            top += 8
        return mouse_x - left, mouse_y - top

    @staticmethod
    def _can_merge_mouse_click(current: RawRecordedEvent, next_event: RawRecordedEvent | None) -> bool:
        return (
            next_event is not None
            and next_event.operation == OperationType.MOUSE_UP.value
            and next_event.value == current.value
            and next_event.timestamp - current.timestamp <= MERGE_THRESHOLD_SECONDS
        )

    @staticmethod
    def _can_merge_key_press(current: RawRecordedEvent, next_event: RawRecordedEvent | None) -> bool:
        return (
            next_event is not None
            and next_event.operation == OperationType.KEY_UP.value
            and next_event.value == current.value
            and next_event.timestamp - current.timestamp <= MERGE_THRESHOLD_SECONDS
        )

    @staticmethod
    def _format_wait(seconds: float) -> str:
        rounded = round(seconds, 3)
        if rounded <= 0:
            return ""
        text = f"{rounded:.3f}".rstrip("0").rstrip(".")
        return text or ""

    @staticmethod
    def _get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
        try:
            import win32gui
        except ModuleNotFoundError:
            return None

        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            return None
        return int(left), int(top), int(right), int(bottom)

    @staticmethod
    def _get_screen_size() -> tuple[int, int]:
        try:
            import win32api
            import win32con
        except ModuleNotFoundError:
            return 0, 0
        return (
            int(win32api.GetSystemMetrics(win32con.SM_CXSCREEN)),
            int(win32api.GetSystemMetrics(win32con.SM_CYSCREEN)),
        )

    @staticmethod
    def _is_window_handle_valid(hwnd: int | None) -> bool:
        if not hwnd:
            return False
        try:
            import win32gui
        except ModuleNotFoundError:
            return False
        try:
            return bool(win32gui.IsWindow(int(hwnd)))
        except Exception:
            return False

    @staticmethod
    def _find_window_at_screen_pos(parent_hwnd: int, screen_point: tuple[int, int]) -> int | None:
        try:
            import win32gui
        except ModuleNotFoundError:
            return None

        candidates: list[tuple[int, int]] = []

        def enum_child_proc(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd) or not win32gui.IsWindowEnabled(hwnd):
                    return True
                rect = win32gui.GetWindowRect(hwnd)
                if win32gui.PtInRect(rect, screen_point):
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    candidates.append((int(hwnd), int(width * height)))
            except Exception:
                return True
            return True

        try:
            win32gui.EnumChildWindows(parent_hwnd, enum_child_proc, None)
        except Exception:
            return parent_hwnd

        if candidates:
            candidates.sort(key=lambda item: item[1])
            return candidates[0][0]

        try:
            rect = win32gui.GetWindowRect(parent_hwnd)
            if win32gui.PtInRect(rect, screen_point):
                return int(parent_hwnd)
        except Exception:
            return None
        return None


def list_visible_windows() -> list[VisibleWindowInfo]:
    try:
        import psutil
        import win32gui
        import win32process
    except ModuleNotFoundError:
        return []

    windows: list[VisibleWindowInfo] = []

    def callback(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd) or ""
            if title == "":
                return True
            class_name = win32gui.GetClassName(hwnd) or ""
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = ""
            try:
                if pid > 0:
                    process_name = psutil.Process(pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                process_name = "Unknown"
            windows.append(
                VisibleWindowInfo(
                    hwnd=int(hwnd),
                    title=title,
                    process_name=process_name,
                    class_name=class_name,
                )
            )
        except Exception:
            return True
        return True

    win32gui.EnumWindows(callback, None)
    windows.sort(key=lambda item: item.title.lower())
    return windows
