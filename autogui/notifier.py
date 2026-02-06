import threading
import winsound
import tkinter as tk

def _beep_windows():
    winsound.MessageBeep(winsound.MB_ICONHAND)

def _show_tk_popup(text: str, width: int = 210, height: int = 120):
    root = getattr(tk, "_default_root", None)
    #有现成窗口
    if root is not None:
        def _create_on_root():
            win = tk.Toplevel(root)
            _init_popup_window(win, text, width, height)
        try:
            root.after(0, _create_on_root)
            return
        except Exception:
            pass

    root = tk.Tk()
    root.withdraw()
    win = tk.Toplevel(root)
    _init_popup_window(win, text, width, height, on_destroy=root.destroy)
    root.mainloop()


def _init_popup_window(win, text: str, width: int, height: int, on_destroy=None):
    try:
        win.overrideredirect(True)
    except Exception:
        pass

    win.configure(bg="#1e1e1e")

    try:
        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        x = int((screen_w - width) / 2)
        y = int((screen_h - height) / 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        pass

    try:
        win.attributes("-topmost", True)
    except Exception:
        pass

    frm = tk.Frame(win, bg="#1e1e1e", padx=16, pady=12)
    frm.pack(fill="both", expand=True)

    title = tk.Label(
        frm,
        text="Notify",
        fg="#ffffff",
        bg="#1e1e1e",
        font=("Segoe UI", 12, "bold"),
        anchor="w",
    )
    title.pack(fill="x")

    msg = tk.Label(
        frm,
        text=text,
        fg="#ffffff",
        bg="#1e1e1e",
        font=("Segoe UI", 16),
        justify="center",
        wraplength=max(200, width - 32),
        anchor="center",
    )
    msg.pack(fill="both", expand=True, pady=(8, 0))

    def _close(*_args):
        try:
            win.destroy()
        except Exception:
            pass

    win.bind("<FocusOut>", _close)
    win.bind("<Escape>", _close)

    try:
        win.deiconify()
        win.lift()
        win.focus_force()
    except Exception:
        pass

    def _drop_topmost():
        try:
            win.attributes("-topmost", False)
        except Exception:
            pass

    try:
        win.after(250, _drop_topmost)
    except Exception:
        pass

    if on_destroy is not None:
        def _on_destroy(_event=None):
            try:
                on_destroy()
            except Exception:
                pass
        win.bind("<Destroy>", _on_destroy)


def notify(text: str | None = None, *, beep: bool = True):
    msg = text if (text is not None and str(text).strip() != "") else "notify"

    if beep:
        threading.Thread(target=_beep_windows, daemon=True).start()

    threading.Thread(target=_show_tk_popup, args=(msg,), daemon=True).start()