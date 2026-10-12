"""
WinKit - Custom PyQt6 UI Widgets
Modern dark-themed animations, custom switches, buttons, indicators, and tooltips.
"""

import sys
import math
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import (
    Qt, QObject, QPoint, QPointF, QRect, QRectF, QSize,
    QPropertyAnimation, QEasingCurve, pyqtSignal, pyqtProperty,
    QEvent, QTimer, QAbstractAnimation
)
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QPolygonF,
    QPainterPath, QCursor, QPixmap
)
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QRadioButton, QCheckBox, QLabel,
    QComboBox, QFrame, QScrollArea, QTextEdit, QGraphicsDropShadowEffect,
    QApplication, QStyleOptionComboBox, QStyle, QHBoxLayout, QVBoxLayout,
    QSizePolicy, QScrollBar, QAbstractItemView, QGraphicsOpacityEffect,
    QStyleOptionSlider, QStyleOptionButton
)
from gui.styles import QSS, DARK_THEME_PALETTE


class HamburgerButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__("", parent)
        self._hover_progress = 0.0
        self._target_progress = 0.0
        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._hover_step)

    def _hover_step(self):
        diff = self._target_progress - self._hover_progress
        if abs(diff) < 0.05:
            self._hover_progress = self._target_progress
            self._hover_timer.stop()
        else:
            self._hover_progress += diff * 0.3
        self.update()

    def set_active(self, active: bool):
        self._target_progress = 1.0 if active else 0.0
        if not self._hover_timer.isActive():
            self._hover_timer.start(16)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        painter.translate(self.width() / 2.0, self.height() / 2.0)
        painter.rotate(90 * self._hover_progress)
        
        pen = QPen(QColor("#FFFFFF"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        w = 14
        h = 10
        painter.drawLine(int(-w/2), int(-h/2), int(w/2), int(-h/2))
        painter.drawLine(int(-w/2), 0, int(w/2), 0)
        painter.drawLine(int(-w/2), int(h/2), int(w/2), int(h/2))
        painter.end()


class WinKitMark(QWidget):
    """WinKit için dosyasız, yüksek DPI'da net kalan çizim tabanlı amblem."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 30)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QRect(1, 1, self.width() - 2, self.height() - 2)
        painter.setPen(QPen(QColor("#FF5C6B"), 1.4))
        painter.setBrush(QColor("#281116"))
        painter.drawRoundedRect(outer, 8, 8)
        mark_pen = QPen(QColor("#F7FAFC"), 2.2)
        mark_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        mark_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(mark_pen)
        painter.drawLine(7, 9, 10, 21)
        painter.drawLine(10, 21, 15, 13)
        painter.drawLine(15, 13, 20, 21)
        painter.drawLine(20, 21, 23, 9)
        painter.end()


class RiftNavButton(QPushButton):
    """WinKit yan menüsü için kaynak dosyasız, çizim tabanlı ikonlu düğme."""

    def __init__(self, text, icon_kind, parent=None, sub_item=False, branch_last=False):
        super().__init__(text, parent)
        self.icon_kind = icon_kind
        self.sub_item = bool(sub_item)
        self.branch_last = bool(branch_last)
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(42)
        self._refresh_style()

    def set_active(self, active):
        self._active = bool(active)
        self._refresh_style()
        self.update()

    def _refresh_style(self):
        left_padding = 46 if self.sub_item else 42
        font_size = "11.5px" if self.sub_item else "12.5px"
        font_weight = "600" if self._active else ("500" if self.sub_item else "600")
        if self._active:
            active_border = "transparent" if self.sub_item else "#E63B4D"
            self.setStyleSheet(
                f"QPushButton {{ background-color: #241217; color: #FFFFFF; "
                f"border: none; border-left: 2px solid {active_border}; border-radius: 6px; "
                f"padding: 0 5px 0 {left_padding}px; "
                f"text-align: left; font-size: {font_size}; font-weight: {font_weight}; }}\n"
                "QPushButton:hover { background-color: #2D141B; }"
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ background-color: transparent; color: #8C9BA8; "
                f"border: none; border-left: 2px solid transparent; border-radius: 6px; "
                f"padding: 0 5px 0 {left_padding}px; "
                f"text-align: left; font-size: {font_size}; font-weight: {font_weight}; }}\n"
                "QPushButton:hover { background-color: #121820; color: #E2E8F0; }"
            )

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        x = 28 if self.sub_item else 20
        y = self.height() // 2

        # Sub-item subtle indicator dot
        if self.sub_item:
            dot_color = QColor("#E63B4D" if self._active else "#4B5665")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(dot_color))
            painter.drawEllipse(13, y - 2, 4, 4)

        color = QColor("#FF6574" if self._active else "#718096")
        painter.setPen(QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

        if self.icon_kind == "debloat":
            painter.drawEllipse(x - 7, y - 7, 14, 14)
            painter.drawLine(x, y, x + 5, y - 4)
            painter.drawEllipse(x - 1, y - 1, 2, 2)
        elif self.icon_kind == "iso":
            painter.drawEllipse(x - 7, y - 7, 14, 14)
            painter.drawEllipse(x - 2, y - 2, 4, 4)
            painter.drawLine(x - 5, y + 5, x + 5, y - 5)
        elif self.icon_kind == "apps":
            for dx, dy in ((-6, -6), (2, -6), (-6, 2), (2, 2)):
                painter.drawRoundedRect(QRect(x + dx, y + dy, 5, 5), 1, 1)
        elif self.icon_kind == "privacy":
            painter.drawRoundedRect(QRect(x - 7, y - 5, 14, 11), 3, 3)
            painter.drawArc(QRect(x - 4, y - 9, 8, 9), 0, 180 * 16)
            painter.drawLine(x, y - 1, x, y + 3)
        elif self.icon_kind == "anti_dpi":
            # Modern Security Shield with Lightning Bolt
            shield = QPolygonF([
                QPointF(x - 6.5, y - 6.5),
                QPointF(x + 6.5, y - 6.5),
                QPointF(x + 6.5, y - 1.0),
                QPointF(x, y + 7.5),
                QPointF(x - 6.5, y - 1.0),
            ])
            painter.drawPolygon(shield)
            bolt = QPolygonF([
                QPointF(x + 0.5, y - 4.5),
                QPointF(x - 2.5, y),
                QPointF(x + 0.5, y),
                QPointF(x - 0.5, y + 4.5),
                QPointF(x + 2.5, y - 0.5),
                QPointF(x - 0.5, y - 0.5),
            ])
            painter.drawPolyline(bolt)
        elif self.icon_kind == "dpi_tester":
            # Modern Speedometer / Diagnostic Probe Gauge
            painter.drawArc(QRectF(x - 6.5, y - 6.5, 13.0, 13.0), -45 * 16, 270 * 16)
            painter.drawEllipse(QPointF(x, y + 1.5), 1.5, 1.5)
            painter.drawLine(QPointF(x, y + 1.5), QPointF(x + 4.0, y - 3.5))
        elif self.icon_kind == "restore":
            # Symmetrical Refresh / Restore Circular Arrow
            painter.drawArc(QRectF(x - 6.5, y - 6.5, 13.0, 13.0), 30 * 16, 280 * 16)
            painter.drawLine(QPointF(x + 5.6, y - 3.2), QPointF(x + 6.0, y - 7.5))
            painter.drawLine(QPointF(x + 5.6, y - 3.2), QPointF(x + 1.5, y - 3.5))
        elif self.icon_kind == "license":
            painter.drawEllipse(x - 7, y - 4, 8, 8)
            painter.drawLine(x + 1, y, x + 7, y)
            painter.drawLine(x + 4, y, x + 4, y + 3)
            painter.drawLine(x + 6, y, x + 6, y + 3)
        elif self.icon_kind == "key_remap":
            # Modern Keyboard Keycap with Switch Indicator
            painter.drawRoundedRect(QRectF(x - 6.5, y - 6.0, 13.0, 12.0), 2.5, 2.5)
            painter.drawLine(QPointF(x - 3.5, y - 2.0), QPointF(x + 3.5, y - 2.0))
            painter.drawLine(QPointF(x, y - 2.0), QPointF(x, y + 3.0))
            painter.drawLine(QPointF(x - 2.5, y + 3.0), QPointF(x + 2.5, y + 3.0))
        painter.end()


class SettingsGlyphButton(QPushButton):
    """Özelleştirilebilir satırlar için kompakt, çizim tabanlı ayar düğmesi."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Özelleştir")
        self.setStyleSheet(
            "QPushButton { background-color: #11161B; border: 1px solid #303A45; border-radius: 6px; }\n"
            "QPushButton:hover { background-color: #29151A; border: 1px solid #FF6574; }\n"
            "QPushButton:pressed { background-color: #35161D; border: 1px solid #303A45; }"
        )

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#FF7784" if self.underMouse() else "#AEB8C3")
        painter.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx, cy = self.width() // 2, self.height() // 2
        painter.drawEllipse(cx - 5, cy - 5, 10, 10)
        painter.drawEllipse(cx - 2, cy - 2, 4, 4)
        for x1, y1, x2, y2 in (
            (cx, cy - 9, cx, cy - 6), (cx, cy + 6, cx, cy + 9),
            (cx - 9, cy, cx - 6, cy), (cx + 6, cy, cx + 9, cy),
            (cx - 6, cy - 6, cx - 4, cy - 4), (cx + 4, cy + 4, cx + 6, cy + 6),
            (cx + 4, cy - 4, cx + 6, cy - 6), (cx - 6, cy + 6, cx - 4, cy + 4),
        ):
            painter.drawLine(x1, y1, x2, y2)
        painter.end()


class RiftSwitch(QPushButton):
    """WinKit ana seçeneklerinde kullanılan sağa hizalı animasyonlu switch (240Hz uyumlu)."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent; border: none;")
        self._knob_progress = 0.0
        self._knob_target = 0.0
        self._switch_timer = QTimer(self)
        self._switch_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._switch_timer.setInterval(4)  # 240Hz
        self._switch_timer.timeout.connect(self._animate_switch)
        self.toggled.connect(self._start_switch_animation)

    def _start_switch_animation(self, checked):
        self._knob_target = 1.0 if checked else 0.0
        self.update()  # Renk, mekanik hareketi beklemeden anında değişsin.
        if not self.isVisible():
            self._knob_progress = self._knob_target
            self.update()
            return
        if not self._switch_timer.isActive():
            self._switch_timer.start()

    def setCheckedImmediate(self, checked):
        """Toplu seçimde renk ve düğme konumunu anında ayarlar."""
        self._switch_timer.stop()
        self.setChecked(bool(checked))
        self._knob_target = 1.0 if checked else 0.0
        self._knob_progress = self._knob_target
        self.update()

    def _animate_switch(self):
        difference = self._knob_target - self._knob_progress
        if abs(difference) < 0.015:
            self._knob_progress = self._knob_target
            self._switch_timer.stop()
        else:
            self._knob_progress += difference * 0.12
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. SOL KENAR LİSTE VURGU ÇİZGİSİ (Animasyonlu yumuşak renk geçişi)
        bar_w, bar_h = 3, 14
        bar_x = 0
        bar_y = (self.height() - bar_h) // 2
        c_off = QColor("#36424F")
        c_on = QColor("#E63B4D")
        r = int(c_off.red() + (c_on.red() - c_off.red()) * self._knob_progress)
        g = int(c_off.green() + (c_on.green() - c_off.green()) * self._knob_progress)
        b = int(c_off.blue() + (c_on.blue() - c_off.blue()) * self._knob_progress)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(r, g, b)))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 1.5, 1.5)

        track_width, track_height = 36, 18
        track_x = self.width() - track_width - 2
        track_y = (self.height() - track_height) // 2

        # 2. METİN (14px sol girintili, belirteçle tam hizalı)
        text_rect = QRect(14, 0, max(0, track_x - 24), self.height())
        painter.setPen(QColor("#FFFFFF" if self.isChecked() else "#D8DFE8"))
        font = painter.font()
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        visible_text = painter.fontMetrics().elidedText(
            self.text(),
            Qt.TextElideMode.ElideRight,
            text_rect.width(),
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            visible_text,
        )

        if self.isChecked():
            track_fill = QColor("#B52F3E")
            track_border = QColor("#FF6574")
            knob = QColor("#FFE4E7")
        else:
            track_fill = QColor("#151A20")
            track_border = QColor("#3B4652")
            knob = QColor("#737E89")
        knob_x = int(track_x + 3 + (track_width - 17) * self._knob_progress)
        if not self.isEnabled():
            track_fill = QColor("#151217")
            track_border = QColor("#302A33")
            knob = QColor("#514A54")

        if self.isChecked() and self.isEnabled():
            painter.setPen(QPen(QColor(230, 59, 77, 72), 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRect(track_x - 1, track_y - 1, track_width + 2, track_height + 2),
                track_height // 2,
                track_height // 2,
            )
        painter.setPen(QPen(track_border, 1))
        painter.setBrush(QBrush(track_fill))
        painter.drawRoundedRect(
            QRect(track_x, track_y, track_width, track_height),
            track_height // 2,
            track_height // 2,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(knob))
        painter.drawEllipse(knob_x, track_y + 3, 12, 12)
        painter.end()


class SmoothScrollArea(QScrollArea):
    """Kesirli konum biriktiren, yüksek yenileme hızlı kinetik kaydırma alanı."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._velocity = 0.0
        self._scroll_position = 0.0
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._scroll_timer.setInterval(4)  # 240 Hz panellerde de düzenli örnekleme
        self._scroll_timer.timeout.connect(self._step_kinetic)
        self.verticalScrollBar().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched == self.verticalScrollBar() and event.type() == QEvent.Type.Wheel:
            self.wheelEvent(event)
            return True
        if watched == self.verticalScrollBar() and event.type() == QEvent.Type.MouseButtonPress:
            self._scroll_timer.stop()
            self._velocity = 0.0
            self._scroll_position = float(self.verticalScrollBar().value())
        return super().eventFilter(watched, event)

    def _step_kinetic(self):
        if abs(self._velocity) < 0.08:
            self._velocity = 0.0
            self._scroll_timer.stop()
            return

        bar = self.verticalScrollBar()
        self._scroll_position -= self._velocity
        self._scroll_position = max(
            float(bar.minimum()), min(float(bar.maximum()), self._scroll_position)
        )
        clamped_val = int(round(self._scroll_position))
        bar.setValue(clamped_val)
        self.viewport().update()

        if clamped_val == bar.minimum() or clamped_val == bar.maximum():
            self._velocity = 0.0
            self._scroll_timer.stop()
            return

        self._velocity *= 0.94

    def wheelEvent(self, event):
        pixel_delta = event.pixelDelta().y()
        angle_delta = event.angleDelta().y()
        if not pixel_delta and not angle_delta:
            return super().wheelEvent(event)
        
        impulse = (pixel_delta * 0.18) if pixel_delta else ((angle_delta / 120.0) * 5.2)
        if not self._scroll_timer.isActive():
            self._scroll_position = float(self.verticalScrollBar().value())
        self._velocity = max(-20.0, min(20.0, self._velocity + impulse))

        if not self._scroll_timer.isActive():
            self._scroll_timer.start()
        event.accept()


class SmoothConsoleTextEdit(QTextEdit):
    """Konsollara da aynı kesirli, yumuşak tekerlek momentumunu uygular."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._velocity = 0.0
        self._scroll_position = 0.0
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._scroll_timer.setInterval(4)
        self._scroll_timer.timeout.connect(self._step_kinetic)
        self.verticalScrollBar().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched == self.verticalScrollBar() and event.type() == QEvent.Type.Wheel:
            self.wheelEvent(event)
            return True
        if watched == self.verticalScrollBar() and event.type() == QEvent.Type.MouseButtonPress:
            self._scroll_timer.stop()
            self._velocity = 0.0
            self._scroll_position = float(self.verticalScrollBar().value())
        return super().eventFilter(watched, event)

    def _step_kinetic(self):
        if abs(self._velocity) < 0.08:
            self._velocity = 0.0
            self._scroll_timer.stop()
            return
        bar = self.verticalScrollBar()
        self._scroll_position -= self._velocity
        self._scroll_position = max(
            float(bar.minimum()), min(float(bar.maximum()), self._scroll_position)
        )
        value = int(round(self._scroll_position))
        bar.setValue(value)
        self.viewport().update()
        if value == bar.minimum() or value == bar.maximum():
            self._velocity = 0.0
            self._scroll_timer.stop()
            return
        self._velocity *= 0.94

    def wheelEvent(self, event):
        pixel_delta = event.pixelDelta().y()
        angle_delta = event.angleDelta().y()
        if not pixel_delta and not angle_delta:
            return super().wheelEvent(event)
        impulse = (pixel_delta * 0.18) if pixel_delta else ((angle_delta / 120.0) * 5.2)
        if not self._scroll_timer.isActive():
            self._scroll_position = float(self.verticalScrollBar().value())
        self._velocity = max(-20.0, min(20.0, self._velocity + impulse))
        if not self._scroll_timer.isActive():
            self._scroll_timer.start()
        event.accept()


class SmoothLoadingRing(QWidget):
    """İkon kullanmadan çizilen, akıcı dönen yüklenme halkası."""

    def __init__(self, color="#E63B4D", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._angle = 0.0
        self._active = False
        self.setFixedSize(28, 28)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance)
        self.hide()

    def start(self):
        self._active = True
        self.show()
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        self._active = False
        self._timer.stop()
        self.hide()
        self.update()

    def _advance(self):
        self._angle = (self._angle + 4.8) % 360.0
        self.update()

    def paintEvent(self, event):
        if not self._active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(
            self._color,
            3,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        rect = self.rect().adjusted(4, 4, -4, -4)
        painter.drawArc(
            rect,
            int(-self._angle * 16),
            int(265 * 16),
        )
        painter.end()


# ---------- Animated Tick CheckBox (crash‑safe, timer‑based, 240Hz) ----------
class AnimatedRadioButton(QRadioButton):
    """RadioButton with smooth animated inner indicator expansion (240Hz uyumlu, tam dairesel)."""
    def __init__(self, text, parent=None, color="#E63B4D"):
        super().__init__(text, parent)
        self._indicator_color = QColor(color)
        self._animProgress = 1.0 if self.isChecked() else 0.0
        self._targetProgress = 1.0 if self.isChecked() else 0.0
        self._animTimer = QTimer(self)
        self._animTimer.setTimerType(Qt.TimerType.PreciseTimer)
        self._animTimer.setInterval(4)
        self._animTimer.timeout.connect(self._animStep)
        self.toggled.connect(self._startAnim)

    def _startAnim(self, checked):
        self._targetProgress = 1.0 if checked else 0.0
        if not self.isVisible():
            self._animProgress = self._targetProgress
            self.update()
            return
        if not self._animTimer.isActive():
            self._animTimer.start()

    def setCheckedImmediate(self, checked):
        self._animTimer.stop()
        self.setChecked(bool(checked))
        self._targetProgress = 1.0 if checked else 0.0
        self._animProgress = self._targetProgress
        self.update()

    def _animStep(self):
        diff = self._targetProgress - self._animProgress
        if abs(diff) < 0.02:
            self._animProgress = self._targetProgress
            self._animTimer.stop()
        else:
            step = diff * 0.18
            if abs(step) < 0.01:
                step = 0.01 if diff > 0 else -0.01
            self._animProgress += step
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isVisible() or self.width() <= 0 or self.height() <= 0:
            return

        try:
            opt = QStyleOptionButton()
            self.initStyleOption(opt)
            indicatorRect = self.style().subElementRect(QStyle.SubElement.SE_RadioButtonIndicator, opt, self)
            if indicatorRect.width() == 0 or indicatorRect.height() == 0:
                indicatorRect = QRect(0, (self.height() - 16) // 2, 16, 16)
        except Exception:
            indicatorRect = QRect(0, (self.height() - 16) // 2, 16, 16)

        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = QPointF(indicatorRect.center())
        
        # Outer circle outline
        r_out = 6.5
        border_color = self._indicator_color if (self.isChecked() or self._animProgress > 0.15) else QColor("#5A6572")
        painter.setPen(QPen(border_color, 1.8))
        painter.setBrush(QBrush(QColor("#0E1217")))
        painter.drawEllipse(center, r_out, r_out)

        # Inner filled circle dot
        r_in = 3.8 * self._animProgress
        if r_in > 0.3:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._indicator_color))
            painter.drawEllipse(center, r_in, r_in)

        painter.end()


class AnimatedTickCheckBox(QCheckBox):
    """CheckBox with a drawn checkmark animation using a QTimer (240Hz uyumlu)."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._tickProgress = 0.0          # 0 = invisible, 1 = fully drawn
        self._targetProgress = 0.0
        self._tickTimer = QTimer(self)
        self._tickTimer.setTimerType(Qt.TimerType.PreciseTimer)
        self._tickTimer.setInterval(4)    # 240Hz tazeleme hızı
        self._tickTimer.timeout.connect(self._tickStep)
        self.toggled.connect(self._startAnim)

    def _startAnim(self, checked):
        self._targetProgress = 1.0 if checked else 0.0
        if not self.isVisible():
            self._tickProgress = self._targetProgress
            self.update()
            return
        if abs(self._tickProgress - self._targetProgress) < 0.001:
            self._tickProgress = self._targetProgress
            self.update()
            return
        if not self._tickTimer.isActive():
            self._tickTimer.start()

    def setCheckedImmediate(self, checked):
        self._tickTimer.stop()
        self.setChecked(bool(checked))
        self._targetProgress = 1.0 if checked else 0.0
        self._tickProgress = self._targetProgress
        self.update()

    def _tickStep(self):
        diff = self._targetProgress - self._tickProgress
        if abs(diff) < 0.02:
            self._tickProgress = self._targetProgress
            self._tickTimer.stop()
        else:
            step = diff * 0.12
            if abs(step) < 0.01:
                step = 0.01 if diff > 0 else -0.01
            self._tickProgress += step
            if (diff > 0 and self._tickProgress > self._targetProgress) or \
               (diff < 0 and self._tickProgress < self._targetProgress):
                self._tickProgress = self._targetProgress
                self._tickTimer.stop()
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        # Safety: do nothing if widget is invalid or invisible
        if not self.isVisible():
            return
        if self.width() <= 0 or self.height() <= 0:
            return

        # Draw animated tick only if needed
        draw = self.isChecked() or self._tickProgress > 0.0
        if not draw:
            return
        progress = self._tickProgress

        # Get indicator rectangle via style (protected with try/except)
        try:
            opt = QStyleOptionButton()
            self.initStyleOption(opt)
            indicatorRect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt, self)
            if indicatorRect.width() == 0 or indicatorRect.height() == 0:
                indicatorRect = QRect(0, (self.height() - 18) // 2, 18, 18)
        except Exception:
            indicatorRect = QRect(0, (self.height() - 18) // 2, 18, 18)

        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isChecked():
            painter.setPen(QPen(QColor(230, 59, 77, 165), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(indicatorRect.adjusted(1, 1, -1, -1), 3, 3)
        pen = QPen(QColor("#FFFFFF"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        x1 = indicatorRect.left() + indicatorRect.width() * 0.20
        y1 = indicatorRect.top() + indicatorRect.height() * 0.50
        x2 = indicatorRect.left() + indicatorRect.width() * 0.40
        y2 = indicatorRect.top() + indicatorRect.height() * 0.70
        x3 = indicatorRect.left() + indicatorRect.width() * 0.80
        y3 = indicatorRect.top() + indicatorRect.height() * 0.30

        t1 = min(1.0, progress * 2.0)
        line1_endx = x1 + (x2 - x1) * t1
        line1_endy = y1 + (y2 - y1) * t1
        painter.drawLine(int(x1), int(y1), int(line1_endx), int(line1_endy))

        if progress > 0.5:
            t2 = (progress - 0.5) * 2.0
            line2_endx = x2 + (x3 - x2) * t2
            line2_endy = y2 + (y3 - y2) * t2
            painter.drawLine(int(x2), int(y2), int(line2_endx), int(line2_endy))
        painter.end()


class SleekAnimatedTooltip(QLabel):
    """Modern, hızlı açılan (70ms) ve akıcı fade animasyonlu özel tooltip balonu."""
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = SleekAnimatedTooltip()
        return cls._instance

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(
            "QLabel { background: transparent; color: #E7ECF2; font-size: 11.5px; line-height: 1.4; }"
        )
        self.setWordWrap(True)
        self.setMaximumWidth(380)

        self._opacity_fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_fx)
        self._opacity_fx.setOpacity(0.0)

        self._fade_anim = QPropertyAnimation(self._opacity_fx, b"opacity")
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.setInterval(70)
        self._show_timer.timeout.connect(self._do_show)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(40)
        self._hide_timer.timeout.connect(self._do_hide)

        self._pending_pos = QPoint()
        self._pending_text = ""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QBrush(QColor("#12161F")))
        painter.setPen(QPen(QColor("#3A4553"), 1.0))
        painter.drawRoundedRect(rect, 8.0, 8.0)

        painter.setPen(QPen(QColor("#E7ECF2")))
        f = self.font()
        f.setPointSizeF(9.0)
        painter.setFont(f)
        text_rect = rect.adjusted(12, 8, -12, -8)
        painter.drawText(text_rect, int(Qt.TextFlag.TextWordWrap), self.text())
        painter.end()

    def sizeHint(self):
        f = self.font()
        f.setPointSizeF(9.0)
        fm = self.fontMetrics()
        max_w = 340
        bounding = fm.boundingRect(0, 0, max_w, 10000, int(Qt.TextFlag.TextWordWrap), self.text() or self._pending_text or "")
        return QSize(max(bounding.width() + 28, 60), bounding.height() + 20)

    def request_show(self, text, global_pos):
        self._hide_timer.stop()
        self._pending_text = text
        self._pending_pos = global_pos
        if self.isVisible() and self._opacity_fx.opacity() > 0.3:
            self.setText(text)
            self.resize(self.sizeHint())
            self.move(global_pos)
            self.update()
        else:
            self._show_timer.start()

    def request_hide(self):
        self._show_timer.stop()
        self._hide_timer.start()

    def _do_show(self):
        self.setText(self._pending_text)
        self.resize(self.sizeHint())
        self.move(self._pending_pos)
        self.show()
        self._fade_anim.stop()
        self._fade_anim.setDuration(140)
        self._fade_anim.setStartValue(self._opacity_fx.opacity())
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def _do_hide(self):
        if not self.isVisible():
            return
        self._fade_anim.stop()
        self._fade_anim.setDuration(100)
        self._fade_anim.setStartValue(self._opacity_fx.opacity())
        self._fade_anim.setEndValue(0.0)
        def _on_hidden():
            if self._opacity_fx.opacity() <= 0.05:
                self.hide()
        self._fade_anim.finished.connect(_on_hidden)
        self._fade_anim.start()


class TooltipHoverFilter(QObject):
    """Bir widget'a fare girdiğinde/çıktığında SleekAnimatedTooltip'i tetikleyen hafif filtre."""
    def __init__(self, text, widget):
        super().__init__(widget)
        self.text = text
        self.widget = widget
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.widget:
            if event.type() == QEvent.Type.Enter:
                pos = self.widget.mapToGlobal(QPoint(0, self.widget.height() + 6))
                SleekAnimatedTooltip.instance().request_show(self.text, pos)
            elif event.type() == QEvent.Type.Leave:
                SleekAnimatedTooltip.instance().request_hide()
        return super().eventFilter(obj, event)


class SmoothComboScrollFilter(QObject):
    """QComboBox popup listesi için tekerlek ve scrollbar tıklamalarında pürüzsüz kaydırma animatörü."""
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo
        self._scroll_anim = None
        self._velocity = 0.0
        self._scroll_position = 0.0
        self._kinetic_timer = QTimer(self)
        self._kinetic_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._kinetic_timer.setInterval(4)
        self._kinetic_timer.timeout.connect(self._step_kinetic)

    def attach(self):
        view = self.combo.view()
        if not view:
            return
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.viewport().installEventFilter(self)
        bar = view.verticalScrollBar()
        if bar:
            bar.installEventFilter(self)

    def eventFilter(self, watched, event):
        try:
            view = self.combo.view()
        except (RuntimeError, AttributeError):
            return False
        bar = view.verticalScrollBar() if view else None
        if not bar or not bar.isVisible():
            return super().eventFilter(watched, event)

        # 1. Tekerlek ile pürüzsüz kinetik kaydırma
        if (watched == view.viewport() or watched == bar) and event.type() == QEvent.Type.Wheel:
            p_delta = event.pixelDelta().y()
            a_delta = event.angleDelta().y()
            if not p_delta and not a_delta:
                return super().eventFilter(watched, event)
            impulse = (p_delta * 0.22) if p_delta else ((a_delta / 120.0) * 8.0)
            if not self._kinetic_timer.isActive():
                self._scroll_position = float(bar.value())
            self._velocity = max(-24.0, min(24.0, self._velocity + impulse))
            if not self._kinetic_timer.isActive():
                self._kinetic_timer.start()
            return True

        # 2. Scrollbar track'ine basıldığında ışınlanmak yerine yumuşakça kayma
        if watched == bar and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                opt = QStyleOptionSlider()
                bar.initStyleOption(opt)
                style = bar.style()
                handle_rect = style.subControlRect(
                    QStyle.ComplexControl.CC_ScrollBar, opt,
                    QStyle.SubControl.SC_ScrollBarSlider, bar
                )
                if not handle_rect.contains(pos):
                    track_rect = style.subControlRect(
                        QStyle.ComplexControl.CC_ScrollBar, opt,
                        QStyle.SubControl.SC_ScrollBarGroove, bar
                    )
                    h_h = handle_rect.height()
                    available_h = max(1, track_rect.height() - h_h)
                    rel_y = max(0, min(available_h, pos.y() - track_rect.y() - h_h // 2))
                    ratio = rel_y / float(available_h)
                    target_val = int(bar.minimum() + ratio * (bar.maximum() - bar.minimum()))

                    self._kinetic_timer.stop()
                    self._velocity = 0.0
                    if self._scroll_anim and self._scroll_anim.state() == QAbstractAnimation.State.Running:
                        self._scroll_anim.stop()
                    self._scroll_anim = QPropertyAnimation(bar, b"value")
                    self._scroll_anim.setDuration(160)
                    self._scroll_anim.setStartValue(bar.value())
                    self._scroll_anim.setEndValue(target_val)
                    self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                    self._scroll_anim.start()
                    return True
                else:
                    self._kinetic_timer.stop()
                    self._velocity = 0.0
                    if self._scroll_anim:
                        self._scroll_anim.stop()

        return super().eventFilter(watched, event)

    def _step_kinetic(self):
        view = self.combo.view()
        if not view:
            self._kinetic_timer.stop()
            return
        bar = view.verticalScrollBar()
        if not bar or not bar.isVisible():
            self._kinetic_timer.stop()
            return

        if abs(self._velocity) < 0.1:
            self._velocity = 0.0
            self._kinetic_timer.stop()
            return

        self._scroll_position -= self._velocity
        self._scroll_position = max(
            float(bar.minimum()), min(float(bar.maximum()), self._scroll_position)
        )
        clamped_val = int(round(self._scroll_position))
        bar.setValue(clamped_val)

        if clamped_val == bar.minimum() or clamped_val == bar.maximum():
            self._velocity = 0.0
            self._kinetic_timer.stop()
            return

        self._velocity *= 0.92


class RiftComboBox(QComboBox):
    """Modern animasyonlu, antialiased chevron oklu ve koyu temalı WinKit açılır seçim kutusu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("""
            QComboBox {
                background-color: #0E1318;
                border: 1px solid #2D3742;
                border-radius: 6px;
                padding: 4px 28px 4px 12px;
                color: #F1F4F8;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox:hover {
                border: 1px solid #E63B4D;
                background-color: #12181F;
            }
            QComboBox:focus, QComboBox:on, QComboBox:pressed {
                border: 1.5px solid #E63B4D;
                background-color: #12181F;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 26px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #0E1318;
                border: 1px solid #2D3742;
                border-radius: 6px;
                color: #F1F4F8;
                padding: 4px;
                selection-background-color: #2D141A;
                selection-color: #FF5A6B;
                outline: none;
                font-size: 12px;
            }
            QComboBox QAbstractItemView::item {
                min-height: 28px;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #1A222B;
                color: #FFFFFF;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #2D141A;
                color: #FF5A6B;
                font-weight: 600;
            }
            QComboBox QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 4px 3px 4px 0px;
                border: none;
            }
            QComboBox QScrollBar::handle:vertical {
                background: #2D3A49;
                min-height: 22px;
                border-radius: 2.5px;
            }
            QComboBox QScrollBar::handle:vertical:hover {
                background: #FF334B;
            }
            QComboBox QScrollBar::add-line:vertical, QComboBox QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
                border: none;
            }
            QComboBox QScrollBar::add-page:vertical, QComboBox QScrollBar::sub-page:vertical {
                background: none;
                border: none;
            }
        """)
        self.view().setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._scroll_filter = SmoothComboScrollFilter(self)
        self._scroll_filter.attach()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        arrow_x = self.width() - 16
        arrow_y = self.height() // 2 - 1
        
        pen = QPen(QColor("#8995A1"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(arrow_x - 4, arrow_y - 2, arrow_x, arrow_y + 2)
        painter.drawLine(arrow_x, arrow_y + 2, arrow_x + 4, arrow_y - 2)
        painter.end()

    def showPopup(self):
        super().showPopup()


class FilterChip(QPushButton):
    """Debloat ve ayarlar için modern hap şeklinde kategori filtre butonu."""

    def __init__(self, text, category, count=0, parent=None):
        label = f"{text} ({count})" if count > 0 else text
        super().__init__(label, parent)
        self.category = category
        self._active = False
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()

    def set_active(self, active):
        self._active = bool(active)
        self._refresh()

    def _refresh(self):
        if self._active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #2A1217;
                    color: #FF5A6B;
                    border: 1px solid #E63B4D;
                    border-radius: 14px;
                    padding: 0 12px;
                    font-size: 11px;
                    font-weight: 600;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #0E1318;
                    color: #8C9BA8;
                    border: 1px solid #232D37;
                    border-radius: 14px;
                    padding: 0 12px;
                    font-size: 11px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #151D26;
                    color: #E2E8F0;
                    border: 1px solid #364453;
                }
            """)


class StatusToastWidget(QFrame):
    """Modern, hafif renkli yüzeye (tinted surface) sahip, sözcük kaydırmalı (word-wrap) Material UI Inline Alert kartı."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(34)
        self.setMinimumWidth(220)
        self.setMaximumWidth(520)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.setObjectName("StatusToast")
        
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 6, 8, 6)
        self._layout.setSpacing(8)

        self.indicator = QLabel("●")
        self.indicator.setStyleSheet("color: #FF5C6B; font-size: 10px; border: none; background: transparent;")
        self.indicator.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet("color: #E2E8F0; font-size: 11px; font-weight: 600; border: none; background: transparent; line-height: 1.3;")
        self.msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #7E8B99; border: none; font-size: 11px; font-weight: bold; border-radius: 9px; }\n"
            "QPushButton:hover { background: #26303B; color: #FFFFFF; }"
        )
        self.close_btn.clicked.connect(self._fade_out)
        
        self._layout.addWidget(self.indicator, 0, Qt.AlignmentFlag.AlignTop)
        self._layout.addWidget(self.msg, 1, Qt.AlignmentFlag.AlignVCenter)
        self._layout.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self.hide()

        self._anim = QPropertyAnimation(self._effect, b"opacity")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    def show_message(self, text, success=False, auto_hide_ms=0, severity=None):
        if not text:
            return
        self.msg.setText(str(text))
        
        # Severity tespiti (success, error, warning)
        if severity is None:
            if success:
                sev = "success"
            elif any(w in str(text).lower() for w in ("uyarı", "dikkat", "beklen", "öneri")):
                sev = "warning"
            else:
                sev = "error"
        else:
            sev = severity

        if sev == "success":
            bg = "#101D17"
            border = "#1B432F"
            accent = "#55D67A"
            icon = "✔"
            txt_color = "#D2F5DC"
        elif sev == "warning":
            bg = "#201B11"
            border = "#4E3E19"
            accent = "#FFB86C"
            icon = "▲"
            txt_color = "#FFF0D4"
        else: # error
            bg = "#201215"
            border = "#4F1D25"
            accent = "#FF5C6B"
            icon = "✖"
            txt_color = "#FFE2E5"

        self.setStyleSheet(f"""
            QFrame#StatusToast {{
                background-color: {bg};
                border: 1px solid {border};
                border-left: 3px solid {accent};
                border-radius: 6px;
            }}
        """)
        self.indicator.setText(icon)
        self.indicator.setStyleSheet(f"color: {accent}; font-size: 10px; font-weight: bold; border: none; background: transparent; padding-top: 1px;")
        self.msg.setStyleSheet(f"color: {txt_color}; font-size: 11px; font-weight: 600; border: none; background: transparent; line-height: 1.3;")

        self.adjustSize()
        self.show()
        self._hide_timer.stop()
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        if auto_hide_ms > 0:
            self._hide_timer.start(auto_hide_ms)

    def _fade_out(self):
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._on_fade_out_finished)
        self._anim.start()

    def _on_fade_out_finished(self):
        try:
            self._anim.finished.disconnect(self._on_fade_out_finished)
        except Exception:
            pass
        if self._effect.opacity() <= 0.05:
            self.hide()



class CTkToolTip(QObject):
    """Eski tooltip'lerin işlevini ve risk göstergesini sağlayan sınıf."""
    def __init__(self, widget, text, risk_level=0):
        super().__init__(widget)
        self.widget = widget
        self.text = text
        self.risk_level = risk_level
        self.tooltip_frame = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide)
        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self.show)
        self.widget.installEventFilter(self)
        self._created = False
        self._fade_anim = None
        self._opacity_effect = None
        self._showing = False

    def _build_tooltip(self):
        if self.tooltip_frame is not None:
            return
        self.tooltip_frame = QFrame(
            None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        self.tooltip_frame.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.tooltip_frame.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.tooltip_frame.hide()

        vbox = QVBoxLayout(self.tooltip_frame)
        vbox.setContentsMargins(7, 5, 7, 5)
        vbox.setSpacing(6)

        border_colors = {0: "#6FE38C", 1: "#F2B84B", 2: "#FF5C6B"}
        border_color = border_colors.get(self.risk_level, "#6FE38C")
        self._label = QLabel(self.text)
        self._label.setMaximumWidth(320)
        self._label.setMinimumWidth(200)
        self._label.setStyleSheet(
            f"color: #F2F5F8; background-color: #0D1116; "
            f"border: 1px solid {border_color}; border-radius: 9px; padding: 10px 12px; "
            "font-family: 'Segoe UI Variable Text'; font-size: 12px; line-height: 1.3;"
        )
        self._label.setWordWrap(True)
        vbox.addWidget(self._label)

        # Risk satırı – tek bir arka plan, border'sız, yalnızca arkaplan ve yuvarlatılmış köşe
        self._risk_row = QFrame()
        self._risk_row.setObjectName("RiskRow")
        self._risk_row.setFixedHeight(28)
        self._risk_row.setStyleSheet(
            f"#RiskRow {{ background-color: #11171D; border: 1px solid {border_color}; border-radius: 14px; }}"
        )
        hrow = QHBoxLayout(self._risk_row)
        hrow.setContentsMargins(12, 0, 12, 0)
        hrow.setSpacing(6)
        hrow.setAlignment(Qt.AlignmentFlag.AlignCenter)

        colors = {0: "#6FE38C", 1: "#F2B84B", 2: "#FF5C6B"}
        names = {0: "Güvenli", 1: "Orta Risk", 2: "Yüksek Risk"}
        risk_color = colors.get(self.risk_level, "#00FF00")
        risk_name = names.get(self.risk_level, "")
        self._risk_visible = self.risk_level >= 0

        circle = QLabel(self._risk_row)
        circle.setFixedSize(14, 14)
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap(14, 14)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(risk_color)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 13, 13)
        painter.end()
        circle.setPixmap(pix)
        circle.setStyleSheet("background: transparent; border: none; padding: 0px; margin: 0px;")
        hrow.addWidget(circle)

        rlbl = QLabel(risk_name, self._risk_row)
        rlbl.setStyleSheet(
            f"color: {risk_color}; "
            "background: transparent; border: none; padding: 0px; "
            "font-family: 'Segoe UI Variable Text'; font-size: 11px; font-weight: 600;"
        )
        hrow.addWidget(rlbl)
        vbox.addWidget(self._risk_row, 0, Qt.AlignmentFlag.AlignCenter)
        self._risk_row.setVisible(self._risk_visible)

        self.tooltip_frame.adjustSize()

        # opacity effect for fade
        self._opacity_effect = QGraphicsOpacityEffect()
        self._opacity_effect.setOpacity(0.0)
        self.tooltip_frame.setGraphicsEffect(self._opacity_effect)

    def _hide(self):
        self._showing = False
        if self.tooltip_frame:
            self.tooltip_frame.hide()

    def show(self):
        if self._showing:
            return
        self._showing = True
        self._hide_timer.stop()
        self._show_timer.stop()
        if not self.tooltip_frame:
            self._build_tooltip()
        # update text in case it changed
        self._label.setText(self.text)
        # update risk visibility
        self._risk_row.setVisible(self.risk_level >= 0)

        pos = self.widget.mapToGlobal(QPoint(30, self.widget.height() + 4))
        self.tooltip_frame.move(pos)
        self.tooltip_frame.show()

        # fade in
        if self._opacity_effect:
            self._opacity_effect.setOpacity(0.0)
            if self._fade_anim:
                self._fade_anim.stop()
            self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
            self._fade_anim.setDuration(150)
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(0.95)
            self._fade_anim.start()

    def hide(self):
        if not self._showing:
            return
        self._showing = False
        self._show_timer.stop()
        self._hide_timer.stop()
        if self.tooltip_frame and self._opacity_effect:
            if self._fade_anim:
                self._fade_anim.stop()
            self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
            self._fade_anim.setDuration(150)
            self._fade_anim.setStartValue(0.95)
            self._fade_anim.setEndValue(0.0)
            self._fade_anim.finished.connect(self._hide)
            self._fade_anim.start()
        else:
            self._hide()

    def eventFilter(self, obj, event):
        if obj != self.widget:
            return super().eventFilter(obj, event)
        if event.type() == QEvent.Type.Enter:
            # show with a short delay to avoid rapid open/close
            self._hide_timer.stop()
            self._show_timer.start(80)
            return True
        elif event.type() == QEvent.Type.Leave:
            self._show_timer.stop()
            self.hide()
            return True
        return super().eventFilter(obj, event)





