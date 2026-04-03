from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QPixmap, QUndoStack
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QDialog,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from csv_editor.adapters import RuntimeOcrPreviewAdapter
from csv_editor.domain.enums import BranchMode, BranchTrigger, OperationType, ValidationSeverity
from csv_editor.domain.models import BranchConfig, EditorDocument, FlowDocument, OperationNode, ValidationIssue
from csv_editor.io.assets import save_capture_image
from csv_editor.io.csv_codec import CsvEditorCodec
from csv_editor.io.editor_state import EditorStateRepository
from csv_editor.services.capture import capture_point, capture_region
from csv_editor.services.asset_usage import find_unused_images
from csv_editor.services.summary import summarize_node
from csv_editor.services.validation import validate_document
from csv_editor.undo_commands import DeleteNodeCommand, InsertNodeCommand, MoveNodeCommand, UpdateNodeCommand

CAPTURE_HIDE_DELAY_SECONDS = 0.2


class EditorMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.codec = CsvEditorCodec()
        self.state_repo = EditorStateRepository(enabled=False)
        self.ocr_preview = RuntimeOcrPreviewAdapter()
        self.undo_stack = QUndoStack(self)
        self.document: EditorDocument | None = None
        self.current_flow_name: str | None = None
        self.current_node_id: str | None = None
        self.issues: list[ValidationIssue] = []
        self._title_base = "CsvAutoGui Editor"
        self.setWindowTitle(f"{self._title_base}[*]")
        self.resize(1400, 900)

        self._build_actions()
        self._build_ui()
        self._connect_signals()
        self._update_actions_enabled(False)

    def _build_actions(self) -> None:
        self.open_action = QAction("打开配置目录", self)
        self.save_action = QAction("保存 CSV", self)
        self.reload_action = QAction("重新加载", self)
        self.scan_unused_images_action = QAction("扫描未使用图片", self)
        self.undo_action = self.undo_stack.createUndoAction(self, "撤销")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action = self.undo_stack.createRedoAction(self, "重做")
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.add_node_action = QAction("新增节点", self)
        self.duplicate_node_action = QAction("复制节点", self)
        self.delete_node_action = QAction("删除节点", self)
        self.move_up_action = QAction("上移", self)
        self.move_down_action = QAction("下移", self)
        self._configure_action_hints()

    def _build_ui(self) -> None:
        menu = self.menuBar().addMenu("文件")
        menu.addAction(self.open_action)
        menu.addAction(self.save_action)
        menu.addAction(self.reload_action)

        edit_menu = self.menuBar().addMenu("编辑")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.add_node_action)
        edit_menu.addAction(self.duplicate_node_action)
        edit_menu.addAction(self.delete_node_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.move_up_action)
        edit_menu.addAction(self.move_down_action)

        tools_menu = self.menuBar().addMenu("工具")
        tools_menu.addAction(self.scan_unused_images_action)

        toolbar = self.addToolBar("编辑")
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addAction(self.scan_unused_images_action)
        toolbar.addSeparator()
        toolbar.addAction(self.add_node_action)
        toolbar.addAction(self.duplicate_node_action)
        toolbar.addAction(self.delete_node_action)
        toolbar.addAction(self.move_up_action)
        toolbar.addAction(self.move_down_action)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(6, 6, 6, 6)

        body_splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(body_splitter, 1)

        self.flow_tree = QTreeWidget()
        self.flow_tree.setHeaderLabels(["流程文件"])
        self.flow_tree.setMinimumWidth(220)
        body_splitter.addWidget(self.flow_tree)

        center_splitter = QSplitter(Qt.Vertical)
        body_splitter.addWidget(center_splitter)
        body_splitter.setStretchFactor(1, 1)

        content_splitter = QSplitter(Qt.Horizontal)
        center_splitter.addWidget(content_splitter)
        center_splitter.setStretchFactor(0, 3)

        self.node_table = NodeTableWidget(0, 5)
        self.node_table.setHorizontalHeaderLabels(["序号", "类型", "跳转标记", "摘要", "备注"])
        self.node_table.verticalHeader().setVisible(False)
        self.node_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.node_table.setSelectionMode(QTableWidget.SingleSelection)
        self.node_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.node_table.horizontalHeader().setStretchLastSection(True)
        self.node_table.setMinimumWidth(520)
        content_splitter.addWidget(self.node_table)
        content_splitter.setStretchFactor(0, 2)

        self.inspector = NodeInspector()
        content_splitter.addWidget(self.inspector)
        content_splitter.setStretchFactor(1, 2)

        bottom_splitter = QSplitter(Qt.Horizontal)
        center_splitter.addWidget(bottom_splitter)
        center_splitter.setStretchFactor(1, 1)

        left_bottom = QWidget()
        left_bottom_layout = QVBoxLayout(left_bottom)
        left_bottom_layout.setContentsMargins(0, 0, 0, 0)

        left_bottom_layout.addWidget(QLabel("校验问题"))
        self.validation_list = QListWidget()
        left_bottom_layout.addWidget(self.validation_list, 1)

        bottom_splitter.addWidget(left_bottom)

        self.csv_preview = QPlainTextEdit()
        self.csv_preview.setReadOnly(True)
        bottom_splitter.addWidget(self.csv_preview)
        bottom_splitter.setStretchFactor(1, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage("请选择配置目录")

    def _connect_signals(self) -> None:
        self.open_action.triggered.connect(self.choose_config_folder)
        self.save_action.triggered.connect(self.save_document)
        self.reload_action.triggered.connect(self.reload_document)
        self.scan_unused_images_action.triggered.connect(self.show_unused_images_dialog)
        self.add_node_action.triggered.connect(self.add_node)
        self.duplicate_node_action.triggered.connect(self.duplicate_node)
        self.delete_node_action.triggered.connect(self.delete_node)
        self.move_up_action.triggered.connect(self.move_node_up)
        self.move_down_action.triggered.connect(self.move_node_down)
        self.flow_tree.itemSelectionChanged.connect(self._on_flow_selection_changed)
        self.node_table.itemSelectionChanged.connect(self._on_node_selection_changed)
        self.validation_list.itemSelectionChanged.connect(self._on_issue_selection_changed)
        self.node_table.customContextMenuRequested.connect(self._show_node_context_menu)
        self.inspector.node_changed.connect(self._on_node_changed)
        self.inspector.action_requested.connect(self._on_inspector_action)
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)
        self.undo_stack.indexChanged.connect(self._on_undo_stack_index_changed)

    def choose_config_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择配置目录")
        if directory:
            self.open_config_folder(Path(directory))

    def open_config_folder(self, root_path: Path) -> None:
        if not root_path.exists():
            QMessageBox.warning(self, "路径不存在", f"未找到目录: {root_path}")
            return
        document = self.codec.load_document(root_path)
        document.state = self.state_repo.load(root_path)
        self.document = document
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self.current_flow_name = document.state.selected_flow if document.get_flow(document.state.selected_flow) else None
        if self.current_flow_name is None and document.flows:
            self.current_flow_name = document.flows[0].filename
        self.current_node_id = document.state.selected_node_id
        self._refresh_all()
        self._update_actions_enabled(True)
        self.statusBar().showMessage(f"已打开: {root_path}")
        self._title_base = f"CsvAutoGui Editor - {root_path}"
        self.setWindowTitle(f"{self._title_base}[*]")
        self.setWindowModified(False)

    def reload_document(self) -> None:
        if not self.document:
            return
        self.open_config_folder(self.document.root_path)

    def save_document(self) -> None:
        if not self.document:
            return
        self.codec.save_document(self.document)
        self.undo_stack.setClean()
        self.statusBar().showMessage("CSV 已保存", 3000)
        self._refresh_preview()

    def _refresh_all(self) -> None:
        self._refresh_flow_tree()
        self._refresh_validation()
        self._refresh_node_table()
        self._refresh_preview()

    def _refresh_flow_tree(self) -> None:
        self.flow_tree.blockSignals(True)
        self.flow_tree.clear()
        if not self.document:
            self.flow_tree.blockSignals(False)
            return

        root_item = QTreeWidgetItem([self.document.root_path.name])
        root_item.setData(0, Qt.UserRole, None)
        self.flow_tree.addTopLevelItem(root_item)
        for flow in self.document.flows:
            child = QTreeWidgetItem([flow.filename])
            child.setData(0, Qt.UserRole, flow.filename)
            root_item.addChild(child)
            if flow.filename == self.current_flow_name:
                self.flow_tree.setCurrentItem(child)
        root_item.setExpanded(True)
        self.flow_tree.blockSignals(False)

    def _refresh_validation(self) -> None:
        self.validation_list.blockSignals(True)
        self.validation_list.clear()
        if self.document:
            self.issues = validate_document(self.document)
        else:
            self.issues = []

        for issue in self.issues:
            if self.current_flow_name and issue.flow_name != self.current_flow_name:
                continue
            prefix = "错误" if issue.severity is ValidationSeverity.ERROR else "警告"
            item = QListWidgetItem(f"[{prefix}] {issue.message}")
            item.setData(Qt.UserRole, issue.node_id)
            self.validation_list.addItem(item)
        self.validation_list.blockSignals(False)

    def _refresh_node_table(self) -> None:
        self.node_table.blockSignals(True)
        self.node_table.setRowCount(0)
        flow = self.current_flow
        if not flow:
            self.node_table.blockSignals(False)
            self.inspector.set_reference_data([], [])
            self.inspector.set_node(None)
            return

        flow.reindex()
        jump_targets = sorted({str(node.index) for node in flow.nodes} | set(flow.jump_marks().keys()), key=str.lower)
        subflow_targets = list(self.document.iter_flow_filenames()) if self.document else []
        self.inspector.set_reference_data(jump_targets, subflow_targets)
        issue_node_ids = {issue.node_id for issue in self.issues if issue.flow_name == flow.filename and issue.node_id}
        self.node_table.setRowCount(len(flow.nodes))
        for row, node in enumerate(flow.nodes):
            index_item = QTableWidgetItem(str(node.index))
            type_item = QTableWidgetItem(node.operation)
            jump_mark_item = QTableWidgetItem(node.jump_mark)
            summary_item = QTableWidgetItem(summarize_node(node))
            note_item = QTableWidgetItem(node.note)
            summary_item.setData(Qt.UserRole, node.node_id)
            if node.node_id in issue_node_ids:
                summary_item.setForeground(Qt.red)
            if node.jump_mark:
                jump_mark_item.setForeground(Qt.blue)
            self.node_table.setItem(row, 0, index_item)
            self.node_table.setItem(row, 1, type_item)
            self.node_table.setItem(row, 2, jump_mark_item)
            self.node_table.setItem(row, 3, summary_item)
            self.node_table.setItem(row, 4, note_item)
            if node.node_id == self.current_node_id:
                self.node_table.selectRow(row)

        if self.current_node_id is None and flow.nodes:
            self.current_node_id = flow.nodes[0].node_id
            self.node_table.selectRow(0)

        self.node_table.resizeColumnsToContents()
        self.node_table.blockSignals(False)
        self.inspector.set_node(self.current_node)

    def _refresh_preview(self) -> None:
        flow = self.current_flow
        if not flow:
            self.csv_preview.clear()
            return
        self.csv_preview.setPlainText(self.codec.flow_to_csv_text(flow))

    def _on_flow_selection_changed(self) -> None:
        selected = self.flow_tree.selectedItems()
        if not selected:
            return
        filename = selected[0].data(0, Qt.UserRole)
        if not filename:
            return
        self.current_flow_name = filename
        flow = self.current_flow
        self.current_node_id = flow.nodes[0].node_id if flow and flow.nodes else None
        self._refresh_validation()
        self._refresh_node_table()
        self._refresh_preview()

    def _on_node_selection_changed(self) -> None:
        current_row = self.node_table.currentRow()
        flow = self.current_flow
        if current_row < 0 or not flow or current_row >= len(flow.nodes):
            self.current_node_id = None
            self.inspector.set_node(None)
            return
        self.current_node_id = flow.nodes[current_row].node_id
        self.inspector.set_node(flow.nodes[current_row])

    def _on_issue_selection_changed(self) -> None:
        items = self.validation_list.selectedItems()
        if not items or not self.current_flow:
            return
        target_node_id = items[0].data(Qt.UserRole)
        if not target_node_id:
            return
        for row, node in enumerate(self.current_flow.nodes):
            if node.node_id == target_node_id:
                self.node_table.selectRow(row)
                break

    def _on_node_changed(self, updated_node: OperationNode) -> None:
        flow = self.current_flow
        if not flow:
            return
        current = flow.get_node(updated_node.node_id)
        if not current:
            return
        before = current.clone()
        after = updated_node.clone()
        if self._nodes_equal(before, after):
            return
        self.undo_stack.push(UpdateNodeCommand(self, flow.filename, before, after))

    def _on_inspector_action(self, action: str, node_id: str) -> None:
        if not self.document:
            return
        flow = self.current_flow
        if not flow:
            return
        node = flow.get_node(node_id)
        if not node:
            return

        if action == "capture_pic":
            before = node.clone()
            captured = self._capture_region_with_hidden_window()
            if not captured:
                return
            filename = save_capture_image(
                self.document.root_path,
                captured.image,
                captured.left,
                captured.top,
                captured.width,
                captured.height,
            )
            node.search_target = filename
            node.region_text = captured.region_text
            if not node.confidence_text:
                node.confidence_text = "0.8"
            self.statusBar().showMessage(f"已保存图片素材: {filename}", 4000)
            after = node.clone()
            node.apply_from(before)
            self.undo_stack.push(UpdateNodeCommand(self, flow.filename, before, after, "截图回填图片节点"))

        elif action == "capture_ocr":
            before = node.clone()
            captured = self._capture_region_with_hidden_window()
            if not captured:
                return
            node.region_text = captured.region_text
            if not node.confidence_text:
                node.confidence_text = "0.9"
            candidates = self.ocr_preview.preview_from_image(captured.image)
            if candidates:
                unique_candidates = list(dict.fromkeys(candidates))
                if len(unique_candidates) == 1:
                    node.search_target = unique_candidates[0]
                    self.statusBar().showMessage(f"OCR 预览命中: {unique_candidates[0]}", 4000)
                else:
                    selected, ok = QInputDialog.getItem(
                        self,
                        "选择 OCR 文本",
                        "检测到多个文本，请选择或自行编辑",
                        unique_candidates,
                        0,
                        editable=True,
                    )
                    if ok and selected.strip():
                        node.search_target = selected.strip()
            else:
                QMessageBox.information(self, "OCR 预览", "当前区域未识别到可用文本，已仅回填搜索区域。")
            after = node.clone()
            node.apply_from(before)
            if not self._nodes_equal(before, after):
                self.undo_stack.push(UpdateNodeCommand(self, flow.filename, before, after, "截图回填 OCR 节点"))

        elif action == "pick_point":
            before = node.clone()
            captured = self._capture_point_with_hidden_window()
            if not captured:
                return
            node.param_text = captured.point_text
            self.statusBar().showMessage(f"已回填坐标: {captured.point_text}", 3000)
            after = node.clone()
            node.apply_from(before)
            self.undo_stack.push(UpdateNodeCommand(self, flow.filename, before, after, "拾取坐标"))
        else:
            return

    def _capture_region_with_hidden_window(self):
        self.hide()
        QGuiApplication.processEvents()
        time.sleep(CAPTURE_HIDE_DELAY_SECONDS)
        QGuiApplication.processEvents()
        try:
            return capture_region(None)
        finally:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QGuiApplication.processEvents()

    def _capture_point_with_hidden_window(self):
        self.hide()
        QGuiApplication.processEvents()
        time.sleep(CAPTURE_HIDE_DELAY_SECONDS)
        QGuiApplication.processEvents()
        try:
            return capture_point(None)
        finally:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QGuiApplication.processEvents()

    def add_node(self) -> None:
        flow = self.current_flow
        if not flow:
            return
        choices = [item.value for item in OperationType]
        operation, ok = QInputDialog.getItem(self, "新增节点", "操作类型", choices, editable=False)
        if not ok or not operation:
            return

        node = OperationNode(operation=operation)
        insert_at = self.node_table.currentRow()
        target_index = len(flow.nodes) if insert_at < 0 else insert_at + 1
        self.undo_stack.push(InsertNodeCommand(self, flow.filename, node, target_index, "新增节点"))

    def duplicate_node(self) -> None:
        flow = self.current_flow
        node = self.current_node
        if not flow or not node:
            return

        duplicate = OperationNode(
            operation=node.operation,
            param_text=node.param_text,
            wait_value=node.wait_value,
            wait_random=node.wait_random,
            search_target=node.search_target,
            region_text=node.region_text,
            confidence_text=node.confidence_text,
            retry_value=node.retry_value,
            retry_random=node.retry_random,
            pic_range_random=node.pic_range_random,
            move_time=node.move_time,
            jump_mark="",
            disable_grayscale=node.disable_grayscale,
            note=node.note,
            branch=BranchConfig(
                trigger=node.branch.trigger,
                mode=node.branch.mode,
                primary_target=node.branch.primary_target,
                secondary_target=node.branch.secondary_target,
            ),
        )
        index = flow.nodes.index(node)
        self.undo_stack.push(InsertNodeCommand(self, flow.filename, duplicate, index + 1, "复制节点"))

    def delete_node(self) -> None:
        flow = self.current_flow
        node = self.current_node
        if not flow or not node:
            return
        index = flow.nodes.index(node)
        self.undo_stack.push(DeleteNodeCommand(self, flow.filename, node, index))

    def move_node_up(self) -> None:
        self._move_node(-1)

    def move_node_down(self) -> None:
        self._move_node(1)

    def _move_node(self, delta: int) -> None:
        flow = self.current_flow
        node = self.current_node
        if not flow or not node:
            return
        index = flow.nodes.index(node)
        target_index = index + delta
        if target_index < 0 or target_index >= len(flow.nodes):
            return
        text = "上移节点" if delta < 0 else "下移节点"
        self.undo_stack.push(MoveNodeCommand(self, flow.filename, node.node_id, index, target_index, text))

    def _show_node_context_menu(self, position) -> None:
        menu = QMenu(self)
        menu.addAction(self.add_node_action)
        menu.addSeparator()
        menu.addAction(self.duplicate_node_action)
        menu.addAction(self.delete_node_action)
        menu.addSeparator()
        menu.addAction(self.move_up_action)
        menu.addAction(self.move_down_action)
        menu.exec(self.node_table.viewport().mapToGlobal(position))

    def _configure_action_hints(self) -> None:
        hint_map = [
            (self.open_action, "打开配置目录"),
            (self.save_action, "保存当前 CSV"),
            (self.reload_action, "重新加载当前配置目录"),
            (self.scan_unused_images_action, "扫描当前配置目录下未使用的图片"),
            (self.undo_action, "撤销上一步操作"),
            (self.redo_action, "重做上一步撤销的操作"),
            (self.add_node_action, "在当前节点后新增节点"),
            (self.duplicate_node_action, "复制当前节点"),
            (self.delete_node_action, "删除当前节点"),
            (self.move_up_action, "将当前节点上移"),
            (self.move_down_action, "将当前节点下移"),
        ]
        for action, description in hint_map:
            shortcut_text = action.shortcut().toString()
            tooltip = description if not shortcut_text else f"{description} ({shortcut_text})"
            action.setToolTip(tooltip)
            action.setStatusTip(tooltip)

    def _on_clean_changed(self, clean: bool) -> None:
        self.setWindowModified(not clean)
        if clean:
            self.statusBar().showMessage("当前内容已保存", 2000)
        else:
            self.statusBar().showMessage("当前内容有未保存修改", 2000)

    def _on_undo_stack_index_changed(self, _index: int) -> None:
        self._configure_action_hints()

    def show_unused_images_dialog(self) -> None:
        if not self.document:
            QMessageBox.information(self, "未打开配置", "请先打开一个配置目录。")
            return
        dialog = UnusedImagesDialog(self.document.root_path, find_unused_images(self.document), self)
        dialog.exec()

    def _update_actions_enabled(self, enabled: bool) -> None:
        for action in [
            self.undo_action,
            self.redo_action,
            self.save_action,
            self.reload_action,
            self.add_node_action,
            self.duplicate_node_action,
            self.delete_node_action,
            self.move_up_action,
            self.move_down_action,
        ]:
            action.setEnabled(enabled)

    @property
    def current_flow(self) -> FlowDocument | None:
        if not self.document or not self.current_flow_name:
            return None
        return self.document.get_flow(self.current_flow_name)

    @property
    def current_node(self) -> OperationNode | None:
        flow = self.current_flow
        if not flow or not self.current_node_id:
            return None
        return flow.get_node(self.current_node_id)

    @staticmethod
    def _nodes_equal(left: OperationNode, right: OperationNode) -> bool:
        left_copy = left.clone()
        right_copy = right.clone()
        left_copy.index = 0
        right_copy.index = 0
        return left_copy == right_copy


