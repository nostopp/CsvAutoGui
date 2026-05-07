from __future__ import annotations

import os
import time
from ctypes import c_void_p, c_wchar_p, create_unicode_buffer, memmove, sizeof

if os.name == "nt":
    from ctypes import windll, wintypes
else:  # pragma: no cover - platform specific
    windll = None
    wintypes = None

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


class ClipboardUnavailableError(RuntimeError):
    pass


class SystemClipboard:
    def read_text(self) -> str | None:
        if os.name == "nt":
            return _read_windows_text()
        return _read_tk_text()

    def write_text(self, text: str) -> None:
        if os.name == "nt":
            _write_windows_text(text)
            return
        _write_tk_text(text)


def _read_windows_text() -> str | None:
    _open_windows_clipboard()
    handle = None
    locked = None
    try:
        handle = windll.user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        locked = windll.kernel32.GlobalLock(handle)
        if not locked:
            raise ClipboardUnavailableError("Failed to lock clipboard data")
        return c_wchar_p(locked).value
    finally:
        if locked:
            windll.kernel32.GlobalUnlock(handle)
        windll.user32.CloseClipboard()


def _write_windows_text(text: str) -> None:
    payload = create_unicode_buffer(text)
    size = sizeof(payload)
    memory_handle = None
    locked = None

    _open_windows_clipboard()
    try:
        if not windll.user32.EmptyClipboard():
            raise ClipboardUnavailableError("Failed to empty clipboard")
        memory_handle = windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not memory_handle:
            raise ClipboardUnavailableError("Failed to allocate clipboard buffer")
        locked = windll.kernel32.GlobalLock(memory_handle)
        if not locked:
            raise ClipboardUnavailableError("Failed to lock clipboard buffer")
        memmove(c_void_p(locked), payload, size)
        windll.kernel32.GlobalUnlock(memory_handle)
        locked = None
        if not windll.user32.SetClipboardData(CF_UNICODETEXT, memory_handle):
            raise ClipboardUnavailableError("Failed to set clipboard data")
        memory_handle = None
    finally:
        if locked:
            windll.kernel32.GlobalUnlock(memory_handle)
        if memory_handle:
            windll.kernel32.GlobalFree(memory_handle)
        windll.user32.CloseClipboard()


def _open_windows_clipboard() -> None:
    if windll is None:
        raise ClipboardUnavailableError("Windows clipboard APIs are unavailable")
    for _ in range(5):
        if windll.user32.OpenClipboard(wintypes.HWND()):
            return
        time.sleep(0.05)
    raise ClipboardUnavailableError("Failed to open clipboard")


def _read_tk_text() -> str | None:
    root = _create_tk_root()
    try:
        try:
            return root.clipboard_get()
        except Exception:
            return None
    finally:
        root.destroy()


def _write_tk_text(text: str) -> None:
    root = _create_tk_root()
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
    finally:
        root.destroy()


def _create_tk_root():
    try:
        import tkinter
    except Exception as exc:  # pragma: no cover - platform specific
        raise ClipboardUnavailableError("Tk clipboard fallback is unavailable") from exc

    root = tkinter.Tk()
    root.withdraw()
    return root
