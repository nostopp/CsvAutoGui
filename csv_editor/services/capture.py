from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageGrab, ImageQt
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QWidget


@dataclass(slots=True)
class CapturedRegion:
    left: int
    top: int
    width: int
    height: int
    image: Image.Image

    @property
    def region_text(self) -> str:
        return f"{self.left};{self.top};{self.width};{self.height}"


@dataclass(slots=True)
class CapturedPoint:
    x: int
    y: int

    @property
    def point_text(self) -> str:
        return f"{self.x};{self.y}"


def capture_region(parent: QWidget | None = None) -> CapturedRegion | None:
    dialog = _CaptureOverlayDialog(mode="region", parent=parent)
    if dialog.exec() == QDialog.Accepted:
        return dialog.result_region
    return None


def capture_point(parent: QWidget | None = None) -> CapturedPoint | None:
    dialog = _CaptureOverlayDialog(mode="point", parent=parent)
    if dialog.exec() == QDialog.Accepted:
        return dialog.result_point
    return None


class _CaptureOverlayDialog(QDialog):
    def __init__(self, mode: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.result_region: CapturedRegion | None = None
        self.result_point: CapturedPoint | None = None
        self._virtual_geometry = _virtual_geometry()
        self._screenshot = ImageGrab.grab(all_screens=True)
        self._pixmap = QPixmap.fromImage(ImageQt.ImageQt(self._screenshot))
        self._start_pos: QPoint | None = None
        self._end_pos: QPoint | None = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowModality(Qt.ApplicationModal)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(self._virtual_geometry)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        self._start_pos = event.position().toPoint()
        self._end_pos = self._start_pos
        if self.mode == "point":
            point = self._to_global_point(self._start_pos)
            self.result_point = CapturedPoint(point.x(), point.y())
            self.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.mode != "region" or self._start_pos is None:
            return
        self._end_pos = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.mode != "region" or event.button() != Qt.LeftButton or self._start_pos is None:
            return
        self._end_pos = event.position().toPoint()
        selection = self._selection_rect()
        if selection.width() < 2 or selection.height() < 2:
            self.reject()
            return

        global_rect = QRect(
            selection.left() + self._virtual_geometry.left(),
            selection.top() + self._virtual_geometry.top(),
            selection.width(),
            selection.height(),
        )
        crop = self._screenshot.crop(
            (
                selection.left(),
                selection.top(),
                selection.left() + selection.width(),
                selection.top() + selection.height(),
            )
        )
        self.result_region = CapturedRegion(
            left=global_rect.left(),
            top=global_rect.top(),
            width=global_rect.width(),
            height=global_rect.height(),
            image=crop,
        )
        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))

        if self.mode == "region" and self._start_pos is not None and self._end_pos is not None:
            selection = self._selection_rect()
            if not selection.isNull():
                painter.drawPixmap(selection, self._pixmap, selection)
                painter.setPen(QPen(QColor("#4da3ff"), 2))
                painter.drawRect(selection)

    def _selection_rect(self) -> QRect:
        if self._start_pos is None or self._end_pos is None:
            return QRect()
        left = min(self._start_pos.x(), self._end_pos.x())
        top = min(self._start_pos.y(), self._end_pos.y())
        right = max(self._start_pos.x(), self._end_pos.x())
        bottom = max(self._start_pos.y(), self._end_pos.y())
        return QRect(left, top, right - left, bottom - top)

    def _to_global_point(self, local_point: QPoint) -> QPoint:
        return QPoint(
            local_point.x() + self._virtual_geometry.left(),
            local_point.y() + self._virtual_geometry.top(),
        )


def _virtual_geometry() -> QRect:
    screens = QGuiApplication.screens()
    if not screens:
        return QRect(0, 0, 1920, 1080)
    geometry = screens[0].geometry()
    for screen in screens[1:]:
        geometry = geometry.united(screen.geometry())
    return geometry
