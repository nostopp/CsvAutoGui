from __future__ import annotations

from collections.abc import Collection
import time
from pathlib import Path

from PySide6.QtCore import QMimeData, QRect, QSize, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QKeySequence, QPainter, QPalette, QPixmap, QShortcut, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QDialogButtonBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QDialog,
    QSplitter,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from autogui.infrastructure.paths import normalize_config_dir
from autogui.runtime.cache import clear_runtime_caches
from operation_contracts import OperationType, get_operation_contract, require_operation_contract
from csv_editor.adapters import RuntimeOcrPreviewAdapter
from csv_editor.controllers.change_set import ChangeImpact, EditorChangeSet
from csv_editor.controllers.document_controller import EditorDocumentController
from csv_editor.domain.enums import BranchMode, BranchTrigger, ValidationSeverity
from csv_editor.domain.models import EditorDocument, FlowDocument, OperationNode, ValidationIssue
from csv_editor.domain.node_patch import NodePatch
from csv_editor.io.assets import save_capture_image
from csv_editor.io.csv_codec import CsvEditorCodec, is_resource_flow_filename, parse_resource_param, parse_script_param
from csv_editor.io.node_clipboard import (
    CLIPBOARD_MIME_TYPE,
    CLIPBOARD_TEXT_PREFIX,
    NodeClipboardPayload,
    build_clipboard_payload,
    clone_nodes_for_paste,
    deserialize_clipboard_payload,
    serialize_clipboard_payload,
)
from csv_editor.recording_dialog import RecordingDialog
from csv_editor.services.capture import capture_point, capture_region
from csv_editor.services.asset_usage import find_unused_images
from csv_editor.services.summary import summarize_node, summarize_node_timing
from csv_editor.undo_commands import DeleteNodeCommand, InsertNodeCommand, MoveNodeCommand, UpdateNodeCommand
from csv_editor.widgets.node_inspector import (
    NodeInspector,
    allowed_operations_for_flow as _allowed_operations_for_flow,
)

CAPTURE_HIDE_DELAY_SECONDS = 0.2
NODE_ID_ROLE = Qt.UserRole
TARGET_ROLE = Qt.UserRole + 1
UNUSED_IMAGE_NAME_ROLE = Qt.UserRole + 2
ISSUE_ROLE = Qt.UserRole + 3
SUMMARY_TITLE_ROLE = Qt.UserRole + 4
SUMMARY_DETAIL_ROLE = Qt.UserRole + 5
UNUSED_IMAGE_THUMBNAIL_SIZE = QSize(128, 96)
UNUSED_IMAGE_GRID_SIZE = QSize(168, 148)


class SummaryItemDelegate(QStyledItemDelegate):
    _PADDING_X = 8
    _PADDING_Y = 4
    _DETAIL_SPACING = 2

    def _detail_font(self, option: QStyleOptionViewItem) -> QFont:
        detail_font = QFont(option.font)
        detail_font.setPointSizeF(max(7.5, option.font.pointSizeF() - 1.5))
        return detail_font

    def _text_rect(self, option: QStyleOptionViewItem) -> QRect:
        return option.rect.adjusted(self._PADDING_X, self._PADDING_Y, -self._PADDING_X, -self._PADDING_Y)

    def _detail_height(self, option: QStyleOptionViewItem, index, detail_font: QFont) -> int:
        detail = str(index.data(SUMMARY_DETAIL_ROLE) or "")
        if not detail:
            return 0
        widget = option.widget
        available_width = self._text_rect(option).width()
        if widget is not None and hasattr(widget, "columnWidth"):
            available_width = max(available_width, widget.columnWidth(index.column()) - self._PADDING_X * 2)
        if available_width <= 0:
            return 0
        detail_metrics = QFontMetrics(detail_font)
        detail_rect = detail_metrics.boundingRect(QRect(0, 0, available_width, 0), Qt.TextWordWrap, detail)
        return detail_rect.height()

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        display_option = QStyleOptionViewItem(option)
        self.initStyleOption(display_option, index)
        display_option.text = ""
        style = display_option.widget.style() if display_option.widget is not None else None
        if style is not None:
            style.drawControl(QStyle.CE_ItemViewItem, display_option, painter, display_option.widget)

        title = str(index.data(SUMMARY_TITLE_ROLE) or index.data(Qt.DisplayRole) or "")
        detail = str(index.data(SUMMARY_DETAIL_ROLE) or "")
        text_rect = option.rect.adjusted(8, 4, -8, -4)
        if text_rect.width() <= 0 or text_rect.height() <= 0:
            return

        painter.save()
        title_font = QFont(option.font)
        detail_font = self._detail_font(option)

        is_selected = bool(option.state & QStyle.State_Selected)
        title_color = option.palette.color(QPalette.HighlightedText if is_selected else QPalette.Text)
        detail_color = QColor("#35516d" if is_selected else "#637588")

        painter.setPen(title_color)
        painter.setFont(title_font)
        title_metrics = painter.fontMetrics()
        title_text = title_metrics.elidedText(title, Qt.ElideRight, text_rect.width())
        title_height = title_metrics.height()
        painter.drawText(text_rect.adjusted(0, 0, 0, -title_metrics.descent()), Qt.AlignLeft | Qt.AlignTop, title_text)

        if detail:
            painter.setPen(detail_color)
            painter.setFont(detail_font)
            detail_rect = text_rect.adjusted(0, title_height + self._DETAIL_SPACING, 0, 0)
            painter.drawText(detail_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, detail)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        title_font = QFont(option.font)
        detail_font = self._detail_font(option)
        title_metrics = QFontMetrics(title_font)
        height = title_metrics.height() + self._PADDING_Y * 2
        detail_height = self._detail_height(option, index, detail_font)
        if detail_height:
            height += detail_height + self._DETAIL_SPACING
        base_size = super().sizeHint(option, index)
        return QSize(base_size.width(), max(base_size.height(), height))


class EditorMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.controller = EditorDocumentController()
        self.ocr_preview = RuntimeOcrPreviewAdapter()
        self.undo_stack = QUndoStack(self)
        self._recording_dialog: RecordingDialog | None = None
        self._syncing_selection = False
        self._rendered_flow_name: str | None = None
        self._row_by_node_id: dict[str, int] = {}
        self._preview_cache: dict[str, str] = {}
        self._preview_dirty_flows: set[str] = set()
        self._title_base = "CsvAutoGui Editor"
        self.setWindowTitle(f"{self._title_base}[*]")
        self.resize(1400, 900)
        self.setObjectName("editorWindow")

        self._build_actions()
        self._build_ui()
        self._connect_signals()
        self._update_actions_enabled(False)

    def _build_actions(self) -> None:
        self.open_action = QAction("打开配置目录", self)
        self.save_action = QAction("保存 CSV", self)
        self.reload_action = QAction("重新加载", self)
        self.import_nodes_action = QAction("从其他自动化复制节点…", self)
        self.record_nodes_action = QAction("录制模式…", self)
        self.scan_unused_images_action = QAction("扫描未使用图片", self)
        self.show_csv_preview_action = QAction("查看 CSV 原始数据…", self)
        self.undo_action = self.undo_stack.createUndoAction(self, "撤销")
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.redo_action = self.undo_stack.createRedoAction(self, "重做")
        self.redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self.add_node_action = QAction("新增节点", self)
        self.copy_nodes_action = QAction("复制节点", self)
        self.copy_nodes_action.setShortcut(QKeySequence("Ctrl+C"))
        self.paste_nodes_action = QAction("粘贴节点", self)
        self.paste_nodes_action.setShortcut(QKeySequence("Ctrl+V"))
        self.delete_node_action = QAction("删除节点", self)
        self.move_up_action = QAction("上移", self)
        self.move_down_action = QAction("下移", self)
        self._configure_action_hints()

    def _build_ui(self) -> None:
        menu = self.menuBar().addMenu("文件")
        menu.addAction(self.open_action)
        menu.addAction(self.save_action)
        menu.addAction(self.reload_action)
        menu.addSeparator()
        menu.addAction(self.import_nodes_action)

        edit_menu = self.menuBar().addMenu("编辑")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.add_node_action)
        edit_menu.addAction(self.copy_nodes_action)
        edit_menu.addAction(self.paste_nodes_action)
        edit_menu.addAction(self.delete_node_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.move_up_action)
        edit_menu.addAction(self.move_down_action)

        tools_menu = self.menuBar().addMenu("工具")
        tools_menu.addAction(self.record_nodes_action)
        tools_menu.addAction(self.scan_unused_images_action)
        tools_menu.addAction(self.show_csv_preview_action)

        toolbar = self.addToolBar("编辑")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addAction(self.import_nodes_action)
        toolbar.addAction(self.record_nodes_action)
        toolbar.addAction(self.scan_unused_images_action)
        toolbar.addAction(self.show_csv_preview_action)

        root = QWidget()
        root.setObjectName("editorRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(6, 6, 6, 6)

        body_splitter = QSplitter(Qt.Horizontal)
        body_splitter.setHandleWidth(8)
        root_layout.addWidget(body_splitter, 1)

        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.setMinimumWidth(220)
        left_splitter.setHandleWidth(8)
        body_splitter.addWidget(left_splitter)

        self.flow_tree = QTreeWidget()
        self.flow_tree.setObjectName("flowTree")
        self.flow_tree.setHeaderLabels(["流程文件"])
        self.flow_tree.setIndentation(16)
        left_splitter.addWidget(self.flow_tree)

        validation_panel = QWidget()
        validation_panel.setObjectName("validationPanel")
        validation_layout = QVBoxLayout(validation_panel)
        validation_layout.setContentsMargins(0, 4, 0, 0)
        validation_title = QLabel("校验问题")
        validation_title.setObjectName("panelTitle")
        validation_layout.addWidget(validation_title)
        self.validation_list = QListWidget()
        self.validation_list.setObjectName("validationList")
        validation_layout.addWidget(self.validation_list, 1)
        left_splitter.addWidget(validation_panel)
        left_splitter.setStretchFactor(0, 4)
        left_splitter.setStretchFactor(1, 1)
        left_splitter.setSizes([600, 170])

        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setHandleWidth(8)
        body_splitter.addWidget(content_splitter)
        body_splitter.setStretchFactor(0, 0)
        body_splitter.setStretchFactor(1, 1)
        body_splitter.setSizes([250, 1150])

        content_splitter.setStretchFactor(0, 2)

        self.node_table = NodeTableWidget(0, 6)
        self.node_table.setObjectName("nodeTable")
        self.node_table.setHorizontalHeaderLabels(["序号", "类型", "跳转标记", "目标", "摘要", "备注"])
        self.node_table.verticalHeader().setVisible(False)
        self.node_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.node_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.node_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.node_table.setAlternatingRowColors(True)
        self.node_table.setShowGrid(False)
        self.node_table.setItemDelegateForColumn(4, SummaryItemDelegate(self.node_table))
        self._configure_node_table_columns()
        self.node_table.setMinimumWidth(520)
        content_splitter.addWidget(self.node_table)

        self.inspector = NodeInspector()
        self.inspector.setObjectName("nodeInspector")
        content_splitter.addWidget(self.inspector)
        content_splitter.setStretchFactor(1, 0)
        content_splitter.setSizes([980, 300])

        self.setCentralWidget(root)
        self.statusBar().showMessage("请选择配置目录")

    def _connect_signals(self) -> None:
        self.open_action.triggered.connect(self.choose_config_folder)
        self.save_action.triggered.connect(self.save_document)
        self.reload_action.triggered.connect(self.reload_document)
        self.import_nodes_action.triggered.connect(self.import_nodes_from_external_project)
        self.record_nodes_action.triggered.connect(self.open_recording_dialog)
        self.scan_unused_images_action.triggered.connect(self.show_unused_images_dialog)
        self.show_csv_preview_action.triggered.connect(self.show_csv_preview_dialog)
        self.add_node_action.triggered.connect(self.add_node)
        self.copy_nodes_action.triggered.connect(self.copy_selected_nodes)
        self.paste_nodes_action.triggered.connect(self.paste_nodes)
        self.delete_node_action.triggered.connect(self.delete_node)
        self.move_up_action.triggered.connect(self.move_node_up)
        self.move_down_action.triggered.connect(self.move_node_down)
        self.flow_tree.itemSelectionChanged.connect(self._on_flow_selection_changed)
        self.node_table.itemSelectionChanged.connect(self._on_node_selection_changed)
        self.node_table.itemActivated.connect(self._on_node_table_item_activated)
        self.validation_list.itemSelectionChanged.connect(self._on_issue_selection_changed)
        self.node_table.customContextMenuRequested.connect(self._show_node_context_menu)
        self.inspector.node_patched.connect(self._on_node_patch)
        self.inspector.action_requested.connect(self._on_inspector_action)
        self.inspector.image_preview_requested.connect(self._open_image_preview)
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)
        self.undo_stack.indexChanged.connect(self._on_undo_stack_index_changed)

    def choose_config_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择配置目录")
        if directory:
            self.open_config_folder(Path(directory))

    def open_config_folder(self, root_path: Path) -> None:
        root_path = normalize_config_dir(root_path)
        if not root_path.exists():
            QMessageBox.warning(self, "路径不存在", f"未找到目录: {root_path}")
            return
        change_set = self.controller.open_document(root_path)
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self.apply_change_set(change_set)
        self._update_actions_enabled(True)
        self.statusBar().showMessage(f"已打开: {root_path}")
        self._title_base = f"CsvAutoGui Editor - {root_path}"
        self.setWindowTitle(f"{self._title_base}[*]")
        self.setWindowModified(False)

    def reload_document(self) -> None:
        if not self.document:
            return
        clear_runtime_caches()
        change_set = self.controller.reload_document()
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self.apply_change_set(change_set)
        self.statusBar().showMessage(f"已重新加载: {self.document.root_path}", 3000)
        self.setWindowModified(False)

    def save_document(self) -> None:
        if not self.document:
            return
        self.controller.save_document()
        self.undo_stack.setClean()
        self.statusBar().showMessage("CSV 已保存", 3000)
        self._refresh_validation()
        if self.current_flow:
            self.update_validation_style(
                frozenset(node.node_id for node in self.current_flow.nodes)
            )

    def apply_change_set(self, change_set: EditorChangeSet) -> None:
        if change_set.impact is ChangeImpact.DOCUMENT_STRUCTURE:
            self._preview_cache.clear()
            self._preview_dirty_flows.clear()
            self._refresh_flow_tree()
            self._refresh_validation()
            self.refresh_flow_table()
            return

        if change_set.flow_name is not None:
            self._preview_dirty_flows.add(change_set.flow_name)

        if self._rendered_flow_name != self.current_flow_name:
            self._sync_flow_tree_selection()
            self._refresh_validation()
            self.refresh_flow_table()
            return

        if change_set.impact is ChangeImpact.FLOW_STRUCTURE:
            self._refresh_validation()
            self.refresh_flow_table()
            return

        if change_set.impact is ChangeImpact.REFERENCE_GRAPH:
            self._refresh_validation()
            self.rebuild_reference_targets()
            flow = self.current_flow
            node_ids = (
                frozenset(node.node_id for node in flow.nodes)
                if flow is not None
                else frozenset()
            )
            if not self.update_node_rows(node_ids):
                return
            self._sync_node_table_selection(change_set.selected_node_id)
            self.update_validation_style(node_ids)
            self._sync_inspector(change_set)
            return

        if not change_set.node_ids:
            self.refresh_flow_table()
            return
        if change_set.impact is ChangeImpact.NODE_VALIDATION:
            self._refresh_validation()
        if not self.update_node_rows(change_set.node_ids):
            return
        self._sync_node_table_selection(change_set.selected_node_id)
        if change_set.impact is ChangeImpact.NODE_VALIDATION:
            self.update_validation_style(change_set.node_ids)
        self._sync_inspector(change_set)

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

    def _sync_flow_tree_selection(self) -> None:
        self.flow_tree.blockSignals(True)
        try:
            root_item = self.flow_tree.topLevelItem(0)
            if root_item is None:
                self._refresh_flow_tree()
                return
            for index in range(root_item.childCount()):
                child = root_item.child(index)
                if child.data(0, Qt.UserRole) == self.current_flow_name:
                    self.flow_tree.setCurrentItem(child)
                    return
            self._refresh_flow_tree()
        finally:
            self.flow_tree.blockSignals(False)

    def _refresh_validation(self) -> None:
        self.validation_list.blockSignals(True)
        self.validation_list.clear()

        visible_issues = (
            self.controller.issues_for_flow(self.current_flow_name)
            if self.current_flow_name
            else self.issues
        )
        for issue in visible_issues:
            prefix = "错误" if issue.severity is ValidationSeverity.ERROR else "警告"
            item = QListWidgetItem(f"[{prefix}] {issue.message}")
            item.setData(Qt.UserRole, issue.node_id)
            self.validation_list.addItem(item)
        self.validation_list.blockSignals(False)

    def _configure_node_table_columns(self) -> None:
        header = self.node_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Interactive)
        self.node_table.setColumnWidth(2, 105)
        self.node_table.setColumnWidth(3, 150)
        self.node_table.setColumnWidth(5, 130)
        self.node_table.setWordWrap(True)
        self.node_table.setTextElideMode(Qt.ElideNone)

    def refresh_flow_table(self) -> None:
        self.node_table.blockSignals(True)
        self._syncing_selection = True
        try:
            self.node_table.setRowCount(0)
            self._row_by_node_id = {}
            self.inspector.set_root_path(
                self.document.root_path if self.document else None
            )
            flow = self.current_flow
            self._rendered_flow_name = flow.filename if flow else None
            if not flow:
                self.inspector.set_reference_data([], [], None)
                self.inspector.set_node(None)
                return

            if self.current_node_id is None and flow.nodes:
                self.controller.select_node(flow.nodes[0].node_id)
            self.rebuild_reference_targets()
            issue_node_ids = self.controller.issue_node_ids(flow.filename)
            self.node_table.clearSelection()
            self.node_table.setRowCount(len(flow.nodes))
            for row, node in enumerate(flow.nodes):
                self._row_by_node_id[node.node_id] = row
                items = self._build_node_row_items(
                    node,
                    issue_node_ids,
                    selected=node.node_id == self.current_node_id,
                )
                for column, item in enumerate(items):
                    self.node_table.setItem(row, column, item)
                if node.node_id == self.current_node_id:
                    self.node_table.selectRow(row)

            self._configure_node_table_columns()
            self.node_table.resizeRowsToContents()
        finally:
            self._syncing_selection = False
            self.node_table.blockSignals(False)
        self._refresh_node_table_selection_styles()
        self.inspector.set_node(self.current_node)

    def update_node_row(self, node_id: str) -> bool:
        return self.update_node_rows(frozenset({node_id}))

    def update_node_rows(self, node_ids: Collection[str]) -> bool:
        target_ids = frozenset(node_ids)
        if not target_ids:
            self.refresh_flow_table()
            return False
        resolved_rows = []
        for node_id in target_ids:
            resolved = self._resolve_rendered_row(node_id)
            if resolved is None:
                self.refresh_flow_table()
                return False
            resolved_rows.append(resolved)

        flow = self.current_flow
        if flow is None:
            self.refresh_flow_table()
            return False
        issue_node_ids = self.controller.issue_node_ids(flow.filename)
        selected_rows = set(self._selected_row_indexes(self.node_table))
        self.node_table.blockSignals(True)
        self._syncing_selection = True
        try:
            for row, node, _items in resolved_rows:
                replacement_items = self._build_node_row_items(
                    node,
                    issue_node_ids,
                    selected=row in selected_rows,
                )
                for column, item in enumerate(replacement_items):
                    self.node_table.setItem(row, column, item)
                self.node_table.resizeRowToContents(row)
        finally:
            self._syncing_selection = False
            self.node_table.blockSignals(False)
        return True

    def update_validation_style(self, node_ids: Collection[str]) -> None:
        target_ids = frozenset(node_ids)
        if not target_ids:
            return
        resolved_rows = []
        for node_id in target_ids:
            resolved = self._resolve_rendered_row(node_id)
            if resolved is None:
                self.refresh_flow_table()
                return
            resolved_rows.append(resolved)
        flow = self.current_flow
        if flow is None:
            return
        issue_node_ids = self.controller.issue_node_ids(flow.filename)
        selected_rows = set(self._selected_row_indexes(self.node_table))
        self.node_table.blockSignals(True)
        try:
            for row, node, items in resolved_rows:
                self._apply_node_table_style(
                    node,
                    issue_node_ids,
                    items,
                    selected=row in selected_rows,
                )
        finally:
            self.node_table.blockSignals(False)

    def rebuild_reference_targets(self) -> None:
        flow = self.current_flow
        if flow is None:
            self.inspector.set_reference_data([], [], None)
            return
        jump_targets = list(flow.jump_marks().keys())
        subflow_targets = (
            [
                name
                for name in self.document.iter_flow_filenames()
                if not is_resource_flow_filename(name)
            ]
            if self.document
            else []
        )
        self.inspector.set_reference_data(
            jump_targets,
            subflow_targets,
            flow.filename,
        )

    def _build_node_row_items(
        self,
        node: OperationNode,
        issue_node_ids: Collection[str],
        *,
        selected: bool,
    ) -> list[QTableWidgetItem]:
        flow = self.current_flow
        flow_filename = flow.filename if flow else ""
        index_item = QTableWidgetItem(str(node.index))
        type_item = QTableWidgetItem(node.operation)
        jump_mark_item = QTableWidgetItem(node.jump_mark)
        target_item = QTableWidgetItem(self._format_target_references(node))
        summary_title = _summarize_editor_node(node)
        summary_detail = _summarize_editor_timing(node, flow_filename)
        summary_item = QTableWidgetItem(summary_title)
        summary_item.setData(SUMMARY_TITLE_ROLE, summary_title)
        summary_item.setData(SUMMARY_DETAIL_ROLE, summary_detail)
        note_item = QTableWidgetItem(node.note)
        items = [
            index_item,
            type_item,
            jump_mark_item,
            target_item,
            summary_item,
            note_item,
        ]
        for item in items:
            item.setData(NODE_ID_ROLE, node.node_id)
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
        targets = self._resolvable_target_references(node)
        if targets:
            target_item.setData(TARGET_ROLE, targets)
            if len(targets) == 1:
                target_tip = f"双击跳转到: {targets[0][1]}"
            else:
                target_tip = "双击选择跳转目标:\n" + "\n".join(
                    f"{label} -> {target}" for label, target in targets
                )
            target_item.setToolTip(f"{target_item.text()}\n{target_tip}")
        elif target_item.text():
            target_item.setToolTip(target_item.text())
        summary_item.setToolTip(
            summary_title
            if not summary_detail
            else f"{summary_title}\n{summary_detail}"
        )
        self._apply_node_table_style(
            node,
            issue_node_ids,
            items,
            selected=selected,
        )
        return items

    def _resolve_rendered_row(
        self,
        node_id: str,
    ) -> tuple[int, OperationNode, list[QTableWidgetItem]] | None:
        flow = self.current_flow
        if flow is None or self._rendered_flow_name != flow.filename:
            return None
        node = flow.get_node(node_id)
        row = self._row_by_node_id.get(node_id)
        if node is None or row is None or row < 0 or row >= self.node_table.rowCount():
            return None
        items = [
            self.node_table.item(row, column)
            for column in range(self.node_table.columnCount())
        ]
        if any(item is None for item in items):
            return None
        concrete_items = [item for item in items if item is not None]
        if any(item.data(NODE_ID_ROLE) != node_id for item in concrete_items):
            return None
        return row, node, concrete_items

    def _sync_inspector(self, change_set: EditorChangeSet) -> None:
        node = self.current_node
        if node is None:
            self.inspector.set_node(None)
            return
        if node.node_id not in change_set.node_ids:
            self.inspector.set_node(node)
            return
        self.inspector.sync_node(node, change_set.changed_fields)

    def _sync_node_table_selection(self, node_id: str | None) -> None:
        if node_id is None:
            return
        row = self._row_by_node_id.get(node_id)
        if row is None or row < 0 or row >= self.node_table.rowCount():
            self.refresh_flow_table()
            return
        current_item = self.node_table.item(self.node_table.currentRow(), 0)
        current_node_id = (
            current_item.data(NODE_ID_ROLE)
            if current_item is not None
            else None
        )
        if current_node_id == node_id:
            return

        self.node_table.blockSignals(True)
        self._syncing_selection = True
        try:
            self.node_table.clearSelection()
            self.node_table.setCurrentCell(row, 0)
            self.node_table.selectRow(row)
            item = self.node_table.item(row, 0)
            if item is not None:
                self.node_table.scrollToItem(
                    item,
                    QAbstractItemView.PositionAtCenter,
                )
        finally:
            self._syncing_selection = False
            self.node_table.blockSignals(False)
        self._refresh_node_table_selection_styles()

    def _get_csv_preview_text(self, flow_name: str) -> str:
        if (
            flow_name not in self._preview_cache
            or flow_name in self._preview_dirty_flows
        ):
            self._preview_cache[flow_name] = self.controller.flow_to_csv_text(
                flow_name
            )
            self._preview_dirty_flows.discard(flow_name)
        return self._preview_cache[flow_name]

    def show_csv_preview_dialog(self) -> None:
        dialog = QDialog(self)
        flow_name = self.current_flow_name or "未选择流程"
        dialog.setWindowTitle(f"CSV 原始数据 - {flow_name}")
        dialog.resize(980, 620)

        layout = QVBoxLayout(dialog)
        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        preview_text = (
            self._get_csv_preview_text(self.current_flow_name)
            if self.current_flow_name
            else ""
        )
        text_edit.setPlainText(preview_text)
        layout.addWidget(text_edit, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _select_node_by_target(self, target: str) -> bool:
        flow = self.current_flow
        if not flow:
            return False
        node = resolve_target_node(flow, target)
        if node is None:
            self.statusBar().showMessage(f"未找到跳转目标: {target}", 3000)
            return False
        return self._select_node_by_id(node.node_id)

    def _select_node_by_id(self, node_id: str) -> bool:
        flow = self.current_flow
        if not flow:
            return False
        for row, node in enumerate(flow.nodes):
            if node.node_id != node_id:
                continue
            self._syncing_selection = True
            try:
                self.controller.select_node(node_id)
                self.node_table.selectRow(row)
                self.node_table.scrollToItem(self.node_table.item(row, 0), QAbstractItemView.PositionAtCenter)
                self.inspector.set_node(node)
            finally:
                self._syncing_selection = False
            return True
        return False

    def _format_target_references(self, node: OperationNode) -> str:
        references = self._target_references(node)
        if not references:
            return ""
        return "\n".join(f"{label} -> {target}" for label, target in references if target)

    def _resolvable_target_references(self, node: OperationNode) -> list[tuple[str, str]]:
        flow = self.current_flow
        if not flow or is_resource_flow_filename(flow.filename):
            return []
        targets: list[tuple[str, str]] = []
        for label, target in self._target_references(node):
            if resolve_target_node(flow, target):
                targets.append((label, target))
        return targets

    def _target_references(self, node: OperationNode) -> list[tuple[str, str]]:
        contract = get_operation_contract(node.operation)
        if node.operation == OperationType.JUMP.value and node.param_text.strip():
            return [("jmp", node.param_text.strip())]
        if node.operation == OperationType.RESOURCE.value:
            parsed = parse_resource_param(node.param_text.strip())
            if parsed is not None and parsed[0] == "jmp" and node.jump_mark.strip():
                return [(f"jmp {parsed[1]}", node.jump_mark.strip())]
        if contract is not None and contract.supports_branch and node.branch.is_enabled:
            if node.branch.mode is BranchMode.JUMP_PAIR:
                trigger = node.branch.trigger.value
                fallback = "notExist" if trigger == BranchTrigger.EXIST.value else "exist"
                return [
                    (trigger, node.branch.primary_target.strip()),
                    (fallback, node.branch.secondary_target.strip()),
                ]
            if node.branch.mode is BranchMode.SUBFLOW and node.branch.primary_target.strip():
                return [(f"{node.branch.trigger.value} subflow", node.branch.primary_target.strip())]
        return []

    def _apply_node_table_style(
        self,
        node: OperationNode,
        issue_node_ids: Collection[str],
        items: list[QTableWidgetItem],
        *,
        selected: bool,
    ) -> None:
        is_issue = node.node_id in issue_node_ids
        selected_row_bg = QColor("#dbeeff")
        issue_row_bg = QColor("#fff1f2")
        normal_text = QColor("#18222d")

        for item in items:
            item.setData(ISSUE_ROLE, is_issue)
            item.setForeground(QBrush(normal_text))
            item.setBackground(QBrush(selected_row_bg if selected else issue_row_bg if is_issue else QColor("transparent")))

        color = _operation_color(node.operation)
        type_item = items[1]
        type_item.setBackground(QBrush(color.lighter(155 if selected else 175)))
        type_item.setForeground(QBrush(color.darker(185)))
        type_font = QFont(type_item.font())
        type_font.setBold(True)
        type_item.setFont(type_font)

        if node.jump_mark:
            mark_item = items[2]
            mark_item.setForeground(QBrush(QColor("#1d4ed8")))
            mark_font = QFont(mark_item.font())
            mark_font.setBold(True)
            mark_item.setFont(mark_font)

        if self._target_references(node):
            target_item = items[3]
            target_item.setForeground(QBrush(QColor("#047857")))
            target_font = QFont(target_item.font())
            target_font.setBold(True)
            target_item.setFont(target_font)

        if is_issue:
            items[4].setForeground(QBrush(QColor("#b91c1c" if not selected else "#8a1c36")))

    def _refresh_node_table_selection_styles(self) -> None:
        flow = self.current_flow
        if not flow:
            return
        issue_node_ids = self.controller.issue_node_ids(flow.filename)
        selected_rows = set(self._selected_row_indexes(self.node_table))
        for row, node in enumerate(flow.nodes):
            items = [self.node_table.item(row, column) for column in range(self.node_table.columnCount())]
            if any(item is None for item in items):
                continue
            self._apply_node_table_style(
                node,
                issue_node_ids,
                [item for item in items if item is not None],
                selected=row in selected_rows,
            )

    def _on_flow_selection_changed(self) -> None:
        selected = self.flow_tree.selectedItems()
        if not selected:
            return
        filename = selected[0].data(0, Qt.UserRole)
        if not filename:
            return
        self.controller.select_flow(filename)
        self._refresh_validation()
        self.refresh_flow_table()

    def _on_node_selection_changed(self) -> None:
        if self._syncing_selection:
            return
        current_row = self.node_table.currentRow()
        flow = self.current_flow
        if current_row < 0 or not flow or current_row >= len(flow.nodes):
            self.controller.select_node(None)
            self._refresh_node_table_selection_styles()
            self.inspector.set_node(None)
            return
        self.controller.select_node(flow.nodes[current_row].node_id)
        self._refresh_node_table_selection_styles()
        self.inspector.set_node(flow.nodes[current_row])

    def _on_node_table_item_activated(self, item: QTableWidgetItem) -> None:
        targets = item.data(TARGET_ROLE)
        if not isinstance(targets, list) or not targets:
            return
        if len(targets) == 1:
            self._select_node_by_target(targets[0][1])
            return

        menu = QMenu(self)
        for label, target in targets:
            action = menu.addAction(f"{label} -> {target}")
            action.setData(target)
        rect = self.node_table.visualItemRect(item)
        chosen = menu.exec(self.node_table.viewport().mapToGlobal(rect.center()))
        if chosen is None:
            return
        target = chosen.data()
        if isinstance(target, str):
            self._select_node_by_target(target)

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

    def _on_node_patch(self, patch: NodePatch) -> None:
        flow = self.current_flow
        if not flow:
            return
        command = UpdateNodeCommand.from_patch(
            self.controller,
            flow.filename,
            patch,
            on_change=self.apply_change_set,
        )
        if command is not None:
            self.undo_stack.push(command)

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
            changed_fields = {
                "search_target": filename,
                "region_text": captured.region_text,
            }
            if not node.confidence_text:
                changed_fields["confidence_text"] = str(
                    require_operation_contract(OperationType.PIC).default_confidence
                )
            self.statusBar().showMessage(f"已保存图片素材: {filename}", 4000)
            self._push_node_patch(
                flow.filename,
                NodePatch(node.node_id, changed_fields),
                "截图回填图片节点",
            )

        elif action == "capture_ocr":
            captured = self._capture_region_with_hidden_window()
            if not captured:
                return
            changed_fields = {"region_text": captured.region_text}
            if not node.confidence_text:
                changed_fields["confidence_text"] = str(
                    require_operation_contract(OperationType.OCR).default_confidence
                )
            candidates = self.ocr_preview.preview_from_image(captured.image)
            if candidates:
                unique_candidates = list(dict.fromkeys(candidates))
                if len(unique_candidates) == 1:
                    changed_fields["search_target"] = unique_candidates[0]
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
                        changed_fields["search_target"] = selected.strip()
            else:
                QMessageBox.information(self, "OCR 预览", "当前区域未识别到可用文本，已仅回填搜索区域。")
            self._push_node_patch(
                flow.filename,
                NodePatch(node.node_id, changed_fields),
                "截图回填 OCR 节点",
            )

        elif action == "pick_point":
            captured = self._capture_point_with_hidden_window()
            if not captured:
                return
            self.statusBar().showMessage(f"已回填坐标: {captured.point_text}", 3000)
            self._push_node_patch(
                flow.filename,
                NodePatch(node.node_id, {"param_text": captured.point_text}),
                "拾取坐标",
            )
        else:
            return

    def _push_node_patch(
        self,
        flow_name: str,
        patch: NodePatch,
        text: str,
    ) -> None:
        command = UpdateNodeCommand.from_patch(
            self.controller,
            flow_name,
            patch,
            on_change=self.apply_change_set,
            text=text,
        )
        if command is not None:
            self.undo_stack.push(command)

    def _open_image_preview(self, image_path: Path) -> None:
        dialog = ImagePreviewDialog(image_path, self)
        dialog.exec()

    def _capture_region_with_hidden_window(self):
        self.showMinimized()
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
        self.showMinimized()
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
        choices = _allowed_operations_for_flow(flow.filename)
        operation, ok = QInputDialog.getItem(self, "新增节点", "操作类型", choices, editable=False)
        if not ok or not operation:
            return

        node = OperationNode(operation=operation)
        insert_at = self.node_table.currentRow()
        target_index = len(flow.nodes) if insert_at < 0 else insert_at + 1
        self.undo_stack.push(
            InsertNodeCommand(
                self.controller,
                flow.filename,
                node,
                target_index,
                on_change=self.apply_change_set,
                text="新增节点",
            )
        )

    def copy_selected_nodes(self) -> None:
        flow = self.current_flow
        if not self.document or not flow:
            return
        selected_rows = self._selected_row_indexes(self.node_table)
        if not selected_rows:
            QMessageBox.information(self, "复制节点", "请先选择要复制的节点。")
            return
        if not self._is_contiguous_selection(selected_rows):
            QMessageBox.information(self, "复制节点", "当前仅支持连续多选复制。")
            return
        nodes = [flow.nodes[row] for row in selected_rows]
        self._write_nodes_to_clipboard(build_clipboard_payload(self.document.root_path, flow.filename, nodes))
        self.statusBar().showMessage(f"已复制 {len(nodes)} 个节点", 3000)

    def paste_nodes(self) -> None:
        flow = self.current_flow
        if not flow:
            return
        payload = self._read_nodes_from_clipboard()
        if payload is None or not payload.nodes:
            QMessageBox.information(self, "粘贴节点", "剪贴板中没有可粘贴的节点数据。")
            return

        paste_nodes, renamed_marks = clone_nodes_for_paste(payload.nodes, flow)
        insert_at = self.node_table.currentRow()
        target_index = len(flow.nodes) if insert_at < 0 else insert_at + 1
        self.undo_stack.beginMacro("粘贴节点")
        try:
            for offset, node in enumerate(paste_nodes):
                self.undo_stack.push(
                    InsertNodeCommand(
                        self.controller,
                        flow.filename,
                        node,
                        target_index + offset,
                        on_change=self.apply_change_set,
                        text="粘贴节点",
                    )
                )
        finally:
            self.undo_stack.endMacro()

        message = f"已粘贴 {len(paste_nodes)} 个节点"
        if renamed_marks:
            message = f"{message}，并自动重命名了 {len(renamed_marks)} 个跳转标记"
        self.statusBar().showMessage(message, 4000)

    def import_nodes_from_external_project(self) -> None:
        if not self.document:
            QMessageBox.information(self, "未打开配置", "请先打开一个目标配置目录。")
            return
        dialog = ExternalNodeImportDialog(self.controller.codec, self)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.selected_payload()
        if payload is None:
            return
        self._write_nodes_to_clipboard(payload)
        self.statusBar().showMessage(
            f"已从 {payload.source_flow} 复制 {len(payload.nodes)} 个节点到剪贴板，请切回目标流程粘贴",
            5000,
        )

    def open_recording_dialog(self) -> None:
        if not self.document:
            QMessageBox.information(self, "未打开配置", "请先打开一个目标配置目录。")
            return

        source_flow = self.current_flow_name or "main.csv"
        self._recording_dialog = RecordingDialog(
            source_root=self.document.root_path,
            source_flow=source_flow,
            clipboard_writer=self._write_nodes_to_clipboard,
            host_window=self,
        )
        self._recording_dialog.show()
        self._recording_dialog.raise_()
        self._recording_dialog.activateWindow()

    def delete_node(self) -> None:
        flow = self.current_flow
        if not flow:
            return
        selected_rows = self._selected_row_indexes(self.node_table)
        if not selected_rows:
            node = self.current_node
            if not node:
                return
            selected_rows = [flow.nodes.index(node)]

        self.undo_stack.beginMacro("删除节点")
        try:
            for row in reversed(selected_rows):
                if row < 0 or row >= len(flow.nodes):
                    continue
                node = flow.nodes[row]
                self.undo_stack.push(
                    DeleteNodeCommand(
                        self.controller,
                        flow.filename,
                        node,
                        row,
                        on_change=self.apply_change_set,
                    )
                )
        finally:
            self.undo_stack.endMacro()

        self.statusBar().showMessage(f"已删除 {len(selected_rows)} 个节点", 3000)

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
        self.undo_stack.push(
            MoveNodeCommand(
                self.controller,
                flow.filename,
                node.node_id,
                index,
                target_index,
                on_change=self.apply_change_set,
                text=text,
            )
        )

    def _show_node_context_menu(self, position) -> None:
        menu = QMenu(self)
        menu.addAction(self.add_node_action)
        menu.addSeparator()
        menu.addAction(self.copy_nodes_action)
        menu.addAction(self.paste_nodes_action)
        menu.addAction(self.delete_node_action)
        menu.addSeparator()
        menu.addAction(self.move_up_action)
        menu.addAction(self.move_down_action)
        menu.exec(self.node_table.viewport().mapToGlobal(position))

    def _configure_action_hints(self) -> None:
        hint_map = [
            (self.open_action, "打开配置目录"),
            (self.save_action, "保存当前 CSV"),
            (self.reload_action, "重新加载当前配置目录（包括脚本和资源文件缓存）"),
            (self.import_nodes_action, "从其他自动化选择节点并复制到剪贴板"),
            (self.record_nodes_action, "录制键鼠操作和 OCR/PIC 标记并复制成节点"),
            (self.scan_unused_images_action, "扫描当前配置目录下未使用的图片"),
            (self.show_csv_preview_action, "弹窗查看当前流程编译后的 CSV 原始数据"),
            (self.undo_action, "撤销上一步操作"),
            (self.redo_action, "重做上一步撤销的操作"),
            (self.add_node_action, "在当前节点后新增节点"),
            (self.copy_nodes_action, "复制选中的一个或多个节点"),
            (self.paste_nodes_action, "在当前节点后粘贴剪贴板中的节点"),
            (self.delete_node_action, "删除当前或选中的一个或多个节点"),
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

    def _selected_row_indexes(self, table: QTableWidget) -> list[int]:
        rows = {index.row() for index in table.selectionModel().selectedRows()} if table.selectionModel() else set()
        return sorted(row for row in rows if row >= 0)

    @staticmethod
    def _is_contiguous_selection(rows: list[int]) -> bool:
        return not rows or rows == list(range(rows[0], rows[-1] + 1))

    def _write_nodes_to_clipboard(self, payload: NodeClipboardPayload) -> None:
        raw_text = serialize_clipboard_payload(payload)
        mime_data = QMimeData()
        mime_data.setData(CLIPBOARD_MIME_TYPE, raw_text.encode("utf-8"))
        mime_data.setText(f"{CLIPBOARD_TEXT_PREFIX}{raw_text}")
        QGuiApplication.clipboard().setMimeData(mime_data)

    def _read_nodes_from_clipboard(self) -> NodeClipboardPayload | None:
        mime_data = QGuiApplication.clipboard().mimeData()
        if mime_data is None:
            return None
        if mime_data.hasFormat(CLIPBOARD_MIME_TYPE):
            raw_bytes = bytes(mime_data.data(CLIPBOARD_MIME_TYPE))
            return deserialize_clipboard_payload(raw_bytes.decode("utf-8"))
        if mime_data.hasText():
            return deserialize_clipboard_payload(mime_data.text())
        return None

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
            self.import_nodes_action,
            self.record_nodes_action,
            self.scan_unused_images_action,
            self.show_csv_preview_action,
            self.add_node_action,
            self.copy_nodes_action,
            self.paste_nodes_action,
            self.delete_node_action,
            self.move_up_action,
            self.move_down_action,
        ]:
            action.setEnabled(enabled)

    @property
    def document(self) -> EditorDocument | None:
        return self.controller.document

    @property
    def current_flow_name(self) -> str | None:
        return self.controller.current_flow_name

    @property
    def current_node_id(self) -> str | None:
        return self.controller.current_node_id

    @property
    def issues(self) -> list[ValidationIssue]:
        return self.controller.issues

    @property
    def current_flow(self) -> FlowDocument | None:
        return self.controller.current_flow

    @property
    def current_node(self) -> OperationNode | None:
        return self.controller.current_node


class NodeTableWidget(QTableWidget):
    def __init__(self, rows: int, columns: int, parent: QWidget | None = None) -> None:
        super().__init__(rows, columns, parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            event.accept()
            return
        super().mousePressEvent(event)


class ExternalNodeImportDialog(QDialog):
    def __init__(self, codec: CsvEditorCodec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.codec = codec
        self.document: EditorDocument | None = None
        self.current_flow_name: str | None = None
        self._selected_payload: NodeClipboardPayload | None = None
        self.setWindowTitle("从其他自动化复制节点")
        self.resize(980, 640)

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.path_label = QLabel("未选择来源配置目录")
        self.path_label.setWordWrap(True)
        self.choose_button = QPushButton("选择目录")
        self.choose_button.clicked.connect(self._choose_directory)
        top_row.addWidget(self.path_label, 1)
        top_row.addWidget(self.choose_button)
        layout.addLayout(top_row)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        self.flow_tree = QTreeWidget()
        self.flow_tree.setHeaderLabels(["来源流程"])
        self.flow_tree.setMinimumWidth(220)
        self.flow_tree.itemSelectionChanged.connect(self._on_flow_selection_changed)
        splitter.addWidget(self.flow_tree)

        self.node_table = NodeTableWidget(0, 5)
        self.node_table.setHorizontalHeaderLabels(["序号", "类型", "跳转标记", "摘要", "备注"])
        self.node_table.verticalHeader().setVisible(False)
        self.node_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.node_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.node_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.node_table.setAlternatingRowColors(True)
        self.node_table.setShowGrid(False)
        self.node_table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.node_table)
        splitter.setStretchFactor(1, 1)

        self.tip_label = QLabel("支持单节点或连续多节点复制。")
        layout.addWidget(self.tip_label)

        buttons = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.button_box = QDialogButtonBox(buttons)
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("复制到剪贴板")
        self.button_box.accepted.connect(self._accept_selection)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def selected_payload(self) -> NodeClipboardPayload | None:
        return self._selected_payload

    @property
    def current_flow(self) -> FlowDocument | None:
        if not self.document or not self.current_flow_name:
            return None
        return self.document.get_flow(self.current_flow_name)

    def _choose_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择来源配置目录")
        if not directory:
            return
        root_path = Path(directory)
        root_path = normalize_config_dir(root_path)
        try:
            self.document = self.codec.load_document(root_path)
        except OSError as exc:
            QMessageBox.critical(self, "加载失败", f"无法读取配置目录：{exc}")
            return

        self.current_flow_name = self.document.flows[0].filename if self.document.flows else None
        self.path_label.setText(str(root_path))
        self._refresh_flow_tree()
        self._refresh_node_table()

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

    def _refresh_node_table(self) -> None:
        self.node_table.setRowCount(0)
        flow = self.current_flow
        if not flow:
            return

        self.node_table.setRowCount(len(flow.nodes))
        for row, node in enumerate(flow.nodes):
            self.node_table.setItem(row, 0, QTableWidgetItem(str(node.index)))
            self.node_table.setItem(row, 1, QTableWidgetItem(node.operation))
            self.node_table.setItem(row, 2, QTableWidgetItem(node.jump_mark))
            summary_item = QTableWidgetItem(summarize_node(node))
            summary_item.setData(Qt.UserRole, node.node_id)
            self.node_table.setItem(row, 3, summary_item)
            self.node_table.setItem(row, 4, QTableWidgetItem(node.note))

        self.node_table.resizeColumnsToContents()

    def _on_flow_selection_changed(self) -> None:
        selected = self.flow_tree.selectedItems()
        if not selected:
            return
        filename = selected[0].data(0, Qt.UserRole)
        if not filename:
            return
        self.current_flow_name = filename
        self._refresh_node_table()

    def _accept_selection(self) -> None:
        flow = self.current_flow
        if not self.document or not flow:
            QMessageBox.information(self, "复制节点", "请先选择来源配置目录和流程。")
            return

        selected_rows = self._selected_row_indexes()
        if not selected_rows:
            QMessageBox.information(self, "复制节点", "请先选择要复制的节点。")
            return
        if not self._is_contiguous_selection(selected_rows):
            QMessageBox.information(self, "复制节点", "当前仅支持连续多选复制。")
            return

        nodes = [flow.nodes[row] for row in selected_rows]
        self._selected_payload = build_clipboard_payload(self.document.root_path, flow.filename, nodes)
        self.accept()

    def _selected_row_indexes(self) -> list[int]:
        rows = {index.row() for index in self.node_table.selectionModel().selectedRows()} if self.node_table.selectionModel() else set()
        return sorted(row for row in rows if row >= 0)

    @staticmethod
    def _is_contiguous_selection(rows: list[int]) -> bool:
        return not rows or rows == list(range(rows[0], rows[-1] + 1))


class UnusedImagesDialog(QDialog):
    def __init__(self, root_path: Path, image_names: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.root_path = root_path
        self.setWindowTitle("未使用图片")
        self.resize(760, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"配置目录: {root_path}"))

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.IconMode)
        self.list_widget.setResizeMode(QListWidget.Adjust)
        self.list_widget.setMovement(QListWidget.Static)
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setIconSize(UNUSED_IMAGE_THUMBNAIL_SIZE)
        self.list_widget.setGridSize(UNUSED_IMAGE_GRID_SIZE)
        self.list_widget.setSpacing(8)
        self.list_widget.setWordWrap(True)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._preview_item)
        layout.addWidget(self.list_widget, 1)
        self.delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self.list_widget)
        self.delete_shortcut.activated.connect(self._delete_selected_items)

        for image_name in image_names:
            self.list_widget.addItem(self._create_image_item(image_name))

        if not image_names:
            self.list_widget.addItem(QListWidgetItem("未扫描到未使用图片"))
            self.list_widget.setEnabled(False)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete and self.list_widget.isEnabled():
            self._delete_selected_items()
            event.accept()
            return
        super().keyPressEvent(event)

    def _create_image_item(self, image_name: str) -> QListWidgetItem:
        item = QListWidgetItem(image_name)
        image_path = self.root_path / image_name
        item.setData(UNUSED_IMAGE_NAME_ROLE, image_name)
        item.setSizeHint(UNUSED_IMAGE_GRID_SIZE)
        item.setToolTip(str(image_path))

        pixmap = QPixmap(str(image_path))
        if not pixmap.isNull():
            thumbnail = pixmap.scaled(UNUSED_IMAGE_THUMBNAIL_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item.setIcon(QIcon(thumbnail))
        return item

    def _show_context_menu(self, position) -> None:
        item = self.list_widget.itemAt(position)
        if item is None or not self.list_widget.isEnabled():
            return
        if not item.isSelected():
            self.list_widget.clearSelection()
            item.setSelected(True)
        selected_items = self._selected_image_items()
        if not selected_items:
            return
        menu = QMenu(self)
        copy_action = menu.addAction("复制图片名")
        delete_action = menu.addAction("删除选中图片")
        chosen = menu.exec(self.list_widget.viewport().mapToGlobal(position))
        if chosen is copy_action:
            QGuiApplication.clipboard().setText("\n".join(self._image_name(selected_item) for selected_item in selected_items))
        elif chosen is delete_action:
            self._delete_items(selected_items)

    def _preview_item(self, item: QListWidgetItem) -> None:
        if not self.list_widget.isEnabled():
            return
        image_path = self.root_path / self._image_name(item)
        if not image_path.exists():
            QMessageBox.warning(self, "图片不存在", f"未找到文件: {image_path}")
            return
        dialog = ImagePreviewDialog(image_path, self)
        dialog.exec()

    def _delete_selected_items(self) -> None:
        self._delete_items(self._selected_image_items())

    def _delete_items(self, items: list[QListWidgetItem]) -> None:
        if not items:
            return

        existing: list[tuple[QListWidgetItem, Path]] = []
        missing: list[QListWidgetItem] = []
        for item in items:
            image_path = self.root_path / self._image_name(item)
            if image_path.exists():
                existing.append((item, image_path))
            else:
                missing.append(item)

        if missing:
            QMessageBox.warning(self, "图片不存在", f"{len(missing)} 个图片文件已不存在，已从列表移除。")
            self._remove_items(missing)

        if not existing:
            self._sync_empty_state()
            return

        names_preview = self._format_image_names([path.name for _, path in existing])
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除 {len(existing)} 张图片？\n{names_preview}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        deleted_items: list[QListWidgetItem] = []
        failures: list[str] = []
        for item, image_path in existing:
            try:
                image_path.unlink()
            except OSError as exc:
                failures.append(f"{image_path.name}: {exc}")
            else:
                deleted_items.append(item)

        self._remove_items(deleted_items)
        if failures:
            QMessageBox.critical(self, "删除失败", "以下图片删除失败：\n" + "\n".join(failures))
        self._sync_empty_state()

    def _selected_image_items(self) -> list[QListWidgetItem]:
        if not self.list_widget.isEnabled():
            return []
        return [item for item in self.list_widget.selectedItems() if item.data(UNUSED_IMAGE_NAME_ROLE)]

    def _image_name(self, item: QListWidgetItem) -> str:
        return item.data(UNUSED_IMAGE_NAME_ROLE) or item.text()

    def _remove_items(self, items: list[QListWidgetItem]) -> None:
        rows = sorted((self.list_widget.row(item) for item in items), reverse=True)
        for row in rows:
            if row >= 0:
                self.list_widget.takeItem(row)

    @staticmethod
    def _format_image_names(image_names: list[str]) -> str:
        visible = image_names[:12]
        message = "\n".join(visible)
        if len(image_names) > len(visible):
            message += f"\n... 另有 {len(image_names) - len(visible)} 张"
        return message

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




def _operation_color(operation: str) -> QColor:
    colors = {
        OperationType.PIC.value: QColor("#2563eb"),
        OperationType.OCR.value: QColor("#7c3aed"),
        OperationType.SCRIPT.value: QColor("#0f766e"),
        OperationType.RESOURCE.value: QColor("#b45309"),
        OperationType.CLICK.value: QColor("#059669"),
        OperationType.MOUSE_DOWN.value: QColor("#059669"),
        OperationType.MOUSE_UP.value: QColor("#059669"),
        OperationType.MOVE_REL.value: QColor("#0891b2"),
        OperationType.MOVE_TO.value: QColor("#0891b2"),
        OperationType.JUMP.value: QColor("#ea580c"),
        OperationType.WRITE.value: QColor("#9333ea"),
        OperationType.PRESS.value: QColor("#4f46e5"),
        OperationType.KEY_DOWN.value: QColor("#4f46e5"),
        OperationType.KEY_UP.value: QColor("#4f46e5"),
        OperationType.NOTIFY.value: QColor("#ca8a04"),
    }
    return colors.get(operation, QColor("#71717a"))


def _summarize_editor_node(node: OperationNode) -> str:
    if node.operation == OperationType.SCRIPT.value:
        parsed = parse_script_param(node.param_text.strip())
        if parsed is None:
            return f"运行脚本 {node.param_text or '(未设置)'}"
        script_name, resource_name = parsed
        if resource_name:
            return f"运行脚本 {script_name}，资源 {resource_name}"
        return f"运行脚本 {script_name}"

    if node.operation == OperationType.RESOURCE.value:
        parsed = parse_resource_param(node.param_text.strip())
        if parsed is None:
            return f"资源声明 {node.param_text or '(未设置)'}"
        kind, alias = parsed
        if kind == "pic":
            return f"图片资源 {alias} -> {node.search_target or '(未设置)'}"
        if kind == "ocr":
            return f"OCR 资源 {alias} -> {node.search_target or '(未设置)'}"
        return f"跳转资源 {alias} -> {node.jump_mark or '(未设置)'}"

    return summarize_node(node)


def _summarize_editor_timing(node: OperationNode, flow_filename: str) -> str:
    if node.operation == OperationType.RESOURCE.value or is_resource_flow_filename(flow_filename):
        return ""
    return summarize_node_timing(node)


def resolve_target_node(flow: FlowDocument, target: str) -> OperationNode | None:
    target = target.strip()
    if not target:
        return None

    for node in flow.nodes:
        if node.jump_mark == target:
            return node

    try:
        index = int(target)
    except ValueError:
        return None

    if 1 <= index <= len(flow.nodes):
        return flow.nodes[index - 1]
    return None
