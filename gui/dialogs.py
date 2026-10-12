"""
WinKit - Custom Dialogs and Overlays
Defender dialogs, Zapret collision notice, Key remapping dialog, and System Restore overlay.
"""

import sys
import math
import os
import ctypes
import subprocess
import winreg
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QObject, QPoint, QPointF, QRect, QRectF, QSize,
    QPropertyAnimation, QVariantAnimation, QEasingCurve, pyqtSignal, pyqtProperty,
    QEvent, QTimer, QParallelAnimationGroup, QAbstractAnimation
)
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QPainterPath, QCursor, QPixmap
)
from PyQt6.QtWidgets import (
    QWidget, QDialog, QPushButton, QLabel, QFrame, QVBoxLayout,
    QHBoxLayout, QGridLayout, QScrollArea, QGraphicsDropShadowEffect,
    QApplication, QMessageBox, QGraphicsOpacityEffect, QProgressBar, QButtonGroup
)

from core.constants import CREATE_NO_WINDOW
from gui.styles import QSS, DARK_THEME_PALETTE
from gui.widgets import (
    RiftNavButton, AnimatedRadioButton, SleekComboBox,
    OverlayCloseButton
)
from core.key_remap import (
    SCANCODE_DATABASE, SCANCODE_TO_LABEL, QT_KEY_TO_SCANCODE,
    KeyboardRemapEngine
)

class DefenderModeDialog(QDialog):
    """Windows Defender tekli sistem geçişi için geriye dönük uyumluluk arayüzü."""

    def __init__(self, current_mode="disable", parent=None):
        super().__init__(parent)
        self.selected_mode = "disable"
        self.opt_purge_full = type('D', (), {'setChecked': lambda v: None})()
        self.opt_purge = type('D', (), {'setChecked': lambda v: None})()
        self.opt_disable = type('D', (), {'setChecked': lambda v: None})()

    def accept(self):
        super().accept()

    def reject(self):
        super().reject()

    def set_current_mode(self, mode):
        self.selected_mode = mode if mode in ("purge", "purge_full") else "disable"


