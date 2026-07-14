from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from operation_contracts import (
    OperationCategory,
    OperationField,
    OperationType,
    ParamKind,
    get_operation_contract,
    iter_operation_contracts,
)
from csv_editor.domain.enums import BranchMode, BranchTrigger
from csv_editor.domain.models import OperationNode
from csv_editor.domain.node_patch import NodePatch, apply_node_patch
from csv_editor.io.csv_codec import is_resource_flow_filename, parse_resource_param
from csv_editor.widgets.field_bindings import (
    FieldBinding,
    WidgetKind,
    build_changed_fields,
    get_field_binding,
)


PIC_INLINE_PREVIEW_HEIGHT = 160
EXPANDABLE_EDITOR_TEXT_COLUMNS = 50
EXPANDABLE_EDITOR_MIN_WIDTH = 420
EXPANDABLE_EDITOR_MAX_WIDTH = 560
EXPANDABLE_EDITOR_ANCHOR_OFFSET = 6


def allowed_operations_for_flow(flow_filename: str | None) -> list[str]:
    contracts = (
        iter_operation_contracts(resource_flow=True)
        if flow_filename and is_resource_flow_filename(flow_filename)
        else iter_operation_contracts(normal_flow=True)
    )
    return [contract.operation.value for contract in contracts]


