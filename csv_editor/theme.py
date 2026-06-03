from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


EDITOR_STYLESHEET = """
QWidget {
    background: #eaf0f7;
    color: #18222d;
    selection-background-color: #c7d6ea;
    selection-color: #18222d;
}

QLabel {
    background: transparent;
}

QMainWindow,
QDialog {
    background: #eaf0f7;
}

QToolTip {
    color: #18222d;
    background: #f8fbff;
    border: 1px solid #c8d4e1;
    padding: 6px 8px;
    border-radius: 8px;
}

QMenuBar {
    background: #f4f8fc;
    border-bottom: 1px solid #c9d5e2;
    padding: 4px 8px;
    spacing: 4px;
}

QMenuBar::item {
    background: transparent;
    border-radius: 8px;
    padding: 6px 10px;
    margin: 2px;
}

QMenuBar::item:selected {
    background: #dce8f4;
}

QMenu {
    background: #f8fbff;
    border: 1px solid #c6d3e0;
    padding: 6px;
}

QMenu::item {
    padding: 8px 14px;
    border-radius: 8px;
    margin: 2px 0;
}

QMenu::item:selected {
    background: #dbe8f5;
    color: #132230;
}

QToolBar#mainToolbar {
    background: #f4f8fc;
    border: none;
    border-bottom: 1px solid #c9d5e2;
    spacing: 6px;
    padding: 8px 10px;
}

QToolBar#mainToolbar::separator {
    background: #cfdae6;
    width: 1px;
    margin: 6px 6px;
}

QToolButton,
QPushButton {
    background: #f9fbfe;
    border: 1px solid #bccbda;
    border-radius: 10px;
    padding: 7px 14px;
    min-height: 18px;
}

QToolBar#mainToolbar QToolButton {
    padding: 6px 10px;
    margin: 0 1px;
}

QPushButton#compactFieldButton,
QPushButton#paletteButton {
    padding: 4px 8px;
    min-height: 0;
    border-radius: 8px;
}

QPushButton#paletteButton {
    font-size: 11px;
}

QToolButton:hover,
QPushButton:hover {
    background: #ffffff;
    border-color: #9fb4c9;
}

QToolButton:pressed,
QPushButton:pressed {
    background: #dbe7f3;
    border-color: #90aac2;
}

QToolButton:disabled,
QPushButton:disabled {
    color: #8a98a6;
    background: #edf2f6;
    border-color: #d1dae4;
}

QDialog#anchoredFieldEditorDialog {
    background: #f8fbff;
    border: 1px solid #c8d5e1;
    border-radius: 14px;
}

QStatusBar {
    background: #f4f8fc;
    border-top: 1px solid #c9d5e2;
    color: #5f7184;
}

QStatusBar::item {
    border: none;
}

QTabWidget::pane {
    border: 1px solid #c7d4e1;
    border-radius: 14px;
    background: #f7faff;
    top: -1px;
}

QTabBar::tab {
    background: transparent;
    border: 1px solid transparent;
    color: #5b6d80;
    padding: 7px 14px;
    margin: 0 4px 0 0;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}

QTabBar::tab:selected {
    background: #f7faff;
    border-color: #c7d4e1;
    color: #16314b;
    font-weight: 700;
}

QTabBar::tab:hover:!selected {
    background: #e4edf6;
}

QTreeWidget,
QListWidget,
QTableWidget,
QPlainTextEdit,
QScrollArea,
QLineEdit,
QComboBox {
    background: #fbfdff;
    border: 1px solid #c6d3e0;
    border-radius: 12px;
}

QTreeWidget,
QListWidget,
QTableWidget,
QPlainTextEdit {
    alternate-background-color: #f3f8fd;
}

QTreeWidget::item,
QListWidget::item,
QTableWidget::item {
    padding: 5px 6px;
}

QTreeWidget::item:selected,
QListWidget::item:selected,
QTableWidget::item:selected {
    background: #dbe8f5;
    color: #122131;
}

QTreeWidget::item:hover,
QListWidget::item:hover,
QTableWidget::item:hover {
    background: #eef4fa;
}

QHeaderView::section {
    background: #edf3f9;
    color: #496174;
    border: none;
    border-bottom: 1px solid #c6d3e0;
    border-right: 1px solid #d7e1ea;
    padding: 8px 10px;
    font-weight: 700;
}

QTableCornerButton::section {
    background: #edf3f9;
    border: none;
    border-bottom: 1px solid #c6d3e0;
    border-right: 1px solid #d7e1ea;
}

QGroupBox {
    background: #f8fbff;
    border: 1px solid #c8d5e1;
    border-radius: 14px;
    margin-top: 16px;
    padding: 14px 12px 12px 12px;
    font-weight: 700;
    color: #21364a;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #4d6478;
    background: #eaf0f7;
}

QLabel#inspectorTitle {
    color: #16293b;
    font-size: 16px;
    font-weight: 800;
    padding: 2px 2px 6px 2px;
}

QLabel#panelTitle {
    color: #3c556a;
    font-size: 12px;
    font-weight: 700;
    padding: 0 2px;
}

QLabel#fieldLabel {
    color: #607488;
    font-size: 11px;
    font-weight: 600;
    padding: 0 1px;
}

QLineEdit,
QPlainTextEdit,
QComboBox {
    padding: 6px 10px;
    min-height: 18px;
}

QLineEdit#compactFieldInput,
QComboBox#compactFieldCombo {
    padding: 4px 8px;
    min-height: 0;
    border-radius: 10px;
}

QLineEdit#popupFieldInput {
    padding: 6px 10px;
    border-radius: 10px;
}

QToolButton#fieldExpandButton {
    padding: 0;
    min-width: 18px;
    min-height: 18px;
    border-radius: 8px;
}

QLineEdit:focus,
QPlainTextEdit:focus,
QComboBox:focus,
QTreeWidget:focus,
QListWidget:focus,
QTableWidget:focus {
    border: 1px solid #8caecd;
}

QComboBox {
    padding-right: 26px;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
    subcontrol-origin: padding;
    subcontrol-position: top right;
}

QComboBox#compactFieldCombo::drop-down {
    width: 18px;
    border-left: 1px solid #d6e0eb;
}

QAbstractItemView {
    outline: 0;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid #afc1d4;
    background: #fbfdff;
}

QCheckBox::indicator:checked {
    background: #5b86b0;
    border-color: #5b86b0;
}

QSplitter::handle {
    background: transparent;
}

QSplitter::handle:horizontal {
    width: 8px;
}

QSplitter::handle:vertical {
    height: 8px;
}

QSplitter::handle:hover {
    background: #d6e1ec;
    border-radius: 4px;
}

QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 4px 0 4px 0;
}

QScrollBar::handle:vertical {
    background: #c4d2df;
    min-height: 24px;
    border-radius: 6px;
}

QScrollBar::handle:vertical:hover {
    background: #aebfd0;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical,
QScrollBar:horizontal,
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    border: none;
    background: transparent;
    height: 0;
    width: 0;
}

QLabel#picInlinePreview {
    background: #f8fbff;
    border: 1px dashed #bfd0df;
    border-radius: 14px;
    color: #708294;
}
"""


def apply_editor_theme(app: QApplication) -> None:
    app.setStyle("Fusion")

    font = QFont("Segoe UI Variable")
    if not font.exactMatch():
        font = QFont("Segoe UI")
    font.setPointSize(10)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#eaf0f7"))
    palette.setColor(QPalette.WindowText, QColor("#18222d"))
    palette.setColor(QPalette.Base, QColor("#fbfdff"))
    palette.setColor(QPalette.AlternateBase, QColor("#f3f8fd"))
    palette.setColor(QPalette.ToolTipBase, QColor("#f8fbff"))
    palette.setColor(QPalette.ToolTipText, QColor("#18222d"))
    palette.setColor(QPalette.Text, QColor("#18222d"))
    palette.setColor(QPalette.Button, QColor("#f9fbfe"))
    palette.setColor(QPalette.ButtonText, QColor("#18222d"))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Highlight, QColor("#c7d6ea"))
    palette.setColor(QPalette.HighlightedText, QColor("#18222d"))
    palette.setColor(QPalette.Link, QColor("#315f8a"))
    app.setPalette(palette)
    app.setStyleSheet(EDITOR_STYLESHEET)
