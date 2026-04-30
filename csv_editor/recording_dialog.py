from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QMouseEvent, QMoveEvent, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from csv_editor.adapters.ocr_adapter import RuntimeOcrPreviewAdapter
from csv_editor.domain.enums import BranchTrigger, OperationType
from csv_editor.domain.models import OperationNode
from csv_editor.io.assets import save_capture_image
from csv_editor.io.node_clipboard import NodeClipboardPayload, build_clipboard_payload
from csv_editor.services.capture import capture_region
from csv_editor.services.recording import (
    RecordingService,
    STOP_HOTKEY,
    VisibleWindowInfo,
    VisualMarkAction,
    VisualMarkKind,
    list_visible_windows,
)

RECORDING_HIDE_DELAY_MS = 200
MARK_CAPTURE_HIDE_DELAY_MS = 150
PALETTE_INTERACTION_RESTORE_DELAY_MS = 160
CAPTURE_RESTORE_DELAY_MS = 180
CAPTURE_EVENT_SUPPRESS_SECONDS = 0.25
PALETTE_IDLE_OPACITY = 0.48
PALETTE_ACTIVE_OPACITY = 0.9
COORDINATE_MODE_SCREEN = "screen"
COORDINATE_MODE_WINDOW = "window"
MARK_KIND_LABELS = {
    VisualMarkKind.OCR: "OCR",
    VisualMarkKind.PIC: "PIC",
}
MARK_ACTION_LABELS = {
    VisualMarkAction.WAIT_EXIST: "等待出现",
    VisualMarkAction.WAIT_NOT_EXIST: "等待消失",
    VisualMarkAction.LOCATE: "定位目标",
}
RESULT_HEADERS = ["序号", "来源", "录制语义", "节点", "目标/参数", "区域/坐标", "策略", "等待", "备注"]


@dataclass(slots=True)
class RecordingReviewRow:
    source: str
    semantic: str
    node_text: str
    target_text: str
    region_text: str
    strategy_text: str
    wait_text: str
    note_text: str


def build_recording_review_rows(nodes: list[OperationNode]) -> list[RecordingReviewRow]:
    rows: list[RecordingReviewRow] = []
    for index, node in enumerate(nodes):
        previous = nodes[index - 1] if index > 0 else None
        previous_previous = nodes[index - 2] if index > 1 else None
        rows.append(_build_recording_review_row(node, previous, previous_previous))
    return rows


def _build_recording_review_row(
    node: OperationNode,
    previous: OperationNode | None,
    previous_previous: OperationNode | None,
) -> RecordingReviewRow:
    if node.operation in {OperationType.OCR.value, OperationType.PIC.value}:
        return _build_visual_review_row(node)

    if node.operation == OperationType.MOVE_REL.value and _is_locator_node(previous):
        return _build_keyboard_mouse_review_row(node, "定位偏移", "相对定位偏移")

    if node.operation == OperationType.CLICK.value and _is_locator_node(previous):
        return _build_keyboard_mouse_review_row(node, "点击定位目标", "丢弃录制坐标")

    if (
        node.operation == OperationType.CLICK.value
        and previous
        and previous.operation == OperationType.MOVE_REL.value
        and _is_locator_node(previous_previous)
    ):
        return _build_keyboard_mouse_review_row(node, "点击偏移位置", "相对定位偏移后点击")

    if node.operation == OperationType.MOVE_TO.value:
        return _build_keyboard_mouse_review_row(node, "移动到录制坐标", "保留绝对坐标")

    if node.operation == OperationType.MOVE_REL.value:
        return _build_keyboard_mouse_review_row(node, "相对移动", "保留相对偏移")

    if node.operation == OperationType.CLICK.value:
        return _build_keyboard_mouse_review_row(node, "鼠标点击", "使用当前鼠标位置")

    if node.operation in {OperationType.MOUSE_DOWN.value, OperationType.MOUSE_UP.value}:
        return _build_keyboard_mouse_review_row(node, "鼠标按下/松开", "使用当前鼠标位置")

    if node.operation in {OperationType.PRESS.value, OperationType.KEY_DOWN.value, OperationType.KEY_UP.value, OperationType.WRITE.value}:
        return _build_keyboard_mouse_review_row(node, "键盘输入", "按录制键盘事件执行")

    return _build_keyboard_mouse_review_row(node, "生成节点", "")