class AnchoredLineEditPopup(QDialog):
    def __init__(self, anchor: QWidget, title: str, value: str) -> None:
        super().__init__(anchor.window())
        self._anchor = anchor
        self._editor = QLineEdit(value, self)
        self._editor.setObjectName("popupFieldInput")
        self._editor.selectAll()

        self.setObjectName("anchoredFieldEditorDialog")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        title_label = QLabel(f"编辑 {title}")
        title_label.setObjectName("panelTitle")
        layout.addWidget(title_label)
        layout.addWidget(self._editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        editor_metrics = self._editor.fontMetrics()
        target_width = max(
            EXPANDABLE_EDITOR_MIN_WIDTH,
            editor_metrics.horizontalAdvance("M" * EXPANDABLE_EDITOR_TEXT_COLUMNS) + 48,
        )
        self.setFixedWidth(min(EXPANDABLE_EDITOR_MAX_WIDTH, target_width))
        self.adjustSize()
        self._reposition()

    def text(self) -> str:
        return self._editor.text()

    def _reposition(self) -> None:
        anchor_top_left = self._anchor.mapToGlobal(QPoint(0, 0))
        anchor_bottom_left = self._anchor.mapToGlobal(QPoint(0, self._anchor.height()))
        screen = QGuiApplication.screenAt(anchor_top_left)
        primary_screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
        elif primary_screen is not None:
            available = primary_screen.availableGeometry()
        else:
            return

        x = anchor_top_left.x()
        y = anchor_bottom_left.y() + EXPANDABLE_EDITOR_ANCHOR_OFFSET
        if x + self.width() > available.right():
            x = max(available.left(), available.right() - self.width())
        if y + self.height() > available.bottom():
            y = anchor_top_left.y() - self.height() - EXPANDABLE_EDITOR_ANCHOR_OFFSET
        if y < available.top():
            y = max(
                available.top(),
                anchor_bottom_left.y() + EXPANDABLE_EDITOR_ANCHOR_OFFSET,
            )
        self.move(x, y)


class ExpandableLineEdit(QLineEdit):
    expandedTextCommitted = Signal()

    def __init__(
        self,
        value: str,
        popup_title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(value, parent)
        self._popup_title = popup_title
        self._default_margins = self.textMargins()
        self._expand_button = QToolButton(self)
        self._expand_button.setObjectName("fieldExpandButton")
        self._expand_button.setCursor(Qt.PointingHandCursor)
        self._expand_button.setFocusPolicy(Qt.NoFocus)
        self._expand_button.setIcon(
            self.style().standardIcon(QStyle.SP_TitleBarMaxButton)
        )
        self._expand_button.setIconSize(QSize(10, 10))
        self._expand_button.setToolTip("展开编辑")
        self._expand_button.hide()
        self._expand_button.clicked.connect(self._open_popup)
        self.textChanged.connect(self._refresh_expand_button)
        self._position_expand_button()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._refresh_expand_button()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._refresh_expand_button()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_expand_button()
        self._refresh_expand_button()

    def _position_expand_button(self) -> None:
        button_size = max(18, self.height() - 8)
        self._expand_button.setFixedSize(button_size, button_size)
        self._expand_button.move(
            max(0, self.width() - button_size - 5),
            max(0, (self.height() - button_size) // 2),
        )

    def _open_popup(self) -> None:
        popup = AnchoredLineEditPopup(self, self._popup_title, self.text())
        if popup.exec() == QDialog.Accepted:
            new_text = popup.text()
            if new_text != self.text():
                self.setText(new_text)
                self.expandedTextCommitted.emit()
        self.setFocus(Qt.MouseFocusReason)
        self._refresh_expand_button()

    def _refresh_expand_button(self) -> None:
        should_show = self.hasFocus() and self._text_overflows()
        self._expand_button.setVisible(should_show)
        right_margin = (
            self._expand_button.width() + 8
            if should_show
            else self._default_margins.right()
        )
        self.setTextMargins(
            self._default_margins.left(),
            self._default_margins.top(),
            right_margin,
            self._default_margins.bottom(),
        )

    def _text_overflows(self) -> bool:
        if not self.text():
            return False
        contents = self.contentsRect()
        available_width = (
            contents.width()
            - self._default_margins.left()
            - self._default_margins.right()
            - 6
        )
        return (
            available_width > 0
            and self.fontMetrics().horizontalAdvance(self.text()) > available_width
        )


class PicInlinePreviewLabel(QLabel):
    image_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_pixmap = QPixmap()
        self._image_path: Path | None = None
        self.setObjectName("picInlinePreview")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(PIC_INLINE_PREVIEW_HEIGHT)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setScaledContents(False)
        self._set_status("未设置图片文件")

    @property
    def image_path(self) -> Path | None:
        return self._image_path

    def sizeHint(self) -> QSize:
        return QSize(220, PIC_INLINE_PREVIEW_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, PIC_INLINE_PREVIEW_HEIGHT)

    def set_image(self, root_path: Path | None, filename: str) -> None:
        filename = filename.strip()
        self._source_pixmap = QPixmap()
        self._image_path = None
        if not filename:
            self._set_status("未设置图片文件")
            return
        if root_path is None:
            self._set_status("未选择配置目录")
            return

        image_path = root_path / filename
        if not image_path.exists():
            self._set_status("图片不存在")
            self.setToolTip(str(image_path))
            return
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self._set_status("无法加载图片")
            self.setToolTip(str(image_path))
            return

        self._source_pixmap = pixmap
        self._image_path = image_path
        self.setText("")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"点击查看大图: {image_path.name}")
        self._sync_scaled_pixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_scaled_pixmap()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._image_path is not None:
            self.image_requested.emit(self._image_path)
            event.accept()
            return
        super().mousePressEvent(event)

    def _set_status(self, text: str) -> None:
        self.clear()
        self.setText(text)
        self.setCursor(Qt.ArrowCursor)
        self.setToolTip("")

    def _sync_scaled_pixmap(self) -> None:
        if self._source_pixmap.isNull():
            return
        scaled = self._source_pixmap.scaled(
            max(1, self.width() - 8),
            max(1, self.height() - 8),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)


class NodeInspector(QWidget):
    node_patched = Signal(object)
    action_requested = Signal(str, str)
    image_preview_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._current_node: OperationNode | None = None
        self._root_path: Path | None = None
        self._building = False
        self._widgets: dict[str, QWidget] = {}
        self._bound_widgets: dict[str, tuple[FieldBinding, QWidget]] = {}
        self._jump_target_options: list[str] = []
        self._subflow_options: list[str] = []
        self._flow_filename: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll)
        self.panel = QWidget()
        self.scroll.setWidget(self.panel)
        self.layout = QVBoxLayout(self.panel)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(8)
        self.layout.setAlignment(Qt.AlignTop)
        self.layout.addWidget(QLabel("请选择一个节点"))

    def set_reference_data(
        self,
        jump_targets: list[str],
        subflow_targets: list[str],
        flow_filename: str | None,
    ) -> None:
        self._jump_target_options = jump_targets
        self._subflow_options = subflow_targets
        self._flow_filename = flow_filename
        self._sync_reference_choice_widgets()

    def _sync_reference_choice_widgets(self) -> None:
        was_building = self._building
        self._building = True
        try:
            param_widget = self._widgets.get("param_text")
            if (
                self._current_node is not None
                and self._current_node.operation == OperationType.JUMP.value
                and isinstance(param_widget, QComboBox)
            ):
                self._replace_combo_choices(
                    param_widget,
                    self._jump_target_options,
                )

            branch_options = list(
                dict.fromkeys(
                    self._subflow_options + self._jump_target_options
                )
            )
            for widget_name in (
                "branch_primary_target",
                "branch_secondary_target",
            ):
                widget = self._widgets.get(widget_name)
                if isinstance(widget, QComboBox):
                    self._replace_combo_choices(widget, branch_options)
        finally:
            self._building = was_building

    @staticmethod
    def _replace_combo_choices(
        combo: QComboBox,
        choices: list[str],
    ) -> None:
        current_text = combo.currentText()
        combo.clear()
        combo.addItems(choices)
        combo.setCurrentText(current_text)

    def set_root_path(self, root_path: Path | None) -> None:
        self._root_path = root_path

    def set_node(self, node: OperationNode | None) -> None:
        self._current_node = None if node is None else node.clone()
        self._rebuild()

    def sync_node(
        self,
        node: OperationNode,
        changed_fields: Collection[str],
    ) -> None:
        if self._current_node is None or self._current_node.node_id != node.node_id:
            self.set_node(node)
            return

        fields = frozenset(changed_fields)
        rebuild = bool(fields & {"operation", "branch.mode"})
        if "param_text" in fields and node.operation == OperationType.RESOURCE.value:
            previous_resource = parse_resource_param(
                self._current_node.param_text.strip()
            )
            current_resource = parse_resource_param(node.param_text.strip())
            rebuild = (
                previous_resource is None
                or current_resource is None
                or previous_resource[0] != current_resource[0]
            )

        self._current_node = node.clone()
        if rebuild:
            self._rebuild()
            return

        self._building = True
        try:
            for field_name in fields:
                bound = self._bound_widgets.get(field_name)
                if bound is not None:
                    binding, widget = bound
                    self._set_widget_value(widget, binding.getter(node))

            branch_widgets = {
                "branch.trigger": ("branch_trigger", node.branch.trigger.value),
                "branch.mode": ("branch_mode", node.branch.mode.value),
                "branch.primary_target": (
                    "branch_primary_target",
                    node.branch.primary_target,
                ),
                "branch.secondary_target": (
                    "branch_secondary_target",
                    node.branch.secondary_target,
                ),
            }
            for field_name, (widget_name, value) in branch_widgets.items():
                if field_name in fields:
                    widget = self._widgets.get(widget_name)
                    if widget is not None:
                        self._set_widget_value(widget, value)

            if "param_text" in fields and node.operation == OperationType.RESOURCE.value:
                parsed = parse_resource_param(node.param_text.strip())
                alias_widget = self._widgets.get("resource_alias")
                if parsed is not None and alias_widget is not None:
                    self._set_widget_value(alias_widget, parsed[1])

            if "search_target" in fields:
                preview = self._widgets.get("pic_preview")
                if isinstance(preview, PicInlinePreviewLabel):
                    preview.set_image(self._root_path, node.search_target)
        finally:
            self._building = False

    @staticmethod
    def _set_widget_value(widget: QWidget, value: object) -> None:
        if isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(str(value))
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))

    def _clear_layout(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild(self) -> None:
        self._building = True
        self._widgets = {}
        self._bound_widgets = {}
        self._clear_layout()
        node = self._current_node
        if node is None:
            empty = QLabel("请选择一个节点")
            empty.setObjectName("panelTitle")
            self.layout.addWidget(empty)
            self._building = False
            return

        title = QLabel(f"节点 #{node.index} - {node.operation}")
        title.setObjectName("inspectorTitle")
        self.layout.addWidget(title)
        common_group = QGroupBox("通用属性")
        common_form = self._create_compact_form(common_group)

        operation_combo = QComboBox()
        self._normalize_combo(operation_combo)
        operation_combo.setObjectName("compactFieldCombo")
        operation_combo.addItems(self._available_operation_choices(node.operation))
        operation_combo.setCurrentText(node.operation)
        self._add_grid_field(common_form, 0, 0, "操作类型", operation_combo)
        self._register_binding("operation", operation_combo)

        next_row, next_column = 0, 1
        contract = get_operation_contract(node.operation)
        supported_fields = None if contract is None else contract.supported_fields
        if self._should_show_jump_mark(node):
            widget = self._bound_line_edit(
                common_form,
                next_row,
                next_column,
                node,
                "jump_mark",
            )
            self._widgets["jump_mark"] = widget
            next_row, next_column = 1, 0

        common_field_names = (
            "wait_value",
            "wait_random",
            "move_time",
            "note",
        )
        operation_fields = {
            "wait_value": OperationField.WAIT,
            "wait_random": OperationField.WAIT_RANDOM,
            "move_time": OperationField.MOVE_TIME,
            "note": OperationField.NOTE,
        }
        for field_name in common_field_names:
            if (
                supported_fields is not None
                and operation_fields[field_name] not in supported_fields
            ):
                continue
            widget = self._bound_line_edit(
                common_form,
                next_row,
                next_column,
                node,
                field_name,
            )
            self._widgets[field_name] = widget
            if next_column == 0:
                next_column = 1
            else:
                next_row += 1
                next_column = 0

        self.layout.addWidget(common_group)
        self.layout.addWidget(self._build_operation_group(node))
        self.layout.addStretch(1)
        self._building = False

    def _available_operation_choices(self, current_operation: str) -> list[str]:
        choices = allowed_operations_for_flow(self._flow_filename)
        if current_operation and current_operation not in choices:
            return [current_operation, *choices]
        return choices

    def _should_show_jump_mark(self, node: OperationNode) -> bool:
        contract = get_operation_contract(node.operation)
        if (
            contract is not None
            and OperationField.JUMP_MARK not in contract.supported_fields
        ):
            return False
        if contract is None or contract.operation is not OperationType.RESOURCE:
            return True
        parsed = parse_resource_param(node.param_text.strip())
        return parsed is not None and parsed[0] == "jmp"

    def _build_operation_group(self, node: OperationNode) -> QWidget:
        contract = get_operation_contract(node.operation)
        group = QGroupBox("操作属性")
        form = self._create_compact_form(group)
        if contract is None:
            self._add_grid_field(
                form,
                0,
                0,
                "说明",
                QLabel("当前操作暂未配置专门表单"),
                span=2,
            )
            return group

        if contract.param_kind is ParamKind.MOUSE_BUTTON:
            combo = QComboBox()
            self._normalize_combo(combo)
            combo.setObjectName("compactFieldCombo")
            combo.addItems(["left", "middle", "right", "x1", "x2"])
            combo.setCurrentText(node.param_text or "left")
            self._add_grid_field(form, 0, 0, "按钮", combo, span=2)
            self._register_binding("param_text", combo)
            return group

        if contract.param_kind in {
            ParamKind.COORDINATE_PAIR,
            ParamKind.KEY,
            ParamKind.TEXT,
            ParamKind.JUMP_TARGET,
            ParamKind.SCRIPT_REFERENCE,
        }:
            label = "参数"
            if contract.param_kind is ParamKind.COORDINATE_PAIR:
                label = "坐标/偏移"
            elif contract.param_kind is ParamKind.TEXT:
                label = "文本"
            elif contract.param_kind is ParamKind.JUMP_TARGET:
                label = "跳转目标"
            elif contract.param_kind is ParamKind.SCRIPT_REFERENCE:
                label = "脚本文件;资源文件"

            if contract.operation is OperationType.MOVE_TO:
                widget = self._line_with_button(
                    form,
                    0,
                    0,
                    label,
                    node.param_text,
                    "取点",
                    "pick_point",
                )
            elif contract.param_kind is ParamKind.JUMP_TARGET:
                widget = self._editable_combo(
                    form,
                    0,
                    0,
                    label,
                    node.param_text,
                    self._jump_target_options,
                    span=2,
                )
            else:
                widget = self._line_edit(
                    form,
                    0,
                    0,
                    label,
                    node.param_text,
                    span=2,
                )
            self._register_binding("param_text", widget)
            return group

        if contract.category is OperationCategory.RESOURCE:
            return self._build_resource_group(group, form, node)
        if contract.category is OperationCategory.RECOGNITION:
            return self._build_recognition_group(group, form, node, contract)

        self._add_grid_field(
            form,
            0,
            0,
            "说明",
            QLabel("当前操作暂未配置专门表单"),
            span=2,
        )
        return group

    def _build_resource_group(
        self,
        group: QGroupBox,
        form: QGridLayout,
        node: OperationNode,
    ) -> QWidget:
        parsed = parse_resource_param(node.param_text.strip())
        resource_kind = parsed[0] if parsed is not None else "pic"
        resource_alias = parsed[1] if parsed is not None else ""

        kind_combo = QComboBox()
        self._normalize_combo(kind_combo)
        kind_combo.setObjectName("compactFieldCombo")
        kind_combo.addItems(["pic", "ocr", "jmp"])
        kind_combo.setCurrentText(resource_kind)
        self._widgets["resource_kind"] = kind_combo
        self._add_grid_field(form, 0, 0, "资源类型", kind_combo)

        alias_edit = self._line_edit(
            form,
            0,
            1,
            "脚本变量名",
            resource_alias,
            expandable=True,
        )
        self._widgets["resource_alias"] = alias_edit
        kind_combo.currentTextChanged.connect(self._emit_resource_change)
        alias_edit.editingFinished.connect(self._emit_resource_change)

        if resource_kind in {"pic", "ocr"}:
            target_label = "图片文件" if resource_kind == "pic" else "OCR 文本"
            target = self._bound_line_edit(
                form,
                1,
                0,
                node,
                "search_target",
                label=target_label,
            )
            region = self._bound_line_edit(
                form,
                1,
                1,
                node,
                "region_text",
            )
            confidence = self._bound_line_edit(
                form,
                2,
                0,
                node,
                "confidence_text",
            )
            self._widgets.update(
                search_target=target,
                region_text=region,
                confidence_text=confidence,
            )

            if resource_kind == "pic":
                grayscale = QCheckBox()
                grayscale.setChecked(node.disable_grayscale)
                self._add_grid_field(
                    form,
                    2,
                    1,
                    "禁用灰度匹配",
                    grayscale,
                )
                self._register_binding("disable_grayscale", grayscale)
                self._add_grid_field(
                    form,
                    3,
                    0,
                    "辅助采集",
                    self._action_button("截图并回填", "capture_pic"),
                    span=2,
                )
                container = QWidget()
                layout = QVBoxLayout(container)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(8)
                layout.addWidget(group)
                preview = PicInlinePreviewLabel()
                preview.set_image(self._root_path, node.search_target)
                preview.image_requested.connect(self.image_preview_requested)
                self._widgets["pic_preview"] = preview
                layout.addWidget(preview)
                return container

            self._add_grid_field(
                form,
                2,
                1,
                "辅助采集",
                self._action_button("框选 OCR 区域", "capture_ocr"),
            )
            return group

        self._add_grid_field(
            form,
            1,
            0,
            "跳转目标来源",
            QLabel("请在通用属性中的“跳转标记”填写真实跳转目标"),
            span=2,
        )
        return group

    def _build_recognition_group(
        self,
        group: QGroupBox,
        form: QGridLayout,
        node: OperationNode,
        contract,
    ) -> QWidget:
        fields = contract.supported_fields
        target_label = (
            "图片文件" if contract.operation is OperationType.PIC else "OCR 文本"
        )
        positions = {
            "search_target": (0, 0, target_label),
            "region_text": (0, 1, "搜索区域"),
            "confidence_text": (1, 0, "置信度"),
            "retry_value": (1, 1, "重试时间"),
            "retry_random": (2, 0, "重试随机"),
        }
        field_map = {
            "search_target": OperationField.SEARCH_TARGET,
            "region_text": OperationField.REGION,
            "confidence_text": OperationField.CONFIDENCE,
            "retry_value": OperationField.RETRY,
            "retry_random": OperationField.RETRY_RANDOM,
        }
        for field_name, (row, column, label) in positions.items():
            if field_map[field_name] not in fields:
                continue
            widget = self._bound_line_edit(
                form,
                row,
                column,
                node,
                field_name,
                label=label,
            )
            self._widgets[field_name] = widget

        if OperationField.RANGE_RANDOM in fields:
            random_checkbox = QCheckBox()
            random_checkbox.setChecked(node.pic_range_random)
            self._add_grid_field(
                form,
                2,
                1,
                "随机命中位置",
                random_checkbox,
            )
            self._register_binding("pic_range_random", random_checkbox)

        if OperationField.DISABLE_GRAYSCALE in fields:
            grayscale = QCheckBox()
            grayscale.setChecked(node.disable_grayscale)
            self._add_grid_field(form, 3, 0, "禁用灰度匹配", grayscale)
            self._register_binding("disable_grayscale", grayscale)
            self._add_grid_field(
                form,
                3,
                1,
                "辅助采集",
                self._action_button("截图并回填", "capture_pic"),
            )
        else:
            self._add_grid_field(
                form,
                3,
                0,
                "辅助采集",
                self._action_button("框选 OCR 区域", "capture_ocr"),
                span=2,
            )

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)
        container_layout.addWidget(group)
        if OperationField.BRANCH in fields:
            container_layout.addWidget(self._build_branch_group(node))
        if contract.operation is OperationType.PIC:
            preview = PicInlinePreviewLabel()
            preview.set_image(self._root_path, node.search_target)
            preview.image_requested.connect(self.image_preview_requested)
            self._widgets["pic_preview"] = preview
            container_layout.addWidget(preview)
        return container

    def _build_branch_group(self, node: OperationNode) -> QGroupBox:
        group = QGroupBox("分支")
        form = self._create_compact_form(group)
        trigger_combo = QComboBox()
        self._normalize_combo(trigger_combo)
        trigger_combo.setObjectName("compactFieldCombo")
        trigger_combo.addItems(
            [
                BranchTrigger.NONE.value,
                BranchTrigger.EXIST.value,
                BranchTrigger.NOT_EXIST.value,
            ]
        )
        trigger_combo.setCurrentText(node.branch.trigger.value)
        self._widgets["branch_trigger"] = trigger_combo
        self._add_grid_field(form, 0, 0, "触发条件", trigger_combo)
        trigger_combo.currentTextChanged.connect(
            lambda *_args: self._emit_branch_change("branch.trigger")
        )

        mode_combo = QComboBox()
        self._normalize_combo(mode_combo)
        mode_combo.setObjectName("compactFieldCombo")
        mode_combo.addItems(
            [
                BranchMode.NONE.value,
                BranchMode.SUBFLOW.value,
                BranchMode.JUMP_PAIR.value,
            ]
        )
        mode_combo.setCurrentText(node.branch.mode.value)
        self._widgets["branch_mode"] = mode_combo
        self._add_grid_field(form, 0, 1, "分支模式", mode_combo)
        mode_combo.currentTextChanged.connect(
            lambda *_args: self._emit_branch_change("branch.mode")
        )

        options = list(
            dict.fromkeys(self._subflow_options + self._jump_target_options)
        )
        primary = self._editable_combo(
            form,
            1,
            0,
            "主目标",
            node.branch.primary_target,
            options,
            span=2,
        )
        secondary = self._editable_combo(
            form,
            2,
            0,
            "次目标",
            node.branch.secondary_target,
            options,
            span=2,
        )
        self._widgets["branch_primary_target"] = primary
        self._widgets["branch_secondary_target"] = secondary
        self._connect_special_combo(
            primary,
            lambda: self._emit_branch_change("branch.primary_target"),
        )
        self._connect_special_combo(
            secondary,
            lambda: self._emit_branch_change("branch.secondary_target"),
        )
        return group

    def _bound_line_edit(
        self,
        form: QGridLayout,
        row: int,
        column: int,
        node: OperationNode,
        field_name: str,
        *,
        label: str | None = None,
    ) -> QLineEdit:
        binding = get_field_binding(field_name)
        widget = self._line_edit(
            form,
            row,
            column,
            label or binding.label,
            str(binding.getter(node)),
            expandable=binding.expandable,
        )
        self._register_binding(field_name, widget)
        return widget

    def _register_binding(self, field_name: str, widget: QWidget) -> None:
        binding = get_field_binding(field_name)
        self._widgets[field_name] = widget
        self._bound_widgets[field_name] = (binding, widget)
        callback = lambda *_args, name=field_name: self._emit_bound_change(name)
        if isinstance(widget, QComboBox):
            if widget.isEditable():
                widget.currentIndexChanged.connect(callback)
            else:
                widget.currentTextChanged.connect(callback)
            line_edit = widget.lineEdit()
            if line_edit is not None:
                line_edit.editingFinished.connect(callback)
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(callback)
        elif isinstance(widget, QLineEdit):
            widget.editingFinished.connect(callback)
            if isinstance(widget, ExpandableLineEdit):
                widget.expandedTextCommitted.connect(callback)

    def _widget_value(self, binding: FieldBinding, widget: QWidget) -> object:
        if binding.widget_kind is WidgetKind.CHECKBOX and isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QLineEdit):
            return widget.text()
        raise TypeError(f"不支持的绑定控件: {type(widget).__name__}")

    def _emit_bound_change(self, field_name: str) -> None:
        if self._building or self._current_node is None:
            return
        binding, widget = self._bound_widgets[field_name]
        changed_fields = build_changed_fields(
            self._current_node,
            {field_name: self._widget_value(binding, widget)},
        )
        self._emit_patch(changed_fields, rebuild=field_name == "operation")

    def _emit_branch_change(self, field_name: str) -> None:
        if self._building or self._current_node is None:
            return
        values = {
            "branch.trigger": lambda: BranchTrigger(
                self._widgets["branch_trigger"].currentText()
            ),
            "branch.mode": lambda: BranchMode(
                self._widgets["branch_mode"].currentText()
            ),
            "branch.primary_target": lambda: self._widgets[
                "branch_primary_target"
            ].currentText(),
            "branch.secondary_target": lambda: self._widgets[
                "branch_secondary_target"
            ].currentText(),
        }
        current_values = {
            "branch.trigger": self._current_node.branch.trigger,
            "branch.mode": self._current_node.branch.mode,
            "branch.primary_target": self._current_node.branch.primary_target,
            "branch.secondary_target": self._current_node.branch.secondary_target,
        }
        value = values[field_name]()
        self._emit_patch(
            {} if value == current_values[field_name] else {field_name: value}
        )

    def _emit_resource_change(self, *_args) -> None:
        if self._building or self._current_node is None:
            return
        kind_widget = self._widgets.get("resource_kind")
        alias_widget = self._widgets.get("resource_alias")
        if not isinstance(kind_widget, QComboBox) or not isinstance(
            alias_widget,
            QLineEdit,
        ):
            return
        previous = parse_resource_param(self._current_node.param_text.strip())
        resource_kind = kind_widget.currentText().strip()
        param_text = f"{resource_kind};{alias_widget.text().strip()}"
        rebuild = previous is None or previous[0] != resource_kind
        self._emit_patch(
            {}
            if param_text == self._current_node.param_text
            else {"param_text": param_text},
            rebuild=rebuild,
        )

    def _emit_patch(
        self,
        changed_fields: dict[str, object],
        *,
        rebuild: bool = False,
    ) -> None:
        if not changed_fields or self._current_node is None:
            return
        patch = NodePatch(self._current_node.node_id, changed_fields)
        apply_node_patch(self._current_node, patch)
        if rebuild:
            self._rebuild()
        self.node_patched.emit(patch)

    def _create_compact_form(self, parent: QWidget) -> QGridLayout:
        grid = QGridLayout(parent)
        grid.setContentsMargins(10, 12, 10, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return grid

    def _create_field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _add_grid_field(
        self,
        form: QGridLayout,
        row: int,
        column: int,
        label: str,
        widget: QWidget,
        *,
        span: int = 1,
    ) -> None:
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._create_field_label(label))
        layout.addWidget(widget)
        form.addWidget(container, row, column, 1, span)

    def _line_edit(
        self,
        form: QGridLayout,
        row: int,
        column: int,
        label: str,
        value: str,
        *,
        span: int = 1,
        expandable: bool = False,
    ) -> QLineEdit:
        edit = (
            ExpandableLineEdit(value, label)
            if expandable
            else QLineEdit(value)
        )
        self._normalize_field(edit)
        edit.setObjectName("compactFieldInput")
        self._add_grid_field(form, row, column, label, edit, span=span)
        return edit

    def _editable_combo(
        self,
        form: QGridLayout,
        row: int,
        column: int,
        label: str,
        value: str,
        options: list[str],
        *,
        span: int = 1,
    ) -> QComboBox:
        combo = QComboBox()
        self._normalize_combo(combo)
        combo.setObjectName("compactFieldCombo")
        combo.setEditable(True)
        combo.addItems(options)
        combo.setCurrentText(value)
        self._add_grid_field(form, row, column, label, combo, span=span)
        return combo

    def _line_with_button(
        self,
        form: QGridLayout,
        row: int,
        column: int,
        label: str,
        value: str,
        button_text: str,
        action: str,
    ) -> QLineEdit:
        edit = QLineEdit(value)
        self._normalize_field(edit)
        edit.setObjectName("compactFieldInput")
        button = QPushButton(button_text)
        button.setObjectName("compactFieldButton")
        button.clicked.connect(lambda: self._request_action(action))
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        self._add_grid_field(form, row, column, label, container, span=2)
        return edit

    def _connect_special_combo(self, combo: QComboBox, callback) -> None:
        combo.currentIndexChanged.connect(lambda *_args: callback())
        line_edit = combo.lineEdit()
        if line_edit is not None:
            line_edit.editingFinished.connect(callback)

    def _normalize_field(self, widget: QWidget) -> None:
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _normalize_combo(self, combo: QComboBox) -> None:
        combo.setMinimumWidth(0)
        combo.setMinimumContentsLength(6)
        combo.setSizeAdjustPolicy(QComboBox.AdjustToContentsOnFirstShow)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _action_button(self, text: str, action: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("compactFieldButton")
        button.clicked.connect(lambda: self._request_action(action))
        return button

    def _request_action(self, action: str) -> None:
        if self._current_node is not None:
            self.action_requested.emit(action, self._current_node.node_id)
