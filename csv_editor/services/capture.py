from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageGrab, ImageQt
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QWidget

MAGNIFIER_ZOOM = 8
MAGNIFIER_SOURCE_SIZE = 19
MAGNIFIER_CONTENT_SIZE = MAGNIFIER_SOURCE_SIZE * MAGNIFIER_ZOOM
MAGNIFIER_MARGIN = 12
MAGNIFIER_OFFSET = 24
MAGNIFIER_TEXT_HEIGHT = 28
PROMPT_MARGIN = 16
PROMPT_HEIGHT = 32


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


def capture_region(parent: QWidget | None = None, prompt: str = "") -> CapturedRegion | None:
    dialog = _CaptureOverlayDialog(mode="region", parent=parent, prompt=prompt)
    if dialog.exec() == QDialog.Accepted:
        return dialog.result_region
    return None


def capture_point(parent: QWidget | None = None, prompt: str = "") -> CapturedPoint | None:
    dialog = _CaptureOverlayDialog(mode="point", parent=parent, prompt=prompt)
    if dialog.exec() == QDialog.Accepted:
        return dialog.result_point
    return None


class _CaptureOverlayDialog(QDialog):
    def __init__(self, mode: str, parent: QWidget | None = None, prompt: str = "") -> None:
        super().__init__(parent)
        self.mode = mode
        self.prompt = prompt
        self.result_region: CapturedRegion | None = None
        self.result_point: CapturedPoint | None = None
        self._virtual_geometry = _virtual_geometry()
        self._screenshot = ImageGrab.grab(all_screens=True)
        self._pixmap = QPixmap.fromImage(ImageQt.ImageQt(self._screenshot))
        self._start_pos: QPoint | None = None
        self._end_pos: QPoint | None = None
        self._hover_pos = QPoint()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowModality(Qt.ApplicationModal)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(self._virtual_geometry)
        self.setMouseTracking(True)
        self._hover_pos = self.rect().center()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        self._hover_pos = event.position().toPoint()
        self._start_pos = event.position().toPoint()
        self._end_pos = self._start_pos
        if self.mode == "point":
            point = self._to_global_point(self._start_pos)
            self.result_point = CapturedPoint(point.x(), point.y())
            self.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._hover_pos = event.position().toPoint()
        if self.mode == "region" and self._start_pos is not None:
            self._end_pos = self._hover_pos
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

        self._draw_magnifier(painter)
        self._draw_prompt(painter)

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

    def _draw_magnifier(self, painter: QPainter) -> None:
        if self._pixmap.isNull():
            return

        source_rect = self._magnifier_source_rect(self._hover_pos)
        if source_rect.isEmpty():
            return

        panel_rect = self._magnifier_panel_rect(self._hover_pos)
        image_rect = QRect(
            panel_rect.left() + MAGNIFIER_MARGIN,
            panel_rect.top() + MAGNIFIER_MARGIN,
            MAGNIFIER_CONTENT_SIZE,
            MAGNIFIER_CONTENT_SIZE,
        )
        text_rect = QRect(
            panel_rect.left() + MAGNIFIER_MARGIN,
            image_rect.bottom() + 1,
            MAGNIFIER_CONTENT_SIZE,
            MAGNIFIER_TEXT_HEIGHT,
        )

        painter.fillRect(panel_rect, QColor(18, 18, 18, 220))
        painter.setPen(QPen(QColor("#4da3ff"), 2))
        painter.drawRect(panel_rect)
        painter.drawPixmap(image_rect, self._pixmap, source_rect)

        center_x = image_rect.left() + image_rect.width() // 2
        center_y = image_rect.top() + image_rect.height() // 2
        painter.setPen(QPen(QColor("#ffcc00"), 1))
        painter.drawLine(center_x, image_rect.top(), center_x, image_rect.bottom())
        painter.drawLine(image_rect.left(), center_y, image_rect.right(), center_y)

        global_point = self._to_global_point(self._hover_pos)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            text_rect,
            Qt.AlignCenter,
            f"X:{global_point.x()}  Y:{global_point.y()}  {MAGNIFIER_ZOOM}x",
        )

    def _draw_prompt(self, painter: QPainter) -> None:
        if not self.prompt:
            return
        rect = QRect(PROMPT_MARGIN, PROMPT_MARGIN, min(520, max(260, self.width() - PROMPT_MARGIN * 2)), PROMPT_HEIGHT)
        painter.fillRect(rect, QColor(18, 18, 18, 220))
        painter.setPen(QPen(QColor("#4da3ff"), 1))
        painter.drawRect(rect)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rect.adjusted(10, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, self.prompt)

    def _magnifier_source_rect(self, center: QPoint) -> QRect:
        pixmap_width = self._pixmap.width()
        pixmap_height = self._pixmap.height()
        if pixmap_width <= 0 or pixmap_height <= 0:
            return QRect()

        half = MAGNIFIER_SOURCE_SIZE // 2
        max_left = max(0, pixmap_width - MAGNIFIER_SOURCE_SIZE)
        max_top = max(0, pixmap_height - MAGNIFIER_SOURCE_SIZE)
        left = max(0, min(center.x() - half, max_left))
        top = max(0, min(center.y() - half, max_top))
        return QRect(left, top, min(MAGNIFIER_SOURCE_SIZE, pixmap_width), min(MAGNIFIER_SOURCE_SIZE, pixmap_height))

    def _magnifier_panel_rect(self, center: QPoint) -> QRect:
        panel_width = MAGNIFIER_CONTENT_SIZE + MAGNIFIER_MARGIN * 2
        panel_height = MAGNIFIER_CONTENT_SIZE + MAGNIFIER_MARGIN * 2 + MAGNIFIER_TEXT_HEIGHT
        x = center.x() + MAGNIFIER_OFFSET
        y = center.y() + MAGNIFIER_OFFSET

        if x + panel_width > self.width():
            x = center.x() - panel_width - MAGNIFIER_OFFSET
        if y + panel_height > self.height():
            y = center.y() - panel_height - MAGNIFIER_OFFSET

        x = max(0, min(x, self.width() - panel_width))
        y = max(0, min(y, self.height() - panel_height))
        return QRect(x, y, panel_width, panel_height)


def _virtual_geometry() -> QRect:
    screens = QGuiApplication.screens()
    if not screens:
        return QRect(0, 0, 1920, 1080)
    geometry = screens[0].geometry()
    for screen in screens[1:]:
        geometry = geometry.united(screen.geometry())
    return geometry