class DefenderWarningDialog(QDialog):
    """Windows Defender devre dışı bırakılmadan önce Kurcalamaya Karşı Koruma uyarısı gösteren modern modal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Windows Defender Uyarısı")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(500, 270)
        self._is_closing = False
        self._anim_group = None
        self._exit_group = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.card = QFrame()
        self.card.setStyleSheet(
            "background-color: #0E1318; border: 1px solid #FF6574; border-radius: 12px;"
        )
        self._card_opacity = QGraphicsOpacityEffect(self.card)
        self._card_opacity.setOpacity(0.0)
        self.card.setGraphicsEffect(self._card_opacity)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(22, 20, 22, 18)
        card_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon_lbl = QLabel()
        logo_path = None
        if parent is not None and hasattr(parent, "get_binary_path"):
            logo_path = parent.get_binary_path("winkit_logo.png")
        pix = QPixmap(logo_path or "")
        if not pix.isNull():
            icon_lbl.setPixmap(
                pix.scaled(
                    30,
                    30,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        icon_lbl.setFixedSize(30, 30)
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        header_row.addWidget(icon_lbl)

        title = QLabel("Windows Defender Kapatma Uyarısı")
        title.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: bold; border: none;")
        header_row.addWidget(title)
        header_row.addStretch()
        card_layout.addLayout(header_row)

        desc = QLabel(
            "Bu işlemi tamamlayabilmek için öncelikle Windows Güvenliği ayarlarından "
            "<b>kurcalamaya karşı koruma</b> ve <b>gerçek zamanlı koruma</b> "
            "özelliklerini kapatmanız gerekmektedir.<br><br>"
            "Aksi takdirde Windows Defender, kendi ayarlarının değiştirilmesini bir tehdit olarak algılayıp "
            "işlemi engelleyebilir."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #C9D3DC; font-size: 12px; line-height: 1.4; border: none;")
        card_layout.addWidget(desc)

        card_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        open_sec_btn = QPushButton("Windows Güvenliği Ayarlarını Aç")
        open_sec_btn.setFixedHeight(36)
        open_sec_btn.setStyleSheet(
            "QPushButton { background-color: #1A222B; color: #55D67A; border: 1px solid #2B3D4F; "
            "border-radius: 6px; font-weight: 600; font-size: 11px; padding: 0 10px; }\n"
            "QPushButton:hover { background-color: #24303D; border-color: #55D67A; }"
        )
        open_sec_btn.clicked.connect(self._open_windows_security)
        btn_row.addWidget(open_sec_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("Vazgeç")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setFixedWidth(80)
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #141A21; color: #8C9BA8; border: 1px solid #2A3440; "
            "border-radius: 6px; font-weight: 600; font-size: 11px; }\n"
            "QPushButton:hover { background-color: #1C242E; color: #FFFFFF; }"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("Anladım, Devam Et")
        ok_btn.setFixedHeight(36)
        ok_btn.setFixedWidth(140)
        ok_btn.setStyleSheet(
            "QPushButton { background-color: #E63B4D; color: #FFFFFF; border: 1px solid #FF6574; "
            "border-radius: 6px; font-weight: bold; font-size: 11px; }\n"
            "QPushButton:hover { background-color: #FF5263; }"
        )
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        card_layout.addLayout(btn_row)
        main_layout.addWidget(self.card)

    def _open_windows_security(self):
        try:
            os.startfile("windowsdefender://threatsettings")
        except Exception:
            try:
                subprocess.Popen(["explorer.exe", "ms-settings:windowsdefender"], creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass

    def showEvent(self, event):
        super().showEvent(event)
        self._is_closing = False
        if self.parent():
            p_geo = self.parent().geometry()
            target_x = p_geo.x() + (p_geo.width() - self.width()) // 2
            target_y = p_geo.y() + (p_geo.height() - self.height()) // 2
            self.move(target_x, target_y + 12)

            if self._anim_group and self._anim_group.state() == QAbstractAnimation.State.Running:
                try:
                    self._anim_group.stop()
                except Exception:
                    pass

            eff = QGraphicsOpacityEffect(self.card)
            eff.setOpacity(0.0)
            self.card.setGraphicsEffect(eff)
            self._card_opacity = eff

            self._fade_anim = QPropertyAnimation(self._card_opacity, b"opacity", self)
            self._fade_anim.setDuration(220)
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._slide_anim = QPropertyAnimation(self, b"pos", self)
            self._slide_anim.setDuration(220)
            self._slide_anim.setStartValue(QPoint(target_x, target_y + 12))
            self._slide_anim.setEndValue(QPoint(target_x, target_y))
            self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._anim_group = QParallelAnimationGroup(self)
            self._anim_group.addAnimation(self._fade_anim)
            self._anim_group.addAnimation(self._slide_anim)

            def _on_entrance_done():
                try:
                    self.card.setGraphicsEffect(None)
                except Exception:
                    pass

            self._anim_group.finished.connect(_on_entrance_done)
            self._anim_group.start()

    def animate_close(self, accepted=False):
        if getattr(self, "_is_closing", False):
            return
        self._is_closing = True

        if self._anim_group and self._anim_group.state() == QAbstractAnimation.State.Running:
            try:
                self._anim_group.stop()
            except Exception:
                pass

        cur_pos = self.pos()
        target_y = cur_pos.y() + 10

        current_op = 1.0
        if getattr(self, "_card_opacity", None) is not None:
            try:
                current_op = self._card_opacity.opacity()
            except Exception:
                current_op = 1.0

        eff = QGraphicsOpacityEffect(self.card)
        eff.setOpacity(current_op)
        self.card.setGraphicsEffect(eff)
        self._card_opacity = eff

        self._exit_fade = QPropertyAnimation(self._card_opacity, b"opacity", self)
        self._exit_fade.setDuration(160)
        self._exit_fade.setStartValue(current_op)
        self._exit_fade.setEndValue(0.0)
        self._exit_fade.setEasingCurve(QEasingCurve.Type.InQuad)

        self._exit_slide = QPropertyAnimation(self, b"pos", self)
        self._exit_slide.setDuration(160)
        self._exit_slide.setStartValue(cur_pos)
        self._exit_slide.setEndValue(QPoint(cur_pos.x(), target_y))
        self._exit_slide.setEasingCurve(QEasingCurve.Type.InQuad)

        self._exit_group = QParallelAnimationGroup(self)
        self._exit_group.addAnimation(self._exit_fade)
        self._exit_group.addAnimation(self._exit_slide)

        def on_exit_done():
            try:
                self.card.setGraphicsEffect(None)
            except Exception:
                pass
            if accepted:
                super(DefenderWarningDialog, self).accept()
            else:
                super(DefenderWarningDialog, self).reject()

        self._exit_group.finished.connect(on_exit_done)
        self._exit_group.start()

    def accept(self):
        self.animate_close(accepted=True)

    def reject(self):
        self.animate_close(accepted=False)


class ZapretAlreadyInstalledDialog(QDialog):
    """Zapret zaten sistemde kuruluyken tekrar kurulmasını önleyen modern uyarı modali."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Zapret Uyarısı")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(500, 260)
        self._is_closing = False
        self._anim_group = None
        self._exit_group = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.card = QFrame()
        self.card.setStyleSheet(
            "background-color: #0E1318; border: 1px solid #FF6574; border-radius: 12px;"
        )
        self._card_opacity = QGraphicsOpacityEffect(self.card)
        self._card_opacity.setOpacity(0.0)
        self.card.setGraphicsEffect(self._card_opacity)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(22, 20, 22, 18)
        card_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon_lbl = QLabel()
        logo_path = None
        if parent is not None and hasattr(parent, "get_binary_path"):
            logo_path = parent.get_binary_path("winkit_logo.png")
        pix = QPixmap(logo_path or "")
        if not pix.isNull():
            icon_lbl.setPixmap(
                pix.scaled(
                    30,
                    30,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        icon_lbl.setFixedSize(30, 30)
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        header_row.addWidget(icon_lbl)

        title = QLabel("Zapret Zaten Kurulu")
        title.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: bold; border: none;")
        header_row.addWidget(title)
        header_row.addStretch()
        card_layout.addLayout(header_row)

        desc = QLabel(
            "Sisteminizde halihazırda bir Zapret servisi veya kurulum dosyaları tespit edildi.<br><br>"
            "Çakışmaları ve dosya bozulmalarını önlemek için mevcut kurulum üzerine tekrar yükleme yapılamaz. "
            "Yeni bir sürüm kurmak istiyorsanız lütfen önce <b>Zapret servisini kaldır</b> seçeneğini kullanın."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #C9D3DC; font-size: 12px; line-height: 1.4; border: none;")
        card_layout.addWidget(desc)

        card_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        ok_btn = QPushButton("Tamam")
        ok_btn.setFixedHeight(36)
        ok_btn.setFixedWidth(110)
        ok_btn.setStyleSheet(
            "QPushButton { background-color: #E63B4D; color: #FFFFFF; border: 1px solid #FF6574; "
            "border-radius: 6px; font-weight: bold; font-size: 11px; }\n"
            "QPushButton:hover { background-color: #FF5263; }"
        )
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        card_layout.addLayout(btn_row)
        main_layout.addWidget(self.card)

    def showEvent(self, event):
        super().showEvent(event)
        self._is_closing = False
        if self.parent():
            p_geo = self.parent().geometry()
            target_x = p_geo.x() + (p_geo.width() - self.width()) // 2
            target_y = p_geo.y() + (p_geo.height() - self.height()) // 2
            self.move(target_x, target_y + 12)

            if self._anim_group and self._anim_group.state() == QAbstractAnimation.State.Running:
                try:
                    self._anim_group.stop()
                except Exception:
                    pass

            eff = QGraphicsOpacityEffect(self.card)
            eff.setOpacity(0.0)
            self.card.setGraphicsEffect(eff)
            self._card_opacity = eff

            self._fade_anim = QPropertyAnimation(self._card_opacity, b"opacity", self)
            self._fade_anim.setDuration(220)
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._slide_anim = QPropertyAnimation(self, b"pos", self)
            self._slide_anim.setDuration(220)
            self._slide_anim.setStartValue(QPoint(target_x, target_y + 12))
            self._slide_anim.setEndValue(QPoint(target_x, target_y))
            self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._anim_group = QParallelAnimationGroup(self)
            self._anim_group.addAnimation(self._fade_anim)
            self._anim_group.addAnimation(self._slide_anim)

            def _on_entrance_done():
                try:
                    self.card.setGraphicsEffect(None)
                except Exception:
                    pass

            self._anim_group.finished.connect(_on_entrance_done)
            self._anim_group.start()

    def animate_close(self, accepted=False):
        if getattr(self, "_is_closing", False):
            return
        self._is_closing = True

        if self._anim_group and self._anim_group.state() == QAbstractAnimation.State.Running:
            try:
                self._anim_group.stop()
            except Exception:
                pass

        cur_pos = self.pos()
        target_y = cur_pos.y() + 10

        current_op = 1.0
        if getattr(self, "_card_opacity", None) is not None:
            try:
                current_op = self._card_opacity.opacity()
            except Exception:
                current_op = 1.0

        eff = QGraphicsOpacityEffect(self.card)
        eff.setOpacity(current_op)
        self.card.setGraphicsEffect(eff)
        self._card_opacity = eff

        self._exit_fade = QPropertyAnimation(self._card_opacity, b"opacity", self)
        self._exit_fade.setDuration(160)
        self._exit_fade.setStartValue(current_op)
        self._exit_fade.setEndValue(0.0)
        self._exit_fade.setEasingCurve(QEasingCurve.Type.InQuad)

        self._exit_slide = QPropertyAnimation(self, b"pos", self)
        self._exit_slide.setDuration(160)
        self._exit_slide.setStartValue(cur_pos)
        self._exit_slide.setEndValue(QPoint(cur_pos.x(), target_y))
        self._exit_slide.setEasingCurve(QEasingCurve.Type.InQuad)

        self._exit_group = QParallelAnimationGroup(self)
        self._exit_group.addAnimation(self._exit_fade)
        self._exit_group.addAnimation(self._exit_slide)

        def on_exit_done():
            try:
                self.card.setGraphicsEffect(None)
            except Exception:
                pass
            if accepted:
                super(ZapretAlreadyInstalledDialog, self).accept()
            else:
                super(ZapretAlreadyInstalledDialog, self).reject()

        self._exit_group.finished.connect(on_exit_done)
        self._exit_group.start()

    def accept(self):
        self.animate_close(accepted=True)

    def reject(self):
        self.animate_close(accepted=False)


class ZapretDnsRestoreDialog(QDialog):
    """Zapret kaldırılırken DNS ve DoH ayarlarının sıfırlanmasını onaylayan modern modal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DNS Yapılandırması")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(520, 270)
        self.restore_dns = True
        self._is_closing = False
        self._anim_group = None
        self._exit_group = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.card = QFrame()
        self.card.setStyleSheet(
            "background-color: #0E1318; border: 1px solid #1E2835; border-radius: 12px;"
        )
        self._card_opacity = QGraphicsOpacityEffect(self.card)
        self._card_opacity.setOpacity(0.0)
        self.card.setGraphicsEffect(self._card_opacity)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(22, 20, 22, 18)
        card_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        title = QLabel("Zapret Kaldırılıyor: Ağ ve DNS Ayarları")
        title.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: bold; border: none;")
        header_row.addWidget(title)
        header_row.addStretch()
        card_layout.addLayout(header_row)

        desc = QLabel(
            "Cloudflare DoH (Şifreli DNS) ve DNS ayarları varsayılana (DHCP / Otomatik) döndürülsün mü?<br><br>"
            "<b>DNS'i Sıfırla (Önerilen):</b> Zapret'in kilitlediği DoH ve statik IP politikaları tamamen temizlenir, olası internet ve aktivasyon erişim sorunları önlenir.<br>"
            "<b>Mevcut Ayarları Koru:</b> Zapret kaldırılır ancak şifreli DNS yapılandırması olduğu gibi bırakılır."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #C9D3DC; font-size: 12px; line-height: 1.4; border: none;")
        card_layout.addWidget(desc)

        card_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        keep_btn = QPushButton("Mevcut Ayarları Koru")
        keep_btn.setFixedHeight(36)
        keep_btn.setFixedWidth(150)
        keep_btn.setStyleSheet(
            "QPushButton { background-color: #161D24; color: #8C9BA8; border: 1px solid #283340; "
            "border-radius: 6px; font-weight: 600; font-size: 12px; }\n"
            "QPushButton:hover { background-color: #202933; color: #FFFFFF; border-color: #3B4A5A; }"
        )
        keep_btn.clicked.connect(self._on_keep_clicked)
        btn_row.addWidget(keep_btn)

        restore_btn = QPushButton("DNS'i Sıfırla (Önerilen)")
        restore_btn.setFixedHeight(36)
        restore_btn.setFixedWidth(170)
        restore_btn.setStyleSheet(
            "QPushButton { background-color: #55D67A; color: #0E1318; border: 1px solid #55D67A; "
            "border-radius: 6px; font-weight: bold; font-size: 12px; }\n"
            "QPushButton:hover { background-color: #6CE88F; }"
        )
        restore_btn.clicked.connect(self._on_restore_clicked)
        btn_row.addWidget(restore_btn)

        card_layout.addLayout(btn_row)
        main_layout.addWidget(self.card)

    def _on_restore_clicked(self):
        self.restore_dns = True
        self.accept()

    def _on_keep_clicked(self):
        self.restore_dns = False
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self._is_closing = False
        if self.parent():
            p_geo = self.parent().geometry()
            target_x = p_geo.x() + (p_geo.width() - self.width()) // 2
            target_y = p_geo.y() + (p_geo.height() - self.height()) // 2
            self.move(target_x, target_y + 12)

            eff = QGraphicsOpacityEffect(self.card)
            eff.setOpacity(0.0)
            self.card.setGraphicsEffect(eff)
            self._card_opacity = eff

            self._fade_anim = QPropertyAnimation(self._card_opacity, b"opacity", self)
            self._fade_anim.setDuration(220)
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._slide_anim = QPropertyAnimation(self, b"pos", self)
            self._slide_anim.setDuration(220)
            self._slide_anim.setStartValue(QPoint(target_x, target_y + 12))
            self._slide_anim.setEndValue(QPoint(target_x, target_y))
            self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._anim_group = QParallelAnimationGroup(self)
            self._anim_group.addAnimation(self._fade_anim)
            self._anim_group.addAnimation(self._slide_anim)
            self._anim_group.start()

    def animate_close(self, accepted=False):
        if getattr(self, "_is_closing", False):
            return
        self._is_closing = True
        cur_pos = self.pos()
        target_y = cur_pos.y() + 10
        current_op = 1.0
        if getattr(self, "_card_opacity", None) is not None:
            try:
                current_op = self._card_opacity.opacity()
            except Exception:
                current_op = 1.0

        eff = QGraphicsOpacityEffect(self.card)
        eff.setOpacity(current_op)
        self.card.setGraphicsEffect(eff)
        self._card_opacity = eff

        self._exit_fade = QPropertyAnimation(self._card_opacity, b"opacity", self)
        self._exit_fade.setDuration(160)
        self._exit_fade.setStartValue(current_op)
        self._exit_fade.setEndValue(0.0)
        self._exit_fade.setEasingCurve(QEasingCurve.Type.InQuad)

        self._exit_slide = QPropertyAnimation(self, b"pos", self)
        self._exit_slide.setDuration(160)
        self._exit_slide.setStartValue(cur_pos)
        self._exit_slide.setEndValue(QPoint(cur_pos.x(), target_y))
        self._exit_slide.setEasingCurve(QEasingCurve.Type.InQuad)

        self._exit_group = QParallelAnimationGroup(self)
        self._exit_group.addAnimation(self._exit_fade)
        self._exit_group.addAnimation(self._exit_slide)

        def on_exit_done():
            try:
                self.card.setGraphicsEffect(None)
            except Exception:
                pass
            if accepted:
                super(ZapretDnsRestoreDialog, self).accept()
            else:
                super(ZapretDnsRestoreDialog, self).reject()

        self._exit_group.finished.connect(on_exit_done)
        self._exit_group.start()

    def accept(self):
        self.animate_close(accepted=True)

    def reject(self):
        self.animate_close(accepted=False)


class RestoreEnablePromptDialog(QDialog):
    """Sistem Geri Yükleme koruması kapalıyken etkinleştirme teklifi sunan modern modal."""

    def __init__(self, parent=None, drive: str = "C:"):
        super().__init__(parent)
        self.setWindowTitle("Sistem Geri Yükleme Koruması")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(520, 270)
        self.drive = drive
        self.action = "enable"  # "enable", "skip", "cancel"
        self._is_closing = False
        self._anim_group = None
        self._exit_group = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.card = QFrame()
        self.card.setStyleSheet(
            "background-color: #0E1318; border: 1px solid #FF8C42; border-radius: 12px;"
        )
        self._card_opacity = QGraphicsOpacityEffect(self.card)
        self._card_opacity.setOpacity(0.0)
        self.card.setGraphicsEffect(self._card_opacity)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(22, 20, 22, 18)
        card_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        title = QLabel("Sistem Geri Yükleme Koruması Kapalı")
        title.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: bold; border: none;")
        header_row.addWidget(title)
        header_row.addStretch()
        card_layout.addLayout(header_row)

        desc = QLabel(
            f"<b>{self.drive}</b> sürücünüzde Sistem Geri Yükleme koruması şu anda devre dışı.<br><br>"
            "Debloat ve sistem temizliği öncesinde geri alma noktası oluşturulabilmesi için korumanın etkinleştirilmesini ister misiniz?<br>"
            "Koruma etkinleştirilmezse olası bir terslik durumunda Windows Geri Yükleme kullanılamaz."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #C9D3DC; font-size: 12px; line-height: 1.4; border: none;")
        card_layout.addWidget(desc)

        card_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        cancel_btn = QPushButton("İptal")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setFixedWidth(80)
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #161D24; color: #8C9BA8; border: 1px solid #283340; "
            "border-radius: 6px; font-weight: 600; font-size: 12px; }\n"
            "QPushButton:hover { background-color: #202933; color: #FFFFFF; border-color: #3B4A5A; }"
        )
        cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(cancel_btn)

        skip_btn = QPushButton("Korumasız Devam Et")
        skip_btn.setFixedHeight(36)
        skip_btn.setFixedWidth(145)
        skip_btn.setStyleSheet(
            "QPushButton { background-color: #201D1A; color: #FFB86C; border: 1px solid #FF8C42; "
            "border-radius: 6px; font-weight: 600; font-size: 12px; }\n"
            "QPushButton:hover { background-color: #2D251E; color: #FFCC80; }"
        )
        skip_btn.clicked.connect(self._on_skip)
        btn_row.addWidget(skip_btn)

        enable_btn = QPushButton("Etkinleştir (Önerilen)")
        enable_btn.setFixedHeight(36)
        enable_btn.setFixedWidth(160)
        enable_btn.setStyleSheet(
            "QPushButton { background-color: #55D67A; color: #0E1318; border: 1px solid #55D67A; "
            "border-radius: 6px; font-weight: bold; font-size: 12px; }\n"
            "QPushButton:hover { background-color: #6CE88F; }"
        )
        enable_btn.clicked.connect(self._on_enable)
        btn_row.addWidget(enable_btn)

        card_layout.addLayout(btn_row)
        main_layout.addWidget(self.card)

    def _on_enable(self):
        self.action = "enable"
        self.accept()

    def _on_skip(self):
        self.action = "skip"
        self.accept()

    def _on_cancel(self):
        self.action = "cancel"
        self.reject()

    def showEvent(self, event):
        super().showEvent(event)
        self._is_closing = False
        if self.parent():
            p_geo = self.parent().geometry()
            target_x = p_geo.x() + (p_geo.width() - self.width()) // 2
            target_y = p_geo.y() + (p_geo.height() - self.height()) // 2
            self.move(target_x, target_y + 12)

            eff = QGraphicsOpacityEffect(self.card)
            eff.setOpacity(0.0)
            self.card.setGraphicsEffect(eff)
            self._card_opacity = eff

            self._fade_anim = QPropertyAnimation(self._card_opacity, b"opacity", self)
            self._fade_anim.setDuration(220)
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._slide_anim = QPropertyAnimation(self, b"pos", self)
            self._slide_anim.setDuration(220)
            self._slide_anim.setStartValue(QPoint(target_x, target_y + 12))
            self._slide_anim.setEndValue(QPoint(target_x, target_y))
            self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._anim_group = QParallelAnimationGroup(self)
            self._anim_group.addAnimation(self._fade_anim)
            self._anim_group.addAnimation(self._slide_anim)
            self._anim_group.start()

    def animate_close(self, accepted=False):
        if getattr(self, "_is_closing", False):
            return
        self._is_closing = True
        cur_pos = self.pos()
        target_y = cur_pos.y() + 10
        current_op = 1.0
        if getattr(self, "_card_opacity", None) is not None:
            try:
                current_op = self._card_opacity.opacity()
            except Exception:
                current_op = 1.0

        eff = QGraphicsOpacityEffect(self.card)
        eff.setOpacity(current_op)
        self.card.setGraphicsEffect(eff)
        self._card_opacity = eff

        self._exit_fade = QPropertyAnimation(self._card_opacity, b"opacity", self)
        self._exit_fade.setDuration(160)
        self._exit_fade.setStartValue(current_op)
        self._exit_fade.setEndValue(0.0)
        self._exit_fade.setEasingCurve(QEasingCurve.Type.InQuad)

        self._exit_slide = QPropertyAnimation(self, b"pos", self)
        self._exit_slide.setDuration(160)
        self._exit_slide.setStartValue(cur_pos)
        self._exit_slide.setEndValue(QPoint(cur_pos.x(), target_y))
        self._exit_slide.setEasingCurve(QEasingCurve.Type.InQuad)

        self._exit_group = QParallelAnimationGroup(self)
        self._exit_group.addAnimation(self._exit_fade)
        self._exit_group.addAnimation(self._exit_slide)

        def on_exit_done():
            try:
                self.card.setGraphicsEffect(None)
            except Exception:
                pass
            if accepted:
                super(RestoreEnablePromptDialog, self).accept()
            else:
                super(RestoreEnablePromptDialog, self).reject()

        self._exit_group.finished.connect(on_exit_done)
        self._exit_group.start()

    def accept(self):
        self.animate_close(accepted=True)

    def reject(self):
        self.animate_close(accepted=False)



class KeyRemapDialog(QDialog):
    """Yeni tuş eşleştirmesi eklemek ve düzenlemek için çift kaynak tuşlu modern modal."""

    def __init__(self, parent=None, initial_source=None, initial_target=None, is_edit=False):
        super().__init__(parent)
        self.is_edit = is_edit
        self.setWindowTitle("Tuş Eşleştirmesini Düzenle" if is_edit else "Yeni Tuş Eşleştirmesi")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(620, 410)
        self._is_closing = False
        self._anim_group = None
        self._exit_group = None
        self.listening_key = False
        self._held_modifier = None

        if initial_source == 0xF001:
            self.selected_source1_code = 0xE05B
            self.selected_source2_code = 0x0039
            self.selected_target_code = initial_target if initial_target is not None else 0x0000
        else:
            self.selected_source1_code = initial_source if initial_source is not None else 0xE01D
            self.selected_source2_code = 0x0000
            self.selected_target_code = initial_target if initial_target is not None else 0x006B

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.card = QFrame()
        self.card.setObjectName("KeyRemapCard")
        self.card.setStyleSheet(
            "#KeyRemapCard { background-color: #0E1318; border: 1px solid #FF334B; border-radius: 12px; }"
        )
        self._card_opacity = QGraphicsOpacityEffect(self.card)
        self._card_opacity.setOpacity(0.0)
        self.card.setGraphicsEffect(self._card_opacity)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 22, 24, 20)
        card_layout.setSpacing(12)

        title = QLabel("Tuş Eşleştirmesini Düzenle" if is_edit else "Yeni Tuş Eşleştirmesi")
        title.setStyleSheet("color: #FFFFFF; font-size: 17px; font-weight: bold; border: none;")
        card_layout.addWidget(title)

        desc = QLabel(
            "Klavyenizden bir tuşa veya kısayola basarak otomatik algılayabilir ya da "
            "aşağıdaki açılır kutulardan kaynak ve hedef tuşları seçebilirsiniz."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8C9BA8; font-size: 11.5px; border: none; line-height: 1.4;")
        card_layout.addWidget(desc)

        self.btn_capture = QPushButton("Klavyeden Bir Tuşa / Kısayola Basın (Otomatik Algıla)")
        self.btn_capture.setFixedHeight(40)
        self.btn_capture.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_capture_btn_style(active=False)
        self.btn_capture.clicked.connect(self._toggle_listening)
        card_layout.addWidget(self.btn_capture)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(8)

        # Kaynak Tuş 1
        src1_col = QVBoxLayout()
        src1_col.setSpacing(4)
        lbl_src1 = QLabel("Kaynak Tuş 1:")
        lbl_src1.setStyleSheet("color: #C2CCD6; font-size: 11px; font-weight: 600; border: none;")
        self.combo_source1 = SleekComboBox()
        src1_col.addWidget(lbl_src1)
        src1_col.addWidget(self.combo_source1)
        form_layout.addLayout(src1_col, 5)

        # + İşareti
        plus_lbl = QLabel("+")
        plus_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus_lbl.setStyleSheet("color: #8C9BA8; font-size: 16px; font-weight: bold; border: none; padding-top: 14px;")
        form_layout.addWidget(plus_lbl)

        # Kaynak Tuş 2
        src2_col = QVBoxLayout()
        src2_col.setSpacing(4)
        lbl_src2 = QLabel("Kaynak Tuş 2:")
        lbl_src2.setStyleSheet("color: #C2CCD6; font-size: 11px; font-weight: 600; border: none;")
        self.combo_source2 = SleekComboBox()
        src2_col.addWidget(lbl_src2)
        src2_col.addWidget(self.combo_source2)
        form_layout.addLayout(src2_col, 5)

        # → Oku
        arrow_lbl = QLabel("→")
        arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow_lbl.setStyleSheet("color: #FF334B; font-size: 20px; font-weight: bold; border: none; padding-top: 14px;")
        form_layout.addWidget(arrow_lbl)

        # Hedef Tuş
        tgt_col = QVBoxLayout()
        tgt_col.setSpacing(4)
        lbl_tgt = QLabel("Hedef Tuş:")
        lbl_tgt.setStyleSheet("color: #C2CCD6; font-size: 11px; font-weight: 600; border: none;")
        self.combo_target = SleekComboBox()
        tgt_col.addWidget(lbl_tgt)
        tgt_col.addWidget(self.combo_target)
        form_layout.addLayout(tgt_col, 5)

        card_layout.addLayout(form_layout)

        # Combo içeriklerini doldur
        self.combo_source2.addItem("(Yok / Tek Tuş)", 0x0000)
        for name, code, _ in SCANCODE_DATABASE:
            self.combo_source1.addItem(name, code)
            self.combo_source2.addItem(name, code)
            self.combo_target.addItem(name, code)

        self._select_combo_by_code(self.combo_source1, self.selected_source1_code)
        self._select_combo_by_code(self.combo_source2, self.selected_source2_code)
        self._select_combo_by_code(self.combo_target, self.selected_target_code)

        self._update_source2_state()

        self.combo_source1.currentIndexChanged.connect(self._on_source1_combo_changed)
        self.combo_source2.currentIndexChanged.connect(self._on_source2_combo_changed)
        self.combo_target.currentIndexChanged.connect(self._on_target_combo_changed)

        card_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        cancel_btn = QPushButton("İptal")
        cancel_btn.setFixedSize(100, 36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #161D24; color: #8C9BA8; border: 1px solid #283340; "
            "border-radius: 6px; font-weight: 600; font-size: 12px; outline: none; }\n"
            "QPushButton:hover { background-color: #202933; color: #FFFFFF; border-color: #3B4A5A; }\n"
            "QPushButton:pressed { background-color: #1A232E; }"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        add_btn = QPushButton("Değişiklikleri Kaydet" if is_edit else "Eşleştirmeyi Ekle")
        add_btn.setFixedSize(150, 36)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            "QPushButton { background-color: #FF334B; color: #FFFFFF; border: 1px solid #FF5263; "
            "border-radius: 6px; font-weight: bold; font-size: 12px; outline: none; }\n"
            "QPushButton:hover { background-color: #FF4D61; }\n"
            "QPushButton:pressed { background-color: #E62E44; }"
        )
        add_btn.clicked.connect(self.accept)
        btn_row.addWidget(add_btn)

        card_layout.addLayout(btn_row)
        main_layout.addWidget(self.card)

    def _update_source2_state(self):
        # Yalnızca Değiştirici tuşlar (Win, Ctrl, Alt, Shift) seçildiğinde ikinci tuş kombinasyonu aktif olsun
        is_mod = self.selected_source1_code in (0xE05B, 0xE05C, 0x001D, 0xE01D, 0x0038, 0xE038, 0x002A, 0x0036)
        self.combo_source2.setEnabled(is_mod)
        if not is_mod:
            self.selected_source2_code = 0x0000
            self._select_combo_by_code(self.combo_source2, 0x0000)

    def _select_combo_by_code(self, combo, code):
        for i in range(combo.count()):
            if combo.itemData(i) == code:
                combo.setCurrentIndex(i)
                break

    def _on_source1_combo_changed(self, idx):
        self.selected_source1_code = self.combo_source1.itemData(idx)
        self._update_source2_state()

    def _on_source2_combo_changed(self, idx):
        self.selected_source2_code = self.combo_source2.itemData(idx)

    def _on_target_combo_changed(self, idx):
        self.selected_target_code = self.combo_target.itemData(idx)

    def _update_capture_btn_style(self, active=False):
        if active:
            self.btn_capture.setText("Tuş / Kısayol Bekleniyor... (Klavyenizden tuşa veya kısayola basın)")
            self.btn_capture.setStyleSheet(
                "QPushButton { background-color: #35161D; color: #FF7784; border: 1px solid #FF334B; "
                "border-radius: 8px; font-size: 12px; font-weight: bold; padding: 4px 10px; outline: none; }"
            )
        else:
            self.btn_capture.setText("Klavyeden Bir Tuşa / Kısayola Basın (Otomatik Algıla)")
            self.btn_capture.setStyleSheet(
                "QPushButton { background-color: #121820; color: #E2E8F0; border: 1px solid #283340; "
                "border-radius: 8px; font-size: 12px; font-weight: 600; padding: 4px 10px; outline: none; }\n"
                "QPushButton:hover { background-color: #1E1217; color: #FFFFFF; border-color: #FF334B; }\n"
                "QPushButton:pressed { background-color: #2D1418; }"
            )

    def _toggle_listening(self):
        self.listening_key = not self.listening_key
        self._held_modifier = None
        self._update_capture_btn_style(self.listening_key)
        if self.listening_key:
            self.setFocus()

    def keyPressEvent(self, event):
        if self.listening_key:
            scancode = 0
            native_scan = event.nativeScanCode()
            key = event.key()

            is_modifier = False
            if key in (Qt.Key.Key_Meta, Qt.Key.Key_Super_L, Qt.Key.Key_Super_R):
                scancode = 0xE05B
                is_modifier = True
            elif key == Qt.Key.Key_Control:
                if event.nativeModifiers() & 0x1 or native_scan == 0x1D and (event.nativeVirtualKey() == 0xA3 or event.nativeScanCode() > 0xFF):
                    scancode = 0xE01D
                else:
                    scancode = 0x001D
                is_modifier = True
            elif key == Qt.Key.Key_Alt:
                if event.nativeModifiers() & 0x1 or native_scan == 0x38 and event.nativeVirtualKey() == 0xA5:
                    scancode = 0xE038
                else:
                    scancode = 0x0038
                is_modifier = True
            elif key == Qt.Key.Key_Shift:
                is_rshift = False
                try:
                    is_rshift = bool(ctypes.windll.user32.GetAsyncKeyState(0xA1) & 0x8000) or (native_scan & 0xFF) == 0x36
                except Exception:
                    is_rshift = (native_scan & 0xFF) == 0x36
                scancode = 0x0036 if is_rshift else 0x002A
                is_modifier = True
            elif key in QT_KEY_TO_SCANCODE:
                scancode = QT_KEY_TO_SCANCODE[key]
            elif native_scan:
                scancode = native_scan

            # Fiziksel donanım tuş durumunu anlık Win32 API ile oku (eşzamanlı basış tespiti)
            phys_win = False
            phys_ctrl = False
            phys_alt = False
            phys_shift = False
            try:
                phys_win = bool((ctypes.windll.user32.GetAsyncKeyState(0x5B) & 0x8000) or (ctypes.windll.user32.GetAsyncKeyState(0x5C) & 0x8000))
                phys_ctrl = bool(ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000)
                phys_alt = bool(ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000)
                phys_shift = bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)
            except Exception:
                pass

            modifiers = event.modifiers()
            has_win = bool(modifiers & Qt.KeyboardModifier.MetaModifier) or phys_win
            has_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier) or phys_ctrl
            has_alt = bool(modifiers & Qt.KeyboardModifier.AltModifier) or phys_alt
            has_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier) or phys_shift

            if scancode:
                # Eşzamanlı veya sıralı çift tuş kombinasyon kontrolü (Win + Space, Ctrl + Shift vb.)
                if is_modifier:
                    if self._held_modifier and self._held_modifier != scancode:
                        # İki farklı niteleyici tuşa aynı anda basıldı (örn: Ctrl + Shift)
                        self.selected_source1_code = self._held_modifier
                        self.selected_source2_code = scancode
                        self._select_combo_by_code(self.combo_source1, self._held_modifier)
                        self._select_combo_by_code(self.combo_source2, scancode)
                        self.listening_key = False
                        self._held_modifier = None
                        self._update_capture_btn_style(active=False)
                        event.accept()
                        return
                    self._held_modifier = scancode
                    self.selected_source1_code = scancode
                    self.selected_source2_code = 0x0000
                    self._select_combo_by_code(self.combo_source1, scancode)
                    self._select_combo_by_code(self.combo_source2, 0x0000)
                else:
                    if self._held_modifier or has_win or has_ctrl or has_alt or has_shift:
                        mod_code = self._held_modifier
                        if not mod_code:
                            if has_win: mod_code = 0xE05B
                            elif has_ctrl: mod_code = 0x001D
                            elif has_alt: mod_code = 0x0038
                            elif has_shift: mod_code = 0x002A
                        self.selected_source1_code = mod_code
                        self.selected_source2_code = scancode
                        self._select_combo_by_code(self.combo_source1, mod_code)
                        self._select_combo_by_code(self.combo_source2, scancode)
                    else:
                        self.selected_source1_code = scancode
                        self.selected_source2_code = 0x0000
                        self._select_combo_by_code(self.combo_source1, scancode)
                        self._select_combo_by_code(self.combo_source2, 0x0000)
                    self.listening_key = False
                    self._held_modifier = None
                    self._update_capture_btn_style(active=False)
                event.accept()
                return

        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def get_mapping(self):
        # Eğer Windows + Space eşleşmesi ise sanal 0xF001 kodu döndür
        if self.selected_source1_code in (0xE05B, 0xE05C) and self.selected_source2_code == 0x0039:
            return (0xF001, self.selected_target_code)
        return (self.selected_source1_code, self.selected_target_code)



    def showEvent(self, event):
        super().showEvent(event)
        self._is_closing = False
        if self.parent():
            p_geo = self.parent().geometry()
            target_x = p_geo.x() + (p_geo.width() - self.width()) // 2
            target_y = p_geo.y() + (p_geo.height() - self.height()) // 2
            self.move(target_x, target_y + 12)

            eff = QGraphicsOpacityEffect(self.card)
            eff.setOpacity(0.0)
            self.card.setGraphicsEffect(eff)
            self._card_opacity = eff

            self._fade_anim = QPropertyAnimation(self._card_opacity, b"opacity", self)
            self._fade_anim.setDuration(220)
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._slide_anim = QPropertyAnimation(self, b"pos", self)
            self._slide_anim.setDuration(220)
            self._slide_anim.setStartValue(QPoint(target_x, target_y + 12))
            self._slide_anim.setEndValue(QPoint(target_x, target_y))
            self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._anim_group = QParallelAnimationGroup(self)
            self._anim_group.addAnimation(self._fade_anim)
            self._anim_group.addAnimation(self._slide_anim)
            self._anim_group.start()

    def animate_close(self, accepted=False):
        if self._is_closing:
            return
        self._is_closing = True

        if self._anim_group and self._anim_group.state() == QAbstractAnimation.State.Running:
            try:
                self._anim_group.stop()
            except Exception:
                pass

        cur_pos = self.pos()
        target_y = cur_pos.y() + 10
        current_op = 1.0
        if self._card_opacity:
            try:
                current_op = self._card_opacity.opacity()
            except Exception:
                current_op = 1.0

        eff = QGraphicsOpacityEffect(self.card)
        eff.setOpacity(current_op)
        self.card.setGraphicsEffect(eff)
        self._card_opacity = eff

        self._exit_fade = QPropertyAnimation(self._card_opacity, b"opacity", self)
        self._exit_fade.setDuration(160)
        self._exit_fade.setStartValue(current_op)
        self._exit_fade.setEndValue(0.0)
        self._exit_fade.setEasingCurve(QEasingCurve.Type.InQuad)

        self._exit_slide = QPropertyAnimation(self, b"pos", self)
        self._exit_slide.setDuration(160)
        self._exit_slide.setStartValue(cur_pos)
        self._exit_slide.setEndValue(QPoint(cur_pos.x(), target_y))
        self._exit_slide.setEasingCurve(QEasingCurve.Type.InQuad)

        self._exit_group = QParallelAnimationGroup(self)
        self._exit_group.addAnimation(self._exit_fade)
        self._exit_group.addAnimation(self._exit_slide)

        def on_exit_done():
            try:
                self.card.setGraphicsEffect(None)
            except Exception:
                pass
            if accepted:
                super(KeyRemapDialog, self).accept()
            else:
                super(KeyRemapDialog, self).reject()

        self._exit_group.finished.connect(on_exit_done)
        self._exit_group.start()

    def accept(self):
        self.animate_close(accepted=True)

    def reject(self):
        self.animate_close(accepted=False)




class RestoreOverlay(QWidget):
    """Ana uygulamanın üstüne yerleşen, yarı saydam arka planlı ve kusursuz ortalanan geri yükleme popup'ı."""
    def __init__(self, parent=None, task_type=None, cancel_on_close=False):
        super().__init__(parent)
        self.parent_window = parent
        self.task_type = task_type
        self.cancel_on_close = cancel_on_close
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._anim_in_progress = False

        if parent:
            self.resize(parent.size())

        # Bloker (yarı saydam siyah)
        self.blocker = QFrame(self)
        self.blocker.setGeometry(0, 0, self.width(), self.height())
        self.blocker.setStyleSheet("background-color: rgba(5, 3, 11, 200);")

        # Popup çerçevesi
        self.popup_frame = QFrame(self)
        popup_w, popup_h = 700, 450
        px = max(0, (self.width() - popup_w) // 2)
        py = max(0, (self.height() - popup_h) // 2)
        self.popup_frame.setGeometry(px, py, popup_w, popup_h)
        self.popup_frame.setStyleSheet(
            "background-color: #1E1B26; border-radius: 12px; "
            "border: 2px solid #E63B4D;"
        )

        # Opacity effect for animation
        self.opacity_effect = QGraphicsOpacityEffect(self.popup_frame)
        self.popup_frame.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        # Başlık
        self.title_label = QLabel("Sistem geri yükleme noktası", self.popup_frame)
        self.title_label.setStyleSheet("color: #E63B4D; font-size: 20px; font-weight: bold; border: none; background: transparent;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setGeometry(50, 45, 600, 32)

        # Soru İçerik Konteyneri (Fade-out için)
        self.question_container = QWidget(self.popup_frame)
        self.question_container.setGeometry(0, 85, popup_w, 345)
        self.question_container.setStyleSheet("background: transparent; border: none;")
        self.question_opacity = None

        desc_text = (
            "Seçtiğiniz optimizasyon ve debloat ayarlarını uygulamadan önce\n"
            "sisteminizin bir yedeğini (Geri Yükleme Noktası) oluşturmak ister misiniz?\n\n"
            "Bu yedekleme; olası bir kararsızlık durumunda sisteminizi tek tıkla\n"
            "eski haline döndürmenizi sağlayacaktır."
        )
        self.desc_label = QLabel(desc_text, self.question_container)
        self.desc_label.setStyleSheet("color: #F0F0F0; font-size: 13px; border: none; background: transparent;")
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_label.setGeometry(50, 25, 600, 90)

        btn_w = 320
        btn_x = (popup_w - btn_w) // 2
        self.yes_btn = QPushButton("Evet, yedek oluştur ve başlat", self.question_container)
        self.yes_btn.setStyleSheet(
            "QPushButton { background-color: #121019; border: 1.5px solid #E63B4D; color: #FF6574; "
            "font-weight: bold; border-radius: 8px; font-size: 13px; }\n"
            "QPushButton:hover { background-color: #E63B4D; color: #FFFFFF; border-color: #FF5263; }\n"
            "QPushButton:pressed { background-color: #C02637; }"
        )
        self.yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.yes_btn.setGeometry(btn_x, 165, btn_w, 45)
        self.yes_btn.clicked.connect(self.on_accept)

        self.no_btn = QPushButton("Hayır, yedek almadan başlat", self.question_container)
        self.no_btn.setStyleSheet(
            "QPushButton { background-color: #16151F; border: 1px solid #32263F; color: #C9D0D7; "
            "font-weight: bold; border-radius: 8px; font-size: 13px; }\n"
            "QPushButton:hover { background-color: #261F33; border-color: #4D3866; color: #FFFFFF; }\n"
            "QPushButton:pressed { background-color: #13101C; }"
        )
        self.no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.no_btn.setGeometry(btn_x, 230, btn_w, 45)
        self.no_btn.clicked.connect(self.on_reject)

        # İlerleme Konteyneri (Fade-in için)
        self.progress_container = QWidget(self.popup_frame)
        self.progress_container.setGeometry(0, 95, popup_w, 325)
        self.progress_container.setStyleSheet("background: transparent; border: none;")
        self.progress_opacity = None
        self.progress_container.hide()

        self.progress_status = QLabel("Sistem yapılandırması yedekleniyor...", self.progress_container)
        self.progress_status.setStyleSheet("color: #E6EDF3; font-size: 14px; font-weight: 600; border: none; background: transparent;")
        self.progress_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_status.setGeometry(50, 20, 600, 28)

        self.progress_subtext = QLabel("Bu işlem 10-30 saniye sürebilir, lütfen bekleyin.", self.progress_container)
        self.progress_subtext.setStyleSheet("color: #7D8B99; font-size: 12px; border: none; background: transparent;")
        self.progress_subtext.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_subtext.setGeometry(50, 52, 600, 22)

        self.progress_percent_label = QLabel("0%", self.progress_container)
        self.progress_percent_label.setStyleSheet(
            "color: #E63B4D; font-size: 38px; font-weight: bold; border: none; "
            "background: transparent; font-family: 'Segoe UI', Consolas, sans-serif;"
        )
        self.progress_percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_percent_label.setGeometry(50, 88, 600, 55)

        self.progress_bar = QProgressBar(self.progress_container)
        self.progress_bar.setGeometry(100, 160, 500, 10)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: #121019; border: 1px solid #2B1E2E; border-radius: 5px; }\n"
            "QProgressBar::chunk { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5263, stop:1 #E63B4D); border-radius: 4px; }"
        )

        # Kapatma düğmesi
        self.close_btn = OverlayCloseButton(self.popup_frame)
        self.close_btn.setGeometry(popup_w - 42, 12, 30, 30)
        self.close_btn.clicked.connect(self.on_close)

        self.current_progress = 0.0
        self.progress_timer = None
        self.completion_timer = None
        self._entrance_anim = None

    def _recenter_popup(self):
        if self.parent_window:
            pw = self.parent_window.width() if callable(getattr(self.parent_window, "width", None)) else getattr(self.parent_window, "width", 1040)
            ph = self.parent_window.height() if callable(getattr(self.parent_window, "height", None)) else getattr(self.parent_window, "height", 720)
            self.setGeometry(0, 0, pw, ph)
        self.blocker.setGeometry(0, 0, self.width(), self.height())
        popup_w, popup_h = 700, 450
        px = max(0, (self.width() - popup_w) // 2)
        py = max(0, (self.height() - popup_h) // 2)
        if not self._anim_in_progress:
            self.popup_frame.setGeometry(px, py, popup_w, popup_h)

    def showEvent(self, event):
        super().showEvent(event)
        self._recenter_popup()
        self._start_entrance_animation()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recenter_popup()

    def eventFilter(self, watched, event):
        if watched == self.parent_window and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._recenter_popup()
        return super().eventFilter(watched, event)

    def _start_entrance_animation(self):
        self._anim_in_progress = True
        popup_w, popup_h = 700, 450
        px = max(0, (self.width() - popup_w) // 2)
        py = max(0, (self.height() - popup_h) // 2)

        self.popup_frame.setGeometry(px, py + 18, popup_w, popup_h)
        if not self.popup_frame.graphicsEffect():
            self.opacity_effect = QGraphicsOpacityEffect(self.popup_frame)
            self.popup_frame.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        pos_anim = QPropertyAnimation(self.popup_frame, b"pos")
        pos_anim.setDuration(240)
        pos_anim.setStartValue(QPoint(px, py + 18))
        pos_anim.setEndValue(QPoint(px, py))
        pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        fade_anim.setDuration(240)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(pos_anim)
        group.addAnimation(fade_anim)

        def _on_entrance_done():
            self._anim_in_progress = False
            self.popup_frame.setGraphicsEffect(None)

        group.finished.connect(_on_entrance_done)
        self._entrance_anim = group
        group.start()

    def _animate_hide(self, callback):
        """Pop-up'ı akıcı biçimde saydamlaştırıp aşağı süzerek kapatır, sonra callback çağrılır."""
        self._anim_in_progress = True
        try:
            self.question_container.setGraphicsEffect(None)
            self.progress_container.setGraphicsEffect(None)
        except Exception:
            pass
        fresh_effect = QGraphicsOpacityEffect(self.popup_frame)
        self.popup_frame.setGraphicsEffect(fresh_effect)
        fresh_effect.setOpacity(1.0)

        px = self.popup_frame.x()
        py = self.popup_frame.y()

        pos_anim = QPropertyAnimation(self.popup_frame, b"pos")
        pos_anim.setDuration(180)
        pos_anim.setStartValue(QPoint(px, py))
        pos_anim.setEndValue(QPoint(px, py + 14))
        pos_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        fade_anim = QPropertyAnimation(fresh_effect, b"opacity")
        fade_anim.setDuration(180)
        fade_anim.setStartValue(1.0)
        fade_anim.setEndValue(0.0)
        fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(pos_anim)
        group.addAnimation(fade_anim)

        def _on_done():
            self._anim_in_progress = False
            callback()

        group.finished.connect(_on_done)
        self._exit_anim = group
        group.start()

    def on_accept(self):
        self.close_btn.setEnabled(False)
        self.close_btn.hide()

        # Soru bileşenlerini yukarı hafif süzerek fade-out yap
        q_effect = QGraphicsOpacityEffect(self.question_container)
        self.question_container.setGraphicsEffect(q_effect)
        q_effect.setOpacity(1.0)

        pos_out = QPropertyAnimation(self.question_container, b"pos")
        pos_out.setDuration(150)
        pos_out.setStartValue(self.question_container.pos())
        pos_out.setEndValue(QPoint(self.question_container.x(), self.question_container.y() - 10))
        pos_out.setEasingCurve(QEasingCurve.Type.InQuad)

        fade_out = QPropertyAnimation(q_effect, b"opacity")
        fade_out.setDuration(150)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InQuad)

        q_group = QParallelAnimationGroup(self)
        q_group.addAnimation(pos_out)
        q_group.addAnimation(fade_out)

        def _on_question_faded():
            self.question_container.hide()
            self.question_container.setGraphicsEffect(None)
            self.title_label.setText("Geri Yükleme Noktası Oluşturuluyor")

            p_effect = QGraphicsOpacityEffect(self.progress_container)
            self.progress_container.setGraphicsEffect(p_effect)
            p_effect.setOpacity(0.0)
            self.progress_container.move(0, 105)
            self.progress_container.show()

            pos_in = QPropertyAnimation(self.progress_container, b"pos")
            pos_in.setDuration(180)
            pos_in.setStartValue(QPoint(0, 105))
            pos_in.setEndValue(QPoint(0, 95))
            pos_in.setEasingCurve(QEasingCurve.Type.OutCubic)

            fade_in = QPropertyAnimation(p_effect, b"opacity")
            fade_in.setDuration(180)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

            p_group = QParallelAnimationGroup(self)
            p_group.addAnimation(pos_in)
            p_group.addAnimation(fade_in)

            def _on_prog_in_done():
                self.progress_container.setGraphicsEffect(None)

            p_group.finished.connect(_on_prog_in_done)
            p_group.start()
            self._prog_fade_anim = p_group

            self.current_progress = 0.0
            self.progress_timer = QTimer(self)
            self.progress_timer.setInterval(45)
            self.progress_timer.timeout.connect(self._step_progress)
            self.progress_timer.start()

            self.parent_window.run_restore_and_task(self)

        q_group.finished.connect(_on_question_faded)
        q_group.start()
        self._q_fade_anim = q_group


    def _step_progress(self):
        if self.current_progress < 88.0:
            increment = max(0.12, (88.0 - self.current_progress) * 0.032)
            self.current_progress = min(88.0, self.current_progress + increment)
            val = int(self.current_progress)
            self.progress_bar.setValue(val)
            self.progress_percent_label.setText(f"{val}%")

    def complete_restore(self):
        if self.progress_timer and self.progress_timer.isActive():
            self.progress_timer.stop()

        self.completion_timer = QTimer(self)
        self.completion_timer.setInterval(18)

        def _step_to_100():
            self.current_progress += 2.5
            if self.current_progress >= 100.0:
                self.current_progress = 100.0
                self.completion_timer.stop()
                self.progress_bar.setValue(100)
                self.progress_percent_label.setText("100%")
                self.title_label.setText("Geri Yükleme Noktası Oluşturuldu")
                self.progress_status.setText("Sistem yapılandırması başarıyla yedeklendi.")
                self.progress_subtext.setText("İşlem başlatılıyor...")
                QTimer.singleShot(350, lambda: self._animate_hide(self._finish_and_proceed))
            else:
                val = int(self.current_progress)
                self.progress_bar.setValue(val)
                self.progress_percent_label.setText(f"{val}%")

        self.completion_timer.timeout.connect(_step_to_100)
        self.completion_timer.start()

    def fail_restore(self, err_msg=""):
        if self.progress_timer and self.progress_timer.isActive():
            self.progress_timer.stop()
        if hasattr(self, "completion_timer") and self.completion_timer and self.completion_timer.isActive():
            self.completion_timer.stop()

        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #FF6B6B; border-radius: 3px; }")
        self.progress_percent_label.setText("!")
        self.progress_percent_label.setStyleSheet("color: #FF6B6B; font-weight: bold;")
        self.title_label.setText("Geri Yükleme Noktası Alınamadı")
        self.progress_status.setText("Sistem koruması etkinleştirilemedi veya hata oluştu.")
        clean_err = (err_msg or "Bilinmeyen hata").strip().replace("\r", " ").replace("\n", " ")
        self.progress_subtext.setText(f"{clean_err[:80]} (İşlem devam ediyor...)")
        QTimer.singleShot(2200, lambda: self._animate_hide(self._finish_and_proceed))

    def _finish_and_proceed(self):
        self.parent_window.close_popup_and_start_task(self)

    def on_reject(self):
        self._animate_hide(self._perform_reject)

    def _perform_reject(self):
        self.parent_window.skip_restore_and_task(self)

    def on_close(self):
        """Sadece popup'ı kapatır, işlem başlatmaz."""
        self._animate_hide(self._perform_close)

    def _perform_close(self):
        self.parent_window.cancel_restore_overlay(self)

    def start_restore_label_update(self):
        pass


class WindowsUpdateOptionsDialog(QDialog):
    """
    Windows Update yapılandırması için animasyonlu, çift seçenekli modern modal.
    - 2100 yılına kadar dondurma
    - Otomatik güncellemeleri kapatıp .NET / FOD indirmelerine izin verme
    """

    def __init__(self, current_mode="disable_auto_allow_features", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Windows Update Yapılandırması")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(540, 310)
        self.selected_mode = current_mode if current_mode in ("pause_2100", "disable_auto_allow_features") else "disable_auto_allow_features"
        self._is_closing = False
        self._anim_group = None
        self._exit_group = None
        self._mode_anim = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.card = QFrame()
        self.card.setStyleSheet(
            "background-color: #0E1318; border: 1px solid #1E2836; border-radius: 12px;"
        )
        self._card_opacity = QGraphicsOpacityEffect(self.card)
        self._card_opacity.setOpacity(0.0)
        self.card.setGraphicsEffect(self._card_opacity)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(22, 20, 22, 18)
        card_layout.setSpacing(12)

        # Başlık Satırı
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon_lbl = QLabel()
        logo_path = None
        if parent is not None and hasattr(parent, "get_binary_path"):
            logo_path = parent.get_binary_path("winkit_logo.png")
        pix = QPixmap(logo_path or "")
        if not pix.isNull():
            icon_lbl.setPixmap(
                pix.scaled(
                    28,
                    28,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Windows Update Yapılandırması")
        title.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: bold; border: none;")
        subtitle = QLabel("Güncelleştirme davranışını ve bileşen indirmelerini yönetin.")
        subtitle.setStyleSheet("color: #8C9BA8; font-size: 11px; border: none;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_row.addLayout(title_col)
        header_row.addStretch()

        btn_close_x = QPushButton("✕")
        btn_close_x.setFixedSize(26, 26)
        btn_close_x.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close_x.setStyleSheet(
            "QPushButton { background: transparent; color: #8C9BA8; font-size: 13px; font-weight: bold; border: none; border-radius: 13px; }\n"
            "QPushButton:hover { background-color: #24303D; color: #FFFFFF; }"
        )
        btn_close_x.clicked.connect(lambda: self.animate_close(accepted=False))
        header_row.addWidget(btn_close_x)

        card_layout.addLayout(header_row)

        # Seçenek 1: 2100'e kadar duraklat
        self.opt1_card = QFrame()
        self.opt1_card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.opt1_card.setFixedHeight(68)
        opt1_layout = QHBoxLayout(self.opt1_card)
        opt1_layout.setContentsMargins(14, 8, 14, 8)
        opt1_layout.setSpacing(12)

        self.opt1_radio = QLabel("●" if self.selected_mode == "pause_2100" else "○")
        self.opt1_radio.setStyleSheet("color: #00E5FF; font-size: 18px; border: none; background: transparent;")
        self.opt1_radio.setFixedWidth(22)
        opt1_layout.addWidget(self.opt1_radio)

        opt1_text_col = QVBoxLayout()
        opt1_text_col.setSpacing(2)
        self.opt1_title = QLabel("2100 Yılına Kadar Güncelleştirmeleri Duraklat")
        self.opt1_title.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        self.opt1_desc = QLabel("Windows Update tamamen dondurulur; hiçbir güncelleme denetlenmez ve indirilmez.")
        self.opt1_desc.setStyleSheet("color: #8C9BA8; font-size: 10px; border: none; background: transparent;")
        opt1_text_col.addWidget(self.opt1_title)
        opt1_text_col.addWidget(self.opt1_desc)
        opt1_layout.addLayout(opt1_text_col, 1)

        card_layout.addWidget(self.opt1_card)

        # Seçenek 2: Otomatik güncelleştirmeleri kapat
        self.opt2_card = QFrame()
        self.opt2_card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.opt2_card.setFixedHeight(68)
        opt2_layout = QHBoxLayout(self.opt2_card)
        opt2_layout.setContentsMargins(14, 8, 14, 8)
        opt2_layout.setSpacing(12)

        self.opt2_radio = QLabel("●" if self.selected_mode == "disable_auto_allow_features" else "○")
        self.opt2_radio.setStyleSheet("color: #55D67A; font-size: 18px; border: none; background: transparent;")
        self.opt2_radio.setFixedWidth(22)
        opt2_layout.addWidget(self.opt2_radio)

        opt2_text_col = QVBoxLayout()
        opt2_text_col.setSpacing(2)
        self.opt2_title = QLabel("Otomatik Güncelleştirmeleri Kapat")
        self.opt2_title.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        self.opt2_desc = QLabel("Otomatik güncellemeler kapatılır; .NET ve isteğe bağlı Windows bileşenleri indirilebilir.")
        self.opt2_desc.setStyleSheet("color: #8C9BA8; font-size: 10px; border: none; background: transparent;")
        opt2_text_col.addWidget(self.opt2_title)
        opt2_text_col.addWidget(self.opt2_desc)
        opt2_layout.addLayout(opt2_text_col, 1)

        card_layout.addWidget(self.opt2_card)

        # Tıklama olayları
        self.opt1_card.mousePressEvent = lambda ev: self._select_mode("pause_2100")
        self.opt2_card.mousePressEvent = lambda ev: self._select_mode("disable_auto_allow_features")

        self._refresh_styles(animate=False)

        # Butonlar Satırı
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Vazgeç")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setFixedWidth(85)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #141A21; color: #8C9BA8; border: 1px solid #2A3440; "
            "border-radius: 6px; font-weight: 600; font-size: 11px; }\n"
            "QPushButton:hover { background-color: #1C242E; color: #FFFFFF; }"
        )
        cancel_btn.clicked.connect(lambda: self.animate_close(accepted=False))
        btn_row.addWidget(cancel_btn)

        apply_btn = QPushButton("Uygula")
        apply_btn.setFixedHeight(34)
        apply_btn.setFixedWidth(110)
        apply_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        apply_btn.setStyleSheet(
            "QPushButton { background-color: #0E2938; color: #00E5FF; border: 1px solid #00E5FF; "
            "border-radius: 6px; font-weight: bold; font-size: 11px; }\n"
            "QPushButton:hover { background-color: #00E5FF; color: #000000; }"
        )
        apply_btn.clicked.connect(lambda: self.animate_close(accepted=True))
        btn_row.addWidget(apply_btn)

        card_layout.addLayout(btn_row)
        main_layout.addWidget(self.card)

    def _select_mode(self, mode):
        if self.selected_mode == mode:
            return
        self.selected_mode = mode
        self._refresh_styles(animate=True)

    def _refresh_styles(self, animate=True):
        is_opt1 = (self.selected_mode == "pause_2100")

        if animate:
            if self._mode_anim and self._mode_anim.state() == QAbstractAnimation.State.Running:
                self._mode_anim.stop()
            self._mode_anim = QVariantAnimation(self)
            self._mode_anim.setDuration(180)
            self._mode_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            self._mode_anim.setStartValue(0.0)
            self._mode_anim.setEndValue(1.0)

            # Renk tanımları
            idle_bg = QColor("#121820")
            idle_border = QColor("#232D38")
            opt1_active_bg = QColor("#101E2B")
            opt1_active_border = QColor("#00E5FF")
            opt2_active_bg = QColor("#0F221B")
            opt2_active_border = QColor("#55D67A")

            def _blend(c_from, c_to, progress):
                r = int(c_from.red() + (c_to.red() - c_from.red()) * progress)
                g = int(c_from.green() + (c_to.green() - c_from.green()) * progress)
                b = int(c_from.blue() + (c_to.blue() - c_from.blue()) * progress)
                return QColor(r, g, b).name()

            def on_frame(val):
                p = float(val)
                if is_opt1:
                    # opt1 açılıyor, opt2 kapanıyor
                    c1_bg = _blend(idle_bg, opt1_active_bg, p)
                    c1_br = _blend(idle_border, opt1_active_border, p)
                    c2_bg = _blend(opt2_active_bg, idle_bg, p)
                    c2_br = _blend(opt2_active_border, idle_border, p)
                else:
                    # opt2 açılıyor, opt1 kapanıyor
                    c1_bg = _blend(opt1_active_bg, idle_bg, p)
                    c1_br = _blend(opt1_active_border, idle_border, p)
                    c2_bg = _blend(idle_bg, opt2_active_bg, p)
                    c2_br = _blend(idle_border, opt2_active_border, p)

                self.opt1_card.setStyleSheet(
                    f"QFrame {{ background-color: {c1_bg}; border: 1.5px solid {c1_br}; border-radius: 9px; }}"
                )
                self.opt2_card.setStyleSheet(
                    f"QFrame {{ background-color: {c2_bg}; border: 1.5px solid {c2_br}; border-radius: 9px; }}"
                )

            self._mode_anim.valueChanged.connect(on_frame)
            self._mode_anim.start()
        else:
            if is_opt1:
                self.opt1_card.setStyleSheet(
                    "QFrame { background-color: #101E2B; border: 1.5px solid #00E5FF; border-radius: 9px; }"
                )
                self.opt2_card.setStyleSheet(
                    "QFrame { background-color: #121820; border: 1px solid #232D38; border-radius: 9px; }\n"
                    "QFrame:hover { background-color: #171F2A; border-color: #384656; }"
                )
            else:
                self.opt1_card.setStyleSheet(
                    "QFrame { background-color: #121820; border: 1px solid #232D38; border-radius: 9px; }\n"
                    "QFrame:hover { background-color: #171F2A; border-color: #384656; }"
                )
                self.opt2_card.setStyleSheet(
                    "QFrame { background-color: #0F221B; border: 1.5px solid #55D67A; border-radius: 9px; }"
                )

        if is_opt1:
            self.opt1_radio.setText("●")
            self.opt1_radio.setStyleSheet("color: #00E5FF; font-size: 18px; border: none; background: transparent;")
            self.opt2_radio.setText("○")
            self.opt2_radio.setStyleSheet("color: #8C9BA8; font-size: 18px; border: none; background: transparent;")
        else:
            self.opt1_radio.setText("○")
            self.opt1_radio.setStyleSheet("color: #8C9BA8; font-size: 18px; border: none; background: transparent;")
            self.opt2_radio.setText("●")
            self.opt2_radio.setStyleSheet("color: #55D67A; font-size: 18px; border: none; background: transparent;")

    def showEvent(self, event):
        super().showEvent(event)
        self._is_closing = False
        if self.parent():
            p_geo = self.parent().geometry()
            target_x = p_geo.x() + (p_geo.width() - self.width()) // 2
            target_y = p_geo.y() + (p_geo.height() - self.height()) // 2
            self.move(target_x, target_y + 14)

            if self._anim_group and self._anim_group.state() == QAbstractAnimation.State.Running:
                try:
                    self._anim_group.stop()
                except Exception:
                    pass

            eff = QGraphicsOpacityEffect(self.card)
            eff.setOpacity(0.0)
            self.card.setGraphicsEffect(eff)
            self._card_opacity = eff

            self._fade_anim = QPropertyAnimation(self._card_opacity, b"opacity", self)
            self._fade_anim.setDuration(220)
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._slide_anim = QPropertyAnimation(self, b"pos", self)
            self._slide_anim.setDuration(220)
            self._slide_anim.setStartValue(QPoint(target_x, target_y + 14))
            self._slide_anim.setEndValue(QPoint(target_x, target_y))
            self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._anim_group = QParallelAnimationGroup(self)
            self._anim_group.addAnimation(self._fade_anim)
            self._anim_group.addAnimation(self._slide_anim)

            def _on_entrance_done():
                try:
                    self.card.setGraphicsEffect(None)
                except Exception:
                    pass

            self._anim_group.finished.connect(_on_entrance_done)
            self._anim_group.start()

    def animate_close(self, accepted=False):
        if getattr(self, "_is_closing", False):
            return
        self._is_closing = True

        if self._anim_group and self._anim_group.state() == QAbstractAnimation.State.Running:
            try:
                self._anim_group.stop()
            except Exception:
                pass

        cur_pos = self.pos()
        target_y = cur_pos.y() + 10

        current_op = 1.0
        if getattr(self, "_card_opacity", None) is not None:
            try:
                current_op = self._card_opacity.opacity()
            except Exception:
                current_op = 1.0

        eff = QGraphicsOpacityEffect(self.card)
        eff.setOpacity(current_op)
        self.card.setGraphicsEffect(eff)
        self._card_opacity = eff

        self._exit_fade = QPropertyAnimation(self._card_opacity, b"opacity", self)
        self._exit_fade.setDuration(160)
        self._exit_fade.setStartValue(current_op)
        self._exit_fade.setEndValue(0.0)
        self._exit_fade.setEasingCurve(QEasingCurve.Type.InCubic)

        self._exit_slide = QPropertyAnimation(self, b"pos", self)
        self._exit_slide.setDuration(160)
        self._exit_slide.setStartValue(cur_pos)
        self._exit_slide.setEndValue(QPoint(cur_pos.x(), target_y))
        self._exit_slide.setEasingCurve(QEasingCurve.Type.InCubic)

        self._exit_group = QParallelAnimationGroup(self)
        self._exit_group.addAnimation(self._exit_fade)
        self._exit_group.addAnimation(self._exit_slide)

        def _on_exit_done():
            if accepted:
                super(WindowsUpdateOptionsDialog, self).accept()
            else:
                super(WindowsUpdateOptionsDialog, self).reject()

        self._exit_group.finished.connect(_on_exit_done)
        self._exit_group.start()



