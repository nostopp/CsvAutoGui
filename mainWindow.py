import argparse
import json
import signal
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import keyboard

import main as main_module


BG_COLOR = "#f3f7fb"
CARD_COLOR = "#ffffff"
CARD_MUTED = "#f7faff"
BORDER_COLOR = "#dbe5f0"
TEXT_COLOR = "#16324a"
MUTED_TEXT = "#71849a"
ACCENT_COLOR = "#2c76e5"
ACCENT_ACTIVE = "#1f63c8"
SUCCESS_COLOR = "#178a67"
WARNING_COLOR = "#bd7b1a"
DANGER_COLOR = "#d25f50"


class InstanceEntry:
    def __init__(self, iid, name, args):
        self.id = iid
        self.name = name
        self.args = args
        self.thread = None
        self.stop_event = threading.Event()
        self.logs = []
        self.running = False
        self.restart_pending = False


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CsvAutoGui Manager")
        self.root.geometry("992x718")
        self.root.minsize(900, 620)
        self.root.configure(bg=BG_COLOR)
        self._closing = False

        self.style = ttk.Style()
        self._configure_styles()
        self._tree_font = tkfont.nametofont("TkDefaultFont")
        self._tree_heading_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")

        defaults = main_module.parse_args([])
        self.instances: dict[int, InstanceEntry] = {}
        self.next_id = 1
        self.log_search_var = tk.StringVar()
        self._log_search_matches: list[tuple[str, str]] = []
        self._log_search_current = -1

        self.var_loop = tk.BooleanVar(value=defaults.loop)
        self.var_log = tk.BooleanVar(value=defaults.log)
        self.var_scale_image = tk.BooleanVar(value=defaults.scale_image)
        self.var_multi = tk.BooleanVar(value=defaults.multi_window)
        self.var_click_move_cursor = tk.BooleanVar(value=defaults.click_move_cursor)
        self.var_process = tk.BooleanVar(value=defaults.process)
        self.var_screenshots = tk.BooleanVar(value=defaults.screenshots)
        self.var_record = tk.BooleanVar(value=defaults.record)

        self._build_layout(defaults)
        self._configure_log_tags()
        self.log_search_var.trace_add("write", self._on_log_search_changed)
        self._refresh_selection_actions()
        self._refresh_instance_summary()
        self._set_status("就绪，可直接启动实例")

        keyboard.add_hotkey("ctrl+shift+x", self.stop_all)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _configure_styles(self):
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.root.option_add("*Font", "{Segoe UI} 10")

        self.style.configure("App.TFrame", background=BG_COLOR)
        self.style.configure("Card.TFrame", background=CARD_COLOR)
        self.style.configure(
            "Card.TLabelframe",
            background=CARD_COLOR,
            borderwidth=1,
            relief="solid",
            bordercolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
        )
        self.style.configure(
            "Card.TLabelframe.Label",
            background=CARD_COLOR,
            foreground=TEXT_COLOR,
            font=("Segoe UI Semibold", 10),
            padding=(2, 0, 2, 4),
        )
        self.style.configure("HeaderTitle.TLabel", background=CARD_COLOR, foreground=TEXT_COLOR, font=("Segoe UI Semibold", 17))
        self.style.configure("HeaderSubtitle.TLabel", background=CARD_COLOR, foreground=MUTED_TEXT, font=("Segoe UI", 9))
        self.style.configure("SectionValue.TLabel", background=CARD_COLOR, foreground=TEXT_COLOR, font=("Segoe UI Semibold", 10))
        self.style.configure("Muted.TLabel", background=CARD_COLOR, foreground=MUTED_TEXT, font=("Segoe UI", 9))
        self.style.configure("Metric.TLabel", background=CARD_COLOR, foreground=MUTED_TEXT, font=("Segoe UI", 9))
        self.style.configure(
            "SearchCount.TLabel",
            background="#edf4ff",
            foreground=ACCENT_ACTIVE,
            font=("Segoe UI Semibold", 9),
            padding=(8, 3),
        )
        self.style.configure(
            "StatusBadge.TLabel",
            background="#eaf2ff",
            foreground=ACCENT_ACTIVE,
            padding=(10, 4),
            font=("Segoe UI Semibold", 9),
        )
        self.style.configure(
            "Primary.TButton",
            padding=(16, 8),
            font=("Segoe UI Semibold", 10),
            foreground="#ffffff",
            background=ACCENT_COLOR,
            borderwidth=1,
            bordercolor=ACCENT_COLOR,
            focusthickness=0,
        )
        self.style.map(
            "Primary.TButton",
            background=[("active", ACCENT_ACTIVE), ("disabled", "#c4d5ec")],
            bordercolor=[("active", ACCENT_ACTIVE), ("disabled", "#c4d5ec")],
            foreground=[("disabled", "#f2f6fb")],
        )
        self.style.configure(
            "Secondary.TButton",
            padding=(12, 8),
            font=("Segoe UI Semibold", 10),
            foreground=TEXT_COLOR,
            background="#eff4fb",
            borderwidth=1,
            bordercolor="#e2eaf4",
            focusthickness=0,
        )
        self.style.map(
            "Secondary.TButton",
            background=[("active", "#e3ecf8"), ("disabled", "#f3f6fa")],
            bordercolor=[("active", "#d7e2ef"), ("disabled", "#eef3f8")],
            foreground=[("disabled", "#9aa8b6")],
        )
        self.style.configure(
            "Danger.TButton",
            padding=(12, 8),
            font=("Segoe UI Semibold", 10),
            foreground="#ffffff",
            background=DANGER_COLOR,
            borderwidth=1,
            bordercolor=DANGER_COLOR,
            focusthickness=0,
        )
        self.style.map(
            "Danger.TButton",
            background=[("active", "#bf5647"), ("disabled", "#e6b8b2")],
            bordercolor=[("active", "#bf5647"), ("disabled", "#e6b8b2")],
            foreground=[("disabled", "#fff5f3")],
        )
        self.style.configure(
            "Subtle.TButton",
            padding=(10, 7),
            font=("Segoe UI", 9),
            foreground=MUTED_TEXT,
            background="#f5f8fc",
            borderwidth=1,
            bordercolor="#e4ebf3",
            focusthickness=0,
        )
        self.style.map(
            "Subtle.TButton",
            background=[("active", "#ebf1f8"), ("disabled", "#f7f9fb")],
            bordercolor=[("active", "#dbe4ee"), ("disabled", "#edf2f7")],
            foreground=[("disabled", "#aeb8c3")],
        )
        self.style.configure(
            "Modern.TEntry",
            fieldbackground="#ffffff",
            bordercolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
            padding=(10, 6),
        )
        self.style.configure(
            "Option.TCheckbutton",
            background=CARD_COLOR,
            foreground=TEXT_COLOR,
            padding=(0, 4),
        )
        self.style.map(
            "Option.TCheckbutton",
            foreground=[("disabled", "#aeb8c3")],
            background=[("active", CARD_COLOR)],
        )
        self.style.configure(
            "Manager.Treeview",
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground=TEXT_COLOR,
            bordercolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
            rowheight=31,
            relief="flat",
            padding=0,
        )
        self.style.map(
            "Manager.Treeview",
            background=[("selected", "#dbeafe")],
            foreground=[("selected", "#0e3a63")],
        )
        self.style.configure(
            "Manager.Treeview.Heading",
            background="#f3f7fc",
            foreground=MUTED_TEXT,
            font=("Segoe UI Semibold", 9),
            padding=(8, 6),
            relief="flat",
        )
        self.style.layout(
            "Modern.Vertical.TScrollbar",
            [
                (
                    "Vertical.Scrollbar.trough",
                    {
                        "sticky": "ns",
                        "children": [
                            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"}),
                        ],
                    },
                )
            ],
        )
        self.style.layout(
            "Modern.Horizontal.TScrollbar",
            [
                (
                    "Horizontal.Scrollbar.trough",
                    {
                        "sticky": "ew",
                        "children": [
                            ("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"}),
                        ],
                    },
                )
            ],
        )
        self.style.configure(
            "Modern.Vertical.TScrollbar",
            troughcolor="#edf3f9",
            background="#b6c9df",
            bordercolor="#edf3f9",
            darkcolor="#b6c9df",
            lightcolor="#b6c9df",
            arrowcolor="#b6c9df",
            gripcount=0,
            relief="flat",
            arrowsize=8,
            troughrelief="flat",
            borderwidth=0,
        )
        self.style.map(
            "Modern.Vertical.TScrollbar",
            background=[("active", "#99b5d4"), ("pressed", "#7f9fc2")],
        )
        self.style.configure(
            "Modern.Horizontal.TScrollbar",
            troughcolor="#edf3f9",
            background="#b6c9df",
            bordercolor="#edf3f9",
            darkcolor="#b6c9df",
            lightcolor="#b6c9df",
            arrowcolor="#b6c9df",
            gripcount=0,
            relief="flat",
            arrowsize=8,
            troughrelief="flat",
            borderwidth=0,
        )
        self.style.map(
            "Modern.Horizontal.TScrollbar",
            background=[("active", "#99b5d4"), ("pressed", "#7f9fc2")],
        )
        self.style.configure("TSeparator", background=BORDER_COLOR)

    def _build_layout(self, defaults):
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        container = ttk.Frame(self.root, style="App.TFrame", padding=(10, 10, 10, 8))
        container.grid(row=0, column=0, sticky="nsew")
        container.rowconfigure(1, weight=1)
        container.columnconfigure(0, weight=1)

        header = ttk.Frame(container, style="Card.TFrame", padding=(14, 12, 14, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title_row = ttk.Frame(header, style="Card.TFrame")
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.columnconfigure(0, weight=1)

        title_stack = ttk.Frame(title_row, style="Card.TFrame")
        title_stack.grid(row=0, column=0, sticky="w")
        ttk.Label(title_stack, text="CsvAutoGui Manager", style="HeaderTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_stack,
            text="集中管理配置、实例和实时日志，减少窗口切换与状态判断成本",
            style="HeaderSubtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        action_stack = ttk.Frame(title_row, style="Card.TFrame")
        action_stack.grid(row=0, column=1, sticky="e")
        ttk.Label(action_stack, text="Ctrl+Shift+X 停止全部实例", style="StatusBadge.TLabel").grid(row=0, column=0, padx=(0, 10))
        self.btn_start = ttk.Button(action_stack, text="启动实例", style="Primary.TButton", command=self.start_instance)
        self.btn_start.grid(row=0, column=1)
        Tooltip(self.btn_start, "按当前表单参数启动一个新实例")

        config_row = ttk.Frame(header, style="Card.TFrame")
        config_row.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        config_row.columnconfigure(1, weight=1)
        config_row.columnconfigure(4, weight=1)

        ttk.Label(config_row, text="配置目录", style="SectionValue.TLabel").grid(row=0, column=0, sticky="w")
        self.e_config = ttk.Entry(config_row, width=52, style="Modern.TEntry")
        self.e_config.insert(0, self._normalize_config_path(defaults.config))
        self.e_config.grid(row=0, column=1, sticky="ew", padx=(10, 8))
        self.btn_browse_config = ttk.Button(config_row, text="浏览…", style="Secondary.TButton", command=self.browse_config_folder)
        self.btn_browse_config.grid(row=0, column=2, padx=(0, 18))
        Tooltip(self.btn_browse_config, "选择一个配置目录")

        ttk.Label(config_row, text="窗口标题", style="SectionValue.TLabel").grid(row=0, column=3, sticky="w")
        self.e_title = ttk.Entry(config_row, width=28, style="Modern.TEntry")
        if defaults.title:
            self.e_title.insert(0, defaults.title)
        self.e_title.grid(row=0, column=4, sticky="ew", padx=(10, 0))

        sections = ttk.Frame(header, style="Card.TFrame")
        sections.grid(row=2, column=0, sticky="ew")
        for idx in range(3):
            sections.columnconfigure(idx, weight=1)

        options_card = ttk.LabelFrame(sections, text="运行选项", style="Card.TLabelframe", padding=(10, 8))
        options_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        options_card.columnconfigure(0, weight=1)
        options_card.columnconfigure(1, weight=1)

        option_defs = [
            ("循环执行", self.var_loop, "运行完成后自动继续执行"),
            ("输出日志", self.var_log, "在日志区持续输出运行细节"),
            ("进程获取模式", self.var_process, "获取当前进程信息"),
            ("多窗口", self.var_multi, "允许在多窗口目标下工作"),
            ("点击前移动鼠标", self.var_click_move_cursor, "执行点击前先移动光标"),
            ("图片缩放", self.var_scale_image, "对图片识别使用缩放适配"),
        ]
        for idx, (label, variable, tip) in enumerate(option_defs):
            widget = ttk.Checkbutton(options_card, text=label, variable=variable, style="Option.TCheckbutton")
            widget.grid(row=idx // 2, column=idx % 2, sticky="w", padx=(0, 8), pady=0)
            Tooltip(widget, tip)

        runtime_card = ttk.LabelFrame(sections, text="运行参数", style="Card.TLabelframe", padding=(10, 8))
        runtime_card.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        runtime_card.columnconfigure(1, weight=1)

        ttk.Label(runtime_card, text="缩放", style="SectionValue.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.e_scale = ttk.Entry(runtime_card, width=12, style="Modern.TEntry")
        self.e_scale.insert(0, str(defaults.scale))
        self.e_scale.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        Tooltip(self.e_scale, "运行时使用的缩放倍率")

        ttk.Label(runtime_card, text="坐标偏移", style="SectionValue.TLabel").grid(row=1, column=0, sticky="w")
        self.e_offset = ttk.Entry(runtime_card, width=12, style="Modern.TEntry")
        self.e_offset.insert(0, defaults.offset)
        self.e_offset.grid(row=1, column=1, sticky="ew")
        Tooltip(self.e_offset, "用于点击或识别区域的额外偏移")

        ttk.Separator(runtime_card).grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)
        self.lbl_param_hint = ttk.Label(
            runtime_card,
            text="建议：常用配置先保存参数文件，再通过加载快速切换。",
            style="Muted.TLabel",
            justify="left",
        )
        self.lbl_param_hint.grid(row=3, column=0, columnspan=2, sticky="w")

        action_card = ttk.LabelFrame(sections, text="实例控制", style="Card.TLabelframe", padding=(10, 8))
        action_card.grid(row=0, column=2, sticky="nsew")
        action_card.columnconfigure(0, weight=1)
        action_card.columnconfigure(1, weight=1)

        self.btn_stop_selected = ttk.Button(action_card, text="停止选中", style="Secondary.TButton", command=self.stop_selected)
        self.btn_stop_selected.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        Tooltip(self.btn_stop_selected, "停止当前选中的实例")

        self.btn_restart_selected = ttk.Button(action_card, text="重启选中", style="Secondary.TButton", command=self.restart_selected)
        self.btn_restart_selected.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        Tooltip(self.btn_restart_selected, "重启当前选中的实例")

        self.btn_stop_all = ttk.Button(action_card, text="停止全部", style="Danger.TButton", command=self.stop_all)
        self.btn_stop_all.grid(row=1, column=0, columnspan=2, sticky="ew")
        Tooltip(self.btn_stop_all, "立即向所有实例发送停止信号")

        ttk.Separator(action_card).grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)
        self.lbl_action_hint = ttk.Label(
            action_card,
            text="选中实例后，可在这里停止或重启。",
            style="Muted.TLabel",
            justify="left",
        )
        self.lbl_action_hint.grid(row=3, column=0, columnspan=2, sticky="w")

        body = ttk.Frame(container, style="App.TFrame")
        body.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
        body.columnconfigure(0, weight=1, minsize=280)
        body.columnconfigure(1, weight=6, minsize=640)
        body.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(body, style="Card.TFrame", padding=(12, 10, 12, 10))
        left_panel.grid(row=0, column=0, sticky="nsew")
        left_panel.rowconfigure(2, weight=1)
        left_panel.columnconfigure(0, weight=1)

        ttk.Label(left_panel, text="实例列表", style="SectionValue.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_instance_summary = ttk.Label(left_panel, text="", style="Metric.TLabel")
        self.lbl_instance_summary.grid(row=1, column=0, sticky="w", pady=(3, 8))

        tree_frame = ttk.Frame(left_panel, style="Card.TFrame")
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.rowconfigure(1, weight=0)
        tree_frame.columnconfigure(0, weight=1)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, style="Modern.Vertical.TScrollbar")
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, style="Modern.Horizontal.TScrollbar")
        self.treeview = ttk.Treeview(
            tree_frame,
            columns=("instance", "status", "mode"),
            show="headings",
            style="Manager.Treeview",
            yscrollcommand=tree_scroll.set,
            xscrollcommand=tree_scroll_x.set,
            selectmode="browse",
            height=18,
        )
        tree_scroll.config(command=self.treeview.yview)
        tree_scroll_x.config(command=self.treeview.xview)
        self.treeview.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self.treeview.heading("instance", text="实例", anchor="center")
        self.treeview.heading("status", text="状态", anchor="center")
        self.treeview.heading("mode", text="模式", anchor="center")
        self.treeview.column("instance", width=180, stretch=False, anchor="center")
        self.treeview.column("status", width=70, stretch=False, anchor="center")
        self.treeview.column("mode", width=180, stretch=False, anchor="center")
        self.treeview.bind("<<TreeviewSelect>>", self.on_select)
        self.treeview.bind("<Button-1>", self._prevent_treeview_column_resize, add=True)
        self.treeview.bind("<B1-Motion>", self._prevent_treeview_column_resize, add=True)
        self.treeview.bind("<Double-1>", self._prevent_treeview_column_resize, add=True)
        self.treeview.tag_configure("running", background="#edf8f3")
        self.treeview.tag_configure("starting", background="#eef5ff")
        self.treeview.tag_configure("stopped", background="#fbfcfe")
        self.treeview.tag_configure("restarting", background="#fff6ea")
        self._update_treeview_column_widths()

        right_panel = ttk.Frame(body, style="Card.TFrame", padding=(12, 10, 12, 10))
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        right_panel.rowconfigure(1, weight=1)
        right_panel.columnconfigure(0, weight=1)

        top_log_row = ttk.Frame(right_panel, style="Card.TFrame")
        top_log_row.grid(row=0, column=0, sticky="ew")
        top_log_row.columnconfigure(0, weight=1)
        top_log_row.columnconfigure(1, weight=0)

        log_title_stack = ttk.Frame(top_log_row, style="Card.TFrame")
        log_title_stack.grid(row=0, column=0, sticky="w")
        ttk.Label(log_title_stack, text="运行日志", style="SectionValue.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_log_meta = ttk.Label(log_title_stack, text="日志条数：0", style="Metric.TLabel")
        self.lbl_log_meta.grid(row=0, column=1, sticky="w", padx=(12, 0))

        search_bar = ttk.Frame(top_log_row, style="Card.TFrame")
        search_bar.grid(row=0, column=1, sticky="e")
        ttk.Label(search_bar, text="搜索", style="Metric.TLabel").grid(row=0, column=0, padx=(0, 6))
        self.e_log_search = ttk.Entry(search_bar, width=18, textvariable=self.log_search_var, style="Modern.TEntry")
        self.e_log_search.grid(row=0, column=1, padx=(0, 8))
        self.btn_search_prev = ttk.Button(search_bar, text="上一个", style="Subtle.TButton", command=self.goto_previous_search_match)
        self.btn_search_prev.grid(row=0, column=2, padx=(0, 6))
        self.btn_search_next = ttk.Button(search_bar, text="下一个", style="Subtle.TButton", command=self.goto_next_search_match)
        self.btn_search_next.grid(row=0, column=3, padx=(0, 6))
        self.lbl_search_result = ttk.Label(search_bar, text="未搜索", style="SearchCount.TLabel")
        self.lbl_search_result.grid(row=0, column=4)

        log_text_frame = ttk.Frame(right_panel, style="Card.TFrame")
        log_text_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        log_text_frame.rowconfigure(0, weight=1)
        log_text_frame.columnconfigure(0, weight=1)

        log_scroll = ttk.Scrollbar(log_text_frame, orient=tk.VERTICAL, style="Modern.Vertical.TScrollbar")
        self.txt_log = tk.Text(
            log_text_frame,
            state="disabled",
            wrap="word",
            font=("Consolas", 10),
            background="#fbfdff",
            foreground="#1f2937",
            insertbackground="#1f2937",
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#e3ebf5",
            highlightcolor="#cfe0f7",
            padx=12,
            pady=12,
            selectbackground="#dceafe",
            selectforeground="#16324a",
        )
        self.txt_log.configure(yscrollcommand=log_scroll.set)
        log_scroll.configure(command=self.txt_log.yview)
        self.txt_log.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns", padx=(4, 0))

        footer = ttk.Frame(container, style="Card.TFrame", padding=(12, 8, 12, 8))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(1, weight=1)

        footer_left = ttk.Frame(footer, style="Card.TFrame")
        footer_left.grid(row=0, column=0, sticky="w")

        self.btn_clear = ttk.Button(footer_left, text="清空实例", style="Secondary.TButton", command=self.clear_instances)
        self.btn_clear.grid(row=0, column=0, padx=(0, 8))
        Tooltip(self.btn_clear, "停止并移除所有实例")

        self.btn_reload_csv = ttk.Button(footer_left, text="重载 CSV", style="Secondary.TButton", command=self.reload_csv)
        self.btn_reload_csv.grid(row=0, column=1, padx=(0, 8))
        Tooltip(self.btn_reload_csv, "停止所有实例后重新加载 CSV")

        self.btn_save = ttk.Button(footer_left, text="保存参数", style="Secondary.TButton", command=self.save_params)
        self.btn_save.grid(row=0, column=2, padx=(0, 8))
        Tooltip(self.btn_save, "将当前参数保存为 JSON 文件")

        self.btn_load = ttk.Button(footer_left, text="加载参数", style="Secondary.TButton", command=self.load_params)
        self.btn_load.grid(row=0, column=3)
        Tooltip(self.btn_load, "从 JSON 文件恢复一组参数")

        footer_right = ttk.Frame(footer, style="Card.TFrame")
        footer_right.grid(row=0, column=1, sticky="e")
        self.lbl_status = ttk.Label(footer_right, text="", style="Metric.TLabel")
        self.lbl_status.grid(row=0, column=0, sticky="e")

    def _configure_log_tags(self):
        self.txt_log.tag_configure("debug", foreground="#60748a")
        self.txt_log.tag_configure("info", foreground="#24384e")
        self.txt_log.tag_configure("warn", foreground=WARNING_COLOR)
        self.txt_log.tag_configure("error", foreground=DANGER_COLOR)
        self.txt_log.tag_configure("success", foreground=SUCCESS_COLOR)
        self.txt_log.tag_configure("meta", foreground="#7b8794")
        self.txt_log.tag_configure("search_match", background="#fff1a8", foreground="#17324d")
        self.txt_log.tag_configure("search_current", background="#ffcf5a", foreground="#10253a")

    def _set_status(self, text: str):
        self.lbl_status.configure(text=text)

    def _instance_mode_text(self, inst: InstanceEntry) -> str:
        flags = []
        if inst.args.process:
            flags.append("进程")
        if inst.args.loop:
            flags.append("循环")
        if inst.args.title:
            flags.append("窗口")
        if inst.args.click_move_cursor:
            flags.append("移动")
        if inst.args.multi_window:
            flags.append("多窗")
        if inst.args.record:
            flags.append("录制")
        if inst.args.screenshots:
            flags.append("截图")
        return " / ".join(flags) if flags else "默认"

    def _instance_status_text(self, inst: InstanceEntry, override: str | None = None) -> str:
        if override:
            return override
        if inst.restart_pending:
            return "重启中"
        return "运行中" if inst.running else "已停止"

    def _prevent_treeview_column_resize(self, event):
        region = self.treeview.identify_region(event.x, event.y)
        if region == "separator":
            return "break"

    def _tree_tag_for_status(self, status: str) -> str:
        if status in {"启动中", "重启中"}:
            return "starting" if status == "启动中" else "restarting"
        if status == "运行中":
            return "running"
        return "stopped"

    def _tree_values_for_instance(self, inst: InstanceEntry, status_override: str | None = None):
        return (
            f"{inst.name} (id:{inst.id})",
            self._instance_status_text(inst, status_override),
            self._instance_mode_text(inst),
        )

    def _update_treeview_column_widths(self):
        columns = [
            ("instance", "实例", 120, 440),
            ("status", "状态", 72, 140),
            ("mode", "模式", 96, 360),
        ]
        padding = 28
        items = self.treeview.get_children()
        for column_id, heading_text, min_width, max_width in columns:
            width = self._tree_heading_font.measure(heading_text) + padding
            for item_id in items:
                value = str(self.treeview.set(item_id, column_id) or "")
                width = max(width, self._tree_font.measure(value) + padding)
            self.treeview.column(column_id, width=max(min_width, min(width, max_width)))

    def _update_tree_item(self, inst: InstanceEntry, status_override: str | None = None):
        item_id = f"item_{inst.id}"
        if not self.treeview.exists(item_id):
            return
        status = self._instance_status_text(inst, status_override)
        self.treeview.item(item_id, values=self._tree_values_for_instance(inst, status_override), tags=(self._tree_tag_for_status(status),))
        self._update_treeview_column_widths()
        self._refresh_instance_summary()
        self._refresh_selection_actions()
        if self.get_selected_instance() and self.get_selected_instance().id == inst.id:
            self._update_log_header(inst)

    def _refresh_instance_summary(self):
        total = len(self.instances)
        running = sum(1 for inst in self.instances.values() if inst.running)
        selected = self.get_selected_instance()
        selected_text = f"当前：{selected.name}" if selected else "当前：未选择"
        self.lbl_instance_summary.configure(text=f"总计 {total}  |  运行中 {running}  |  {selected_text}")
        if hasattr(self, "btn_clear"):
            state = tk.NORMAL if total else tk.DISABLED
            self.btn_clear.configure(state=state)

    def _refresh_selection_actions(self):
        inst = self.get_selected_instance()
        state = tk.NORMAL if inst else tk.DISABLED
        for button in (getattr(self, "btn_stop_selected", None), getattr(self, "btn_restart_selected", None)):
            if button is not None:
                button.configure(state=state)
        self._refresh_log_search_buttons()

    def _refresh_log_search_buttons(self):
        has_matches = bool(self._log_search_matches)
        state = tk.NORMAL if has_matches else tk.DISABLED
        for button in (getattr(self, "btn_search_prev", None), getattr(self, "btn_search_next", None)):
            if button is not None:
                button.configure(state=state)

    def _clear_log_search_tags(self):
        self.txt_log.tag_remove("search_match", "1.0", tk.END)
        self.txt_log.tag_remove("search_current", "1.0", tk.END)

    def _set_log_search_result_text(self, text: str):
        if hasattr(self, "lbl_search_result"):
            self.lbl_search_result.configure(text=text)

    def _on_log_search_changed(self, *_args):
        self.refresh_log_search()

    def refresh_log_search(self):
        query = self.log_search_var.get().strip()
        self._log_search_matches = []
        self._log_search_current = -1

        self.txt_log["state"] = "normal"
        self._clear_log_search_tags()
        if not query:
            self.txt_log["state"] = "disabled"
            self._set_log_search_result_text("未搜索")
            self._refresh_log_search_buttons()
            return

        start_index = "1.0"
        while True:
            match_start = self.txt_log.search(query, start_index, stopindex=tk.END, nocase=True)
            if not match_start:
                break
            match_end = f"{match_start}+{len(query)}c"
            self.txt_log.tag_add("search_match", match_start, match_end)
            self._log_search_matches.append((match_start, match_end))
            start_index = match_end

        self.txt_log["state"] = "disabled"
        if not self._log_search_matches:
            self._set_log_search_result_text("0 结果")
            self._refresh_log_search_buttons()
            return

        self._log_search_current = 0
        self._focus_log_search_match()

    def _focus_log_search_match(self):
        if not self._log_search_matches:
            self._set_log_search_result_text("0 结果")
            self._refresh_log_search_buttons()
            return

        self.txt_log["state"] = "normal"
        self.txt_log.tag_remove("search_current", "1.0", tk.END)
        start, end = self._log_search_matches[self._log_search_current]
        self.txt_log.tag_add("search_current", start, end)
        self.txt_log.mark_set(tk.INSERT, start)
        self.txt_log.see(start)
        self.txt_log["state"] = "disabled"
        self._set_log_search_result_text(f"{self._log_search_current + 1}/{len(self._log_search_matches)}")
        self._refresh_log_search_buttons()

    def goto_previous_search_match(self):
        if not self._log_search_matches:
            return
        self._log_search_current = (self._log_search_current - 1) % len(self._log_search_matches)
        self._focus_log_search_match()

    def goto_next_search_match(self):
        if not self._log_search_matches:
            return
        self._log_search_current = (self._log_search_current + 1) % len(self._log_search_matches)
        self._focus_log_search_match()

    def _update_log_header(self, inst: InstanceEntry | None):
        count = len(inst.logs) if inst else 0
        self.lbl_log_meta.configure(text=f"日志条数：{count}")

    def browse_config_folder(self):
        path = filedialog.askdirectory(title="选择配置目录")
        if not path:
            return
        display_path = self._normalize_config_path(path)
        self.e_config.delete(0, tk.END)
        self.e_config.insert(0, display_path)
        self._set_status(f"已选择配置目录：{display_path}")

    def on_closing(self):
        if self._closing:
            return
        self._closing = True
        try:
            keyboard.remove_hotkey("ctrl+shift+x")
        except Exception:
            pass
        self.stop_all()
        self._poll_close_instances()

    def _poll_close_instances(self, remaining_checks=30):
        running_instances = [inst for inst in self.instances.values() if inst.running]
        if not running_instances:
            self.root.destroy()
            return

        if remaining_checks <= 0:
            messagebox.showwarning("警告", "仍有实例未完全退出，窗口将关闭")
            self.root.destroy()
            return

        self.root.after(100, lambda: self._poll_close_instances(remaining_checks - 1))

    def build_args(self):
        try:
            scale = float(self.e_scale.get())
        except Exception:
            scale = 1.0

        return argparse.Namespace(
            config=self._normalize_config_path(self.e_config.get()),
            loop=self.var_loop.get(),
            log=self.var_log.get(),
            screenshots=self.var_screenshots.get(),
            scale=scale,
            scale_image=self.var_scale_image.get(),
            offset=self.e_offset.get(),
            title=self.e_title.get() or None,
            multi_window=self.var_multi.get(),
            click_move_cursor=self.var_click_move_cursor.get(),
            process=self.var_process.get(),
            record=self.var_record.get(),
            _from_window=True,
        )

    def _normalize_config_path(self, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""

        path = Path(raw)
        try:
            if not path.is_absolute():
                return path.as_posix()
            return Path(path.resolve().relative_to(Path.cwd().resolve())).as_posix()
        except ValueError:
            try:
                return Path(path.resolve()).as_posix()
            except OSError:
                return path.as_posix()
        except OSError:
            return path.as_posix()

    def _normalize_log_message(self, msg: str) -> str:
        normalized = msg
        level_markers = ("[DEBUG]", "[INFO]", "[WARNING]", "[WARN]", "[ERROR]", "[TRACE]")
        marker_positions = [normalized.find(marker) for marker in level_markers if marker in normalized]
        if marker_positions:
            start = min(pos for pos in marker_positions if pos >= 0)
            normalized = normalized[start:]
        return normalized

    def _log_tag_for_message(self, msg: str) -> str:
        upper = msg.upper()
        if "[ERROR]" in upper or "异常" in msg or "失败" in msg:
            return "error"
        if "[WARNING]" in upper or "警告" in msg:
            return "warn"
        if "[DEBUG]" in upper:
            return "debug"
        if "成功" in msg or "完成" in msg:
            return "success"
        if "启动" in msg or "停止" in msg or "重启" in msg:
            return "meta"
        return "info"

    def _append_log_to_view(self, msg: str):
        msg = self._normalize_log_message(msg)
        try:
            yview = self.txt_log.yview()
            at_bottom = yview[1] >= 0.999
        except Exception:
            at_bottom = True

        self.txt_log["state"] = "normal"
        self.txt_log.insert(tk.END, msg, self._log_tag_for_message(msg))
        if at_bottom:
            self.txt_log.see(tk.END)
        self.txt_log["state"] = "disabled"
        self.refresh_log_search()
        self._refresh_selection_actions()

    def _render_selected_logs(self, inst: InstanceEntry | None):
        self.txt_log["state"] = "normal"
        self.txt_log.delete("1.0", tk.END)
        if inst:
            for msg in inst.logs:
                normalized = self._normalize_log_message(msg)
                self.txt_log.insert(tk.END, normalized, self._log_tag_for_message(normalized))
        self.txt_log["state"] = "disabled"
        self.refresh_log_search()
        self._update_log_header(inst)
        self._refresh_selection_actions()

    def _launch_instance_thread(self, inst):
        def log_cb(msg: str):
            if not msg.endswith("\n"):
                msg = msg + "\n"
            normalized = self._normalize_log_message(msg)
            inst.logs.append(normalized)
            if len(inst.logs) > 5000:
                inst.logs = inst.logs[-2500:]

            def _update():
                sel = self.get_selected_instance()
                if sel and sel.id == inst.id:
                    self._append_log_to_view(normalized)
                    self._update_log_header(inst)

            self.root.after(1, _update)

        def target():
            inst.running = True
            try:
                self.root.after(1, lambda: self._update_tree_item(inst, "运行中"))
            except Exception:
                pass

            try:
                main_module.start_instance(inst.args, log_callback=log_cb, stop_event=inst.stop_event, use_hotkey=False)
            except Exception as exc:
                log_cb(f"实例异常结束: {exc}\n")
            finally:
                inst.running = False
                self.root.after(1, lambda: self._update_tree_item(inst, "已停止"))

        t = threading.Thread(target=target, daemon=True)
        inst.thread = t
        t.start()

    def start_instance(self):
        args = self.build_args()
        self._start_instance_with_args(args)

    def _start_instance_with_args(self, args):
        name = args.config
        iid = self.next_id
        self.next_id += 1
        inst = InstanceEntry(iid, name, args)
        self.instances[iid] = inst

        item_id = f"item_{iid}"
        self.treeview.insert("", tk.END, iid=item_id, values=self._tree_values_for_instance(inst, "启动中"), tags=("starting",))
        self.treeview.selection_set(item_id)
        self.treeview.focus(item_id)
        self._update_treeview_column_widths()
        self._refresh_instance_summary()
        self._render_selected_logs(inst)
        self._set_status(f"实例已加入队列：{name}")

        self._launch_instance_thread(inst)

    def get_selected_instance(self):
        sel = self.treeview.selection()
        if not sel:
            return None
        try:
            iid = int(sel[0].split("_")[1])
            return self.instances.get(iid)
        except Exception:
            return None

    def on_select(self, event=None):
        inst = self.get_selected_instance()
        self._render_selected_logs(inst)
        self._refresh_instance_summary()

    def clear_log_view(self):
        self.txt_log["state"] = "normal"
        self.txt_log.delete("1.0", tk.END)
        self.txt_log["state"] = "disabled"
        self._refresh_selection_actions()

    def stop_selected(self):
        inst = self.get_selected_instance()
        if not inst:
            messagebox.showinfo("提示", "未选择实例")
            return
        inst.stop_event.set()
        self._set_status(f"已发送停止信号：{inst.name}")

    def stop_all(self):
        for inst in self.instances.values():
            inst.stop_event.set()
        self._set_status("已向全部实例发送停止信号")

    def restart_selected(self):
        inst = self.get_selected_instance()
        if not inst:
            messagebox.showinfo("提示", "未选择实例")
            return

        if not inst.running:
            self._start_instance_with_args(inst.args)
            self._set_status(f"已重新启动实例：{inst.name}")
            return

        if inst.restart_pending:
            return

        inst.restart_pending = True
        inst.stop_event.set()
        self._update_tree_item(inst, "重启中")
        self._set_status(f"实例正在重启：{inst.name}")
        self._poll_restart_instance(inst)

    def _poll_restart_instance(self, inst, remaining_checks=30):
        if not inst.restart_pending:
            return

        if not inst.running:
            inst.restart_pending = False
            self._start_instance_with_args(inst.args)
            return

        if remaining_checks <= 0:
            inst.restart_pending = False
            self._update_tree_item(inst)
            messagebox.showwarning("警告", "实例停止超时，未执行重启")
            return

        self.root.after(100, lambda: self._poll_restart_instance(inst, remaining_checks - 1))

    def clear_instances(self):
        if not self.instances:
            messagebox.showinfo("提示", "没有实例可清理")
            return

        if not messagebox.askyesno("确认", "确定要清空所有实例吗？"):
            return

        for inst in self.instances.values():
            inst.stop_event.set()

        self.instances.clear()
        self.next_id = 1
        for item in self.treeview.get_children():
            self.treeview.delete(item)
        self._update_treeview_column_widths()

        self.txt_log["state"] = "normal"
        self.txt_log.delete("1.0", tk.END)
        self.txt_log["state"] = "disabled"
        self._update_log_header(None)
        self._refresh_instance_summary()
        self._refresh_selection_actions()
        self._set_status("实例列表已清空")

    def save_params(self):
        args = self.build_args()
        data = {
            "config": args.config,
            "loop": args.loop,
            "log": args.log,
            "screenshots": args.screenshots,
            "scale": args.scale,
            "scale_image": args.scale_image,
            "offset": args.offset,
            "title": args.title,
            "multi_window": args.multi_window,
            "click_move_cursor": args.click_move_cursor,
            "process": args.process,
            "record": args.record,
        }

        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], title="保存参数为 JSON")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            self._set_status(f"参数已保存：{path}")
        except Exception as exc:
            messagebox.showerror("保存失败", f"无法保存参数：{exc}")

    def load_params(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], title="选择参数 JSON 文件")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            messagebox.showerror("读取失败", f"无法读取文件：{exc}")
            return

        try:
            if "config" in data:
                self.e_config.delete(0, tk.END)
                self.e_config.insert(0, self._normalize_config_path(str(data.get("config", ""))))

            if "loop" in data:
                self.var_loop.set(bool(data.get("loop")))

            if "log" in data:
                self.var_log.set(bool(data.get("log")))

            if "screenshots" in data:
                self.var_screenshots.set(bool(data.get("screenshots")))

            if "scale" in data:
                self.e_scale.delete(0, tk.END)
                self.e_scale.insert(0, str(data.get("scale")))

            if "scale_image" in data:
                self.var_scale_image.set(bool(data.get("scale_image")))

            if "offset" in data:
                self.e_offset.delete(0, tk.END)
                self.e_offset.insert(0, str(data.get("offset")))

            if "title" in data:
                self.e_title.delete(0, tk.END)
                if data.get("title"):
                    self.e_title.insert(0, str(data.get("title")))

            if "multi_window" in data:
                self.var_multi.set(bool(data.get("multi_window")))

            if "click_move_cursor" in data:
                self.var_click_move_cursor.set(bool(data.get("click_move_cursor")))

            if "process" in data:
                self.var_process.set(bool(data.get("process")))

            if "record" in data:
                self.var_record.set(bool(data.get("record")))

            self._set_status(f"参数已加载：{path}")
        except Exception as exc:
            messagebox.showerror("应用失败", f"无法应用参数：{exc}")

    def reload_csv(self):
        try:
            import autogui.parser as parser

            if messagebox.askyesno("确认", "重载 CSV 需要停止所有实例，是否继续？"):
                self.stop_all()
                parser.csvDataDict.clear()
                self._set_status("CSV 缓存已清空，后续运行将重新加载")
        except Exception as exc:
            messagebox.showerror("重载失败", f"无法重载 CSV：{exc}")


class Tooltip:
    def __init__(self, widget: tk.Widget, text=None, delay=500, wraplength=300):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self._job = None
        self._tipwindow = None

        widget.bind("<Enter>", self._on_enter, add=True)
        widget.bind("<Leave>", self._on_leave, add=True)
        widget.bind("<Motion>", self._on_motion, add=True)

    def _on_enter(self, event=None):
        self._schedule()

    def _on_leave(self, event=None):
        self._unschedule()
        self._hide()

    def _on_motion(self, event=None):
        if self._tipwindow:
            self._reposition()

    def _schedule(self):
        self._unschedule()
        self._job = self.widget.after(self.delay, self._show)

    def _unschedule(self):
        if self._job:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _get_text(self):
        if callable(self.text):
            try:
                return str(self.text())
            except Exception:
                return ""
        return str(self.text or "")

    def _show(self):
        if self._tipwindow or not self.widget.winfo_ismapped():
            return
        text = self._get_text()
        if not text:
            return

        self._tipwindow = tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)

        label = tk.Label(
            tip,
            text=text,
            justify=tk.LEFT,
            background="#ffffff",
            foreground=TEXT_COLOR,
            relief=tk.SOLID,
            borderwidth=1,
            wraplength=self.wraplength,
            padx=10,
            pady=6,
        )
        label.pack()
        self._reposition()

    def _reposition(self):
        if not self._tipwindow:
            return
        try:
            x, y = self.widget.winfo_pointerxy()
            self._tipwindow.wm_geometry(f"+{x + 16}+{y + 18}")
        except Exception:
            pass

    def _hide(self):
        if self._tipwindow:
            try:
                self._tipwindow.destroy()
            except Exception:
                pass
            self._tipwindow = None


def main():
    def signal_handler(sig, frame):
        print("\n检测到 Ctrl+C，已忽略。请使用窗口关闭按钮来停止。")
        return

    signal.signal(signal.SIGINT, signal_handler)

    root = tk.Tk()
    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