class NodeTableWidget(QTableWidget):
    def __init__(self, rows: int, columns: int, parent: QWidget | None = None) -> None:
        super().__init__(rows, columns, parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            event.accept()
            return
        super().mousePressEvent(event)


class UnusedImagesDialog(QDialog):
    def __init__(self, root_path: Path, image_names: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.root_path = root_path
        self.setWindowTitle("未使用图片")
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"配置目录: {root_path}"))

        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._preview_item)
        layout.addWidget(self.list_widget, 1)

        for image_name in image_names:
            self.list_widget.addItem(QListWidgetItem(image_name))

        if not image_names:
            self.list_widget.addItem(QListWidgetItem("未扫描到未使用图片"))
            self.list_widget.setEnabled(False)

    def _show_context_menu(self, position) -> None:
        item = self.list_widget.itemAt(position)
        if item is None or not self.list_widget.isEnabled():
            return
        menu = QMenu(self)
        copy_action = menu.addAction("复制图片名")
        delete_action = menu.addAction("删除图片")
        chosen = menu.exec(self.list_widget.viewport().mapToGlobal(position))
        if chosen is copy_action:
            QGuiApplication.clipboard().setText(item.text())
        elif chosen is delete_action:
            self._delete_item(item)

    def _preview_item(self, item: QListWidgetItem) -> None:
        if not self.list_widget.isEnabled():
            return
        image_path = self.root_path / item.text()
        if not image_path.exists():
            QMessageBox.warning(self, "图片不存在", f"未找到文件: {image_path}")
            return
        dialog = ImagePreviewDialog(image_path, self)
        dialog.exec()

    def _delete_item(self, item: QListWidgetItem) -> None:
        image_path = self.root_path / item.text()
        if not image_path.exists():
            QMessageBox.warning(self, "图片不存在", f"未找到文件: {image_path}")
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
            self._sync_empty_state()
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除图片？\n{image_path.name}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            image_path.unlink()
        except OSError as exc:
            QMessageBox.critical(self, "删除失败", f"无法删除图片：{exc}")
            return

        row = self.list_widget.row(item)
        self.list_widget.takeItem(row)
        self._sync_empty_state()

    def _sync_empty_state(self) -> None:
        if self.list_widget.count() > 0:
            return
        self.list_widget.setEnabled(False)
        self.list_widget.addItem(QListWidgetItem("未扫描到未使用图片"))