def _build_visual_review_row(node: OperationNode) -> RecordingReviewRow:
    target = node.search_target or "(未设置)"
    kind = "OCR" if node.operation == OperationType.OCR.value else "PIC"
    if node.branch.is_enabled:
        if node.branch.trigger is BranchTrigger.EXIST:
            semantic = "等待出现（不移动）"
        elif node.branch.trigger is BranchTrigger.NOT_EXIST:
            semantic = "等待消失（不移动）"
        else:
            semantic = "等待条件（不移动）"
        strategy = f"{node.branch.trigger.value} -> {node.branch.primary_target}; 否则 {node.branch.secondary_target}"
    else:
        semantic = "定位目标（移动到匹配）"
        strategy = "后续点击在区域内则丢弃坐标；区域外则转相对偏移"

    return RecordingReviewRow(
        source=f"{kind} 标记",
        semantic=semantic,
        node_text=node.operation,
        target_text=target,
        region_text=node.region_text or "(未设置)",
        strategy_text=strategy,
        wait_text=node.wait_value,
        note_text=node.note,
    )


def _build_keyboard_mouse_review_row(node: OperationNode, semantic: str, strategy: str) -> RecordingReviewRow:
    return RecordingReviewRow(
        source="键鼠事件",
        semantic=semantic,
        node_text=node.operation,
        target_text=node.param_text or "",
        region_text=_format_recorded_coordinate(node),
        strategy_text=strategy,
        wait_text=node.wait_value,
        note_text=node.note,
    )


def _format_recorded_coordinate(node: OperationNode) -> str:
    if node.operation in {OperationType.MOVE_TO.value, OperationType.MOVE_REL.value}:
        return node.param_text
    return ""


def _is_locator_node(node: OperationNode | None) -> bool:
    return bool(
        node
        and node.operation in {OperationType.OCR.value, OperationType.PIC.value}
        and not node.branch.is_enabled
    )


