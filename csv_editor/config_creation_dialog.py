from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

from autogui.infrastructure.paths import logical_abs_path
from csv_editor.services.config_creation import ConfigCreationPlan, prepare_config_creation


class ConfigCreationDialog(QDialog):
    def __init__(
        self, parent_directory: Path,
        create: Callable[[ConfigCreationPlan], Path],
        before_create: Callable[[], bool],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("创建配置")
        self.resize(620, 300)
        self.created_path: Path | None = None
        self._create = create
        self._before_create = before_create

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.parent_edit = QLineEdit(str(parent_directory))
        self.parent_edit.setObjectName("configParentEdit")
        parent_browse = QPushButton("浏览…")
        parent_browse.clicked.connect(self._browse_parent)
        parent_row = QHBoxLayout()
        parent_row.addWidget(self.parent_edit)
        parent_row.addWidget(parent_browse)
        form.addRow("存放位置", parent_row)

        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("configNameEdit")
        self.name_edit.setPlaceholderText("新配置目录名称")
        form.addRow("配置名称", self.name_edit)

        modes = QHBoxLayout()
        self.default_radio = QRadioButton("使用默认参数")
        self.reuse_radio = QRadioButton("复用参数 JSON")
        self.default_radio.setChecked(True)
        modes.addWidget(self.default_radio)
        modes.addWidget(self.reuse_radio)
        modes.addStretch()
        form.addRow("参数来源", modes)

        self.source_edit = QLineEdit()
        self.source_edit.setObjectName("configSourceJsonEdit")
        self.source_edit.setPlaceholderText("选择 Manager 保存的参数 JSON")
        self.source_browse = QPushButton("浏览…")
        self.source_browse.clicked.connect(self._browse_source)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_edit)
        source_row.addWidget(self.source_browse)
        form.addRow("来源 JSON", source_row)

        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setTextFormat(Qt.PlainText)
        self.preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("创建位置", self.preview_label)
        self.files_label = QLabel()
        self.files_label.setWordWrap(True)
        self.files_label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.files_label)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.create_button = buttons.button(QDialogButtonBox.Ok)
        self.create_button.setText("创建")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.reuse_radio.toggled.connect(self._update_source_mode)
        self.parent_edit.textChanged.connect(self._update_preview)
        self.name_edit.textChanged.connect(self._update_preview)
        self._update_source_mode()
        self._update_preview()
        self.name_edit.setFocus()

    def _update_source_mode(self) -> None:
        enabled = self.reuse_radio.isChecked()
        self.source_edit.setEnabled(enabled)
        self.source_browse.setEnabled(enabled)

    def _update_preview(self) -> None:
        name = self.name_edit.text()
        try:
            target = str(logical_abs_path(self.parent_edit.text()) / name) if name else "请输入配置名称"
        except (OSError, ValueError):
            target = "请输入有效的存放位置"
        self.preview_label.setText(target)
        self.files_label.setText(f"将生成：main.csv（仅列头）、{name or '配置名称'}.json")

    def _browse_parent(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择存放位置", self.parent_edit.text())
        if selected:
            self.parent_edit.setText(selected)

    def _browse_source(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "选择运行参数 JSON", self.source_edit.text() or self.parent_edit.text(),
            "JSON 文件 (*.json)",
        )
        if selected:
            self.source_edit.setText(selected)

    def _submit(self) -> None:
        try:
            if not self.parent_edit.text().strip():
                raise ValueError("请选择存放位置。")
            source = None
            if self.reuse_radio.isChecked():
                if not self.source_edit.text().strip():
                    raise ValueError("请选择要复用的参数 JSON。")
                source = Path(self.source_edit.text().strip())
            plan = prepare_config_creation(
                Path(self.parent_edit.text().strip()), self.name_edit.text(), source,
            )
            if not self._before_create():
                return
            self.created_path = self._create(plan)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "创建失败", str(exc))
            return
        self.accept()