class ImagePreviewDialog(QDialog):
    def __init__(self, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(image_path.name)
        self.resize(900, 700)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(str(image_path)))

        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        preview.setMinimumSize(320, 240)
        preview.setScaledContents(False)

        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            preview.setText("无法加载图片预览")
        else:
            scaled = pixmap.scaled(860, 620, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            preview.setPixmap(scaled)

        layout.addWidget(preview, 1)


class NodeInspector(QWidget):
    node_changed = Signal(OperationNode)
    action_requested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._current_node: OperationNode | None = None
        self._building = False
        self._widgets: dict[str, QWidget] = {}
        self._jump_target_options: list[str] = []
        self._subflow_options: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll)

        self.panel = QWidget()
        self.scroll.setWidget(self.panel)
        self.layout = QVBoxLayout(self.panel)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setAlignment(Qt.AlignTop)
        self.layout.addWidget(QLabel("请选择一个节点"))

    def set_reference_data(self, jump_targets: list[str], subflow_targets: list[str]) -> None:
        self._jump_target_options = jump_targets
        self._subflow_options = subflow_targets

    def set_node(self, node: OperationNode | None) -> None:
        if node is None:
            self._current_node = None
        else:
            self._current_node = OperationNode(
                node_id=node.node_id,
                index=node.index,
                operation=node.operation,
                param_text=node.param_text,
                wait_value=node.wait_value,
                wait_random=node.wait_random,
                search_target=node.search_target,
                region_text=node.region_text,
                confidence_text=node.confidence_text,
                retry_value=node.retry_value,
                retry_random=node.retry_random,
                pic_range_random=node.pic_range_random,
                move_time=node.move_time,
                jump_mark=node.jump_mark,
                disable_grayscale=node.disable_grayscale,
                note=node.note,
                branch=BranchConfig(
                    trigger=node.branch.trigger,
                    mode=node.branch.mode,
                    primary_target=node.branch.primary_target,
                    secondary_target=node.branch.secondary_target,
                ),
            )
        self._rebuild()

    def _clear_layout(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _rebuild(self) -> None:
        self._building = True
        self._widgets = {}
        self._clear_layout()

        node = self._current_node
        if node is None:
            self.layout.addWidget(QLabel("请选择一个节点"))
            self._building = False
            return

        title = QLabel(f"节点 #{node.index} - {node.operation}")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.layout.addWidget(title)

        common_group = QGroupBox("通用属性")
        common_form = QFormLayout(common_group)
        operation_combo = QComboBox()
        for item in OperationType:
            operation_combo.addItem(item.value)
        operation_combo.setCurrentText(node.operation)
        operation_combo.currentTextChanged.connect(self._emit_change)
        self._widgets["operation"] = operation_combo
        common_form.addRow("操作类型", operation_combo)

        self._widgets["jump_mark"] = self._line_edit(common_form, "跳转标记", node.jump_mark)
        self._widgets["wait_value"] = self._line_edit(common_form, "等待时间", node.wait_value)
        self._widgets["wait_random"] = self._line_edit(common_form, "等待随机", node.wait_random)
        self._widgets["move_time"] = self._line_edit(common_form, "移动用时", node.move_time)
        self._widgets["note"] = self._line_edit(common_form, "备注", node.note)
        self.layout.addWidget(common_group)

        self.layout.addWidget(self._build_operation_group(node))
        self.layout.addStretch(1)
        self._building = False

    def _build_operation_group(self, node: OperationNode) -> QWidget:
        operation = node.operation
        group = QGroupBox("操作属性")
        form = QFormLayout(group)

        if operation in {
            OperationType.CLICK.value,
            OperationType.MOUSE_DOWN.value,
            OperationType.MOUSE_UP.value,
        }:
            combo = QComboBox()
            for button in ["left", "middle", "right", "x1", "x2"]:
                combo.addItem(button)
            combo.setCurrentText(node.param_text or "left")
            combo.currentTextChanged.connect(self._emit_change)
            self._widgets["param_text"] = combo
            form.addRow("按钮", combo)
            return group

        if operation in {
            OperationType.MOVE_REL.value,
            OperationType.MOVE_TO.value,
            OperationType.PRESS.value,
            OperationType.KEY_DOWN.value,
            OperationType.KEY_UP.value,
            OperationType.WRITE.value,
            OperationType.NOTIFY.value,
            OperationType.JUMP.value,
        }:
            label = "参数"
            if operation in {OperationType.MOVE_REL.value, OperationType.MOVE_TO.value}:
                label = "坐标/偏移"
            elif operation in {OperationType.WRITE.value, OperationType.NOTIFY.value}:
                label = "文本"
            elif operation == OperationType.JUMP.value:
                label = "跳转目标"
            if operation == OperationType.MOVE_TO.value:
                self._widgets["param_text"] = self._line_with_button(form, label, node.param_text, "取点", "pick_point")
            elif operation == OperationType.JUMP.value:
                self._widgets["param_text"] = self._editable_combo(form, label, node.param_text, self._jump_target_options)
            else:
                self._widgets["param_text"] = self._line_edit(form, label, node.param_text)
            return group

        if operation in {OperationType.PIC.value, OperationType.OCR.value}:
            target_label = "图片文件" if operation == OperationType.PIC.value else "OCR 文本"
            self._widgets["search_target"] = self._line_edit(form, target_label, node.search_target)
            self._widgets["region_text"] = self._line_edit(form, "搜索区域", node.region_text)
            self._widgets["confidence_text"] = self._line_edit(form, "置信度", node.confidence_text)
            self._widgets["retry_value"] = self._line_edit(form, "重试时间", node.retry_value)
            self._widgets["retry_random"] = self._line_edit(form, "重试随机", node.retry_random)

            random_checkbox = QCheckBox()
            random_checkbox.setChecked(node.pic_range_random)
            random_checkbox.stateChanged.connect(self._emit_change)
            self._widgets["pic_range_random"] = random_checkbox
            form.addRow("随机命中位置", random_checkbox)

            if operation == OperationType.PIC.value:
                grayscale_checkbox = QCheckBox()
                grayscale_checkbox.setChecked(node.disable_grayscale)
                grayscale_checkbox.stateChanged.connect(self._emit_change)
                self._widgets["disable_grayscale"] = grayscale_checkbox
                form.addRow("禁用灰度匹配", grayscale_checkbox)
                form.addRow("辅助采集", self._action_button("截图并回填", "capture_pic"))
            else:
                form.addRow("辅助采集", self._action_button("框选 OCR 区域", "capture_ocr"))

            branch_group = QGroupBox("分支")
            branch_form = QFormLayout(branch_group)
            trigger_combo = QComboBox()
            for item in [BranchTrigger.NONE.value, BranchTrigger.EXIST.value, BranchTrigger.NOT_EXIST.value]:
                trigger_combo.addItem(item)
            trigger_combo.setCurrentText(node.branch.trigger.value)
            trigger_combo.currentTextChanged.connect(self._emit_change)
            self._widgets["branch_trigger"] = trigger_combo
            branch_form.addRow("触发条件", trigger_combo)

            mode_combo = QComboBox()
            for item in [BranchMode.NONE.value, BranchMode.SUBFLOW.value, BranchMode.JUMP_PAIR.value]:
                mode_combo.addItem(item)
            mode_combo.setCurrentText(node.branch.mode.value)
            mode_combo.currentTextChanged.connect(self._emit_change)
            self._widgets["branch_mode"] = mode_combo
            branch_form.addRow("分支模式", mode_combo)

            branch_options = list(dict.fromkeys(self._subflow_options + self._jump_target_options))
            self._widgets["branch_primary_target"] = self._editable_combo(branch_form, "主目标", node.branch.primary_target, branch_options)
            self._widgets["branch_secondary_target"] = self._editable_combo(branch_form, "次目标", node.branch.secondary_target, branch_options)
            self.layout.addWidget(branch_group)
            return group

        form.addRow("说明", QLabel("当前操作暂未配置专门表单"))
        return group

    def _line_edit(self, form: QFormLayout, label: str, value: str) -> QLineEdit:
        edit = QLineEdit(value)
        edit.textChanged.connect(self._emit_change)
        form.addRow(label, edit)
        return edit

    def _editable_combo(self, form: QFormLayout, label: str, value: str, options: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(options)
        combo.setCurrentText(value)
        combo.currentTextChanged.connect(self._emit_change)
        form.addRow(label, combo)
        return combo

    def _line_with_button(self, form: QFormLayout, label: str, value: str, button_text: str, action: str) -> QLineEdit:
        edit = QLineEdit(value)
        edit.textChanged.connect(self._emit_change)
        button = QPushButton(button_text)
        button.clicked.connect(lambda: self._request_action(action))
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        form.addRow(label, row)
        return edit

    def _action_button(self, text: str, action: str) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(lambda: self._request_action(action))
        return button

    def _request_action(self, action: str) -> None:
        if self._current_node is None:
            return
        self.action_requested.emit(action, self._current_node.node_id)

    def _emit_change(self, *_args) -> None:
        if self._building or self._current_node is None:
            return

        node = self._current_node

        operation_widget = self._widgets.get("operation")
        if isinstance(operation_widget, QComboBox):
            node.operation = operation_widget.currentText()

        for key in [
            "jump_mark",
            "wait_value",
            "wait_random",
            "move_time",
            "note",
            "param_text",
            "search_target",
            "region_text",
            "confidence_text",
            "retry_value",
            "retry_random",
        ]:
            widget = self._widgets.get(key)
            if isinstance(widget, QLineEdit):
                setattr(node, key, widget.text())

        random_checkbox = self._widgets.get("pic_range_random")
        if isinstance(random_checkbox, QCheckBox):
            node.pic_range_random = random_checkbox.isChecked()

        grayscale_checkbox = self._widgets.get("disable_grayscale")
        if isinstance(grayscale_checkbox, QCheckBox):
            node.disable_grayscale = grayscale_checkbox.isChecked()

        trigger_combo = self._widgets.get("branch_trigger")
        if isinstance(trigger_combo, QComboBox):
            node.branch.trigger = BranchTrigger(trigger_combo.currentText())

        mode_combo = self._widgets.get("branch_mode")
        if isinstance(mode_combo, QComboBox):
            node.branch.mode = BranchMode(mode_combo.currentText())

        branch_primary = self._widgets.get("branch_primary_target")
        if isinstance(branch_primary, QLineEdit):
            node.branch.primary_target = branch_primary.text()
        elif isinstance(branch_primary, QComboBox):
            node.branch.primary_target = branch_primary.currentText()

        branch_secondary = self._widgets.get("branch_secondary_target")
        if isinstance(branch_secondary, QLineEdit):
            node.branch.secondary_target = branch_secondary.text()
        elif isinstance(branch_secondary, QComboBox):
            node.branch.secondary_target = branch_secondary.currentText()

        param_widget = self._widgets.get("param_text")
        if isinstance(param_widget, QComboBox):
            node.param_text = param_widget.currentText()

        self.node_changed.emit(node)