class RecordingDialog(QDialog):
    def __init__(
        self,
        source_root: Path,
        source_flow: str,
        clipboard_writer: Callable[[NodeClipboardPayload], None],
        host_window: QWidget | None = None,
    ) -> None:
        super().__init__(host_window)
        self._source_root = source_root
        self._source_flow = source_flow
        self._clipboard_writer = clipboard_writer
        self._host_window = host_window
        self._recorded_nodes: list[OperationNode] = []
        self._window_options: list[VisibleWindowInfo] = []
        self._recorder = RecordingService()
        self._recorder.stop_requested.connect(self._finish_recording)
        self._ocr_preview = RuntimeOcrPreviewAdapter()
        self._palette: RecordingPalette | None = None
        self._mark_restore_paused = False
        self._palette_restore_paused = False
        self._marking_active = False

        self.setWindowTitle("录制模式")
        self.resize(900, 620)

        layout = QVBoxLayout(self)

        self.status_label = QLabel("点击“开始录制”后将隐藏窗口，并显示录制浮窗。")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.options_widget = QWidget()
        options_layout = QFormLayout(self.options_widget)
        options_layout.setContentsMargins(0, 0, 0, 0)

        self.coordinate_mode_combo = QComboBox()
        self.coordinate_mode_combo.addItem("屏幕绝对坐标（FrontInput）", COORDINATE_MODE_SCREEN)
        self.coordinate_mode_combo.addItem("窗口内坐标（BackInput）", COORDINATE_MODE_WINDOW)
        self.coordinate_mode_combo.currentIndexChanged.connect(self._update_window_selector_state)
        options_layout.addRow("坐标模式", self.coordinate_mode_combo)

        self.window_search_input = QLineEdit()
        self.window_search_input.setPlaceholderText("搜索窗口标题 / 进程名 / 类名")
        self.window_search_input.textChanged.connect(self._apply_window_filter)
        options_layout.addRow("搜索窗口", self.window_search_input)

        window_row = QWidget()
        window_row_layout = QHBoxLayout(window_row)
        window_row_layout.setContentsMargins(0, 0, 0, 0)
        self.window_combo = QComboBox()
        self.window_combo.setMinimumContentsLength(40)
        self.window_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        window_row_layout.addWidget(self.window_combo, 1)
        self.refresh_windows_button = QPushButton("刷新窗口")
        self.refresh_windows_button.clicked.connect(self._refresh_window_list)
        window_row_layout.addWidget(self.refresh_windows_button)
        options_layout.addRow("目标窗口", window_row)

        self.match_child_window_checkbox = QCheckBox("开启子窗口匹配")
        self.match_child_window_checkbox.setToolTip("按点击位置匹配最合适的子窗口，并使用子窗口内坐标。")
        options_layout.addRow("", self.match_child_window_checkbox)

        self.window_tip_label = QLabel("选择目标窗口后，录制到的鼠标坐标会自动转换成窗口内坐标。")
        self.window_tip_label.setWordWrap(True)
        options_layout.addRow("", self.window_tip_label)
        layout.addWidget(self.options_widget)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("开始录制")
        self.start_button.clicked.connect(self._prepare_recording)
        button_row.addWidget(self.start_button)

        self.stop_button = QPushButton("停止录制")
        self.stop_button.clicked.connect(self._stop_recording_from_button)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.stop_button)

        self.copy_selected_button = QPushButton("复制选中")
        self.copy_selected_button.clicked.connect(self._copy_selected_nodes)
        self.copy_selected_button.setEnabled(False)
        button_row.addWidget(self.copy_selected_button)

        self.copy_all_button = QPushButton("复制全部")
        self.copy_all_button.clicked.connect(self._copy_all_nodes)
        self.copy_all_button.setEnabled(False)
        button_row.addWidget(self.copy_all_button)

        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.reject)
        button_row.addWidget(self.close_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.result_summary_label = QLabel("录制结束后会在这里显示草稿节点审查表。")
        self.result_summary_label.setWordWrap(True)
        layout.addWidget(self.result_summary_label)

        self.result_table = QTableWidget(0, len(RESULT_HEADERS))
        self.result_table.setHorizontalHeaderLabels(RESULT_HEADERS)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        header.setSectionResizeMode(5, QHeaderView.Interactive)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.Interactive)
        layout.addWidget(self.result_table, 1)

        self.tip_label = QLabel("录制结果按生成节点展示；可多选离散节点复制，也可以一键复制全部草稿节点。")
        self.tip_label.setWordWrap(True)
        layout.addWidget(self.tip_label)

        self._refresh_window_list()
        self._update_window_selector_state()

    def _prepare_recording(self) -> None:
        if self._recorder.is_recording:
            return

        target_window = self._selected_window()
        if self._coordinate_mode() == COORDINATE_MODE_WINDOW and target_window is None:
            QMessageBox.information(self, "请选择窗口", "窗口内坐标模式下，请先选择一个目标窗口。")
            return
        self._recorder.set_target_window(
            target_window,
            match_child_window=self.match_child_window_checkbox.isChecked(),
        )

        QMessageBox.information(
            self,
            "开始录制",
            f"录制开始后会隐藏编辑器和录制窗口，并显示录制浮窗。\n可点击浮窗停止，{STOP_HOTKEY.upper()} 也可作为备用结束方式。",
        )
        self._set_recording_ui_state(True)
        self.status_label.setText("录制中，可通过录制浮窗添加 OCR/PIC 标记或停止录制。")

        if self._host_window is not None:
            self._host_window.showMinimized()
        self.showMinimized()
        QTimer.singleShot(RECORDING_HIDE_DELAY_MS, self._start_recording)

    def _start_recording(self) -> None:
        try:
            self._recorder.start()
            self._show_palette()
        except Exception as exc:
            self._restore_windows()
            self._set_recording_ui_state(False)
            self.status_label.setText("录制启动失败。")
            QMessageBox.critical(self, "录制失败", f"无法启动录制：{exc}")

    def _finish_recording(self) -> None:
        self._close_palette()
        self._recorded_nodes = self._recorder.stop()
        self._refresh_table()
        self._restore_windows()
        self._set_recording_ui_state(False)
        self.start_button.setText("重新录制")
        self.copy_selected_button.setEnabled(bool(self._recorded_nodes))
        self.copy_all_button.setEnabled(bool(self._recorded_nodes))
        self.status_label.setText(
            f"录制结束，共生成 {len(self._recorded_nodes)} 个草稿节点。"
            if self._recorded_nodes
            else "录制结束，但没有捕获到可生成的节点。"
        )

    def _stop_recording_from_button(self) -> None:
        if not self._recorder.is_recording:
            return
        self._finish_recording()

    def _restore_windows(self) -> None:
        if self._host_window is not None:
            self._host_window.showNormal()
            self._host_window.raise_()
            self._host_window.activateWindow()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _show_palette(self) -> None:
        self._palette = RecordingPalette()
        self._palette.mark_requested.connect(self._capture_visual_mark)
        self._palette.stop_requested.connect(self._stop_recording_from_button)
        self._palette.pause_changed.connect(self._set_recording_paused)
        self._palette.interaction_started.connect(self._pause_for_palette_interaction)
        self._palette.interaction_finished.connect(self._restore_after_palette_interaction)
        self._palette.geometry_changed.connect(self._update_palette_ignore_rect)
        self._palette.show()
        self._palette.raise_()
        self._update_palette_ignore_rect()

    def _close_palette(self) -> None:
        if self._palette is None:
            return
        self._recorder.set_ignored_screen_rects([])
        self._palette.allow_close()
        self._palette.close()
        self._palette = None

    def _set_recording_paused(self, paused: bool) -> None:
        self._recorder.set_capture_paused(paused)
        if self._palette is not None:
            self._palette.set_status("已暂停" if paused else "录制中")

    def _pause_for_palette_interaction(self) -> None:
        self._palette_restore_paused = bool(self._palette and self._palette.is_paused())
        self._recorder.set_capture_paused(True)

    def _restore_after_palette_interaction(self) -> None:
        QTimer.singleShot(PALETTE_INTERACTION_RESTORE_DELAY_MS, self._restore_after_palette_delay)

    def _restore_after_palette_delay(self) -> None:
        if not self._recorder.is_recording:
            return
        if self._marking_active:
            return
        self._recorder.set_capture_paused(self._palette_restore_paused)

    def _update_palette_ignore_rect(self) -> None:
        if self._palette is None or not self._palette.isVisible():
            self._recorder.set_ignored_screen_rects([])
            return
        geometry = self._palette.frameGeometry()
        self._recorder.set_ignored_screen_rects(
            [(geometry.left(), geometry.top(), geometry.width(), geometry.height())]
        )

    def _capture_visual_mark(self, kind: str, action: str) -> None:
        if not self._recorder.is_recording:
            return
        palette = self._palette
        self._marking_active = True
        self._mark_restore_paused = bool(palette and palette.is_paused())
        self._recorder.set_capture_paused(True)
        self._recorder.suppress_events_for(CAPTURE_EVENT_SUPPRESS_SECONDS)
        if palette is not None:
            palette.remember_position()
            palette.setEnabled(False)
            palette.set_status("标记中")
            palette.hide()
            self._update_palette_ignore_rect()
        QTimer.singleShot(MARK_CAPTURE_HIDE_DELAY_MS, lambda: self._capture_visual_mark_after_hide(kind, action))

    def _capture_visual_mark_after_hide(self, kind: str, action: str) -> None:
        label = f"{MARK_KIND_LABELS.get(kind, kind)} {MARK_ACTION_LABELS.get(action, action)}：框选目标区域"
        captured = None
        error_text = ""
        note = ""
        search_target = ""
        try:
            captured = capture_region(None, prompt=label)
            if captured is not None:
                if kind == VisualMarkKind.PIC:
                    search_target = save_capture_image(
                        self._source_root,
                        captured.image,
                        captured.left,
                        captured.top,
                        captured.width,
                        captured.height,
                    )
                else:
                    candidates = self._ocr_preview.preview_from_image(captured.image)
                    unique_candidates = [candidate for candidate in dict.fromkeys(candidates) if candidate.strip()]
                    if unique_candidates:
                        search_target = unique_candidates[0].strip()
                        if len(unique_candidates) > 1:
                            note = f"OCR 录制候选: {' | '.join(unique_candidates[:5])}"
                    else:
                        note = "OCR 录制未识别到文本，请在复制前补充目标"

                self._recorder.add_visual_mark(
                    kind=kind,
                    action=action,
                    search_target=search_target,
                    region_text=captured.region_text,
                    note=note,
                )
        except Exception as exc:
            error_text = f"标记失败：{exc}"

        self._recorder.suppress_events_for(CAPTURE_EVENT_SUPPRESS_SECONDS)
        if self._palette is not None:
            self._palette.setEnabled(True)
            self._palette.restore_position()
            self._palette.show()
            self._palette.raise_()
            self._update_palette_ignore_rect()
            if error_text:
                self._palette.set_status(error_text)
            elif captured is None:
                self._palette.set_status("已取消标记")
            else:
                target_label = search_target or "(未识别目标)"
                self._palette.set_status(f"已添加 {MARK_KIND_LABELS.get(kind, kind)} {MARK_ACTION_LABELS.get(action, action)} {target_label}")
            if self._mark_restore_paused:
                self._palette.set_status("已暂停")
        QTimer.singleShot(CAPTURE_RESTORE_DELAY_MS, self._restore_after_capture_delay)

    def _restore_after_capture_delay(self) -> None:
        if not self._recorder.is_recording:
            self._marking_active = False
            return
        self._recorder.set_capture_paused(self._mark_restore_paused)
        self._marking_active = False

    def _refresh_table(self) -> None:
        rows = build_recording_review_rows(self._recorded_nodes)
        visual_operations = {OperationType.OCR.value, OperationType.PIC.value}
        visual_count = sum(1 for node in self._recorded_nodes if node.operation in visual_operations)
        wait_count = sum(1 for node in self._recorded_nodes if node.operation in visual_operations and node.branch.is_enabled)
        locator_count = sum(1 for node in self._recorded_nodes if node.operation in visual_operations and not node.branch.is_enabled)
        input_count = len(self._recorded_nodes) - visual_count
        self.result_summary_label.setText(
            f"草稿节点 {len(self._recorded_nodes)} 个；视觉标记 {visual_count} 个"
            f"（等待 {wait_count}，定位 {locator_count}）；键鼠节点 {input_count} 个。"
        )
        self.result_table.setRowCount(len(self._recorded_nodes))
        for row, (node, review) in enumerate(zip(self._recorded_nodes, rows, strict=True)):
            self.result_table.setItem(row, 0, QTableWidgetItem(str(node.index)))
            self.result_table.setItem(row, 1, QTableWidgetItem(review.source))
            self.result_table.setItem(row, 2, QTableWidgetItem(review.semantic))
            self.result_table.setItem(row, 3, QTableWidgetItem(review.node_text))
            self.result_table.setItem(row, 4, QTableWidgetItem(review.target_text))
            self.result_table.setItem(row, 5, QTableWidgetItem(review.region_text))
            self.result_table.setItem(row, 6, QTableWidgetItem(review.strategy_text))
            self.result_table.setItem(row, 7, QTableWidgetItem(review.wait_text))
            self.result_table.setItem(row, 8, QTableWidgetItem(review.note_text))

    def _copy_selected_nodes(self) -> None:
        selected_rows = self._selected_row_indexes()
        if not selected_rows:
            QMessageBox.information(self, "复制节点", "请先选择要复制的录制节点。")
            return
        self._copy_nodes([self._recorded_nodes[row] for row in selected_rows])

    def _copy_all_nodes(self) -> None:
        if not self._recorded_nodes:
            QMessageBox.information(self, "复制节点", "当前没有可复制的录制节点。")
            return
        self._copy_nodes(self._recorded_nodes)

    def _copy_nodes(self, nodes: list[OperationNode]) -> None:
        payload = build_clipboard_payload(self._source_root, self._source_flow, nodes)
        self._clipboard_writer(payload)
        self.status_label.setText(f"已复制 {len(nodes)} 个录制节点，可切回主流程粘贴。")

    def _selected_row_indexes(self) -> list[int]:
        rows = {index.row() for index in self.result_table.selectionModel().selectedRows()} if self.result_table.selectionModel() else set()
        return sorted(row for row in rows if 0 <= row < len(self._recorded_nodes))

    def _set_recording_ui_state(self, recording: bool) -> None:
        self.start_button.setEnabled(not recording)
        self.stop_button.setEnabled(recording)
        self.copy_selected_button.setEnabled(not recording and bool(self._recorded_nodes))
        self.copy_all_button.setEnabled(not recording and bool(self._recorded_nodes))
        self.close_button.setEnabled(not recording)
        self.coordinate_mode_combo.setEnabled(not recording)
        self.window_combo.setEnabled(not recording and self._coordinate_mode() == COORDINATE_MODE_WINDOW)
        self.refresh_windows_button.setEnabled(not recording and self._coordinate_mode() == COORDINATE_MODE_WINDOW)
        self.window_search_input.setEnabled(not recording and self._coordinate_mode() == COORDINATE_MODE_WINDOW)
        self.match_child_window_checkbox.setEnabled(not recording and self._coordinate_mode() == COORDINATE_MODE_WINDOW)

    def _coordinate_mode(self) -> str:
        return str(self.coordinate_mode_combo.currentData() or COORDINATE_MODE_SCREEN)

    def _selected_window(self) -> VisibleWindowInfo | None:
        value = self.window_combo.currentData()
        return value if isinstance(value, VisibleWindowInfo) else None

    def _refresh_window_list(self) -> None:
        selected_window = self._selected_window()
        current_hwnd = selected_window.hwnd if selected_window else None
        self._window_options = list_visible_windows()
        self._apply_window_filter(current_hwnd=current_hwnd)

    def _apply_window_filter(self, _text: str | None = None, current_hwnd: int | None = None) -> None:
        search_text = self.window_search_input.text().strip().lower()
        selected_hwnd = current_hwnd if current_hwnd is not None else (self._selected_window().hwnd if self._selected_window() else None)
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        self.window_combo.addItem("请选择目标窗口", None)
        selected_index = 0
        filtered_windows = [
            window for window in self._window_options
            if not search_text or search_text in window.display_text.lower()
        ]
        for index, window in enumerate(filtered_windows, start=1):
            self.window_combo.addItem(window.display_text, window)
            if selected_hwnd and window.hwnd == selected_hwnd:
                selected_index = index
        self.window_combo.setCurrentIndex(selected_index)
        self.window_combo.blockSignals(False)
        self.window_tip_label.setText(
            "选择目标窗口后，录制到的鼠标坐标会自动转换成窗口内坐标。"
            if filtered_windows
            else "当前没有匹配到窗口，可调整搜索词或点击“刷新窗口”。"
        )
        self._update_window_selector_state()

    def _update_window_selector_state(self) -> None:
        enabled = self._coordinate_mode() == COORDINATE_MODE_WINDOW and not self._recorder.is_recording
        self.window_combo.setEnabled(enabled)
        self.refresh_windows_button.setEnabled(enabled)
        self.window_search_input.setEnabled(enabled)
        self.match_child_window_checkbox.setEnabled(enabled)

    def reject(self) -> None:
        if self._recorder.is_recording:
            QMessageBox.information(self, "录制中", "请先结束录制，再关闭录制窗口。")
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._recorder.is_recording:
            event.ignore()
            QMessageBox.information(self, "录制中", "请先结束录制，再关闭录制窗口。")
            return
        super().closeEvent(event)


