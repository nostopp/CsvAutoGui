from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tkinter as tk
    from PIL import Image as PILImage

PROMPT_MARGIN = 16
PROMPT_HEIGHT = 32
MIN_SELECTION_SIZE = 2
OVERLAY_BRIGHTNESS = 0.55


@dataclass(slots=True)
class CapturedRegion:
    left: int
    top: int
    width: int
    height: int
    image: Any

    @property
    def region_text(self) -> str:
        return f"{self.left};{self.top};{self.width};{self.height}"


@dataclass(slots=True)
class CapturedPoint:
    x: int
    y: int

    @property
    def point_text(self) -> str:
        return f"{self.x};{self.y}"


@dataclass(slots=True)
class _VirtualScreenGeometry:
    left: int
    top: int
    width: int
    height: int


def capture_region(parent: object | None = None, prompt: str = "") -> CapturedRegion | None:
    del parent
    return _CaptureOverlay(mode="region", prompt=prompt).run().result_region


def capture_point(parent: object | None = None, prompt: str = "") -> CapturedPoint | None:
    del parent
    return _CaptureOverlay(mode="point", prompt=prompt).run().result_point


class _CaptureOverlay:
    def __init__(self, mode: str, prompt: str = "") -> None:
        try:
            import tkinter as tk_module
        except ModuleNotFoundError as exc:
            raise RuntimeError("当前 Python 环境缺少 tkinter，无法使用原生框选/点选截图。") from exc

        try:
            from PIL import ImageEnhance, ImageGrab
            from PIL import ImageTk as image_tk_module
        except ModuleNotFoundError as exc:
            raise RuntimeError("当前 Python 环境缺少 Pillow，无法使用原生框选/点选截图。") from exc

        self._tk = tk_module
        self.mode = mode
        self.prompt = prompt
        self.result_region: CapturedRegion | None = None
        self.result_point: CapturedPoint | None = None
        self._selection_start: tuple[int, int] | None = None
        self._selection_end: tuple[int, int] | None = None
        self._done = False

        self._virtual_geometry = _virtual_geometry()
        self._screenshot = ImageGrab.grab(all_screens=True)
        if self._screenshot.width > 0 and self._screenshot.height > 0:
            self._virtual_geometry = _normalize_geometry(self._virtual_geometry, self._screenshot)
        self._display_image = ImageEnhance.Brightness(self._screenshot).enhance(OVERLAY_BRIGHTNESS)

        try:
            self._root = self._tk.Tk()
        except self._tk.TclError as exc:
            raise RuntimeError("当前环境无法创建原生截图遮罩窗口。") from exc

        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.configure(background="black", cursor="crosshair")
        self._root.geometry(
            f"{self._virtual_geometry.width}x{self._virtual_geometry.height}"
            f"{self._virtual_geometry.left:+d}{self._virtual_geometry.top:+d}"
        )
        self._root.protocol("WM_DELETE_WINDOW", self._cancel)

        self._canvas = self._tk.Canvas(
            self._root,
            width=self._virtual_geometry.width,
            height=self._virtual_geometry.height,
            highlightthickness=0,
            bd=0,
            background="black",
            cursor="crosshair",
        )
        self._canvas.pack(fill="both", expand=True)

        self._photo_image = image_tk_module.PhotoImage(self._display_image)
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo_image)

        self._prompt_items = _draw_prompt(self._canvas, self.prompt)
        self._selection_rect = self._canvas.create_rectangle(
            0,
            0,
            0,
            0,
            outline="#4da3ff",
            width=2,
            state="hidden",
        )
        self._cursor_label = self._canvas.create_text(
            0,
            0,
            anchor="nw",
            fill="white",
            text="",
            font=("Segoe UI", 10, "bold"),
        )
        self._cursor_label_bg = self._canvas.create_rectangle(0, 0, 0, 0, fill="#121212", outline="#4da3ff", width=1)
        self._canvas.tag_raise(self._cursor_label_bg)
        self._canvas.tag_raise(self._cursor_label)
        if self._prompt_items:
            for item in self._prompt_items:
                self._canvas.tag_raise(item)

        self._canvas.bind("<Escape>", lambda _event: self._cancel())
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<ButtonPress-1>", self._on_button_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_button_release)

    def run(self) -> _CaptureOverlay:
        self._root.update_idletasks()
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()
        try:
            self._root.mainloop()
        finally:
            if self._root.winfo_exists():
                self._root.destroy()
        return self

    def _cancel(self) -> None:
        self.result_region = None
        self.result_point = None
        self._finish()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._root.quit()

    def _on_motion(self, event) -> None:
        self._update_cursor_label(int(event.x), int(event.y))

    def _on_button_press(self, event) -> None:
        local_x = int(event.x)
        local_y = int(event.y)
        self._selection_start = (local_x, local_y)
        self._selection_end = (local_x, local_y)
        if self.mode == "point":
            global_x, global_y = self._to_global(local_x, local_y)
            self.result_point = CapturedPoint(x=global_x, y=global_y)
            self._finish()
            return

        self._canvas.itemconfigure(self._selection_rect, state="normal")
        self._update_selection_rect()

    def _on_drag(self, event) -> None:
        if self.mode != "region" or self._selection_start is None:
            return
        self._selection_end = (int(event.x), int(event.y))
        self._update_cursor_label(int(event.x), int(event.y))
        self._update_selection_rect()

    def _on_button_release(self, event) -> None:
        if self.mode != "region" or self._selection_start is None:
            return

        self._selection_end = (int(event.x), int(event.y))
        left, top, right, bottom = self._selection_bounds()
        width = right - left
        height = bottom - top
        if width < MIN_SELECTION_SIZE or height < MIN_SELECTION_SIZE:
            self._cancel()
            return

        crop = self._screenshot.crop((left, top, right, bottom))
        global_left, global_top = self._to_global(left, top)
        self.result_region = CapturedRegion(
            left=global_left,
            top=global_top,
            width=width,
            height=height,
            image=crop,
        )
        self._finish()

    def _selection_bounds(self) -> tuple[int, int, int, int]:
        start_x, start_y = self._selection_start or (0, 0)
        end_x, end_y = self._selection_end or (start_x, start_y)
        left = max(0, min(start_x, end_x))
        top = max(0, min(start_y, end_y))
        right = min(self._virtual_geometry.width, max(start_x, end_x))
        bottom = min(self._virtual_geometry.height, max(start_y, end_y))
        return left, top, right, bottom

    def _update_selection_rect(self) -> None:
        left, top, right, bottom = self._selection_bounds()
        self._canvas.coords(self._selection_rect, left, top, right, bottom)

    def _update_cursor_label(self, local_x: int, local_y: int) -> None:
        global_x, global_y = self._to_global(local_x, local_y)
        text = f"X:{global_x}  Y:{global_y}"
        self._canvas.itemconfigure(self._cursor_label, text=text)

        text_box = self._canvas.bbox(self._cursor_label)
        if not text_box:
            return
        pad_x = 8
        pad_y = 5
        label_width = (text_box[2] - text_box[0]) + pad_x * 2
        label_height = (text_box[3] - text_box[1]) + pad_y * 2

        max_left = max(0, self._virtual_geometry.width - label_width)
        max_top = max(0, self._virtual_geometry.height - label_height)
        anchor_x = min(max(local_x + 18, 0), max_left)
        anchor_y = min(max(local_y + 18, 0), max_top)

        self._canvas.coords(self._cursor_label, anchor_x + pad_x, anchor_y + pad_y)
        self._canvas.coords(
            self._cursor_label_bg,
            anchor_x,
            anchor_y,
            anchor_x + label_width,
            anchor_y + label_height,
        )
        self._canvas.tag_raise(self._cursor_label_bg)
        self._canvas.tag_raise(self._cursor_label)

    def _to_global(self, local_x: int, local_y: int) -> tuple[int, int]:
        return local_x + self._virtual_geometry.left, local_y + self._virtual_geometry.top


