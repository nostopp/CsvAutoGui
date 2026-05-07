from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Callable, Iterator

MARK_KIND_OCR = "ocr"
MARK_KIND_PIC = "pic"

MARK_ACTION_LOCATE = "locate"
MARK_ACTION_WAIT_EXIST = "wait_exist"
MARK_ACTION_WAIT_NOT_EXIST = "wait_not_exist"

COMMAND_PAUSE = "pause"
COMMAND_RESUME = "resume"
COMMAND_STOP = "stop"
COMMAND_MARK = "mark"
COMMAND_CLOSE_ATTEMPT = "close_attempt"

DEFAULT_WINDOW_WIDTH = 360
DEFAULT_WINDOW_HEIGHT = 268
DEFAULT_WINDOW_OFFSET_X = 48
DEFAULT_WINDOW_OFFSET_Y = 48

CommandCallback = Callable[["AssistantCommand"], None]
GeometryCallback = Callable[["AssistantRect | None"], None]


@dataclass(slots=True, frozen=True)
class AssistantRect:
    left: int
    top: int
    width: int
    height: int

    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.width, self.height


@dataclass(slots=True, frozen=True)
class AssistantCommand:
    name: str
    mark_kind: str = ""
    mark_action: str = ""


@dataclass(slots=True)
class _AssistantState:
    status: str = "idle"
    event_count: int = 0
    paused: bool = False
    coordinate_mode: str = "screen"
    target_label: str = ""
    message: str = ""
    close_protected: bool = True
    visible: bool = False