class SleekComboBox(QComboBox):
    """WinKit temasına uygun, neon-kırmızı vurgulu, zarif yuvarlatılmış özel açılır kutu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QComboBox { background-color: #121820; color: #F7F9FB; "
            "border: 1px solid #283340; border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 500; outline: none; }\n"
            "QComboBox:hover { border: 1px solid #FF334B; background-color: #161F28; }\n"
            "QComboBox:focus, QComboBox:on { border: 1px solid #FF334B; background-color: #161F28; outline: none; }\n"
            "QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 26px; "
            "border-left: 1px solid #283340; border-top-right-radius: 6px; border-bottom-right-radius: 6px; }\n"
            "QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; "
            "border-top: 5px solid #8C9BA8; width: 0; height: 0; }\n"
            "QComboBox::down-arrow:hover, QComboBox::down-arrow:on { border-top-color: #FF334B; }\n"
            "QComboBox QAbstractItemView { background-color: #0E1318; color: #E2E8F0; "
            "selection-background-color: #35161D; selection-color: #FF7784; border: 1px solid #283340; border-radius: 6px; padding: 4px; outline: none; }\n"
            "QComboBox QAbstractItemView::item { min-height: 28px; padding: 4px 8px; border-radius: 4px; outline: none; }\n"
            "QComboBox QAbstractItemView::item:hover { background-color: #241217; color: #FFFFFF; }\n"
            "QScrollBar:vertical { border: none; background: transparent; width: 8px; margin: 0px; }\n"
            "QScrollBar::handle:vertical { background: #555555; border-radius: 4px; min-height: 20px; border: none; }\n"
            "QScrollBar::handle:vertical:hover { background: #FF334B; }\n"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none; background: none; height: 0px; }\n"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { border: none; background: none; }"
        )
        try:
            vsb = self.view().verticalScrollBar()
            vsb.setStyleSheet(
                "QScrollBar:vertical { border: none; background: transparent; width: 8px; margin: 0px; }\n"
                "QScrollBar::handle:vertical { background: #555555; border-radius: 4px; min-height: 20px; border: none; }\n"
                "QScrollBar::handle:vertical:hover { background: #FF334B; }\n"
                "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none; background: none; height: 0px; }\n"
                "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { border: none; background: none; }"
            )
        except Exception:
            pass
        self._scroll_filter = SmoothComboScrollFilter(self)
        self._scroll_filter.attach()

    def showPopup(self):
        super().showPopup()
        try:
            view = self.view()
            if view:
                view.setStyleSheet(
                    "QAbstractItemView { background-color: #0E1318; color: #E2E8F0; "
                    "selection-background-color: #35161D; selection-color: #FF7784; "
                    "border: 1px solid #283340; border-radius: 6px; padding: 4px; outline: none; }\n"
                    "QScrollBar:vertical { border: none !important; background: transparent !important; width: 8px; margin: 0px; }\n"
                    "QScrollBar::handle:vertical { background: #555555; border-radius: 4px; min-height: 20px; border: none !important; }\n"
                    "QScrollBar::handle:vertical:hover { background: #FF334B; border: none !important; }\n"
                    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none !important; background: none !important; height: 0px; }\n"
                    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { border: none !important; background: none !important; }"
                )
                vsb = view.verticalScrollBar()
                if vsb:
                    vsb.setStyleSheet(
                        "QScrollBar:vertical { border: none !important; background: transparent !important; width: 8px; margin: 0px; }\n"
                        "QScrollBar::handle:vertical { background: #555555; border-radius: 4px; min-height: 20px; border: none !important; }\n"
                        "QScrollBar::handle:vertical:hover { background: #FF334B; border: none !important; }\n"
                        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none !important; background: none !important; height: 0px; }\n"
                        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { border: none !important; background: none !important; }"
                    )
        except Exception:
            pass



class OverlayCloseButton(QPushButton):
    """Yazı tipine bağlı kalmadan keskin bir kapatma işareti çizer."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton { background-color: #25151A; border: 1px solid #E63B4D; "
            "border-radius: 6px; }\n"
            "QPushButton:hover { background-color: #E63B4D; }"
        )

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#FFFFFF" if self.underMouse() else "#FF6574")
        pen = QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        margin = 9
        painter.drawLine(margin, margin, self.width() - margin, self.height() - margin)
        painter.drawLine(self.width() - margin, margin, margin, self.height() - margin)
        painter.end()