def _draw_prompt(canvas, prompt: str) -> list[int]:
    if not prompt:
        return []
    width = int(canvas.cget("width"))
    prompt_width = min(560, max(280, width - PROMPT_MARGIN * 2))
    left = PROMPT_MARGIN
    top = PROMPT_MARGIN
    rect_id = canvas.create_rectangle(
        left,
        top,
        left + prompt_width,
        top + PROMPT_HEIGHT,
        fill="#121212",
        outline="#4da3ff",
        width=1,
    )
    text_id = canvas.create_text(
        left + 10,
        top + PROMPT_HEIGHT // 2,
        anchor="w",
        fill="white",
        text=prompt,
        font=("Segoe UI", 10),
    )
    return [rect_id, text_id]


def _normalize_geometry(geometry: _VirtualScreenGeometry, image: Any) -> _VirtualScreenGeometry:
    width = int(image.width or geometry.width or 0)
    height = int(image.height or geometry.height or 0)
    return _VirtualScreenGeometry(
        left=geometry.left,
        top=geometry.top,
        width=width,
        height=height,
    )


def _virtual_geometry() -> _VirtualScreenGeometry:
    user32 = getattr(ctypes, "windll", None)
    if user32 is None:
        return _VirtualScreenGeometry(left=0, top=0, width=1920, height=1080)

    metrics = user32.user32
    try:
        left = int(metrics.GetSystemMetrics(76))
        top = int(metrics.GetSystemMetrics(77))
        width = int(metrics.GetSystemMetrics(78))
        height = int(metrics.GetSystemMetrics(79))
    except Exception:
        return _VirtualScreenGeometry(left=0, top=0, width=1920, height=1080)

    if width <= 0 or height <= 0:
        return _VirtualScreenGeometry(left=0, top=0, width=1920, height=1080)
    return _VirtualScreenGeometry(left=left, top=top, width=width, height=height)