class NativeRecordingAssistant:
    """Minimal Windows-native recording assistant window backed by tkinter.

    Intended bridge integration:

    - `on_command` receives `pause` / `resume` / `stop` / `mark` / `close_attempt`
    - `on_geometry_changed` receives the assistant rect in screen coordinates so
      the recorder can keep `ignored_rects` in sync; hidden state emits `None`
    - `temporary_hide()` or `run_hidden()` wraps native capture calls so the
      assistant does not occlude screenshot/OCR selection
    """

    def __init__(
        self,
        *,
        title: str = "Recording Assistant",
        initial_geometry: str | None = None,
        on_command: CommandCallback | None = None,
        on_geometry_changed: GeometryCallback | None = None,
    ) -> None:
        self._title = title
        self._initial_geometry = initial_geometry or (
            f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}"
            f"+{DEFAULT_WINDOW_OFFSET_X}+{DEFAULT_WINDOW_OFFSET_Y}"
        )
        self._on_command = on_command
        self._on_geometry_changed = on_geometry_changed

        self._state = _AssistantState()
        self._state_lock = Lock()
        self._queue: Queue[Callable[[], None]] = Queue()
        self._thread: Thread | None = None
        self._ready = Event()
        self._stopped = Event()
        self._startup_error: BaseException | None = None
        self._hide_depth = 0
        self._last_rect: AssistantRect | None = None

        self._tk = None
        self._root = None
        self._geometry_after_id = None
        self._status_value = None
        self._detail_value = None
        self._target_value = None
        self._message_value = None
        self._pause_button = None
        self._status_badge = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._reset_runtime()
        self._thread = Thread(target=self._run_ui, name="recording-assistant-ui", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._startup_error is not None:
            raise RuntimeError(str(self._startup_error)) from self._startup_error

    def close(self, *, force: bool = False, wait: bool = False, timeout: float = 2.0) -> None:
        if not self.is_running:
            return
        self._enqueue(lambda: self._handle_close(force=force))
        if wait:
            self._stopped.wait(timeout)

    def show(self) -> None:
        with self._state_lock:
            self._state.visible = True
        if self.is_running:
            self._enqueue(self._show_window)

    def hide(self, *, clear_ignored_rect: bool = True) -> None:
        with self._state_lock:
            self._state.visible = False
        if self.is_running:
            self._enqueue(self._hide_window)
        if clear_ignored_rect:
            self._emit_geometry(None)

    def set_status(
        self,
        *,
        status: str | None = None,
        event_count: int | None = None,
        paused: bool | None = None,
        coordinate_mode: str | None = None,
        target_label: str | None = None,
        message: str | None = None,
        close_protected: bool | None = None,
    ) -> None:
        with self._state_lock:
            if status is not None:
                self._state.status = str(status)
                if paused is None:
                    if self._state.status == "paused":
                        self._state.paused = True
                    elif self._state.status == "recording":
                        self._state.paused = False
            if event_count is not None:
                self._state.event_count = max(0, int(event_count))
            if paused is not None:
                self._state.paused = bool(paused)
            if coordinate_mode is not None:
                self._state.coordinate_mode = str(coordinate_mode)
            if target_label is not None:
                self._state.target_label = str(target_label)
            if message is not None:
                self._state.message = str(message)
            if close_protected is not None:
                self._state.close_protected = bool(close_protected)
            snapshot = self._copy_state()
        if self.is_running:
            self._enqueue(lambda: self._render_state(snapshot))

    def get_ignored_rect(self) -> AssistantRect | None:
        return self._last_rect

    def run_hidden(self, callback: Callable[..., object], *args: object, **kwargs: object) -> object:
        with self.temporary_hide():
            return callback(*args, **kwargs)

    def choose_text_candidate(
        self,
        candidates: list[str],
        *,
        title: str = "Choose OCR Candidate",
        prompt: str = "Select the OCR text to use for this recording mark.",
        initial_value: str = "",
    ) -> str | None:
        if not candidates:
            return initial_value.strip() or None
        if not self.is_running:
            return candidates[0]

        result_event = Event()
        result_box: dict[str, str | None] = {"value": None}

        def action() -> None:
            result_box["value"] = self._show_candidate_dialog(
                candidates,
                title=title,
                prompt=prompt,
                initial_value=initial_value,
            )
            result_event.set()

        self._enqueue(action)
        result_event.wait()
        return result_box["value"]

    @contextmanager
    def temporary_hide(self) -> Iterator[None]:
        should_restore = False
        with self._state_lock:
            currently_visible = self._state.visible
            self._hide_depth += 1
            if currently_visible and self._hide_depth == 1:
                should_restore = True
                self._state.visible = False
        if should_restore:
            if self.is_running:
                self._enqueue(self._hide_window)
            self._emit_geometry(None)
        try:
            yield
        finally:
            should_show = False
            with self._state_lock:
                self._hide_depth = max(0, self._hide_depth - 1)
                if should_restore and self._hide_depth == 0:
                    should_show = True
                    self._state.visible = True
            if should_show:
                if self.is_running:
                    self._enqueue(self._show_window)
                else:
                    self._emit_geometry(self._last_rect)

    def _reset_runtime(self) -> None:
        self._queue = Queue()
        self._ready = Event()
        self._stopped = Event()
        self._startup_error = None
        self._geometry_after_id = None
        self._tk = None
        self._root = None
        self._status_value = None
        self._detail_value = None
        self._target_value = None
        self._message_value = None
        self._pause_button = None
        self._status_badge = None

    def _copy_state(self) -> _AssistantState:
        return _AssistantState(
            status=self._state.status,
            event_count=self._state.event_count,
            paused=self._state.paused,
            coordinate_mode=self._state.coordinate_mode,
            target_label=self._state.target_label,
            message=self._state.message,
            close_protected=self._state.close_protected,
            visible=self._state.visible,
        )

    def _run_ui(self) -> None:
        try:
            import tkinter as tk_module
        except ModuleNotFoundError as exc:
            self._startup_error = RuntimeError("tkinter is required for the native recording assistant.")
            self._ready.set()
            self._stopped.set()
            return

        self._tk = tk_module
        try:
            root = tk_module.Tk()
        except tk_module.TclError as exc:
            self._startup_error = RuntimeError("Unable to create tkinter window for the native recording assistant.")
            self._ready.set()
            self._stopped.set()
            return

        self._root = root
        self._configure_root(root)
        self._build_ui(root)
        self._render_state(self._copy_state())
        if self._copy_state().visible:
            self._show_window()
        else:
            root.withdraw()
        self._ready.set()
        root.after(20, self._drain_queue)
        root.after(120, self._emit_current_geometry)
        try:
            root.mainloop()
        finally:
            try:
                if root.winfo_exists():
                    root.destroy()
            except Exception:
                pass
            self._stopped.set()

    def _configure_root(self, root) -> None:
        root.title(self._title)
        root.geometry(self._initial_geometry)
        root.minsize(320, 236)
        root.configure(background="#0f1722")
        root.attributes("-topmost", True)
        try:
            root.attributes("-toolwindow", True)
        except Exception:
            pass
        root.protocol("WM_DELETE_WINDOW", lambda: self._handle_close(force=False))
        root.bind("<Escape>", lambda _event: self._handle_close(force=False))
        root.bind("<Configure>", self._on_configure)

    def _build_ui(self, root) -> None:
        tk = self._tk
        self._status_value = tk.StringVar(value="Idle")
        self._detail_value = tk.StringVar(value="Events 0 | Mode screen")
        self._target_value = tk.StringVar(value="Target: free screen")
        self._message_value = tk.StringVar(value="Ready")

        shell = tk.Frame(root, bg="#0f1722", padx=12, pady=12)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(0, weight=1)

        header = tk.Frame(shell, bg="#0f1722")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title = tk.Label(
            header,
            text="Recording Assistant",
            font=("Segoe UI", 12, "bold"),
            fg="#f8fafc",
            bg="#0f1722",
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="w")

        self._status_badge = tk.Label(
            header,
            textvariable=self._status_value,
            font=("Segoe UI", 10, "bold"),
            fg="#0f1722",
            bg="#93c5fd",
            padx=10,
            pady=4,
        )
        self._status_badge.grid(row=0, column=1, sticky="e")

        detail = tk.Label(
            shell,
            textvariable=self._detail_value,
            font=("Consolas", 10),
            fg="#cbd5e1",
            bg="#0f1722",
            anchor="w",
        )
        detail.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        target = tk.Label(
            shell,
            textvariable=self._target_value,
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#0f1722",
            anchor="w",
            justify="left",
            wraplength=320,
        )
        target.grid(row=2, column=0, sticky="ew", pady=(4, 10))

        action_row = tk.Frame(shell, bg="#0f1722")
        action_row.grid(row=3, column=0, sticky="ew")
        action_row.grid_columnconfigure(0, weight=1)
        action_row.grid_columnconfigure(1, weight=1)

        self._pause_button = tk.Button(
            action_row,
            text="Pause",
            command=self._handle_pause_toggle,
            font=("Segoe UI", 10, "bold"),
            bg="#1d4ed8",
            fg="#ffffff",
            activebackground="#2563eb",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=8,
        )
        self._pause_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        stop_button = tk.Button(
            action_row,
            text="Stop",
            command=lambda: self._emit_command(AssistantCommand(name=COMMAND_STOP)),
            font=("Segoe UI", 10, "bold"),
            bg="#b91c1c",
            fg="#ffffff",
            activebackground="#dc2626",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=8,
        )
        stop_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ocr_frame = self._build_mark_group(shell, row=4, title="OCR marks", mark_kind=MARK_KIND_OCR)
        pic_frame = self._build_mark_group(shell, row=5, title="PIC marks", mark_kind=MARK_KIND_PIC)

        message = tk.Label(
            shell,
            textvariable=self._message_value,
            font=("Segoe UI", 9),
            fg="#fde68a",
            bg="#162031",
            anchor="w",
            justify="left",
            wraplength=320,
            padx=10,
            pady=8,
        )
        message.grid(row=6, column=0, sticky="ew", pady=(10, 0))

        for frame in (ocr_frame, pic_frame):
            frame.configure(highlightbackground="#334155", highlightthickness=1)

    def _build_mark_group(self, parent, *, row: int, title: str, mark_kind: str):
        tk = self._tk
        frame = tk.LabelFrame(
            parent,
            text=title,
            font=("Segoe UI", 9, "bold"),
            fg="#e2e8f0",
            bg="#0f1722",
            padx=8,
            pady=8,
        )
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        for column in range(3):
            frame.grid_columnconfigure(column, weight=1)

        buttons = [
            ("Locate", MARK_ACTION_LOCATE, "#0f766e"),
            ("Wait+", MARK_ACTION_WAIT_EXIST, "#15803d"),
            ("Wait-", MARK_ACTION_WAIT_NOT_EXIST, "#a16207"),
        ]
        for column, (label, action, color) in enumerate(buttons):
            button = tk.Button(
                frame,
                text=label,
                command=lambda kind=mark_kind, mark_action=action: self._emit_command(
                    AssistantCommand(name=COMMAND_MARK, mark_kind=kind, mark_action=mark_action)
                ),
                font=("Segoe UI", 9, "bold"),
                bg=color,
                fg="#ffffff",
                activebackground=color,
                activeforeground="#ffffff",
                relief="flat",
                padx=8,
                pady=7,
            )
            button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 0))
        return frame

    def _drain_queue(self) -> None:
        root = self._root
        if root is None or not root.winfo_exists():
            return
        while True:
            try:
                callback = self._queue.get_nowait()
            except Empty:
                break
            try:
                callback()
            except Exception:
                continue
        root.after(20, self._drain_queue)

    def _enqueue(self, callback: Callable[[], None]) -> None:
        self._queue.put(callback)

    def _render_state(self, state: _AssistantState) -> None:
        if self._status_value is None:
            return
        label = self._status_label(state)
        self._status_value.set(label)
        self._detail_value.set(f"Events {state.event_count} | Mode {state.coordinate_mode}")
        self._target_value.set(f"Target: {state.target_label or 'free screen'}")
        self._message_value.set(state.message or self._default_message(state))
        if self._pause_button is not None:
            self._pause_button.configure(text="Resume" if state.paused else "Pause")
        if self._status_badge is not None:
            fg, bg = self._status_palette(state)
            self._status_badge.configure(fg=fg, bg=bg)

    def _show_window(self) -> None:
        root = self._root
        if root is None or not root.winfo_exists():
            return
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        root.after(40, self._emit_current_geometry)

    def _hide_window(self) -> None:
        root = self._root
        if root is None or not root.winfo_exists():
            return
        root.withdraw()

    def _handle_pause_toggle(self) -> None:
        with self._state_lock:
            paused = self._state.paused
        self._emit_command(AssistantCommand(name=COMMAND_RESUME if paused else COMMAND_PAUSE))

    def _handle_close(self, *, force: bool) -> None:
        root = self._root
        if root is None or not root.winfo_exists():
            return

        with self._state_lock:
            close_protected = self._state.close_protected and not force
            if close_protected:
                self._state.message = "Stop recording before closing the assistant."
                snapshot = self._copy_state()
            else:
                self._state.visible = False
                snapshot = None

        if close_protected:
            self._render_state(snapshot)
            self._emit_command(AssistantCommand(name=COMMAND_CLOSE_ATTEMPT))
            return

        self._emit_geometry(None)
        root.quit()

    def _on_configure(self, _event) -> None:
        root = self._root
        if root is None or not root.winfo_exists():
            return
        if self._geometry_after_id is not None:
            try:
                root.after_cancel(self._geometry_after_id)
            except Exception:
                pass
        self._geometry_after_id = root.after(80, self._emit_current_geometry)

    def _emit_current_geometry(self) -> None:
        root = self._root
        if root is None or not root.winfo_exists():
            return
        with self._state_lock:
            visible = self._state.visible
        if not visible or root.state() == "withdrawn":
            self._emit_geometry(None)
            return
        root.update_idletasks()
        rect = AssistantRect(
            left=int(root.winfo_rootx()),
            top=int(root.winfo_rooty()),
            width=max(0, int(root.winfo_width())),
            height=max(0, int(root.winfo_height())),
        )
        self._last_rect = rect
        self._emit_geometry(rect)

    def _show_candidate_dialog(
        self,
        candidates: list[str],
        *,
        title: str,
        prompt: str,
        initial_value: str,
    ) -> str | None:
        root = self._root
        tk = self._tk
        if root is None or tk is None or not root.winfo_exists():
            return candidates[0] if candidates else (initial_value.strip() or None)

        dialog = tk.Toplevel(root)
        dialog.title(title)
        dialog.transient(root)
        dialog.attributes("-topmost", True)
        dialog.configure(background="#0f1722")
        dialog.geometry("460x360")
        dialog.minsize(420, 320)
        dialog.grab_set()

        selected_value = tk.StringVar(value=initial_value.strip() or candidates[0])
        result: dict[str, str | None] = {"value": None}

        shell = tk.Frame(dialog, bg="#0f1722", padx=12, pady=12)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        label = tk.Label(
            shell,
            text=prompt,
            font=("Segoe UI", 10),
            fg="#e2e8f0",
            bg="#0f1722",
            justify="left",
            wraplength=420,
            anchor="w",
        )
        label.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        listbox = tk.Listbox(
            shell,
            exportselection=False,
            activestyle="dotbox",
            font=("Consolas", 10),
            bg="#111827",
            fg="#f8fafc",
            selectbackground="#0f766e",
            selectforeground="#ffffff",
        )
        for candidate in candidates:
            listbox.insert("end", candidate)
        listbox.grid(row=1, column=0, sticky="nsew")
        try:
            initial_index = candidates.index(selected_value.get())
        except ValueError:
            initial_index = 0
        listbox.selection_set(initial_index)
        listbox.see(initial_index)

        entry = tk.Entry(
            shell,
            textvariable=selected_value,
            font=("Consolas", 10),
            bg="#f8fafc",
            fg="#0f1722",
            relief="flat",
        )
        entry.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        def sync_from_list(_event=None) -> None:
            selection = listbox.curselection()
            if not selection:
                return
            selected_value.set(str(listbox.get(selection[0])).strip())

        def confirm() -> None:
            value = selected_value.get().strip()
            result["value"] = value or None
            dialog.destroy()

        def cancel() -> None:
            result["value"] = None
            dialog.destroy()

        listbox.bind("<<ListboxSelect>>", sync_from_list)
        listbox.bind("<Double-Button-1>", lambda _event: confirm())
        entry.bind("<Return>", lambda _event: confirm())
        dialog.bind("<Escape>", lambda _event: cancel())
        dialog.protocol("WM_DELETE_WINDOW", cancel)

        buttons = tk.Frame(shell, bg="#0f1722")
        buttons.grid(row=3, column=0, sticky="e", pady=(12, 0))
        tk.Button(
            buttons,
            text="Cancel",
            command=cancel,
            font=("Segoe UI", 9, "bold"),
            bg="#475569",
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            buttons,
            text="Apply",
            command=confirm,
            font=("Segoe UI", 9, "bold"),
            bg="#0f766e",
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
        ).pack(side="left")

        sync_from_list()
        entry.focus_set()
        dialog.wait_window()
        return result["value"]

    def _emit_command(self, command: AssistantCommand) -> None:
        if self._on_command is None:
            return
        Thread(target=self._safe_command_callback, args=(command,), daemon=True).start()

    def _emit_geometry(self, rect: AssistantRect | None) -> None:
        if rect is None:
            self._last_rect = None
        else:
            self._last_rect = rect
        if self._on_geometry_changed is None:
            return
        Thread(target=self._safe_geometry_callback, args=(rect,), daemon=True).start()

    def _safe_command_callback(self, command: AssistantCommand) -> None:
        try:
            self._on_command(command)
        except Exception:
            return

    def _safe_geometry_callback(self, rect: AssistantRect | None) -> None:
        try:
            self._on_geometry_changed(rect)
        except Exception:
            return

    @staticmethod
    def _status_label(state: _AssistantState) -> str:
        if state.paused or state.status == "paused":
            return "Paused"
        if state.status == "recording":
            return "Recording"
        if state.status == "stopped":
            return "Stopped"
        if state.status == "error":
            return "Error"
        return "Idle"

    @staticmethod
    def _default_message(state: _AssistantState) -> str:
        if state.paused or state.status == "paused":
            return "Capture paused. Keyboard/mouse events are ignored."
        if state.status == "recording":
            return "Use OCR/PIC mark buttons before capture when needed."
        if state.status == "stopped":
            return "Recording stopped. Review results in the main editor."
        if state.status == "error":
            return "Recording assistant encountered an error."
        return "Ready"

    @staticmethod
    def _status_palette(state: _AssistantState) -> tuple[str, str]:
        if state.paused or state.status == "paused":
            return "#111827", "#facc15"
        if state.status == "recording":
            return "#ffffff", "#dc2626"
        if state.status == "stopped":
            return "#ffffff", "#475569"
        if state.status == "error":
            return "#ffffff", "#7f1d1d"
        return "#0f1722", "#93c5fd"