class RecordingPalette(QDialog):
    mark_requested = Signal(str, str)
    stop_requested = Signal()
    pause_changed = Signal(bool)
    interaction_started = Signal()
    interaction_finished = Signal()
    geometry_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._allow_close = False
        self._drag_offset: QPoint | None = None
        self._last_position: QPoint | None = None
        self._hovering = False
        self.setWindowTitle("录制模式")
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setWindowOpacity(PALETTE_IDLE_OPACITY)
        self.setFixedWidth(210)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.status_label = QLabel("录制中")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        first_mark_row = QHBoxLayout()
        first_mark_row.addWidget(self._mark_button("OCR出现", VisualMarkKind.OCR, VisualMarkAction.WAIT_EXIST))
        first_mark_row.addWidget(self._mark_button("OCR消失", VisualMarkKind.OCR, VisualMarkAction.WAIT_NOT_EXIST))
        first_mark_row.addWidget(self._mark_button("OCR定位", VisualMarkKind.OCR, VisualMarkAction.LOCATE))
        layout.addLayout(first_mark_row)

        second_mark_row = QHBoxLayout()
        second_mark_row.addWidget(self._mark_button("PIC出现", VisualMarkKind.PIC, VisualMarkAction.WAIT_EXIST))
        second_mark_row.addWidget(self._mark_button("PIC消失", VisualMarkKind.PIC, VisualMarkAction.WAIT_NOT_EXIST))
        second_mark_row.addWidget(self._mark_button("PIC定位", VisualMarkKind.PIC, VisualMarkAction.LOCATE))
        layout.addLayout(second_mark_row)

        button_row = QHBoxLayout()
        self.pause_button = QPushButton("暂停")
        self.pause_button.setCheckable(True)
        self.pause_button.toggled.connect(self._toggle_pause)
        stop_button = QPushButton("停止")
        stop_button.clicked.connect(self.stop_requested.emit)
        button_row.addWidget(self.pause_button)
        button_row.addWidget(stop_button)
        layout.addLayout(button_row)
        self._wire_interaction_pause()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self._refresh_opacity()

    def _mark_button(self, text: str, kind: str, action: str) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(
            lambda _checked=False, mark_kind=kind, mark_action=action: self.mark_requested.emit(
                mark_kind,
                mark_action,
            )
        )
        return button

    def _toggle_pause(self, paused: bool) -> None:
        self.pause_button.setText("继续" if paused else "暂停")
        self._refresh_opacity()
        self.pause_changed.emit(paused)

    def is_paused(self) -> bool:
        return self.pause_button.isChecked()

    def allow_close(self) -> None:
        self._allow_close = True

    def remember_position(self) -> None:
        self._last_position = self.pos()

    def restore_position(self) -> None:
        if self._last_position is not None:
            self.move(self._last_position)

    def _wire_interaction_pause(self) -> None:
        for button in self.findChildren(QPushButton):
            button.pressed.connect(self._begin_interaction)
            button.released.connect(self._finish_interaction)

    def _begin_interaction(self) -> None:
        self.interaction_started.emit()

    def _finish_interaction(self) -> None:
        self.interaction_finished.emit()

    def _refresh_opacity(self) -> None:
        if self._hovering or self.is_paused():
            self.setWindowOpacity(PALETTE_ACTIVE_OPACITY)
        else:
            self.setWindowOpacity(PALETTE_IDLE_OPACITY)

    def enterEvent(self, event) -> None:
        self._hovering = True
        self._refresh_opacity()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovering = False
        self._refresh_opacity()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._begin_interaction()
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.button() == Qt.LeftButton:
            self._drag_offset = None
            self.remember_position()
            self._finish_interaction()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def moveEvent(self, event: QMoveEvent) -> None:
        self.remember_position()
        self.geometry_changed.emit()
        super().moveEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.geometry_changed.emit()
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close:
            super().closeEvent(event)
            return
        event.ignore()
        self.stop_requested.emit()
