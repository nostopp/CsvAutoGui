from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
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

from csv_editor.domain.models import OperationNode
from csv_editor.io.node_clipboard import NodeClipboardPayload, build_clipboard_payload
from csv_editor.services.recording import RecordingService, STOP_HOTKEY, VisibleWindowInfo, list_visible_windows

RECORDING_HIDE_DELAY_MS = 200
COORDINATE_MODE_SCREEN = "screen"
COORDINATE_MODE_WINDOW = "window"


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

        self.setWindowTitle("录制操作")
        self.resize(900, 620)

        layout = QVBoxLayout(self)

        self.status_label = QLabel("点击“开始录制”后将隐藏窗口，按 Shift+X 结束录制。")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        options_widget = QWidget()
        options_layout = QFormLayout(options_widget)
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
        layout.addWidget(options_widget)

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

        self.result_table = QTableWidget(0, 4)
        self.result_table.setHorizontalHeaderLabels(["序号", "操作", "操作参数", "完成后等待时间"])
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.result_table, 1)

        self.tip_label = QLabel("支持任意多选离散节点后复制，也可以一键复制全部录制结果。")
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
            f"录制开始后会隐藏编辑器和录制窗口。\n录制过程中按 {STOP_HOTKEY.upper()} 结束。",
        )
        self._set_recording_ui_state(True)
        self.status_label.setText("录制中，按 Shift+X 结束录制。")

        if self._host_window is not None:
            self._host_window.showMinimized()
        self.showMinimized()
        QTimer.singleShot(RECORDING_HIDE_DELAY_MS, self._start_recording)

    def _start_recording(self) -> None:
        try:
            self._recorder.start()
        except Exception as exc:
            self._restore_windows()
            self._set_recording_ui_state(False)
            self.status_label.setText("录制启动失败。")
            QMessageBox.critical(self, "录制失败", f"无法启动录制：{exc}")

    def _finish_recording(self) -> None:
        self._recorded_nodes = self._recorder.stop()
        self._refresh_table()
        self._restore_windows()
        self._set_recording_ui_state(False)
        self.copy_selected_button.setEnabled(bool(self._recorded_nodes))
        self.copy_all_button.setEnabled(bool(self._recorded_nodes))
        self.status_label.setText(
            f"录制结束，共生成 {len(self._recorded_nodes)} 个节点。可选择任意节点复制。"
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

    def _refresh_table(self) -> None:
        self.result_table.setRowCount(len(self._recorded_nodes))
        for row, node in enumerate(self._recorded_nodes):
            self.result_table.setItem(row, 0, QTableWidgetItem(str(node.index)))
            self.result_table.setItem(row, 1, QTableWidgetItem(node.operation))
            self.result_table.setItem(row, 2, QTableWidgetItem(node.param_text))
            self.result_table.setItem(row, 3, QTableWidgetItem(node.wait_value))
        self.result_table.resizeColumnsToContents()

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
