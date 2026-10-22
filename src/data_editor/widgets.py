"""Small custom widgets."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QRectF, Qt, QTimer, Property
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPen
from PySide6.QtWidgets import QWidget

from .theme import accent_color


class LoadingOverlay(QWidget):
    """Translucent overlay with a spinning arc, shown on top of another widget while it loads.

    It only appears if loading takes longer than `delay_ms`, so quick loads don't flicker.
    """

    def __init__(self, target: QWidget, delay_ms: int = 120):
        super().__init__(target)
        self.target = target
        self.message = ""
        self._angle = 0
        self._span = 90
        self._opacity = 0.0
        self.hide()

        self._spin = QTimer(self, interval=16)
        self._spin.timeout.connect(self._tick)
        self._delay = QTimer(self, singleShot=True, interval=delay_ms)
        self._delay.timeout.connect(self._appear)
        self._fade = QPropertyAnimation(self, b"opacity", self, duration=180)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        target.installEventFilter(self)

    def get_opacity(self) -> float:
        return self._opacity

    def set_opacity(self, value: float) -> None:
        self._opacity = value
        self.update()

    opacity = Property(float, get_opacity, set_opacity)

    def start(self, message: str) -> None:
        self.message = message
        self.update()
        if not self.isVisible() and not self._delay.isActive():
            self._delay.start()

    def stop(self) -> None:
        self._delay.stop()
        self._spin.stop()
        self.hide()
        self._opacity = 0.0

    @property
    def active(self) -> bool:
        return self.isVisible() or self._delay.isActive()

    def _appear(self) -> None:
        self.setGeometry(self.target.rect())
        self.raise_()
        self.show()
        self._spin.start()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _tick(self) -> None:
        self._angle = (self._angle + 6) % 360
        # The arc grows and shrinks as it turns, like a native progress ring.
        self._span = 60 + abs((self._angle * 2) % 360 - 180) * 1.2
        self.update()

    def eventFilter(self, obj, event):
        if obj is self.target and event.type() == QEvent.Resize:
            self.setGeometry(self.target.rect())
        return False

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self._opacity)

        # The overlay sits inside a disabled view, so use the active colors, not the greyed-out ones.
        base = self.palette().color(QPalette.Active, QPalette.Base)
        text = self.palette().color(QPalette.Active, QPalette.Text)

        veil = QColor(base)
        veil.setAlpha(170)
        p.fillRect(self.rect(), veil)

        center = self.rect().center()
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() + 1)
        text_width = QFontMetrics(font).horizontalAdvance(self.message)
        card = QRectF(0, 0, max(200, text_width + 56), 130)
        card.moveCenter(center)
        border = QColor(text)
        border.setAlpha(40)
        p.setPen(QPen(border, 1))
        p.setBrush(base)
        p.drawRoundedRect(card, 10, 10)

        size = 44
        ring = QRectF(center.x() - size / 2, card.top() + 22, size, size)
        track = QColor(text)
        track.setAlpha(30)
        p.setPen(QPen(track, 5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(ring)

        pen = QPen(accent_color(), 5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(ring, int(-self._angle * 16), int(self._span * 16))

        p.setFont(font)
        p.setPen(text)
        text_rect = QRectF(card.left(), ring.bottom() + 14, card.width(), 24)
        p.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, self.message)
