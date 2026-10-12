"""
WinKit - Main GUI Window (WinKitApp)
Comprehensive PyQt6 interface preserving all tabs, configurations, and features.
"""

import os
import sys
import re
import time
import math
import csv
import json
import base64
import ctypes
import shutil
import hashlib
import winreg
import tempfile
import winsound
import subprocess
import threading
import queue
import urllib.request
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QPushButton, QCheckBox, QRadioButton, QButtonGroup, QLabel, QLineEdit, QTextEdit, QScrollArea, QComboBox,
    QStackedWidget, QDialog, QSizePolicy, QFileDialog, QGraphicsOpacityEffect,
    QStyle, QStyleOptionButton, QStyleOptionSlider, QProgressBar, QAbstractItemView, QScrollBar, QSplitter
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QVariantAnimation, QParallelAnimationGroup, QEasingCurve,
    QEvent, QPoint, QPointF, QObject, pyqtSlot, pyqtProperty, pyqtSignal, QRect, QRectF, QUrl, QCoreApplication,
    QAbstractAnimation, QSize, QThread, QMutex, QWaitCondition
)
from PyQt6.QtGui import (
    QFont, QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QTextCharFormat, QTextCursor, QTextDocument, QPolygonF,
    QPainterPath, QCursor
)


from core.constants import (
    SUPPORTED_WINDOWS_VERSION, SUPPORTED_WINDOWS_BUILD, CREATE_NO_WINDOW,
    ZAPRET_V1_PAYLOAD_FILES, ZAPRET_V2_PAYLOAD_FILES, ZAPRET_ALL_PAYLOAD_FILES,
    WINKIT_SILENT_EXE_B64
)
from core.privileges import (
    enable_process_privileges,
    run_powershell_as_system,
    run_powershell_as_trustedinstaller
)
from core.system import (
    is_admin,
    deploy_winkit_silent,
    get_winkit_data_directory,
    get_documents_directory,
    append_runtime_diagnostic,
    capture_filtered_start_pins_json,
    schedule_system_path_cleanup_on_boot,
    repair_stale_start_pin_policy
)
from core.registry import (
    RegistryEngine,
    is_defender_active,
    check_appx_installed_via_registry
)
from core.shutup10 import (
    load_oosu_config_rules,
    localize_oosu_description,
    get_detailed_shutup_tooltip
)
from core.iso import (
    normalize_windows_product_name,
    get_current_windows_release,
    get_current_windows_edition,
    is_supported_windows_release,
    validate_iso_paths,
    windows_release_for_build,
    summarize_oscdimg_failure,
    write_iso_build_log,
    validate_extracted_iso_tree,
    get_windows_image_info,
    generate_unattend_xml,
    build_custom_iso
)
from core.key_remap import (
    SCANCODE_DATABASE,
    SCANCODE_TO_LABEL,
    QT_KEY_TO_SCANCODE,
    KeyboardRemapEngine,
    apply_sticky_keys_fix
)
from core.context_menu import (
    register_winkit_context_menu,
    install_winkit_ownership_tools
)
from core.tweaks import (
    apply_msi_interrupt_tuning,
    pause_windows_updates_2099,
    resume_windows_updates
)
from core.debloater import (
    remove_selected_apps_safely,
    deep_remove_selected_apps
)
from core.anti_dpi import (
    is_zapret_installed,
    get_zapret_paths,
    install_zapret,
    remove_zapret
)
from core.dpi_tester import (
    run_dpi_test,
    get_dpi_report_path
)
from core.restore import (
    create_system_restore_point,
    is_system_restore_enabled,
    restore_windows_defender,
    restore_windows_updates,
    restore_network_settings,
    restore_sticky_keys,
    open_system_restore_gui
)
from core.licensing import (
    get_windows_license_status,
    activate_windows
)
from gui.styles import QSS, DARK_THEME_PALETTE
from gui.widgets import (
    HamburgerButton, WinKitMark, RiftNavButton, SettingsGlyphButton,
    RiftSwitch, SmoothScrollArea, SmoothConsoleTextEdit, SmoothLoadingRing,
    AnimatedRadioButton, AnimatedTickCheckBox, SleekAnimatedTooltip,
    TooltipHoverFilter, SmoothComboScrollFilter, RiftComboBox, FilterChip,
    StatusToastWidget, CTkToolTip, SleekComboBox, OverlayCloseButton
)
from gui.dialogs import (
    DefenderWarningDialog, ZapretAlreadyInstalledDialog,
    ZapretDnsRestoreDialog, RestoreEnablePromptDialog,
    KeyRemapDialog, RestoreOverlay
)

class WinKitApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.default_width, self.default_height = 1040, 720
        self.setMinimumSize(920, 700)
        self.resize(self.default_width, self.default_height)

        self.root_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
        self.setWindowTitle("WinKit")

        try:
            for icon_name in ("winkit_logo.ico", "ico.ico"):
                icon_path = self.get_binary_path(icon_name)
                if os.path.exists(icon_path):
                    self.setWindowIcon(QIcon(icon_path))
                    break
        except Exception:
            pass

        self.sevenzip = self.get_binary_path("7z.exe")
        self.oscdimg_exe = self.get_binary_path("oscdimg.exe")
        self.oosu_exe = self.get_binary_path("OOSU10.exe")

        self.etfs = self.get_binary_path("etfsboot.com")
        self.efisys = self.get_binary_path("efisys_noprompt.bin")

        self.active_page = "iso"

        self.setStyleSheet(QSS)

        self.resize(self.default_width, self.default_height)
        self.center_window()

        self.main_font = QFont("Segoe UI Variable Text", 12, QFont.Weight.DemiBold)
        self.console_font = QFont("Consolas", 13)

        # WinKit: kırmızı odaklı, koyu ve yüksek kontrastlı arayüz paleti.
        self.bg_window = "#07090C"
        self.bg_card = "#0B0E12"
        self.bg_sidebar = "#080A0D"
        self.accent = "#E63B4D"
        self.accent_hover = "#FF5263"
        self.secondary_accent = "#E5A64A"
        self.inactive_color = "#14191F"
        self.text_color = "#F4F7FA"
        self.border_gray = "#28313A"

        self.ui_queue = queue.Queue()

        self.is_processing = False
        self.spinner_chars = ['◜', '◠', '◝', '◞', '◡', '◟']
        self.spinner_idx = 0

        self.iso_path = ""

        self.bypass_requirements = False
        self.bypass_online_account = False
        self.bypass_bitlocker = False
        self.iso_inject_debloat = False

        # Debloat kontrol değişkenleri
        self.cfg_apps_enabled = False
        self.cfg_bsod = False
        self.cfg_dark = False
        self.cfg_extensions = False
        self.cfg_hidden = False
        self.cfg_ultraperf = False
        self.cfg_gaming_tweaks = False
        self.cfg_bing_search = False
        self.cfg_consumer_features = False
        self.cfg_delivery_opt = False
        self.cfg_end_task = False
        self.cfg_feafd = False
        self.cfg_hibernate = False
        self.cfg_location = False
        self.cfg_store_recommend = False
        self.cfg_telemetry = False
        self.cfg_widgets = False
        self.cfg_wpbt = False
        self.cfg_classic_menu = False
        self.cfg_remove_ai = False
        self.cfg_shutup10 = False
        self.cfg_services = False
        self.cfg_remove_bitlocker = False
        self.cfg_sticky_keys = False
        self.cfg_disable_fso = False
        self.cfg_disable_mpo = False
        self.cfg_disable_s0_drain = False
        self.cfg_ntp_sync = False
        self.cfg_defender = False
        self.cfg_pause_updates_2099 = False
        self.cfg_update_mode = "disable_auto_allow_features"
        self.cfg_context_menu_tools = False
        self.cfg_llmnr_poisoning = False
        self.cfg_disable_lastaccess = False
        self.cfg_hags = False
        self.cfg_reserved_storage = False
        self.cfg_verbose_status = False
        self.cfg_long_paths = False
        self.cfg_utc_clock = False
        self.cfg_smartscreen_clipboard = False
        self.cfg_clipboard_local = False
        self.cfg_smartscreen_explorer = False
        self.cfg_device_companion = False
        self.cfg_msi_interrupts = False
        self.cfg_disable_ai = False
        self.cfg_disable_win_space = False
        self.cfg_control_panel_small_icons = False

        self.bloat_apps = [
            ("Microsoft Edge", "edge"),
            ("Microsoft OneDrive", "onedrive"),
            ("Microsoft Family Safety", "MicrosoftCorporationII.MicrosoftFamily"),
            ("Windows Kişiler", "Microsoft.People"),
            ("AV1 Video Uzantısı", "Microsoft.AV1VideoExtension"),
            ("AVC Video Uzantısı", "Microsoft.AVCEncoderVideoExtension"),
            ("HEVC Video Uzantısı", "Microsoft.HEVCVideoExtension"),
            ("Cihazlar Arası Deneyim", "MicrosoftWindows.CrossDevice"),
            ("Dev Home", "Microsoft.Windows.DevHome"),
            ("Fotoğraflar", "Microsoft.Windows.Photos"),
            ("Xbox Game Bar", "Microsoft.XboxGamingOverlay"),
            ("Xbox Oyun Konuşma Penceresi", "Microsoft.XboxSpeechToTextOverlay"),
            ("Geri Bildirim Merkezi", "Microsoft.WindowsFeedbackHub"),
            ("Hava Durumu", "Microsoft.BingWeather"),
            ("HEIF Resim Uzantısı", "Microsoft.HEIFImageExtension"),
            ("Hızlı Yardım", "MicrosoftCorporationII.QuickAssist"),
            ("Microsoft 365", "Microsoft.MicrosoftOfficeHub"),
            ("Microsoft Bing Arama", "Microsoft.BingSearch"),
            ("Clipchamp Video Düzenleyici", "Clipchamp.Clipchamp"),
            ("Haberler", "Microsoft.BingNews"),
            ("Microsoft Teams", "MSTeams"),
            ("Microsoft To Do", "Microsoft.Todos"),
            ("MPEG-2 Video Uzantısı", "Microsoft.MPEG2VideoExtension"),
            ("Outlook", "Microsoft.OutlookForWindows"),
            ("Power Automate", "Microsoft.PowerAutomateDesktop"),
            ("RAW Resim Uzantısı", "Microsoft.RawImageExtension"),
            ("Saat", "Microsoft.WindowsAlarms"),
            ("Ekran Alıntısı Aracı", "Microsoft.ScreenSketch"),
            ("Telefon Bağlantısı", "Microsoft.YourPhone"),
            ("VP9 Video Uzantısı", "Microsoft.VP9VideoExtensions"),
            ("Web Medya Uzantıları", "Microsoft.WebMediaExtensions"),
            ("WebP Resim Uzantısı", "Microsoft.WebpImageExtension"),
            ("Windows Web Deneyimi Paketi", "MicrosoftWindows.Client.WebExperience"),
            ("Widgets Platform Çalışma Zamanı", "Microsoft.WidgetsPlatformRuntime"),
            ("Başlangıç Deneyimleri", "Microsoft.StartExperiencesApp"),
            ("Uygulama Uyumluluk İyileştirmeleri", "Microsoft.ApplicationCompatibilityEnhancements"),
            ("Xbox Kimlik Sağlayıcısı", "Microsoft.XboxIdentityProvider"),
            ("Xbox Live", "Microsoft.Xbox.TCUI"),
            ("Xbox Uygulaması", "Microsoft.GamingApp"),
            ("Yapışkan Notlar", "Microsoft.MicrosoftStickyNotes"),
            ("Yardım Al", "Microsoft.GetHelp"),
            ("İpuçları", "Microsoft.Getstarted"),
            ("Microsoft Solitaire Collection", "Microsoft.MicrosoftSolitaireCollection"),
            ("Medya Oynatıcı", "Microsoft.ZuneMusic"),
            ("Kamera", "Microsoft.WindowsCamera"),
            ("Ses Kaydedicisi", "Microsoft.WindowsSoundRecorder"),
            ("Paint", "Microsoft.Paint"),
            ("Hesap Makinesi", "Microsoft.WindowsCalculator")
        ]
        self.app_vars = {app[0]: False for app in self.bloat_apps}
        self.app_risk_map = {
            "Dev Home": 0,
            "Geri Bildirim Merkezi": 0,
            "Hava Durumu": 0,
            "Microsoft 365": 0,
            "Clipchamp Video Düzenleyici": 0,
            "Haberler": 0,
            "Power Automate": 0,
            "Yardım Al": 0,
            "İpuçları": 0,
            "Microsoft Solitaire Collection": 0,
            "Kamera": 0,
            "Ses Kaydedicisi": 0,
            "Paint": 0,
            "Hesap Makinesi": 0,
            "Fotoğraflar": 0,
            "Saat": 0,
            "Microsoft Edge": 2,
            "Microsoft OneDrive": 1,
            "Cihazlar Arası Deneyim": 1,
            "Microsoft Bing Arama": 1,
            "Windows Web Deneyimi Paketi": 1,
            "Widgets Platform Çalışma Zamanı": 1,
            "Başlat Deneyimleri": 1,
            "Uygulama Uyumluluk İyileştirmeleri": 2,
        }

        self.shutup_rules = [
            ("P001", "+", "El yazısı veri paylaşımını kapat", "Gizlilik"),
            ("P002", "+", "El yazısı hata raporlamasını kapat", "Gizlilik"),
            ("P003", "+", "Envanter Toplayıcıyı kapat", "Gizlilik"),
            ("P005", "+", "Reklam kimliğini kapat ve sıfırla", "Gizlilik"),
            ("P006", "+", "Kullanıcı reklam kimliğini kapat", "Gizlilik"),
            ("P008", "+", "Yazma bilgilerinin gönderimini kapat", "Gizlilik"),
            ("P027", "+", "Müşteri Deneyimi Programını kapat", "Gizlilik"),
            ("P028", "+", "Buluta mesaj yedeklemeyi kapat", "Gizlilik"),
            ("P064", "+", "Zaman tüneli önerilerini kapat", "Gizlilik"),
            ("P065", "+", "Başlat menüsü önerilerini kapat", "Gizlilik"),
            ("P066", "+", "Windows ipuçları ve önerilerini kapat", "Gizlilik"),
            ("P070", "+", "Kurulum tamamlama önerilerini kapat", "Gizlilik"),
            ("P069", "+", "Windows Hata Raporlamayı kapat", "Gizlilik"),
            ("P009", "+", "Biyometrik özellikleri kapat", "Gizlilik"),
            ("A001", "+", "Kullanıcı etkinlik kayıtlarını kapat", "Etkinlik Geçmişi"),
            ("A002", "+", "Etkinlik geçmişini depolamayı kapat", "Etkinlik Geçmişi"),
            ("A003", "+", "Etkinlik geçmişini Microsoft'a göndermeyi kapat", "Etkinlik Geçmişi"),
            ("A005", "+", "Bulut pano senkronizasyonunu kapat", "Etkinlik Geçmişi"),
            ("P036", "+", "Hesap bilgilerine erişimi kapat", "Uygulama İzinleri"),
            ("P025", "+", "Uygulama başlatma takibini kapat", "Uygulama İzinleri"),
            ("P033", "+", "Tanılama bilgilerine erişimi kapat", "Uygulama İzinleri"),
            ("P023", "+", "Kullanıcı tanılama erişimini kapat", "Uygulama İzinleri"),
            ("P056", "+", "Cihaz konum erişimini kapat", "Uygulama İzinleri"),
            ("P057", "+", "Kullanıcı konum erişimini kapat", "Uygulama İzinleri"),
            ("S002", "+", "Kullanıcı adımları kaydediciyi kapat", "Güvenlik & Telemetri"),
            ("S003", "+", "Sistem telemetrisini kapat", "Güvenlik & Telemetri"),
            ("S008", "+", "Windows Media DRM internet erişimini kapat", "Güvenlik & Telemetri"),
            ("U001", "+", "Uygulama telemetrisini kapat", "Güvenlik & Telemetri"),
            ("U004", "+", "Tanılama verileriyle özelleştirmeyi kapat", "Güvenlik & Telemetri"),
            ("U005", "+", "Tanılama verileriyle kullanıcı özelleştirmelerini kapat", "Güvenlik & Telemetri"),
            ("U006", "+", "Tanılama günlük toplamayı kapat", "Güvenlik & Telemetri"),
            ("U007", "+", "OneSettings yapılandırma indirmelerini kapat", "Güvenlik & Telemetri"),
            ("C012", "+", "Cortana'yı kapat ve sıfırla", "Cortana & Yapay Zeka"),
            ("C002", "+", "Giriş kişiselleştirmeyi kapat", "Cortana & Yapay Zeka"),
            ("C013", "+", "Çevrimiçi konuşma tanımayı kapat", "Cortana & Yapay Zeka"),
            ("C007", "+", "Cortana konum erişimini kapat", "Cortana & Yapay Zeka"),
            ("C008", "+", "Windows Masaüstü Arama web sonuçlarını kapat", "Cortana & Yapay Zeka"),
            ("C009", "+", "Arama web sonuçlarını görüntülemeyi kapat", "Cortana & Yapay Zeka"),
            ("C010", "+", "Konuşma tanıma model güncellemelerini kapat", "Cortana & Yapay Zeka"),
            ("C011", "+", "Bulut aramayı kapat", "Cortana & Yapay Zeka"),
            ("C014", "+", "Kilit ekranında Cortana'yı kapat", "Cortana & Yapay Zeka"),
            ("C015", "+", "Görev çubuğu arama vurgularını kapat", "Cortana & Yapay Zeka"),
            ("C101", "+", "Windows Copilot'u kapat", "Cortana & Yapay Zeka"),
            ("C201", "+", "Kullanıcı Copilot'unu kapat", "Cortana & Yapay Zeka"),
            ("C204", "+", "Recall özelliğini tüm kullanıcılar için kapat", "Cortana & Yapay Zeka"),
            ("C205", "+", "Paint Image Creator özelliğini kapat", "Cortana & Yapay Zeka"),
            ("C102", "+", "Görev çubuğundan Copilot butonunu kaldır", "Cortana & Yapay Zeka"),
            ("C104", "+", "Windows Copilot Bing Chat uygunluğunu kapat", "Cortana & Yapay Zeka"),
            ("C103", "+", "Windows Recall özelliğini kapat", "Cortana & Yapay Zeka"),
            ("C203", "+", "Kullanıcı Recall özelliğini kapat", "Cortana & Yapay Zeka"),
            ("C206", "+", "Paint Cocreator özelliğini kapat", "Cortana & Yapay Zeka"),
            ("C207", "+", "Paint yapay zeka dolgu özelliğini kapat", "Cortana & Yapay Zeka"),
            ("W001", "+", "Peer-to-peer Windows Update'i kapat", "Sistem Güncellemeleri"),
            ("W011", "+", "Konuşma sentezi güncellemelerini kapat", "Sistem Güncellemeleri"),
            ("W010", "+", "Windows Update sürücü güncellemelerini kapat", "Sistem Güncellemeleri"),
            ("W009", "+", "Mağaza uygulamaları otomatik güncellemelerini kapat", "Sistem Güncellemeleri"),
            ("K001", "+", "Windows Spotlight özelliğini kapat", "Kilit Ekranı & Mobil"),
            ("K002", "+", "Kilit ekranı ipuçları ve eğlenceli bilgileri kapat", "Kilit Ekranı & Mobil"),
            ("D001", "+", "Mobil cihazlara erişimi kapat", "Kilit Ekranı & Mobil"),
            ("D002", "+", "Telefon Bağlantısı uygulamasını kapat", "Kilit Ekranı & Mobil"),
            ("D003", "+", "Mobil cihaz önerilerini kapat", "Kilit Ekranı & Mobil"),
            ("D104", "+", "PC'yi mobil cihazlara bağlamayı kapat", "Kilit Ekranı & Mobil"),
            ("M025", "+", "Arama kutusunda yapay zeka aramalarını kapat", "Arama & Görev Çubuğu"),
            ("M003", "+", "Windows aramasında Bing genişletmesini kapat", "Arama & Görev Çubuğu"),
            ("M019", "+", "Haber ve İlgi Alanlarını kapat", "Arama & Görev Çubuğu"),
            ("M016", "+", "Görev çubuğu arama kutusunu kapat", "Arama & Görev Çubuğu"),
            ("M015", "+", "Görev çubuğu Kişiler simgesini kapat", "Arama & Görev Çubuğu"),
            ("M017", "+", "Görev çubuğu Şimdi Toplan kapat", "Arama & Görev Çubuğu"),
            ("M018", "+", "Kullanıcı Şimdi Toplan kapat", "Arama & Görev Çubuğu"),
            ("M022", "+", "Geri bildirim anımsatıcılarını kapat", "Diğer Ayarlar"),
            ("M001", "+", "Kullanıcı geri bildirim anımsatıcılarını kapat", "Diğer Ayarlar"),
            ("M004", "+", "Önerilen Mağaza uygulamalarının otomatik yüklenmesini kapat", "Diğer Ayarlar"),
            ("M005", "+", "Windows ipuçları ve önerilerini kapat", "Diğer Ayarlar"),
            ("M024", "+", "Windows Media Player Tanılamalarını kapat", "Diğer Ayarlar"),
            ("M026", "+", "Uzaktan yardım bağlantılarını kapat", "Diğer Ayarlar"),
            ("M027", "+", "Bilgisayara uzaktan bağlantıları kapat", "Diğer Ayarlar"),
            ("M028", "+", "Windows Spotlight masaüstü simgesini kapat", "Diğer Ayarlar"),
            ("M012", "+", "Çevrimiçi KMS Aktivasyonunu kapat", "Diğer Ayarlar")
        ]
        # Dosyadaki 281 seçeneğin tamamını arayüze taşı. Kodda bulunan Türkçe
        # açıklamalar korunur; yeni O&O seçenekleri dosyadaki resmi metni kullanır.
        localized_rules = {
            code: (description, category)
            for code, _, description, category in self.shutup_rules
        }
        config_rules = load_oosu_config_rules(self.get_binary_path("ooshutup10.cfg"))
        if config_rules:
            self.shutup_rules = [
                (
                    code,
                    sign,
                    localized_rules.get(
                        code,
                        (localize_oosu_description(description), category),
                    )[0],
                    category,
                )
                for code, sign, description, category in config_rules
            ]
        self.shutup_vars = {code: sign == "+" for code, sign, _, _ in self.shutup_rules}
        self.shutup_risk_map = {"P056": 1, "P057": 1, "W001": 1, "W010": 1, "W011": 1}
        self._bulk_toggle_in_progress = False

        self.temp_app_vars = {}
        self.temp_shutup_vars = {}

        # Sidebar
        self.sidebar_width = 172
        self.sidebar_open = True
        self.sidebar_anim = None

        self.menu_btn = None
        self.sidebar_frame = None
        self.btn_iso = None
        self.btn_debloat = None
        self.btn_apps = None
        self.btn_privacy = None
        self.btn_anti_dpi = None
        self.btn_license = None
        self.right_area = None

        self.console_iso = None
        self.console_debloat = None
        self.apply_btn = None
        self.inject_btn = None

        self.iso_entry = None
        self.spinner_label = None
        self.console_loading_ring = None
        self.page_switch_btn = None
        self._stage_progress_rows = {}
        self._active_progress_row = None
        self._active_progress_target = None
        self._console_transition_anim = None
        self._transition_widget = None

        self.blocker_overlay = None
        self.popup_overlay = None
        self.restore_task_type = None
        self.restore_popup = None
        self.current_worker = None
        self.last_debloat_subpage = "debloat"

        self.iso_frame = None
        self.iso_console_frame = None
        self.debloat_frame = None
        self.debloat_console_frame = None
        self.app_checklist_frame = None
        self.shutup_checklist_frame = None
        self.anti_dpi_frame = None
        self.anti_console_frame = None
        self.license_frame = None
        self.console_anti = None
        self.anti_install_btn = None
        self.anti_remove_btn = None
        self.anti_status_label = None
        self.anti_console_back_btn = None
        self.anti_console_loading_ring = None
        self.btn_key_remap = None
        self.key_remap_frame = None
        self.key_remap_list_layout = None
        self.key_remap_count_label = None
        self.btn_win_space_toggle = None
        self.btn_dpi_tester = None
        self.dpi_tester_frame = None
        self.dpi_tester_console_frame = None
        self.console_dpi_tester = None
        self.dpi_tester_start_btn = None
        self.dpi_tester_console_back_btn = None
        self.dpi_tester_open_report_btn = None
        self.dpi_tester_loading_ring = None
        self.anti_zapret_ver = "v2"
        self.dpi_zapret_ver = "v2" 
        self._iso_path_anim = None
        self.iso_console_loading_ring = None
        self.iso_console_back_btn = None
        self.shutup_category_buttons = []
        self.shutup_category_stack = None
        self.stacked_pages = QStackedWidget()

        self.sidebar_close_timer = QTimer(self)
        self.sidebar_close_timer.setSingleShot(True)
        self.sidebar_close_timer.timeout.connect(self._close_sidebar_if_needed)

        # Sayfa geçiş animasyonlarını canlı tutmak için referanslar
        self._page_anims = []

        # Lisanslama arayüz referansları (init_main_interface öncesi tanımlanmalıdır)
        self.license_key_entry = None
        self.license_activate_btn = None
        self.license_clear_btn = None
        self._license_activation_attempted = False

        self.init_main_interface()

        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self.check_queue_loop)
        self.queue_timer.start(100)

        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self.animate_spinner)

        # Sistem durumu kullanıcı seçimi değildir; seçenekleri işaretleyen eski
        # başlangıç taraması çalıştırılmaz. Winver bilgisi üst çubukta gösterilir.
        threading.Thread(target=self._scan_anti_status, daemon=True).start()

    # ---------- helpers ----------
    def get_binary_path(self, filename):
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            bundled_path = os.path.join(sys._MEIPASS, filename)
            if os.path.exists(bundled_path):
                return bundled_path
        try:
            nuitka_dir = os.path.dirname(os.path.abspath(__file__))
            bundled_path = os.path.join(nuitka_dir, filename)
            if os.path.exists(bundled_path):
                return bundled_path
        except Exception:
            pass
        return os.path.join(self.root_dir, filename)

    def center_window(self):
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

    def _create_wave_dots_pixmap(self, phase=0.0):
        # Noktayı her karede yeniden rasterleştirmek kenarlarda değişen tek
        # piksellik çıkıntılar oluşturuyordu. Daireyi bir kez üretip yalnızca
        # tam fiziksel piksel adımlarıyla taşıyarak şekli her karede sabit tut.
        logical_w, logical_h = 28, 14
        dpr = 4.0
        dot = getattr(self, "_wave_dot_sprite", None)
        if dot is None:
            dot = QPixmap(int(6 * dpr), int(6 * dpr))
            dot.setDevicePixelRatio(dpr)
            dot.fill(Qt.GlobalColor.transparent)
            dot_painter = QPainter(dot)
            dot_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            dot_painter.setPen(Qt.PenStyle.NoPen)
            dot_painter.setBrush(QBrush(QColor("#E63B4D")))
            dot_painter.drawEllipse(QRectF(1.0, 1.0, 4.0, 4.0))
            dot_painter.end()
            self._wave_dot_sprite = dot
        pixmap = QPixmap(int(logical_w * dpr), int(logical_h * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for i in range(3):
            dot_phase = phase + i * 0.95
            y_offset = math.sin(dot_phase) * 3.0
            x = 5.0 + i * 9.0
            y = round((7.0 - y_offset) * dpr) / dpr
            painter.drawPixmap(QPointF(x - 3.0, y - 3.0), dot)
        painter.end()
        return pixmap

    def _format_completed_stage_segments(self, base_text, raw_result=None, override_color=None):
        text = str(base_text or "").strip()
        if text.startswith(">"):
            text = text[1:].strip()
        
        # Subtitle suffix clean up if sub-info was attached (e.g. ": MapsBroker" or " · Microsoft Edge")
        for sep in (":", " · ", " - "):
            if sep in text:
                text = text.split(sep, 1)[0].strip()

        is_failed = False
        is_warning = False
        if raw_result and any(w in str(raw_result) for w in ("Uygulanamadı", "Kapatılamadı", "Etkinleştirilemedi", "HATA", "✖", "Başarısız", "başarısız")):
            is_failed = True
        elif raw_result and "⚠" in str(raw_result):
            is_warning = True

        # Mapping for verbs (Tasarım Standardı: Başarılı işlem nötr açık metin #DDE4EC + yeşil onay #55D67A)
        verb_color_map = {
            "etkinleştiriliyor": ("etkinleştirildi", "#DDE4EC"),
            "başlatılıyor": ("başlatıldı", "#DDE4EC"),
            "kapatılıyor": ("kapatıldı", "#DDE4EC"),
            "kaldırılıyor": ("kaldırıldı", "#DDE4EC"),
            "durduruluyor": ("durduruldu", "#DDE4EC"),
            "sınırlandırılıyor": ("sınırlandırıldı", "#DDE4EC"),
            "uygulanıyor": ("uygulandı", "#DDE4EC"),
            "ayarlanıyor": ("ayarlandı", "#DDE4EC"),
            "yenileniyor": ("yenilendi", "#DDE4EC"),
            "yapılandırılıyor": ("yapılandırıldı", "#DDE4EC"),
            "doğrulanıyor": ("doğrulandı", "#DDE4EC"),
            "ekleniyor": ("eklendi", "#DDE4EC"),
            "oluşturuluyor": ("oluşturuldu", "#DDE4EC"),
            "yeniden oluşturuluyor": ("yeniden oluşturuldu", "#DDE4EC"),
            "kuruluyor": ("kuruldu", "#DDE4EC"),
            "temizleniyor": ("temizlendi", "#DDE4EC"),
            "taranıyor": ("tarandı", "#DDE4EC"),
            "geri yükleniyor": ("geri yüklendi", "#DDE4EC"),
            "Ayıklanıyor": ("Ayıklandı", "#DDE4EC"),
            "ayıklanıyor": ("Ayıklandı", "#DDE4EC"),
            "optimize ediliyor": ("optimize edildi", "#DDE4EC"),
            "devre dışı bırakılıyor": ("devre dışı bırakıldı", "#DDE4EC"),
            "erteleniyor": ("ertelendi", "#DDE4EC"),
            "uygulanacak": ("uygulanacak", "#DDE4EC"),
        }

        matched_verb = None
        matched_past = None
        matched_color = None
        for verb, (past, col) in verb_color_map.items():
            if text.endswith(verb):
                matched_verb = verb
                matched_past = past
                matched_color = col
                break

        if is_failed:
            icon_char = "✖"
            icon_color = "#FF5C6B"
        elif is_warning:
            icon_char = "⚠"
            icon_color = "#FFB86C"
        else:
            icon_char = "✔"
            icon_color = "#00FF9D"

        if is_failed:
            if matched_verb:
                prefix = text[:-len(matched_verb)].rstrip()
                fail_verb = (
                    matched_verb.replace("etkinleştiriliyor", "etkinleştirilemedi")
                    .replace("başlatılıyor", "başlatılamadı")
                    .replace("kapatılıyor", "kapatılamadı")
                    .replace("kaldırılıyor", "kaldırılamadı")
                    .replace("durduruluyor", "durdurulamadı")
                    .replace("uygulanıyor", "uygulanamadı")
                    .replace("ayarlanıyor", "ayarlanamadı")
                    .replace("yapılandırılıyor", "yapılandırılamadı")
                    .replace("doğrulanıyor", "doğrulanamadı")
                    .replace("ekleniyor", "eklenemedi")
                    .replace("oluşturuluyor", "oluşturulamadı")
                    .replace("kuruluyor", "kurulamadı")
                    .replace("temizleniyor", "temizlenemedi")
                    .replace("taranıyor", "taranamadı")
                    .replace("geri yükleniyor", "geri yüklenemedi")
                    .replace("Ayıklanıyor", "Ayıklanamadı")
                    .replace("ayıklanıyor", "Ayıklanamadı")
                    .replace("erteleniyor", "ertelenemedi")
                    .replace("uygulanacak", "uygulanamadı")
                )
                if fail_verb == matched_verb:
                    fail_verb = "başarısız oldu"
                segments = [("• ", "#8C9BA8")]
                if prefix:
                    segments.append((f"{prefix} ", "#DDE4EC"))
                segments.append((fail_verb, override_color or "#FF5C6B"))
                segments.append((f"  {icon_char}", icon_color))
                return segments
            return [("• ", "#8C9BA8"), (f"{text} ", "#DDE4EC"), ("başarısız", override_color or "#FF5C6B"), (f"  {icon_char}", icon_color)]

        if matched_verb:
            prefix = text[:-len(matched_verb)].rstrip()
            segments = [("• ", "#8C9BA8")]
            if prefix:
                segments.append((f"{prefix} ", "#DDE4EC"))
            segments.append((matched_past, override_color or matched_color))
            segments.append((f"  {icon_char}", icon_color))
            return segments

        # Custom explicit result string if no standard verb matched
        if text.endswith(("uygulanacak", "ertelendi", "tamamlandı", "bırakıldı")):
            segments = [("• ", "#8C9BA8"), (f"{text}", "#DDE4EC")]
            segments.append((f"  {icon_char}", icon_color))
            return segments

        segments = [("• ", "#8C9BA8"), (f"{text} ", "#DDE4EC")]
        if raw_result and str(raw_result) not in ("✔", "✖", "⚠"):
            segments.append((str(raw_result), override_color or "#00FF9D"))
        else:
            segments.append(("tamamlandı", override_color or "#00FF9D"))
        segments.append((f"  {icon_char}", icon_color))
        return segments

    def log(self, message, color="#00ff66", target=None):
        msg = str(message or "").strip()
        while msg.startswith(">"):
            msg = msg[1:].strip()
        self._append_console_segments(
            [("• ", "#8C9BA8"), (msg, color)],
            target=target,
        )

    def _console_for_target(self, target=None):
        console = None
        if target == "debloat" or (target is None and self.active_page in ("debloat", "debloat_console")):
            console = self.console_debloat
        elif target == "iso" or (target is None and self.active_page == "iso"):
            console = self.console_iso
        elif target == "anti" or (target is None and self.active_page in ("anti_dpi", "anti_console")):
            console = self.console_anti
        elif target == "dpi_tester" or (target is None and self.active_page in ("dpi_tester", "dpi_tester_console")):
            console = self.console_dpi_tester
        elif target is None and getattr(self, 'current_worker', None) == "debloat":
            console = self.console_debloat
        elif target is None and getattr(self, 'current_worker', None) == "iso":
            console = self.console_iso
        elif target is None and getattr(self, 'current_worker', None) == "anti":
            console = self.console_anti
        elif target is None and getattr(self, 'current_worker', None) == "dpi_tester":
            console = self.console_dpi_tester
        return console

    def _settle_console_scroll(self, console, previous_scroll, follow_bottom):
        """Belge yerleşimi tamamlandıktan sonra doğru kaydırma konumunu uygular."""
        if console is None:
            return
        scrollbar = console.verticalScrollBar()
        if follow_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(min(previous_scroll, scrollbar.maximum()))

    def _append_console_segments(self, segments, target=None, show_spinner=False):
        console = self._console_for_target(target)
        if console is not None:
            scrollbar = console.verticalScrollBar()
            previous_scroll = scrollbar.value()
            was_at_bottom = previous_scroll >= max(0, scrollbar.maximum() - 3)
            doc = console.document()
            cursor = console.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            if not doc.isEmpty():
                cursor.insertBlock()
            block_number = cursor.blockNumber()
            for text, color in segments:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(color))
                cursor.insertText(text, fmt)
            if show_spinner:
                wave_pix = getattr(self, '_cached_wave_pixmap', None)
                if wave_pix is None:
                    wave_pix = self._create_wave_dots_pixmap(getattr(self, '_wave_phase', 0.0))
                    self._cached_wave_pixmap = wave_pix
                doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl("winkit_wave.png"), wave_pix)
                cursor.insertText("  ")
                cursor.insertHtml("<img src='winkit_wave.png' width='28' height='14' style='vertical-align: middle;' />")
            if was_at_bottom:
                cursor.movePosition(QTextCursor.MoveOperation.End)
                console.setTextCursor(cursor)
                scrollbar.setValue(scrollbar.maximum())
            else:
                scrollbar.setValue(min(previous_scroll, scrollbar.maximum()))
            QTimer.singleShot(
                0,
                lambda c=console, p=previous_scroll, bottom=was_at_bottom:
                self._settle_console_scroll(c, p, bottom),
            )
            console.setReadOnly(True)
            return block_number
        return None

    def _replace_console_block(self, block_number, segments, target=None, show_spinner=False):
        console = self._console_for_target(target)
        if console is None or block_number is None:
            return
        block = console.document().findBlockByNumber(block_number)
        if not block.isValid():
            return
        console.setReadOnly(False)
        scrollbar = console.verticalScrollBar()
        previous_scroll = scrollbar.value()
        was_at_bottom = previous_scroll >= max(0, scrollbar.maximum() - 3)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        for text, color in segments:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            cursor.insertText(text, fmt)
        if show_spinner:
            cursor.insertText("  ")
            cursor.insertHtml("<img src='winkit_wave.png' width='28' height='14' style='vertical-align: middle;' />")
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(min(previous_scroll, scrollbar.maximum()))
        QTimer.singleShot(
            0,
            lambda c=console, p=previous_scroll, bottom=was_at_bottom:
            self._settle_console_scroll(c, p, bottom),
        )
        console.setReadOnly(True)

    def set_progress_line(self, text, color="#00ff66", target=None):
        """Gerçek zamanlı olarak konsoldaki son satırı günceller (tek satır)."""
        console = None
        if target == "debloat" or (target is None and self.active_page in ("debloat", "debloat_console")):
            console = self.console_debloat
        elif target == "iso" or (target is None and self.active_page == "iso"):
            console = self.console_iso
        elif target == "anti" or (target is None and self.active_page in ("anti_dpi", "anti_console")):
            console = self.console_anti
        elif target is None and getattr(self, 'current_worker', None) == "debloat":
            console = self.console_debloat
        elif target is None and getattr(self, 'current_worker', None) == "iso":
            console = self.console_iso
        elif target is None and getattr(self, 'current_worker', None) == "anti":
            console = self.console_anti

        if console is None:
            return
        console.setReadOnly(False)
        scrollbar = console.verticalScrollBar()
        previous_scroll = scrollbar.value()
        was_at_bottom = previous_scroll >= max(0, scrollbar.maximum() - 3)
        doc = console.document()
        # Remove the text of the last block only (do not remove previous blocks)
        last_block = doc.lastBlock()
        if last_block.isValid():
            cursor = QTextCursor(last_block)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        else:
            cursor = console.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)

        # Insert new text at end
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.insertText(text, fmt)
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(min(previous_scroll, scrollbar.maximum()))
        QTimer.singleShot(
            0,
            lambda c=console, p=previous_scroll, bottom=was_at_bottom:
            self._settle_console_scroll(c, p, bottom),
        )
        console.setReadOnly(True)

    def check_queue_loop(self):
        try:
            for _ in range(10):
                msg = self.ui_queue.get_nowait()
                action = msg.get("action")
                target = msg.get("target")
                if action == "log":
                    self.log(msg["text"], msg.get("color", "#00ff66"), target=target)
                elif action == "log_segments":
                    self._append_console_segments(msg.get("segments", []), target=target)
                elif action == "finish_debloat":
                    self.is_processing = False
                    self.current_worker = None
                    self._set_navigation_enabled(True)
                    self.spinner_timer.stop()
                    self.apply_btn.setEnabled(True)
                    self.apply_btn.setText("SONUÇLARI GÖSTER")
                    if hasattr(self, 'console_back_btn'):
                        self.console_back_btn.setEnabled(True)
                    if getattr(self, 'console_loading_ring', None) is not None:
                        self.console_loading_ring.stop()
                    if self.page_switch_btn is not None:
                        self.page_switch_btn.setEnabled(True)
# Debloat log is saved as structured removal log from deep_remove_selected_apps
                    self.play_finish_sound()
                elif action == "finish_iso":
                    self.is_processing = False
                    self.current_worker = None
                    self._set_navigation_enabled(True)
                    self.spinner_timer.stop()
                    self.inject_btn.setEnabled(True)
                    self.inject_btn.setText("ISO'yu düzenle")
                    if getattr(self, 'iso_console_loading_ring', None) is not None:
                        self.iso_console_loading_ring.stop()
                    if self.iso_console_back_btn is not None:
                        self.iso_console_back_btn.setEnabled(True)
                    self.play_finish_sound()
                elif action == "finish_anti":
                    self.is_processing = False
                    self.current_worker = None
                    self._set_navigation_enabled(True)
                    self.spinner_timer.stop()
                    if self.anti_install_btn is not None:
                        self.anti_install_btn.setEnabled(True)
                    if self.anti_remove_btn is not None:
                        self.anti_remove_btn.setEnabled(True)
                    if self.anti_console_back_btn is not None:
                        self.anti_console_back_btn.setEnabled(True)
                    if getattr(self, 'anti_console_loading_ring', None) is not None:
                        self.anti_console_loading_ring.stop()
                    self.play_finish_sound()
                    threading.Thread(target=self._scan_anti_status, daemon=True).start()
                elif action == "finish_dpi_tester":
                    self.is_processing = False
                    self.current_worker = None
                    self._set_navigation_enabled(True)
                    self.spinner_timer.stop()
                    if hasattr(self, 'dpi_tester_start_btn') and self.dpi_tester_start_btn is not None:
                        self.dpi_tester_start_btn.setEnabled(True)
                    if hasattr(self, 'dpi_tester_console_back_btn') and self.dpi_tester_console_back_btn is not None:
                        self.dpi_tester_console_back_btn.setEnabled(True)
                    if hasattr(self, 'dpi_tester_open_report_btn') and self.dpi_tester_open_report_btn is not None:
                        self.dpi_tester_open_report_btn.setEnabled(True)
                    if hasattr(self, 'dpi_tester_cancel_btn') and self.dpi_tester_cancel_btn is not None:
                        self.dpi_tester_cancel_btn.setEnabled(False)
                        self.dpi_tester_cancel_btn.setText("Testi iptal et")
                    if getattr(self, 'dpi_tester_loading_ring', None) is not None:
                        self.dpi_tester_loading_ring.stop()
                    self.play_finish_sound()
                elif action == "anti_status":
                    installed = bool(msg.get("installed"))
                    if self.anti_status_label is not None:
                        self.anti_status_label.setText("KURULU" if installed else "KURULU DEĞİL")
                        color = "#55D67A" if installed else "#8B96A2"
                        self.anti_status_label.setStyleSheet(
                            f"color: {color}; background-color: #14191F; "
                            f"border: 1px solid {color}; border-radius: 11px; "
                            "padding: 4px 10px; font-size: 10px; font-weight: 700;"
                        )
                elif action == "progress_update":
                    if (
                        self._active_progress_row is None
                        or self._active_progress_target != target
                    ):
                        raw_base = msg.get("text_base", "")
                        clean_base = str(raw_base).lstrip("> ").strip()
                        self._active_progress_row = self._append_console_segments(
                            [("• ", "#8C9BA8"), (clean_base, msg.get("color", "#DDE4EC"))],
                            target=target,
                            show_spinner=True,
                        )
                        self._active_progress_target = target
                    self.active_progress_base = msg.get("text_base")
                    self.active_progress_pct = msg.get("pct")
                    self.active_progress_color = msg.get("color", "#E7ECF2")
                    self.active_progress_pct_color = msg.get(
                        "pct_color", self.active_progress_color
                    )
                elif action == "progress_stop":
                    self.active_progress_base = None
                    base_text = msg.get("text_base") or "İşlem"
                    segments = self._format_completed_stage_segments(
                        base_text,
                        raw_result=msg.get("result"),
                        override_color=msg.get("result_color"),
                    )
                    if self._active_progress_row is not None:
                        self._replace_console_block(
                            self._active_progress_row,
                            segments,
                            target=self._active_progress_target or target,
                            show_spinner=False,
                        )
                    else:
                        self._append_console_segments(
                            segments,
                            target=target,
                            show_spinner=False,
                        )
                    self._active_progress_row = None
                    self._active_progress_target = None
                elif action == "progress_cancel":
                    self.active_progress_base = None
                    self.active_progress_pct = None
                    self._active_progress_row = None
                    self._active_progress_target = None
                elif action == "stage_start":
                    stage_id = msg.get("stage_id")
                    raw_base = msg.get("text_base", "")
                    clean_base = str(raw_base).lstrip("> ").strip()
                    block_number = self._append_console_segments(
                        [("• ", "#8C9BA8"), (clean_base, msg.get("color", "#DDE4EC"))],
                        target=target,
                        show_spinner=True,
                    )
                    self._stage_progress_rows[stage_id] = {
                        "block": block_number,
                        "base": clean_base,
                        "color": msg.get("color", "#E7ECF2"),
                        "target": target,
                    }
                elif action == "stage_update_title":
                    stage_id = msg.get("stage_id")
                    stage = self._stage_progress_rows.get(stage_id)
                    if stage:
                        raw_base = msg.get("text_base", stage["base"])
                        clean_base = str(raw_base).lstrip("> ").strip()
                        stage["base"] = clean_base
                        self._replace_console_block(
                            stage["block"],
                            [("• ", "#8C9BA8"), (clean_base, stage["color"])],
                            target=stage["target"],
                            show_spinner=True,
                        )
                elif action == "stage_finish":
                    stage_id = msg.get("stage_id")
                    stage = self._stage_progress_rows.pop(stage_id, None)
                    if stage:
                        segments = self._format_completed_stage_segments(
                            stage["base"],
                            raw_result=msg.get("result"),
                            override_color=msg.get("result_color"),
                        )
                        self._replace_console_block(
                            stage["block"],
                            segments,
                            target=stage["target"],
                            show_spinner=False,
                        )
                elif action == "progress_line":
                    self.set_progress_line(msg.get("text"), msg.get("color", "#FFFFFF"), target=target)
                elif action == "apply_scan_results":
                    pass
                elif action == "restore_complete":
                    overlay_ref = msg.get("overlay")
                    if overlay_ref and hasattr(overlay_ref, "complete_restore"):
                        overlay_ref.complete_restore()
                    else:
                        self.close_popup_and_start_task(overlay_ref)
                elif action == "restore_failed":
                    overlay_ref = msg.get("overlay")
                    err_msg = msg.get("error", "Bilinmeyen hata")
                    if overlay_ref and hasattr(overlay_ref, "fail_restore"):
                        overlay_ref.fail_restore(err_msg)
                    else:
                        self.close_popup_and_start_task(overlay_ref)
                elif action == "restore_action_done":
                    button = msg.get("button")
                    if button is not None:
                        button.setEnabled(True)
                        original_text = button.property("restore_original_text")
                        if original_text:
                            button.setText(str(original_text))
                    success = bool(msg.get("success"))
                    if hasattr(self, "status_toast") and self.status_toast:
                        self.status_toast.show_message(
                            msg.get("message", "Geri yükleme işlemi tamamlandı."),
                            success=success,
                            auto_hide_ms=4200,
                        )
                elif action == "toast":
                    if hasattr(self, "status_toast") and self.status_toast:
                        self.status_toast.show_message(
                            msg.get("message", ""),
                            success=bool(msg.get("success", True)),
                            auto_hide_ms=4500,
                        )
                elif action == "license_status":
                    self.stop_loading_license_status()
                    if self.license_status_label is not None:
                        self.license_status_label.setText(msg.get("text", ""))
                        self.license_status_label.setStyleSheet(
                            f"color: {msg.get('color', '#AEB8C3')}; border: none; "
                            "font-size: 12px; font-weight: 600;"
                        )
                elif action == "license_status_update":
                    self.license_status_base_text = msg.get("text", "")
                    if self.license_status_label is not None:
                        self.license_status_label.setText(f"{self.license_status_base_text}...")
                        self.license_status_label.setStyleSheet(
                            "color: #FFB86C; border: none; font-size: 12px; font-weight: 600;"
                        )
                elif action == "license_activation_done":
                    self.stop_loading_license_status()
                    if hasattr(self, 'license_method_combo') and self.license_method_combo is not None:
                        self.license_method_combo.setEnabled(True)
                        method = self.license_method_combo.itemData(self.license_method_combo.currentIndex())
                        if hasattr(self, 'license_activate_btn') and self.license_activate_btn is not None:
                            self.license_activate_btn.setEnabled(bool(method))
                    elif hasattr(self, 'license_activate_btn') and self.license_activate_btn is not None:
                        self.license_activate_btn.setEnabled(True)
                    if hasattr(self, 'license_status_label') and self.license_status_label is not None:
                        self.license_status_label.setText(msg.get("text", ""))
                        self.license_status_label.setStyleSheet(
                            f"color: {msg.get('color', '#AEB8C3')}; border: none; font-size: 12px; font-weight: 600;"
                        )
                    if msg.get("color") in ("#55D67A", "#FFB86C"):
                        self.refresh_license_status()
        except queue.Empty:
            pass

    @pyqtSlot()
    def animate_spinner(self):
        if self.is_processing:
            # 60 FPS'te önceki hareket hızını koru; yalnızca kare aralığını yarıya indir.
            self._wave_phase = (getattr(self, '_wave_phase', 0.0) + 0.0475) % (2 * math.pi)
            wave_pixmap = self._create_wave_dots_pixmap(self._wave_phase)
            self._cached_wave_pixmap = wave_pixmap
            for c in (self.console_debloat, self.console_iso, self.console_anti, self.console_dpi_tester):
                if c is not None:
                    c.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl("winkit_wave.png"), wave_pixmap)
                    c.viewport().update()

            if self.active_page == "iso":
                self.inject_btn.setText("İŞLEM SÜRÜYOR")
            elif self.active_page in ("debloat", "debloat_console"):
                self.apply_btn.setText("İŞLEM SÜRÜYOR")

            if hasattr(self, 'active_progress_base') and self.active_progress_base:
                clean_base = str(self.active_progress_base).lstrip("> ").strip()
                pct_str = f" [%{self.active_progress_pct}]" if self.active_progress_pct is not None else ""
                self._replace_console_block(
                    self._active_progress_row,
                    [
                        ("• ", "#8C9BA8"),
                        (clean_base, getattr(self, 'active_progress_color', "#E7ECF2")),
                        (pct_str, getattr(self, 'active_progress_pct_color', getattr(self, 'active_progress_color', "#E63B4D"))),
                    ],
                    target=self._active_progress_target,
                    show_spinner=True,
                )

    def play_finish_sound(self):
        threading.Thread(target=lambda: winsound.Beep(650, 60), daemon=True).start()

    # ---------- RESTORE OVERLAY (yerini aldı: show_restore_popup vb.) ----------
    def show_restore_popup(self, task_type, cancel_on_close=False):
        self.restore_task_type = task_type
        if self.popup_overlay is not None:
            try:
                self.removeEventFilter(self.popup_overlay)
            except Exception:
                pass
            self.popup_overlay.close()
            self.popup_overlay = None
        self.popup_overlay = RestoreOverlay(self, task_type, cancel_on_close)
        pw = self.width() if callable(getattr(self, "width", None)) else getattr(self, "width", 1040)
        ph = self.height() if callable(getattr(self, "height", None)) else getattr(self, "height", 720)
        self.popup_overlay.setGeometry(0, 0, pw, ph)
        self.installEventFilter(self.popup_overlay)
        self.popup_overlay.show()
        self.popup_overlay.raise_()

    def run_restore_and_task(self, overlay):
        if hasattr(overlay, "start_restore_label_update"):
            try:
                overlay.start_restore_label_update()
            except Exception:
                pass
        threading.Thread(target=lambda: self._popup_restore_worker(overlay, enable_if_disabled=True), daemon=True).start()

    def _popup_restore_worker(self, overlay, enable_if_disabled=True):
        ok, res = create_system_restore_point(timeout=60, enable_if_disabled=enable_if_disabled)
        if not ok:
            self.ui_queue.put({
                "action": "log",
                "text": f"[!] Sistem geri yükleme noktası oluşturulamadı: {res[:120]}",
                "color": "#FFB86C",
                "target": "debloat",
            })
            self.ui_queue.put({
                "action": "restore_failed",
                "overlay": overlay,
                "error": res,
            })
        else:
            self.ui_queue.put({
                "action": "log",
                "text": f"• Sistem geri yükleme noktası oluşturuldu: {res}",
                "color": "#55D67A",
                "target": "debloat",
            })
            self.ui_queue.put({"action": "restore_complete", "overlay": overlay})

    def cancel_restore_overlay(self, overlay):
        """Kullanıcı çarpı tuşuna bastığında popup'ı kapatır, işlemi başlatmaz."""
        if overlay:
            overlay.close()
        self.popup_overlay = None

    def skip_restore_and_task(self, overlay):
        if overlay:
            overlay.close()
        self.popup_overlay = None
        if hasattr(self, 'restore_task_type') and self.restore_task_type == "debloat":
            self.actual_start_debloat()
        elif hasattr(self, 'restore_task_type') and self.restore_task_type == "iso":
            self.start_injection_thread()

    def close_popup_and_start_task(self, overlay):
        if overlay:
            overlay.close()
        self.popup_overlay = None
        if self.restore_task_type == "debloat":
            self.actual_start_debloat()
        elif self.restore_task_type == "iso":
            self.start_injection_thread()

    # ---------- sidebar ----------
    def _animate_sidebar(self, open_sidebar):
        if self.sidebar_anim is not None:
            self.sidebar_anim.stop()
        target = self.sidebar_width if open_sidebar else 0
        self.sidebar_anim = QPropertyAnimation(self.sidebar_frame, b"maximumWidth")
        self.sidebar_anim.setDuration(350)
        self.sidebar_anim.setStartValue(self.sidebar_frame.maximumWidth())
        self.sidebar_anim.setEndValue(target)
        self.sidebar_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.sidebar_anim.start()
        self.sidebar_open = open_sidebar
        self.menu_btn.set_active(open_sidebar)

    def _close_sidebar_if_needed(self):
        if self.sidebar_open and not (
                self.sidebar_frame.underMouse() or self.menu_btn.underMouse()
        ):
            self._animate_sidebar(False)

    def _animate_menu_shift(self, shift_right):
        # Sadece pozisyon animasyonu; rotation kaldırıldı.
        target_x = 12 if shift_right else 5
        anim = QPropertyAnimation(self.menu_btn, b"pos")
        anim.setDuration(200)
        anim.setStartValue(self.menu_btn.pos())
        end_pos = self.menu_btn.pos()
        end_pos.setX(target_x)
        anim.setEndValue(end_pos)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.start()

    def eventFilter(self, obj, event):
        if obj == self.menu_btn:
            if event.type() == QEvent.Type.Enter:
                self.sidebar_close_timer.stop()
                if not self.sidebar_open:
                    self._animate_sidebar(True)
                self._animate_menu_shift(True)
            elif event.type() == QEvent.Type.Leave:
                self.sidebar_close_timer.start(80)
                self._animate_menu_shift(False)
        elif obj == self.sidebar_frame:
            if event.type() == QEvent.Type.Enter:
                self.sidebar_close_timer.stop()
            elif event.type() == QEvent.Type.Leave:
                self.sidebar_close_timer.start(80)
        return super().eventFilter(obj, event)

    # ---------- WinKit sayfa navigasyonu ----------
    def show_page(self, page):
        if page in ("debloat", "debloat_console"):
            self.last_debloat_subpage = page

        map_pages = {
            "iso": self.iso_frame,
            "iso_console": self.iso_console_frame,
            "debloat": self.debloat_frame,
            "debloat_console": self.debloat_console_frame,
            "app_checklist": self.app_checklist_frame,
            "shutup_checklist": self.shutup_checklist_frame,
            "anti_dpi": self.anti_dpi_frame,
            "anti_console": self.anti_console_frame,
            "dpi_tester": self.dpi_tester_frame,
            "dpi_tester_console": self.dpi_tester_console_frame,
            "restore": self.restore_frame,
            "license": self.license_frame,
            "key_remap": self.key_remap_frame,
        }
        target = map_pages[page]
        current = self.stacked_pages.currentWidget()

        if self._console_transition_anim is not None:
            self._console_transition_anim.stop()
            self._console_transition_anim = None
        if self._transition_widget is not None:
            self._transition_widget.setGraphicsEffect(None)
            if self._transition_widget.property("page_transition_overlay"):
                self._transition_widget.deleteLater()
            self._transition_widget = None

        if current is not None and current != target:
            old_snapshot = current.grab()
            self.stacked_pages.setCurrentWidget(target)
            # Önceki sayfanın tek karelik görüntüsünü yeni sayfanın üzerinde
            # erit. Gerçek widget geometrisi hiç animasyona girmediği için ISO
            # seçim çubuğu ara koordinatlarda görünmez ve geçiş düşük maliyetli kalır.
            overlay = QLabel(self.stacked_pages)
            overlay.setProperty("page_transition_overlay", True)
            overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            overlay.setPixmap(old_snapshot)
            overlay.setGeometry(self.stacked_pages.rect())
            overlay.show()
            overlay.raise_()
            effect = QGraphicsOpacityEffect(overlay)
            overlay.setGraphicsEffect(effect)
            effect.setOpacity(1.0)
            opacity_anim = QPropertyAnimation(effect, b"opacity")
            opacity_anim.setDuration(220)
            opacity_anim.setStartValue(1.0)
            opacity_anim.setEndValue(0.0)
            opacity_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            transition = QParallelAnimationGroup(self)
            transition.addAnimation(opacity_anim)
            self._console_transition_anim = transition
            self._transition_widget = overlay
            self._console_transition_anim.finished.connect(
                lambda widget=overlay: self._finish_page_transition(widget)
            )
            self._console_transition_anim.start()
        else:
            self.stacked_pages.setCurrentWidget(target)

        self.active_page = page
        if self.page_switch_btn is not None:
            self.page_switch_btn.hide()

        active_button = {
            "iso": self.btn_iso,
            "iso_console": self.btn_iso,
            "debloat": self.btn_debloat,
            "debloat_console": self.btn_debloat,
            "app_checklist": self.btn_apps,
            "shutup_checklist": self.btn_privacy,
            "anti_dpi": self.btn_anti_dpi,
            "anti_console": self.btn_anti_dpi,
            "dpi_tester": self.btn_dpi_tester,
            "dpi_tester_console": self.btn_dpi_tester,
            "restore": self.btn_restore,
            "license": self.btn_license,
            "key_remap": self.btn_key_remap,
        }.get(page)
        for button in (
            self.btn_debloat,
            self.btn_iso,
            self.btn_apps,
            self.btn_privacy,
            self.btn_anti_dpi,
            self.btn_dpi_tester,
            self.btn_key_remap,
            self.btn_restore,
            self.btn_license,
        ):
            if button is not None:
                button.set_active(button is active_button)

    def _finish_page_transition(self, widget):
        widget.setGraphicsEffect(None)
        if widget.property("page_transition_overlay"):
            widget.deleteLater()
        if self._transition_widget is widget:
            self._transition_widget = None
        self._console_transition_anim = None

    def on_debloat_sidebar_click(self):
        if self.is_processing and getattr(self, 'current_worker', None) == "debloat":
            self.show_page("debloat_console")
        else:
            self.show_page("debloat")

    def _set_navigation_enabled(self, enabled):
        for button in (
            self.btn_debloat,
            self.btn_iso,
            self.btn_apps,
            self.btn_privacy,
            self.btn_anti_dpi,
            self.btn_dpi_tester,
            self.btn_restore,
            self.btn_license,
        ):
            if button is not None:
                button.setEnabled(bool(enabled))

    def toggle_debloat_view(self):
        if self.is_processing:
            return
        if self.active_page == "debloat_console":
            self.show_page("debloat")
        else:
            self.show_page("debloat_console")

    # ---------- interface ----------
    def init_main_interface(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # WinKit başlığı tüm pencere boyunca uzanır; sidebar başlığın altında
        # başlar. Bu düzen referans tasarımdaki ana oranları korur.
        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(58)
        top_bar.setStyleSheet(
            "QFrame#TopBar { background-color: #0A0D11; "
            "border: none; border-bottom: 1px solid #252D36; }"
        )
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(18, 0, 18, 0)

        brand_mark = WinKitMark()
        top_layout.addWidget(brand_mark)
        brand = QLabel("WinKit")
        brand.setStyleSheet(
            "color: #F7F9FB; font-size: 16px; font-weight: 650; letter-spacing: 0.4px; "
            "background: transparent; border: none;"
        )
        top_layout.addWidget(brand)
        top_layout.addStretch()

        display_version, build, product_name = get_current_windows_release()
        version_parts = [
            product_name or "Windows 11",
            display_version or SUPPORTED_WINDOWS_VERSION,
            build or SUPPORTED_WINDOWS_BUILD,
        ]
        
        self.status_toast = StatusToastWidget()
        top_layout.addWidget(self.status_toast)
        top_layout.addSpacing(12)

        winver_badge = QFrame()
        winver_badge.setFixedHeight(24)
        winver_badge.setStyleSheet(
            "QFrame { background-color: #11161D; border: 1px solid #232D37; border-radius: 4px; }"
        )
        badge_layout = QHBoxLayout(winver_badge)
        badge_layout.setContentsMargins(8, 1, 8, 1)
        badge_layout.setSpacing(6)
        
        self.winver_label = QLabel(" · ".join(version_parts))
        self.winver_label.setStyleSheet(
            "color: #8C9BA8; font-size: 11px; font-weight: 500; "
            "background-color: transparent; border: none; padding: 0;"
        )
        badge_layout.addWidget(self.winver_label)
        top_layout.addWidget(winver_badge)
        main_layout.addWidget(top_bar)

        body = QFrame()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("Sidebar")
        self.sidebar_frame.setStyleSheet(
            f"QFrame#Sidebar {{ background-color: {self.bg_sidebar}; border: none; }}"
        )
        self.sidebar_frame.setFixedWidth(self.sidebar_width)
        self.sidebar_frame.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )

        sidebar_layout = QVBoxLayout(self.sidebar_frame)
        sidebar_layout.setContentsMargins(10, 20, 10, 12)
        sidebar_layout.setSpacing(4)

        modules_label = QLabel("Seçenekler")
        modules_label.setStyleSheet(
            "color: #8C9BA8; font-size: 10.5px; font-weight: 700; "
            "letter-spacing: 1.2px; padding: 6px 10px 6px 10px; border: none; background: transparent;"
        )
        sidebar_layout.addWidget(modules_label)

        self.btn_debloat = RiftNavButton("Debloat", "debloat")
        self.btn_iso = RiftNavButton("ISO aracı", "iso")
        self.btn_apps = RiftNavButton("Uygulamalar", "apps", sub_item=True)
        self.btn_privacy = RiftNavButton("Gizlilik", "privacy", sub_item=True, branch_last=True)
        self.btn_anti_dpi = RiftNavButton("Anti-DPI", "anti_dpi")
        self.btn_dpi_tester = RiftNavButton("DPI test aracı", "dpi_tester", sub_item=True, branch_last=True)
        self.btn_key_remap = RiftNavButton("Tuş Dönüştürücü", "key_remap")
        self.btn_restore = RiftNavButton("Geri yükle", "restore")
        self.btn_license = RiftNavButton("Lisanslama", "license")
        self.btn_debloat.clicked.connect(self.on_debloat_sidebar_click)
        self.btn_iso.clicked.connect(lambda: self.show_page("iso"))
        self.btn_apps.clicked.connect(self.open_app_checklist_view)
        self.btn_privacy.clicked.connect(self.open_shutup_checklist_view)
        self.btn_anti_dpi.clicked.connect(lambda: self.show_page("anti_dpi"))
        self.btn_dpi_tester.clicked.connect(lambda: self.show_page("dpi_tester"))
        self.btn_key_remap.clicked.connect(lambda: self.show_page("key_remap"))
        self.btn_restore.clicked.connect(lambda: self.show_page("restore"))
        self.btn_license.clicked.connect(self.open_license_page)
        sidebar_layout.addWidget(self.btn_iso)
        sidebar_layout.addSpacing(4)
        sidebar_layout.addWidget(self.btn_debloat)
        sidebar_layout.addWidget(self.btn_apps)
        sidebar_layout.addWidget(self.btn_privacy)
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(self.btn_anti_dpi)
        sidebar_layout.addWidget(self.btn_dpi_tester)
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(self.btn_key_remap)
        sidebar_layout.addSpacing(4)
        sidebar_layout.addWidget(self.btn_restore)
        sidebar_layout.addWidget(self.btn_license)
        sidebar_layout.addStretch()

        body_layout.addWidget(self.sidebar_frame)

        self.right_area = QFrame()
        self.right_area.setStyleSheet(f"background-color: {self.bg_window};")
        body_layout.addWidget(self.right_area, 1)

        content_layout = QVBoxLayout(self.right_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.page_switch_btn = QPushButton("Konsol")
        self.page_switch_btn.clicked.connect(self.toggle_debloat_view)
        self.page_switch_btn.hide()

        card_container = QFrame()
        card_container.setStyleSheet(f"background-color: {self.bg_card};")
        content_layout.addWidget(card_container, 1)

        card_layout = QVBoxLayout(card_container)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(self.stacked_pages)

        # Build pages
        self.iso_frame = QFrame()
        self.iso_console_frame = QFrame()
        self.debloat_frame = QFrame()
        self.debloat_console_frame = QFrame()
        self.app_checklist_frame = QFrame()
        self.shutup_checklist_frame = QFrame()
        self.anti_dpi_frame = QFrame()
        self.anti_console_frame = QFrame()
        self.dpi_tester_frame = QFrame()
        self.dpi_tester_console_frame = QFrame()
        self.restore_frame = QFrame()
        self.license_frame = QFrame()
        self.key_remap_frame = QFrame()

        self.stacked_pages.addWidget(self.iso_frame)
        self.stacked_pages.addWidget(self.iso_console_frame)
        self.stacked_pages.addWidget(self.debloat_frame)
        self.stacked_pages.addWidget(self.debloat_console_frame)
        self.stacked_pages.addWidget(self.app_checklist_frame)
        self.stacked_pages.addWidget(self.shutup_checklist_frame)
        self.stacked_pages.addWidget(self.anti_dpi_frame)
        self.stacked_pages.addWidget(self.anti_console_frame)
        self.stacked_pages.addWidget(self.dpi_tester_frame)
        self.stacked_pages.addWidget(self.dpi_tester_console_frame)
        self.stacked_pages.addWidget(self.restore_frame)
        self.stacked_pages.addWidget(self.license_frame)
        self.stacked_pages.addWidget(self.key_remap_frame)

        self.build_iso_frame()
        self.build_iso_console_frame()
        self.build_debloat_frame()
        self.build_debloat_console_frame()
        self.build_app_checklist_frame()
        self.build_shutup_checklist_frame()
        self.build_anti_dpi_frame()
        self.build_anti_console_frame()
        self.build_dpi_tester_frame()
        self.build_dpi_tester_console_frame()
        self.build_restore_frame()
        self.build_license_frame()
        self.build_key_remap_frame()

        # İlk açılışta doğru sayfayı göster ve buton stillerini ayarla
        self.show_page(self.active_page)
        main_layout.addWidget(body, 1)

    # ---------- Checkbox flash animasyonu (artık kullanılmıyor) ----------
    def flash_checkbox(self, chk):
        """Artık gerek kalmadı, AnimatedTickCheckBox animasyonu ile aynı iş yapılıyor."""
        pass

    def build_anti_dpi_frame(self):
        layout = QVBoxLayout(self.anti_dpi_frame)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        section = QLabel("Ağ araçları / Anti-DPI")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; border: none;"
        )
        header = QHBoxLayout()
        title = QLabel("Zapret ve Güvenli DNS")
        title.setStyleSheet("color: #F4F7FA; font-size: 23px; font-weight: 700; border: none;")
        self.anti_status_label = QLabel("Kontrol ediliyor")
        self.anti_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.anti_status_label.setStyleSheet(
            "color: #8B96A2; background-color: #14191F; border: 1px solid #39434D; "
            "border-radius: 11px; padding: 4px 10px; font-size: 10px; font-weight: 700;"
        )
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.anti_status_label)
        description = QLabel(
            "İnternet kısıtlamalarını ve DPI engellerini aşmak için Zapret servisini kurar, "
            "güvenli ve şifreli DNS (DoH) yapılandırmasını sisteme uygular."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #929DA8; font-size: 12px; border: none;")
        layout.addWidget(section)
        layout.addLayout(header)
        layout.addWidget(description)

        feature_grid = QGridLayout()
        feature_grid.setSpacing(10)
        features = [
            ("ZAPRET", "Windows servisi", "Otomatik başlatılır ve DPI trafiğini işler."),
            ("DOH", "Cloudflare", "1.1.1.1 ve 1.0.0.1, şifreli DNS'e yükseltilir."),
            (
                "IPV6",
                "IPv4 odaklı profil",
                "Global IPv6 henüz yaygın olmadığı için kapatılır; IPv6 üzerinden akan sitelerde Zapret devre dışı kalabilir.",
            ),
        ]
        for index, (tag, name, detail) in enumerate(features):
            card = QFrame()
            card.setObjectName(f"AntiFeature{index}")
            card.setMinimumHeight(118)
            card.setStyleSheet(
                f"QFrame#AntiFeature{index} {{ background-color: #0D1116; "
                "border: 1px solid #27313A; border-radius: 10px; }\n"
                f"QFrame#AntiFeature{index} QLabel {{ background: transparent; background-color: transparent; border: none; }}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 13, 15, 13)
            card_layout.setSpacing(5)
            tag_label = QLabel(tag)
            tag_label.setStyleSheet(
                "color: #E63B4D; font-size: 10px; font-weight: 750; letter-spacing: 1px; border: none; background: transparent;"
            )
            name_label = QLabel(name)
            name_label.setStyleSheet("color: #F0F3F6; font-size: 14px; font-weight: 650; border: none; background: transparent;")
            detail_label = QLabel(detail)
            detail_label.setWordWrap(True)
            detail_label.setStyleSheet("color: #87929D; font-size: 10px; border: none; background: transparent;")
            card_layout.addWidget(tag_label)
            card_layout.addWidget(name_label)
            card_layout.addWidget(detail_label)
            card_layout.addStretch()
            feature_grid.addWidget(card, 0, index)
        layout.addLayout(feature_grid)

        # Zapret Version Selector Card
        version_card = QFrame()
        version_card.setObjectName("ZapretVersionCard")
        version_card.setStyleSheet(
            "QFrame#ZapretVersionCard { background-color: #0D1116; border: 1px solid #27313A; "
            "border-radius: 9px; }"
        )
        ver_layout = QHBoxLayout(version_card)
        ver_layout.setContentsMargins(14, 11, 14, 11)
        ver_title = QLabel("Zapret motor sürümü:")
        ver_title.setStyleSheet("color: #717D88; font-size: 9px; font-weight: 700; border: none; background: transparent;")
        self.anti_ver_v1_radio = AnimatedRadioButton("Zapret v1 (winws)")
        self.anti_ver_v2_radio = AnimatedRadioButton("Zapret v2 (winws2 - Gelişmiş)")
        radio_style = (
            "QRadioButton { color: #E7ECF2; font-size: 11px; border: none; background: transparent; spacing: 8px; }\n"
            "QRadioButton::indicator { width: 16px; height: 16px; border: none; background: transparent; }"
        )
        self.anti_ver_v1_radio.setStyleSheet(radio_style)
        self.anti_ver_v2_radio.setStyleSheet(radio_style)
        self.anti_ver_v2_radio.setChecked(True)
        CTkToolTip(self.anti_ver_v1_radio, "Zapret v1 (winws) - Klasik C tabanlı motor.\nPaketleri TCP seviyesinde bölerek (split2), TTL manipülasyonu (autottl) ve sahte paket (fake desync) enjekte ederek ISS filtrelerini atlatır.\nDüşük kaynak tüketir ve temel engellemelerde yüksek kararlılık sağlar.", risk_level=0)
        CTkToolTip(self.anti_ver_v2_radio, "Zapret v2 (winws2) - Lua betik motorlu yeni nesil sürüm.\nGelişmiş TLS ClientHello modifikasyonu (rnd, dupsid, padencap), SNI sahteleme ve dinamik çoklu paket bölme (multisplit) yeteneklerine sahiptir.\nDerin paket incelemesi (DPI) uygulayan karmaşık ISP filtrelerini aşmak için önerilir.", risk_level=0)
        ver_layout.addWidget(ver_title)
        ver_layout.addSpacing(10)
        ver_layout.addWidget(self.anti_ver_v1_radio)
        ver_layout.addSpacing(10)
        ver_layout.addWidget(self.anti_ver_v2_radio)
        ver_layout.addStretch()
        layout.addWidget(version_card)

        location_card = QFrame()
        location_card.setObjectName("ZapretLocation")
        location_card.setStyleSheet(
            "QFrame#ZapretLocation { background-color: #0A0D11; border: 1px solid #222B34; "
            "border-radius: 9px; }"
        )
        location_layout = QHBoxLayout(location_card)
        location_layout.setContentsMargins(14, 11, 14, 11)
        location_title = QLabel("Kurulum konumu")
        location_title.setStyleSheet("color: #717D88; font-size: 9px; font-weight: 700; border: none;")
        location_value = QLabel(str(get_documents_directory() / "Zapret"))
        location_value.setStyleSheet("color: #C9D0D7; font-size: 11px; border: none;")
        location_layout.addWidget(location_title)
        location_layout.addStretch()
        location_layout.addWidget(location_value)
        layout.addWidget(location_card)
        layout.addStretch()

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.anti_remove_btn = QPushButton("Zapret servisini kaldır")
        self.anti_remove_btn.setFixedHeight(48)
        self.anti_remove_btn.clicked.connect(lambda: self.start_anti_dpi_task(False))
        self.anti_install_btn = QPushButton("Zapret motorunu kur")
        self.anti_install_btn.setFixedHeight(48)
        self.anti_install_btn.setStyleSheet(
            "QPushButton { background-color: #E63B4D; color: #FFFFFF; "
            "border: 1px solid #FF6574; border-radius: 8px; font-weight: bold; }\n"
            "QPushButton:hover { background-color: #FF5263; }\n"
            "QPushButton:disabled { background-color: #252B31; color: #717A84; border-color: #303A45; }"
        )
        self.anti_install_btn.clicked.connect(lambda: self.start_anti_dpi_task(True))
        button_row.addWidget(self.anti_remove_btn, 1)
        button_row.addWidget(self.anti_install_btn, 2)
        layout.addLayout(button_row)

    def build_anti_console_frame(self):
        layout = QVBoxLayout(self.anti_console_frame)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        section = QLabel("Anti-DPI / İşlem")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 9px; font-weight: 700; letter-spacing: 1px;"
        )
        title = QLabel("Zapret İşlem Konsolu")
        title.setStyleSheet("color: #F4F7FA; font-size: 20px; font-weight: 700;")
        title_box.addWidget(section)
        title_box.addWidget(title)
        title_row.addLayout(title_box)
        title_row.addStretch()
        self.anti_console_loading_ring = None
        layout.addLayout(title_row)

        self.console_anti = SmoothConsoleTextEdit()
        self.console_anti.setReadOnly(True)
        self.console_anti.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.console_anti.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.console_anti.setFont(QFont("Consolas", 13))
        self.console_anti.setStyleSheet(
            "QTextEdit { background-color: #06080A; border: 1px solid #7E2934; "
            "border-left: 2px solid #E63B4D; border-radius: 6px; "
            "padding: 14px; color: #C9D1DA; selection-background-color: #6D202B; }"
        )
        layout.addWidget(self.console_anti, 1)
        self.anti_console_back_btn = QPushButton("Konsolu kapat")
        self.anti_console_back_btn.setFixedHeight(45)
        self.anti_console_back_btn.clicked.connect(lambda: self.show_page("anti_dpi"))
        layout.addWidget(self.anti_console_back_btn)

    def _scan_anti_status(self):
        try:
            result = subprocess.run(
                ["sc.exe", "query", "ZapretService"],
                capture_output=True,
                text=True,
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
                timeout=12,
                check=False,
            )
            installed = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            installed = False
        self.ui_queue.put({"action": "anti_status", "installed": installed})

    def _run_powershell_checked(self, script, timeout=120):
        # Windows PowerShell varsayılan olarak hata akışını CLIXML'e çevirebilir;
        # bu da gerçek hata yerine yalnızca "kod 1" görülmesine yol açıyordu.
        # UTF-8 metin çıkışı ve dış try/catch ile son hatayı düz metin koru.
        full_script = (
            "$ProgressPreference = 'SilentlyContinue'\n"
            "$WarningPreference = 'SilentlyContinue'\n"
            "$InformationPreference = 'SilentlyContinue'\n"
            "$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
            "try {\n& {\n" + script + "\n}\n} catch {\n"
            "[Console]::Error.WriteLine([string]$_.Exception.Message)\n"
            "exit 1\n}\n"
        )
        temp_ps1 = None
        try:
            # Win32 CreateProcessW komut satırı sınırını (32.767 karakter)
            # ve cmd sınırını (8.191 karakter) aşmamak için 3000 karakterden
            # uzun scriptleri güvenli geçici UTF-8 dosyasıyla çalıştır.
            if len(full_script) > 3000:
                fd, temp_ps1 = tempfile.mkstemp(prefix="winkit_run_", suffix=".ps1")
                with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                    f.write(full_script)
                cmd = [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-OutputFormat", "Text",
                    "-ExecutionPolicy", "Bypass",
                    "-File", temp_ps1,
                ]
            else:
                encoded = base64.b64encode(full_script.encode("utf-16le")).decode("ascii")
                cmd = [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-OutputFormat", "Text",
                    "-ExecutionPolicy", "Bypass",
                    "-EncodedCommand", encoded,
                ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
                timeout=timeout,
                check=False,
            )
        finally:
            if temp_ps1 and os.path.exists(temp_ps1):
                try:
                    os.unlink(temp_ps1)
                except OSError:
                    pass
        if result.returncode != 0:
            raw = (result.stderr + "\n" + result.stdout).strip()
            lines = [
                line.strip()
                for line in raw.splitlines()
                if line.strip() and not line.strip().startswith(("#<", "<Objs", "<Obj", "<TN", "<T>", "<MS>", "<I64", "<PR", "<AV", "<SD", "</Obj", "</MS", "</TN", "</PR"))
            ]
            detail = lines[-1] if lines else f"PowerShell kodu {result.returncode}"
            raise RuntimeError(detail[:260])
        return result.stdout

    def _is_zapret_already_installed(self):
        return is_zapret_installed()

    def start_anti_dpi_task(self, install):
        if self.is_processing:
            return
        if install and self._is_zapret_already_installed():
            diag = ZapretAlreadyInstalledDialog(self)
            diag.exec()
            if hasattr(self, "status_toast") and self.status_toast:
                self.status_toast.show_message(
                    "Zapret zaten sisteminizde kurulu! Lütfen önce mevcut servisi kaldırın.",
                    severity="warning",
                )
            return

        restore_dns = True
        if not install:
            diag = ZapretDnsRestoreDialog(self)
            if diag.exec() == QDialog.DialogCode.Rejected:
                return
            restore_dns = getattr(diag, "restore_dns", True)

        self.is_processing = True
        self.current_worker = "anti"
        self._set_navigation_enabled(False)
        if self.console_anti is not None:
            self.console_anti.clear()
        self._active_progress_row = None
        self._active_progress_target = None
        self.active_progress_base = None
        self.active_progress_pct = None
        self.anti_install_btn.setEnabled(False)
        self.anti_remove_btn.setEnabled(False)
        self.anti_console_back_btn.setEnabled(False)
        self.show_page("anti_console")
        if self.anti_console_loading_ring is not None:
            self.anti_console_loading_ring.start()
        self.spinner_timer.start(16)
        threading.Thread(
            target=self._anti_dpi_worker,
            args=(bool(install), restore_dns),
            daemon=True,
        ).start()

    def _anti_stage_start(self, stage_id, text):
        self.ui_queue.put({
            "action": "stage_start",
            "stage_id": stage_id,
            "text_base": text,
            "color": "#E7ECF2",
            "target": "anti",
        })

    def _anti_stage_finish(self, stage_id, result="✔", color="#55D67A"):
        self.ui_queue.put({
            "action": "stage_finish",
            "stage_id": stage_id,
            "result": result,
            "result_color": color,
            "target": "anti",
        })

    def _anti_dpi_worker(self, install, restore_dns=True):
        try:
            source_dir, install_dir = get_zapret_paths(Path(self.get_binary_path("zapret")))
            if install:
                use_v1 = hasattr(self, 'anti_ver_v1_radio') and self.anti_ver_v1_radio is not None and self.anti_ver_v1_radio.isChecked()
                install_zapret(
                    source_dir,
                    install_dir,
                    use_v1=use_v1,
                    stage_start=self._anti_stage_start,
                    stage_finish=self._anti_stage_finish,
                )
                self.ui_queue.put({
                    "action": "log_segments",
                    "segments": [
                        ("• ", "#8C9BA8"),
                        ("Zapret ", "#E7ECF2"),
                        ("kuruldu", "#55D67A"),
                        ("  ✔", "#55D67A"),
                    ],
                    "target": "anti",
                })
            else:
                remove_zapret(
                    install_dir,
                    restore_dns=restore_dns,
                    stage_start=self._anti_stage_start,
                    stage_finish=self._anti_stage_finish,
                )
                self.ui_queue.put({
                    "action": "log_segments",
                    "segments": [
                        ("• ", "#8C9BA8"),
                        ("Zapret ", "#E7ECF2"),
                        ("kaldırıldı", "#FF7582"),
                        ("  ✔", "#55D67A"),
                    ],
                    "target": "anti",
                })
        except Exception as exc:
            self.ui_queue.put({
                "action": "log_segments",
                "segments": [
                    ("• ", "#8C9BA8"),
                    ("HATA: ", "#FF5C6B"),
                    (str(exc), "#E7ECF2"),
                ],
                "target": "anti",
            })
        finally:
            self.ui_queue.put({"action": "finish_anti", "target": "anti"})


# =========================================================================
    # DPI TESTER (BLOCKCHECK) MODÜLÜ
    # =========================================================================

    def build_dpi_tester_frame(self):
        layout = QVBoxLayout(self.dpi_tester_frame)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        section = QLabel("Ağ araçları / DPI test aracı")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; border: none;"
        )
        title = QLabel("DPI test aracı")
        title.setStyleSheet("color: #F4F7FA; font-size: 23px; font-weight: 700; border: none;")
        subtitle = QLabel(
            "Bağlantınızdaki engelleme yöntemlerini test ederek servis sağlayıcınıza en uygun Zapret bypass profilini belirler."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #929DA8; font-size: 12px; border: none;")

        layout.addWidget(section)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Config Card
        config_card = QFrame()
        config_card.setStyleSheet(
            "background-color: #0D1116; border: 1px solid #27313A; border-radius: 10px;"
        )
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(16, 14, 16, 14)
        config_layout.setSpacing(14)

        # Zapret Version Selection
        ver_box = QHBoxLayout()
        ver_label = QLabel("Zapret motoru:")
        ver_label.setStyleSheet("color: #C9D0D7; font-size: 11px; font-weight: 700; border: none; background: transparent;")
        self.dpi_ver_v1_radio = AnimatedRadioButton("Zapret v1 (winws)")
        self.dpi_ver_v2_radio = AnimatedRadioButton("Zapret v2 (winws2 - Gelişmiş)")
        self.dpi_ver_v2_radio.setChecked(True)
        radio_style = (
            "QRadioButton { color: #E7ECF2; font-size: 12px; border: none; background: transparent; spacing: 8px; } "
            "QRadioButton::indicator { width: 16px; height: 16px; border: none; background: transparent; }"
        )
        self.dpi_ver_v1_radio.setStyleSheet(radio_style)
        self.dpi_ver_v2_radio.setStyleSheet(radio_style)
        CTkToolTip(self.dpi_ver_v1_radio, "Zapret v1 (winws) - Klasik C tabanlı motor.\nPaketleri TCP seviyesinde bölerek (split2), TTL manipülasyonu (autottl) ve sahte paket (fake desync) enjekte ederek ISS filtrelerini atlatır.\nDüşük kaynak tüketir ve temel engellemelerde yüksek kararlılık sağlar.", risk_level=0)
        CTkToolTip(self.dpi_ver_v2_radio, "Zapret v2 (winws2 - Gelişmiş) - Lua betik motorlu yeni nesil sürüm.\nGelişmiş TLS ClientHello modifikasyonu (rnd, dupsid, padencap), SNI sahteleme ve dinamik çoklu paket bölme (multisplit) yeteneklerine sahiptir.\nDerin paket incelemesi (DPI) uygulayan karmaşık ISP filtrelerini aşmak için önerilir.", risk_level=0)
        ver_box.addWidget(ver_label)
        ver_box.addSpacing(10)
        ver_box.addWidget(self.dpi_ver_v1_radio)
        ver_box.addSpacing(12)
        ver_box.addWidget(self.dpi_ver_v2_radio)
        ver_box.addStretch()
        config_layout.addLayout(ver_box)

        # Domain Input
        dom_box = QVBoxLayout()
        dom_label = QLabel("Hedef alan adları:")
        dom_label.setStyleSheet("color: #C9D0D7; font-size: 11px; font-weight: 700; border: none; background: transparent;")
        self.dpi_domains_input = QLineEdit()
        self.dpi_domains_input.setPlaceholderText("discord.com, roblox.com ...")
        self.dpi_domains_input.setFixedHeight(38)
        self.dpi_domains_input.setStyleSheet(
            "QLineEdit { background-color: #06080A; border: 1px solid #323C47; border-radius: 6px; "
            "color: #F0F3F6; font-size: 12px; padding: 0 10px; selection-background-color: #E63B4D; } "
            "QLineEdit:focus { border-color: #E63B4D; }"
        )
        dom_hint = QLabel("Birden fazla alan adı için virgül veya boşlukla ayırın (Boş bırakılırsa varsayılan hedefler test edilir).")
        dom_hint.setStyleSheet("color: #717D88; font-size: 10px; border: none; background: transparent;")
        dom_box.addWidget(dom_label)
        dom_box.addWidget(self.dpi_domains_input)
        dom_box.addWidget(dom_hint)
        config_layout.addLayout(dom_box)

        # Scan Mode & Protocols Row
        opt_grid = QGridLayout()
        opt_grid.setSpacing(14)
        opt_grid.setColumnStretch(0, 1)
        opt_grid.setColumnStretch(1, 1)

        mode_label = QLabel("Tarama seviyesi:")
        mode_label.setStyleSheet("color: #C9D0D7; font-size: 11px; font-weight: 700; border: none; background: transparent;")
        self.dpi_scan_mode_combo = RiftComboBox()
        self.dpi_scan_mode_combo.addItems([
            "Derin ve Tam (Tüm Kurallar)",
            "Akıllı Tarama (Hızlı & Popüler)",
            "Temel Kurallar (Hızlı Ön Test)",
        ])
        self.dpi_scan_mode_combo.setCurrentIndex(0)
        self.dpi_scan_mode_combo.setFixedHeight(36)

        proto_label = QLabel("Test edilecek protokoller:")
        proto_label.setStyleSheet("color: #C9D0D7; font-size: 11px; font-weight: 700; border: none; background: transparent;")
        proto_box = QHBoxLayout()
        proto_box.setSpacing(10)
        self.dpi_http_chk = AnimatedTickCheckBox("HTTP (Port 80)")
        self.dpi_tls12_chk = AnimatedTickCheckBox("TLS 1.2 (Port 443)")
        self.dpi_tls13_chk = AnimatedTickCheckBox("TLS 1.3 (Port 443)")
        self.dpi_http_chk.setChecked(False)
        self.dpi_tls12_chk.setChecked(False)
        self.dpi_tls13_chk.setChecked(False)
        self.dpi_http_chk_filter = TooltipHoverFilter(
            "Şifrelenmemiş web trafiği için kullanılır.\n"
            "Öneri: Çoğu modern sansür HTTPS üzerinde gerçekleştiğinden yalnızca özel HTTP testi gerekiyorsa işaretleyin.",
            self.dpi_http_chk
        )
        self.dpi_tls12_chk_filter = TooltipHoverFilter(
            "Geleneksel şifreli web bağlantıları için kullanılır. SNI bilgisi açık metindir.\n"
            "Öneri: Eski istemciler veya TLS 1.2 zorunlu kılan servisler test edilecekse seçilmelidir.",
            self.dpi_tls12_chk
        )
        self.dpi_tls13_chk_filter = TooltipHoverFilter(
            "Modern ve güvenli şifreli web trafiği standardıdır (Discord, YouTube vb.).\n"
            "Öneri: Güncel DPI engellerini ve ECH/SNI sansürünü aşma testlerinde mutlaka işaretlenmesi tavsiye edilir.",
            self.dpi_tls13_chk
        )
        chk_style = (
            "QCheckBox { color: #E7ECF2; font-size: 11px; border: none; background: transparent; spacing: 6px; } "
            "QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #485461; border-radius: 3px; background: #0E1217; } "
            "QCheckBox::indicator:checked { border: 1px solid #E63B4D; background: #E63B4D; }"
        )
        self.dpi_http_chk.setStyleSheet(chk_style)
        self.dpi_tls12_chk.setStyleSheet(chk_style)
        self.dpi_tls13_chk.setStyleSheet(chk_style)
        proto_box.addWidget(self.dpi_http_chk)
        proto_box.addWidget(self.dpi_tls12_chk)
        proto_box.addWidget(self.dpi_tls13_chk)
        proto_box.addStretch()

        opt_grid.addWidget(mode_label, 0, 0)
        opt_grid.addWidget(self.dpi_scan_mode_combo, 1, 0)
        opt_grid.addWidget(proto_label, 0, 1)
        opt_grid.addLayout(proto_box, 1, 1)
        config_layout.addLayout(opt_grid)

        layout.addWidget(config_card)
        layout.addStretch()

        # Start Button
        self.dpi_tester_start_btn = QPushButton("DPI testini başlat")
        self.dpi_tester_start_btn.setFixedHeight(48)
        self.dpi_tester_start_btn.setStyleSheet(
            "QPushButton { background-color: #E63B4D; color: #FFFFFF; "
            "border: 1px solid #FF6574; border-radius: 8px; font-weight: bold; font-size: 13px; } "
            "QPushButton:hover { background-color: #FF5263; } "
            "QPushButton:disabled { background-color: #252B31; color: #717A84; border-color: #303A45; }"
        )
        self.dpi_tester_start_btn.clicked.connect(self.start_dpi_tester_task)
        layout.addWidget(self.dpi_tester_start_btn)

    def build_dpi_tester_console_frame(self):
        layout = QVBoxLayout(self.dpi_tester_console_frame)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        section = QLabel("Anti-DPI / Test konsolu")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 9px; font-weight: 700; letter-spacing: 1px;"
        )
        title = QLabel("DPI Test Konsolu")
        title.setStyleSheet("color: #F4F7FA; font-size: 20px; font-weight: 700;")
        title_box.addWidget(section)
        title_box.addWidget(title)
        title_row.addLayout(title_box)
        title_row.addStretch()
        self.dpi_tester_loading_ring = None
        layout.addLayout(title_row)

        self.console_dpi_tester = SmoothConsoleTextEdit()
        self.console_dpi_tester.setReadOnly(True)
        self.console_dpi_tester.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.console_dpi_tester.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.console_dpi_tester.setFont(QFont("Consolas", 12))
        self.console_dpi_tester.setStyleSheet(
            "QTextEdit { background-color: #06080A; border: 1px solid #7E2934; "
            "border-left: 2px solid #E63B4D; border-radius: 6px; "
            "padding: 14px; color: #C9D1DA; selection-background-color: #6D202B; }"
        )
        layout.addWidget(self.console_dpi_tester, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.dpi_tester_cancel_btn = QPushButton("Testi iptal et")
        self.dpi_tester_cancel_btn.setFixedHeight(45)
        self.dpi_tester_cancel_btn.setEnabled(False)
        self.dpi_tester_cancel_btn.setStyleSheet(
            "QPushButton { background-color: #2D1A1E; color: #FF5C6B; border: 1px solid #7E2934; border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #3D2228; border-color: #E63B4D; } "
            "QPushButton:disabled { background-color: #1A1D20; color: #555E68; border-color: #2D3339; }"
        )
        self.dpi_tester_cancel_btn.clicked.connect(self._cancel_dpi_tester)

        self.dpi_tester_open_report_btn = QPushButton("Raporu aç")
        self.dpi_tester_open_report_btn.setFixedHeight(45)
        self.dpi_tester_open_report_btn.setEnabled(False)
        self.dpi_tester_open_report_btn.clicked.connect(self._open_dpi_report)

        self.dpi_tester_console_back_btn = QPushButton("Test ayarlarına dön")
        self.dpi_tester_console_back_btn.setFixedHeight(45)
        self.dpi_tester_console_back_btn.clicked.connect(lambda: self.show_page("dpi_tester"))

        btn_row.addWidget(self.dpi_tester_cancel_btn, 1)
        btn_row.addWidget(self.dpi_tester_open_report_btn, 1)
        btn_row.addWidget(self.dpi_tester_console_back_btn, 2)
        layout.addLayout(btn_row)

    def _cancel_dpi_tester(self):
        self._dpi_cancel_flag = True
        if hasattr(self, 'dpi_tester_cancel_btn') and self.dpi_tester_cancel_btn is not None:
            self.dpi_tester_cancel_btn.setEnabled(False)
            self.dpi_tester_cancel_btn.setText("İptal ediliyor...")

    def _open_dpi_report(self):
        report_path = get_dpi_report_path()
        if report_path.is_file():
            try:
                os.startfile(str(report_path))
            except Exception:
                pass

    def start_dpi_tester_task(self):
        if self.is_processing:
            return
        domains_text = self.dpi_domains_input.text().strip() if self.dpi_domains_input else ""
        if not domains_text:
            domains_text = "discord.com, roblox.com"
        domains = [d.strip() for d in domains_text.replace(',', ' ').split() if d.strip()]
        if not domains:
            domains = ["discord.com", "roblox.com"]
        
        zapret_ver = "v1" if (self.dpi_ver_v1_radio and self.dpi_ver_v1_radio.isChecked()) else "v2"
        scan_idx = self.dpi_scan_mode_combo.currentIndex() if self.dpi_scan_mode_combo else 0
        scan_level = "DEEP" if scan_idx == 0 else ("SMART" if scan_idx == 1 else "BASIC")
        test_http = self.dpi_http_chk.isChecked() if self.dpi_http_chk else False
        test_tls12 = self.dpi_tls12_chk.isChecked() if self.dpi_tls12_chk else False
        test_tls13 = self.dpi_tls13_chk.isChecked() if self.dpi_tls13_chk else False

        if not (test_http or test_tls12 or test_tls13):
            if hasattr(self, "status_toast") and self.status_toast:
                self.status_toast.show_message("Lütfen test edilecek en az bir protokol seçin (HTTP, TLS 1.2 veya TLS 1.3).", severity="warning")
            return

        self.is_processing = True
        self.current_worker = "dpi_tester"
        self._dpi_cancel_flag = False
        if self.console_dpi_tester is not None:
            self.console_dpi_tester.clear()
        self._active_progress_row = None
        self._active_progress_target = None
        self.active_progress_base = None
        self.active_progress_pct = None

        if self.dpi_tester_start_btn is not None:
            self.dpi_tester_start_btn.setEnabled(False)
        if self.dpi_tester_console_back_btn is not None:
            self.dpi_tester_console_back_btn.setEnabled(False)
        if hasattr(self, 'dpi_tester_cancel_btn') and self.dpi_tester_cancel_btn is not None:
            self.dpi_tester_cancel_btn.setEnabled(True)
            self.dpi_tester_cancel_btn.setText("Testi iptal et")
        if self.dpi_tester_open_report_btn is not None:
            self.dpi_tester_open_report_btn.setEnabled(False)

        self.show_page("dpi_tester_console")
        self.spinner_timer.start(16)
        threading.Thread(
            target=self._dpi_tester_worker,
            args=(zapret_ver, domains, scan_level, test_http, test_tls12, test_tls13),
            daemon=True,
        ).start()

    def _dpi_tester_worker(self, zapret_ver, domains, scan_level, test_http, test_tls12, test_tls13):
        def emit_log(segments):
            self.ui_queue.put({
                "action": "log_segments",
                "segments": segments,
                "target": "dpi_tester",
            })

        try:
            source_dir = Path(self.get_binary_path("zapret"))
            run_dpi_test(
                zapret_ver=zapret_ver,
                domains=domains,
                scan_level=scan_level,
                test_http=test_http,
                test_tls12=test_tls12,
                test_tls13=test_tls13,
                log_callback=emit_log,
                cancel_check=lambda: getattr(self, '_dpi_cancel_flag', False),
                custom_source_dir=source_dir,
            )
        except Exception as exc:
            emit_log([("• ", "#8C9BA8"), ("HATA: ", "#FF5C6B"), (f"{exc}\n", "#E7ECF2")])
        finally:
            self.ui_queue.put({"action": "finish_dpi_tester", "target": "dpi_tester"})

    def build_iso_frame(self):
        layout = QVBoxLayout(self.iso_frame)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(14)

        section = QLabel("ISO aracı / Windows 11")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 9px; font-weight: bold; letter-spacing: 1px;"
        )
        layout.addWidget(section)
        title = QLabel("Kurulum medyasını özelleştir")
        title.setStyleSheet("color: #F4F7FA; font-size: 21px; font-weight: bold;")
        layout.addWidget(title)
        subtitle = QLabel("Windows 11 kurulum medyasını seçerek sistem bileşenlerini ve ilkelerini doğrudan ISO üzerinde yapılandırın.")
        subtitle.setStyleSheet("color: #8995A1; font-size: 11px;")
        layout.addWidget(subtitle)

        self.iso_path_frame = QFrame()
        self.iso_path_frame.setObjectName("IsoPathFrame")
        self.iso_path_frame.setStyleSheet(
            "QFrame#IsoPathFrame { background-color: #0D1116; border: 1px solid #2D3742; border-radius: 8px; }"
        )
        row_path = QHBoxLayout(self.iso_path_frame)
        row_path.setContentsMargins(10, 9, 10, 9)
        row_path.setSpacing(8)
        self.iso_entry = QLineEdit()
        self.iso_entry.setPlaceholderText("ISO dosyası seçilmedi...")
        self.iso_entry.setText(self.iso_path)
        self.iso_entry.setFixedHeight(38)
        self.iso_entry.textChanged.connect(self._update_iso_frame_style)
        row_path.addWidget(self.iso_entry)
        browse_btn = QPushButton("ISO seç")
        browse_btn.setFixedSize(100, 38)
        browse_btn.clicked.connect(self.browse_iso)
        row_path.addWidget(browse_btn)
        layout.addWidget(self.iso_path_frame)
        self._update_iso_frame_style()

        layout.addSpacing(6)
        options_label = QLabel("Kurulum seçenekleri")
        options_label.setStyleSheet(
            f"color: {self.accent}; font-size: 12px; font-weight: bold; letter-spacing: 1px; "
            "padding-top: 4px;"
        )
        layout.addWidget(options_label)

        option_grid = QGridLayout()
        option_grid.setHorizontalSpacing(0)
        option_grid.setVerticalSpacing(0)
        iso_options = [
            (
                "Zorunlulukları atla",
                "TPM, Secure Boot, RAM ve CPU denetimlerini geç.",
                "bypass_requirements",
                0,
            ),
            (
                "Yerel hesap kurulumuna zorla",
                "Microsoft hesabı zorunluluğunu devre dışı bırak.",
                "bypass_online_account",
                0,
            ),
            (
                "Otomatik şifrelemeyi kapat",
                "Cihaz şifrelemesini ve BitLocker servisini kapat.",
                "bypass_bitlocker",
                1,
            ),
        ]
        for index, (text, description, attr, risk) in enumerate(iso_options):
            tile = QFrame()
            tile.setMinimumHeight(72)
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tile.setStyleSheet(
                "QFrame { background-color: transparent; border: none; "
                "border-bottom: 1px solid #232D37; border-radius: 0; }"
            )
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(12, 12, 12, 12)
            tile_layout.setSpacing(4)
            checkbox = RiftSwitch(text)
            checkbox.toggled.connect(
                lambda state, name=attr: setattr(self, name, state)
            )
            detail = QLabel(description)
            detail.setWordWrap(True)
            detail.setStyleSheet("color: #8C9BA8; font-size: 11px; padding-left: 14px; border: none; background: transparent;")
            detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            tile_layout.addWidget(checkbox)
            tile_layout.addWidget(detail)
            CTkToolTip(checkbox, description, risk_level=risk)
            option_grid.addWidget(tile, index, 0)
        option_grid.setColumnStretch(0, 1)
        layout.addLayout(option_grid)
        layout.addStretch(1)

        self.inject_btn = QPushButton("ISO'yu düzenle")
        self.inject_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self.accent}; color: #FFFFFF; "
            "font-weight: bold; border: 1px solid #FF6675; border-radius: 7px; height: 46px; }\n"
            f"QPushButton:hover {{ background-color: {self.accent_hover}; }}\n"
            "QPushButton:disabled { background-color: #252B31; color: #7C6D83; border-color: #303A45; }"
        )
        self.inject_btn.clicked.connect(self.start_injection_thread)
        layout.addWidget(self.inject_btn)

    def build_iso_console_frame(self):
        layout = QVBoxLayout(self.iso_console_frame)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        section = QLabel("ISO aracı / İşlem")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 9px; font-weight: bold; letter-spacing: 1px;"
        )
        title = QLabel("ISO İşlem Konsolu")
        title.setStyleSheet("color: #F4F7FA; font-size: 20px; font-weight: bold;")
        title_box.addWidget(section)
        title_box.addWidget(title)
        title_row.addLayout(title_box)
        title_row.addStretch()
        self.iso_console_loading_ring = None
        layout.addLayout(title_row)

        self.console_iso = SmoothConsoleTextEdit()
        self.console_iso.setReadOnly(True)
        self.console_iso.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.console_iso.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        console_font = QFont("Consolas", 13)
        console_font.setStyleHint(QFont.StyleHint.Monospace)
        self.console_iso.setFont(console_font)
        self.console_iso.setStyleSheet(
            "QTextEdit { background-color: #050407; border: 1px solid #7E2934; "
            "border-left: 2px solid #E63B4D; border-radius: 5px; "
            "padding: 14px; color: #C9D1DA; selection-background-color: #6D202B; }"
        )
        layout.addWidget(self.console_iso, 1)

        self.iso_console_back_btn = QPushButton("Konsolu kapat")
        self.iso_console_back_btn.setFixedHeight(45)
        self.iso_console_back_btn.setStyleSheet(
            "QPushButton { background-color: #11161B; color: #D4DAE0; "
            "border: 1px solid #303A45; border-radius: 7px; font-weight: bold; }\n"
            "QPushButton:hover { background-color: #261217; border-color: #E63B4D; color: #FFFFFF; }\n"
            "QPushButton:disabled { background-color: #110E14; color: #66717D; border-color: #29202D; }"
        )
        self.iso_console_back_btn.clicked.connect(lambda: self.show_page("iso"))
        layout.addWidget(self.iso_console_back_btn)

    def build_debloat_frame(self):
        layout = QVBoxLayout(self.debloat_frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        section = QLabel("Debloat / Özel profil")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 9px; font-weight: bold; letter-spacing: 1px;"
        )
        title = QLabel("Sistem optimizasyonu")
        title.setStyleSheet("color: #F4F7FA; font-size: 20px; font-weight: bold;")
        title_box.addWidget(section)
        title_box.addWidget(title)
        title_row.addLayout(title_box)
        title_row.addStretch()
        self.debloat_selection_count = QLabel("0 seçenek aktif")
        self.debloat_selection_count.setStyleSheet(
            "color: #8995A1; font-size: 10px; font-weight: normal; letter-spacing: 1px;"
        )
        title_row.addWidget(self.debloat_selection_count)
        layout.addLayout(title_row)

        scroll_container = QFrame()
        scroll_container.setStyleSheet(
            "QFrame { background-color: transparent; border: none; }"
        )
        scroll_container_layout = QVBoxLayout(scroll_container)
        scroll_container_layout.setContentsMargins(6, 6, 6, 6)
        scroll_container_layout.setSpacing(0)

        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        scroll_container_layout.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet("background-color: transparent; border: none;")
        scroll_layout = QVBoxLayout(content)
        scroll_layout.setContentsMargins(5, 3, 5, 3)
        scroll_layout.setSpacing(1)

        # App checkbox row + customize button
        app_frame = QFrame()
        app_frame.setMinimumHeight(54)
        app_frame.setStyleSheet(
            "QFrame { background-color: transparent; border: none; "
            "border-bottom: 1px solid #2A333D; }"
        )
        app_row = QHBoxLayout(app_frame)
        app_row.setContentsMargins(10, 8, 10, 8)
        app_row.setSpacing(7)
        self.app_master_chk = RiftSwitch("Windows uygulamaları")
        CTkToolTip(self.app_master_chk, "Sistemle gelen gereksiz bloatware uygulamalarını temizler.\n"
                   "Sildiğiniz uygulamayı Microsoft Store'dan geri yükleyebilirsiniz.", risk_level=0)
        self.app_master_chk.toggled.connect(
            lambda state: setattr(self, 'cfg_apps_enabled', state)
        )
        self.app_master_chk.toggled.connect(self._update_debloat_selection_count)
        app_row.addWidget(self.app_master_chk)
        btn_app_cust = SettingsGlyphButton()
        btn_app_cust.clicked.connect(self.open_app_checklist_view)
        app_row.addWidget(btn_app_cust)
        scroll_layout.addWidget(app_frame)

        shutup_frame = QFrame()
        shutup_frame.setMinimumHeight(54)
        shutup_frame.setStyleSheet(
            "QFrame { background-color: transparent; border: none; "
            "border-bottom: 1px solid #2A333D; }"
        )
        shutup_row = QHBoxLayout(shutup_frame)
        shutup_row.setContentsMargins(10, 8, 10, 8)
        shutup_row.setSpacing(7)
        self.shutup_master_chk = RiftSwitch("Gizlilik ve telemetri ayarları")
        CTkToolTip(self.shutup_master_chk, "Sistemdeki gizlilik ve telemetri ayarlarını sıkılaştırır.\n"
                   "Bazı uygulamaların çalışmasını engelleyebilir.", risk_level=1)
        self.shutup_master_chk.toggled.connect(
            lambda state: setattr(self, 'cfg_shutup10', state)
        )
        self.shutup_master_chk.toggled.connect(self._update_debloat_selection_count)
        shutup_row.addWidget(self.shutup_master_chk)
        btn_shut_cust = SettingsGlyphButton()
        btn_shut_cust.clicked.connect(self.open_shutup_checklist_view)
        shutup_row.addWidget(btn_shut_cust)
        scroll_layout.addWidget(shutup_frame)

        scroll_layout.addSpacing(6)

        cfg_tooltips = [
            ("Detaylı mavi ekran", 'cfg_bsod',
             "Mavi ekran çökmesi durumunda hata kodunu ve çöken sürücü ayrıntılarını gösterir.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Windows karanlık tema zorla", 'cfg_dark',
             "Sistem ve destekleyen tüm uygulamalarda karanlık modu etkinleştirir.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Dosya uzantılarını ve gizli dosyaları göster", 'cfg_extensions',
             "Dosya Gezgini'nde dosya uzantılarını ve gizli dosyaları görünür kılar.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Ultra performans güç planını aktif et", 'cfg_ultraperf',
             "Windows'un en yüksek performans güç şemasını aktifleştirir.\nNormal kullanıcıyı etkilemez; dizüstü cihazlarda pil tüketimi artabilir.",
             1),
            ("Oyun gecikmesi iyileştirmeleri", 'cfg_gaming_tweaks',
             "Oyunlardaki giriş gecikmesini düşürür: multimedya zamanlayıcı önceliği, ağ kısıtlaması kaldırma ve 1:1 fare hareketi.\nNormal kullanıcıyı etkilemez.",
             1),
            ("Başlat menüsü web aramalarını ve önerileri engelle", 'cfg_bing_search',
             "Başlat aramasında internetten web sonuçlarının ve reklamların getirilmesini engeller.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Tüketici özelliklerini kapat", 'cfg_consumer_features',
             "Windows'un arka planda sessizce oyun, reklam ve üçüncü parti mağaza uygulamaları yüklemesini kapatır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Teslimat iyileştirmesini kapat", 'cfg_delivery_opt',
             "Güncellemelerde internet bant genişliğinizin diğer bilgisayarlara yükleme için harcanmasını engeller.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Görev çubuğuna 'Görevi sonlandır' ekle", 'cfg_end_task',
             "Çalışan uygulamalara görev çubuğundan sağ tıklayıp doğrudan sonlandırma seçeneği ekler.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Dosya Gezgini klasör türü keşfini kapat", 'cfg_feafd',
             "Gezginin klasör içeriğini tahmin etmeye çalışmasını kapatıp klasör açılışlarını hızlandırır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Hazırda bekletmeyi kapat", 'cfg_hibernate',
             "Hazırda bekletme özelliğini kapatarak diskteki hiberfil.sys dosyasını siler.\nUyku modunu kullanıyorsanız etkileyebilir.",
             1),
            ("Konum takibini kapat", 'cfg_location',
             "Uygulamaların ve Windows servislerinin konumunuza erişmesini engeller.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Microsoft Store önerilen arama sonuçlarını kapat", 'cfg_store_recommend',
             "Başlat menüde arama yaparken Mağaza üzerindeki sponsorlu uygulama ve oyunları gizler.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Telemetri ve tanılama verilerini kapat", 'cfg_telemetry',
             "Arka planda Microsoft'a veri gönderen tüm tanılama, telemetri ve hata raporlama servislerini kapatır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Haberler ve ilgi alanlarını kaldır", 'cfg_widgets',
             "Görev çubuğundaki haberler, hava durumu ve pano araçlarını (Widgets) tamamen kaldırır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Klasik sağ tık menüsünü geri getir", 'cfg_classic_menu',
             "Windows 11'in kısıtlı sağ tık menüsünü kapatıp eski, hızlı ve tam kapsamlı menüyü getirir.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Gereksiz servisleri kapat", 'cfg_services',
             "Kullanılmayan arka plan telemetri, tanılama, arama indeksleme ve dağıtım servislerini devre dışı bırakır.\nİlgili Windows özellikleri çalışmaz.",
             1),
            ("BitLocker korumasını askıya al ve servisini kapat", 'cfg_remove_bitlocker',
             "Tüm sabit disklerde BitLocker korumasını süresiz askıya alır, otomatik cihaz şifrelemesini engeller ve servisini kapatır.",
             2),
            ("Yapışkan tuşları tamamen kapat", 'cfg_sticky_keys',
             "Yapışkan Tuşlar, Filtre Tuşları ve Geçiş Tuşları kısayollarını; sesli uyarılarını kapatır.",
             0),
            ("Tam ekran optimizasyonlarını kapat", 'cfg_disable_fso',
             "Oyunlarda pencereli kompozisyon katmanını aradan çıkararak doğrudan gecikmesiz özel tam ekran modunu zorlar.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Ekran kartı katman iyileştirmesi", 'cfg_disable_mpo',
             "Ekran kartı sürücüsünün pencereli oyunlarda, çift monitörde veya video izlerken oluşturduğu siyah ekran ve takılmaları önler.\nNormal kullanıcıyı etkilemez.",
             1),
            ("Uyku modunda ağ tüketimini kapat", 'cfg_disable_s0_drain',
             "Bilgisayar veya dizüstü uyku modundayken arka planda ağ bağlantısını keserek pil tüketimini ve ısınmayı engeller.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Saat sunucusunu optimize et", 'cfg_ntp_sync',
             "Yavaş varsayılan sunucu yerine yüksek hassasiyetli saat sunucularını ayarlar ve sistem saatini anında senkronize eder.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Windows Defender'ı Durdur", 'cfg_defender',
             "Windows Defender koruma ilkelerini, sürücülerini ve arka plan servislerini Defender Control yöntemiyle anında durdurur.\nYeniden başlatma gerektirmez.",
             2),
            ("Windows güncellemelerini 2099'a kadar duraklat", 'cfg_pause_updates_2099',
             "Windows güncellemelerini sistem dosyalarını bozmadan ve Mağaza'yı etkilemeden 2099 yılına kadar duraklatır.\nİstediğiniz zaman geri açabilirsiniz.",
             1),
            ("Klasik sağ tık menüsüne 'WinKit araçları' ekle", 'cfg_context_menu_tools',
             "Masaüstü ve dosyalara sağ tıkladığınızda 'WinKit araçları' alt menüsü ekler (Sahipliği al, Güvenilir yükleyiciye devret, Kilitli dosyayı zorla sil).\nNormal kullanıcıyı etkilemez.",
             0),
            ("Yerel ağ ad çözümleme yayınlarını kapat", 'cfg_llmnr_poisoning',
             "Yerel ağda gereksiz broadcast yayınlarını kapatıp ad çözümleme güvenliğini artırır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Disk yazma yükünü azalt", 'cfg_disable_lastaccess',
             "Dosya okuma işlemlerinde diske son erişim zamanı yazılmasını kapatır; disk ömrünü ve tepki hızını artırır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Donanım hızlandırmalı GPU zamanlama", 'cfg_hags',
             "Ekran kartının video belleğini doğrudan yönetmesini sağlayarak oyunlarda gecikmeyi azaltır ve kare hızını artırır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Ayrılmış depolama alanını geri al", 'cfg_reserved_storage',
             "Windows güncellemeleri için rehin tutulan 7-8 GB disk alanını serbest bırakıp kullanılabilir yapar.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Ayrıntılı başlangıç ve kapanış mesajları", 'cfg_verbose_status',
             "Bilgisayar açılırken ve kapanırken arka planda yüklenen servisleri ve işlemleri ekranda gösterir.\nNormal kullanıcıyı etkilemez.",
             0),
            ("260 karakter dosya yolu sınırını kaldır", 'cfg_long_paths',
             "Windows'un eski 260 karakterlik MAX_PATH dosya ve klasör yolu sınırlamasını kaldırır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Donanım saatini UTC olarak ayarla", 'cfg_utc_clock',
             "BIOS ve donanım saatini UTC olarak ayarlayarak çift önyüklemede (Dual Boot) saat kaymasını önler.\nNormal kullanıcıyı etkilemez.",
             0),
            ("SmartScreen, pano ve geçmişin bulutla paylaşımını kapat", 'cfg_smartscreen_clipboard',
             "Dosya Gezgini SmartScreen denetimini ve pano geçmişinin bulutla/telemetriyle paylaşılmasını kapatır; verileri sadece bu bilgisayarda yerel saklar.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Cihaz reklam ve eşlikçi uygulamaları engelle", 'cfg_device_companion',
             "Yeni bağlanan donanımlar için internetten otomatik üretici reklamı ve gereksiz ek yazılım indirilmesini kapatır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Ekran kartı ve ağ bağdaştırıcı gecikmesini düşür", 'cfg_msi_interrupts',
              "Ekran kartı ve uyumlu ağ kartlarını MSI moduna geçirerek kesme gecikmesini düşürür.\nNormal kullanıcıyı etkilemez.",
              0),
            ("Yapay zeka ve Copilot özelliklerini kapat", 'cfg_disable_ai',
             "Windows Copilot, Recall ve sistem yapay zeka arka plan bileşenlerini kapatır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Windows + Space dil değiştirme kısayolunu kapat", 'cfg_disable_win_space',
             "Oyun oynarken veya yazı yazarken yanlışlıkla dil değiştirmeyi önlemek için Win+Space ve Alt+Shift kısayollarını kapatır.\nNormal kullanıcıyı etkilemez.",
             0),
            ("Denetim Masasını küçük simgelerle aç", 'cfg_control_panel_small_icons',
             "Denetim Masası açıldığında varsayılan kategori görünümü yerine doğrudan küçük simgeler (tüm öğeler) görünümünde açılır.\nNormal kullanıcıyı etkilemez.",
             0),
        ]

        cfg_summaries = {
            "cfg_bsod": "Çökme ekranında hata ayrıntılarını gösterir.",
            "cfg_dark": "Windows ve uygulamalarda koyu görünümü kullanır.",
            "cfg_extensions": "Gizli öğeleri ve dosya uzantılarını görünür yapar.",
            "cfg_ultraperf": "En yüksek performans güç planını etkinleştirir.",
            "cfg_gaming_tweaks": "Giriş gecikmesi ve oyun önceliklerini iyileştirir.",
            "cfg_bing_search": "Başlat aramasındaki web sonuçlarını kaldırır.",
            "cfg_consumer_features": "Sponsorlu uygulama ve önerileri engeller.",
            "cfg_delivery_opt": "Güncelleme paylaşımını ve arka plan yüklemesini kapatır.",
            "cfg_end_task": "Görev çubuğuna hızlı sonlandırma seçeneği ekler.",
            "cfg_feafd": "Klasör görünümü tahminini kapatarak Gezgini sadeleştirir.",
            "cfg_hibernate": "Hazırda bekletmeyi ve hiberfil.sys dosyasını kaldırır.",
            "cfg_location": "Windows ve uygulamalar için konum erişimini kapatır.",
            "cfg_store_recommend": "Microsoft Store önerilerini gizler.",
            "cfg_telemetry": "Tanılama ve telemetri trafiğini sınırlar.",
            "cfg_widgets": "Haberler, hava durumu ve pano araçlarını kaldırır.",
            "cfg_classic_menu": "Windows 11 tam sağ tık menüsünü geri getirir.",
            "cfg_services": "Kullanılmayan arka plan servislerini devre dışı bırakır.",
            "cfg_remove_bitlocker": "BitLocker korumasını askıya alıp servisini kapatır.",
            "cfg_sticky_keys": "Erişilebilirlik klavye kısayollarını ve seslerini kapatır.",
            "cfg_disable_fso": "Oyunlarda giriş gecikmesini düşürmek için tam ekran optimizasyonunu kapatır.",
            "cfg_disable_mpo": "Ekran kartı video ve çoklu monitör takılmalarını çözer.",
            "cfg_disable_s0_drain": "Uyku modunda arka plan ağ kullanımını ve pil tüketimini kapatır.",
            "cfg_ntp_sync": "Sistem saatini yüksek hassasiyetli saat sunucularıyla eşitler.",
            "cfg_defender": "Windows Defender güvenlik servislerini ve sürücülerini anında durdurur.",
            "cfg_pause_updates_2099": "Windows güncellemelerini 2099 yılına kadar güvenli duraklatır.",
            "cfg_context_menu_tools": "Sağ tık menüsüne sahiplik alma ve kilitli dosya silme alt menüsü ekler.",
            "cfg_llmnr_poisoning": "Yerel ağda gereksiz yayınları kapatarak ad çözümleme güvenliğini artırır.",
            "cfg_disable_lastaccess": "Dosya okumalarında diske son erişim zamanı yazılmasını kapatır.",
            "cfg_hags": "Donanım hızlandırmalı GPU zamanlamasını etkinleştirir.",
            "cfg_reserved_storage": "Windows güncellemeleri için ayrılan disk alanını serbest bırakır.",
            "cfg_verbose_status": "Açılış ve kapanışta ayrıntılı durum mesajlarını gösterir.",
            "cfg_long_paths": "260 karakter dosya ve klasör yolu sınırlamasını kaldırır.",
            "cfg_utc_clock": "Çift önyükleme için BIOS saatini UTC standardına alır.",
            "cfg_smartscreen_clipboard": "SmartScreen ve pano geçmişinin bulutla paylaşımını kapatır.",
            "cfg_clipboard_local": "Pano ve Çalıştır geçmişini bulutla paylaşıma kapatır.",
            "cfg_smartscreen_explorer": "Dosya Gezgini SmartScreen denetimini kapatır.",
            "cfg_device_companion": "Cihazlar için internetten üretici reklam ve bloatware indirmesini engeller.",
            "cfg_msi_interrupts": "Ekran kartı ve ağ bağdaştırıcı kesme gecikmesini düşürür.",
            "cfg_disable_ai": "Windows Copilot, Recall ve yapay zeka bileşenlerini kapatır.",
            "cfg_disable_win_space": "Oyunlarda yanlışlıkla dil değiştirmeyi önlemek için Win+Space kısayolunu kapatır.",
            "cfg_control_panel_small_icons": "Denetim Masasını doğrudan küçük simgeler görünümünde açar.",
        }

        tweak_categories = {
            "cfg_disable_fso": "gaming",
            "cfg_disable_mpo": "gaming",
            "cfg_gaming_tweaks": "gaming",
            "cfg_ultraperf": "gaming",
            "cfg_disable_s0_drain": "gaming",
            "cfg_ntp_sync": "gaming",
            "cfg_hags": "gaming",
            "cfg_msi_interrupts": "gaming",
            "cfg_disable_win_space": "gaming",
            "cfg_telemetry": "privacy",
            "cfg_location": "privacy",
            "cfg_bing_search": "privacy",
            "cfg_consumer_features": "privacy",
            "cfg_store_recommend": "privacy",
            "cfg_delivery_opt": "privacy",
            "cfg_widgets": "privacy",
            "cfg_llmnr_poisoning": "privacy",
            "cfg_smartscreen_clipboard": "privacy",
            "cfg_clipboard_local": "privacy",
            "cfg_smartscreen_explorer": "privacy",
            "cfg_device_companion": "privacy",
            "cfg_disable_ai": "privacy",
            "cfg_classic_menu": "system",
            "cfg_end_task": "system",
            "cfg_extensions": "system",
            "cfg_dark": "system",
            "cfg_feafd": "system",
            "cfg_bsod": "system",
            "cfg_hibernate": "system",
            "cfg_sticky_keys": "system",
            "cfg_disable_lastaccess": "system",
            "cfg_reserved_storage": "system",
            "cfg_verbose_status": "system",
            "cfg_long_paths": "system",
            "cfg_utc_clock": "system",
            "cfg_context_menu_tools": "system",
            "cfg_control_panel_small_icons": "system",
            "cfg_services": "services",
            "cfg_remove_bitlocker": "services",
            "cfg_defender": "services",
            "cfg_pause_updates_2099": "services",
        }

        scroll_layout.addSpacing(6)

        # Kategori Filtre Çipleri
        chips_frame = QFrame()
        chips_frame.setStyleSheet("background: transparent; border: none;")
        chips_layout = QHBoxLayout(chips_frame)
        chips_layout.setContentsMargins(0, 2, 0, 8)
        chips_layout.setSpacing(7)

        self.debloat_chips = []
        chip_defs = [
            ("Tümü", "all", len(cfg_tooltips)),
            ("Oyun ve performans", "gaming", sum(1 for _, a, _, _ in cfg_tooltips if tweak_categories.get(a) == "gaming")),
            ("Gizlilik", "privacy", sum(1 for _, a, _, _ in cfg_tooltips if tweak_categories.get(a) == "privacy")),
            ("Sistem ve görünüm", "system", sum(1 for _, a, _, _ in cfg_tooltips if tweak_categories.get(a) == "system")),
            ("Servisler ve gelişmiş", "services", sum(1 for _, a, _, _ in cfg_tooltips if tweak_categories.get(a) == "services")),
        ]

        grid_wrapper = QWidget()
        grid_wrapper.setStyleSheet("background: transparent; border: none;")

        settings_grid = QGridLayout(grid_wrapper)
        settings_grid.setContentsMargins(0, 0, 0, 0)
        settings_grid.setHorizontalSpacing(0)
        settings_grid.setVerticalSpacing(0)

        self._active_debloat_cat = "all"
        self._chip_transition_anim = None

        def on_chip_clicked(target_cat):
            if getattr(self, "_active_debloat_cat", "all") == target_cat:
                return
            self._active_debloat_cat = target_cat
            for chip in self.debloat_chips:
                chip.set_active(chip.category == target_cat)

            if getattr(self, "_chip_transition_anim", None) is not None:
                try:
                    self._chip_transition_anim.stop()
                except Exception:
                    pass

            eff = grid_wrapper.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(grid_wrapper)
                grid_wrapper.setGraphicsEffect(eff)

            start_op = eff.opacity() if eff else 1.0

            fade_out = QPropertyAnimation(eff, b"opacity", self)
            fade_out.setDuration(70)
            fade_out.setStartValue(start_op)
            fade_out.setEndValue(0.05)
            fade_out.setEasingCurve(QEasingCurve.Type.InQuad)

            fade_in = QPropertyAnimation(eff, b"opacity", self)
            fade_in.setDuration(180)
            fade_in.setStartValue(0.05)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

            def _on_fade_out_done():
                for tile, cat in self.debloat_tiles:
                    tile.setVisible(target_cat == "all" or cat == target_cat)
                fade_in.start()

            def _on_fade_in_done():
                try:
                    grid_wrapper.setGraphicsEffect(None)
                except Exception:
                    pass

            fade_out.finished.connect(_on_fade_out_done)
            fade_in.finished.connect(_on_fade_in_done)
            self._chip_transition_anim = fade_in
            fade_out.start()

        for label, cat, cnt in chip_defs:
            chip_btn = FilterChip(label, cat, cnt)
            chip_btn.clicked.connect(lambda checked, c=cat: on_chip_clicked(c))
            chips_layout.addWidget(chip_btn)
            self.debloat_chips.append(chip_btn)

        chips_layout.addStretch()
        self.debloat_chips[0].set_active(True)
        scroll_layout.addWidget(chips_frame)

        self.debloat_checkboxes = []
        self.debloat_tiles = []
        for index, (text, attr, tip, risk) in enumerate(cfg_tooltips):
            cat = tweak_categories.get(attr, "system")
            tile = QFrame()
            tile.setMinimumHeight(60)
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tile.setStyleSheet(
                "QFrame { background-color: transparent; border: none; "
                "border-bottom: 1px solid #232D37; border-radius: 0; }"
            )
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(11, 8, 11, 8)
            tile_layout.setSpacing(2)

            chk_row = QHBoxLayout()
            chk_row.setContentsMargins(0, 0, 0, 0)
            chk_row.setSpacing(8)

            chk = RiftSwitch(text)
            chk.attr_name = attr
            
            def make_toggle_handler(a, c):
                def handler(state):
                    if state and a == "cfg_defender" and not getattr(self, "_bulk_toggle_in_progress", False):
                        # QDialog.exec() iç içe olay döngüsü ilk açılışta ana
                        # pencereyi donmuş gibi gösterebiliyordu. Switch'i geçici
                        # olarak geri al, uyarıyı asenkron aç ve yalnızca onaydan
                        # sonra seçimi uygula.
                        c.blockSignals(True)
                        c.setChecked(False)
                        c.blockSignals(False)
                        setattr(self, a, False)

                        def accept_defender():
                            c.blockSignals(True)
                            c.setChecked(True)
                            c.blockSignals(False)
                            setattr(self, a, True)
                            self._update_debloat_selection_count()
                        QTimer.singleShot(0, lambda: self._show_defender_warning(accept_defender))
                        self._update_debloat_selection_count()
                        return
                    setattr(self, a, state)
                    if a == "cfg_disable_win_space":
                        if getattr(self, "btn_win_space_toggle", None) is not None:
                            self.btn_win_space_toggle.blockSignals(True)
                            self.btn_win_space_toggle.setChecked(state)
                            self.btn_win_space_toggle.blockSignals(False)
                    self._update_debloat_selection_count()
                return handler

            chk.toggled.connect(make_toggle_handler(attr, chk))
            chk.setProperty("risk_level", risk)
            CTkToolTip(chk, tip, risk_level=risk)
            chk_row.addWidget(chk, 1)

            if attr == "cfg_pause_updates_2099":
                btn_wu_cust = SettingsGlyphButton()
                CTkToolTip(btn_wu_cust, "Windows Güncelleme Seçenekleri (2100'e kadar duraklat veya otomatik güncellemeleri kapat)", risk_level=0)
                btn_wu_cust.clicked.connect(self.open_windows_update_options)
                chk_row.addWidget(btn_wu_cust)

            summary = cfg_summaries.get(attr, tip.split("\n", 1)[0].strip())
            detail = QLabel(summary)
            detail.setStyleSheet("color: #8C9BA8; font-size: 11px; padding-left: 14px; border: none; background: transparent;")
            detail.setWordWrap(True)
            detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

            if attr == "cfg_defender":
                self.defender_checkbox = chk

            tile_layout.addLayout(chk_row)
            tile_layout.addWidget(detail)
            settings_grid.addWidget(tile, index, 0)
            self.debloat_checkboxes.append(chk)
            self.debloat_tiles.append((tile, cat))
        settings_grid.setColumnStretch(0, 1)
        scroll_layout.addWidget(grid_wrapper)
        scroll_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll_container, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        select_all = QPushButton("Tümünü seç")
        select_all.setFixedWidth(110)
        select_all.clicked.connect(lambda checked=False: self.toggle_all_debloat(True))
        btn_row.addWidget(select_all)
        deselect_all = QPushButton("Tüm seçimleri kaldır")
        deselect_all.setFixedWidth(150)
        deselect_all.clicked.connect(lambda checked=False: self.toggle_all_debloat(False))
        btn_row.addWidget(deselect_all)
        btn_row.addStretch()

        self.apply_btn = QPushButton("Optimize et")
        self.apply_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self.accent}; color: #FFFFFF; "
            "font-weight: bold; border: 1px solid #FF6675; border-radius: 7px; height: 44px; }\n"
            f"QPushButton:hover {{ background-color: {self.accent_hover}; }}\n"
            "QPushButton:disabled { background-color: #252B31; color: #7C6D83; border-color: #303A45; }"
        )
        self.apply_btn.setFixedWidth(170)
        self.apply_btn.clicked.connect(self.on_apply_btn_click)
        btn_row.addWidget(self.apply_btn)
        layout.addLayout(btn_row)
        self._update_debloat_selection_count()


    def _update_debloat_selection_count(self, checked=None):
        count = sum(
            1 for checkbox in getattr(self, "debloat_checkboxes", [])
            if checkbox.isChecked()
        )
        count += int(bool(getattr(self, "app_master_chk", None) and self.app_master_chk.isChecked()))
        count += int(bool(getattr(self, "shutup_master_chk", None) and self.shutup_master_chk.isChecked()))
        if hasattr(self, "debloat_selection_count"):
            self.debloat_selection_count.setText(f"{count} SEÇENEK AKTİF")

    def build_debloat_console_frame(self):
        layout = QVBoxLayout(self.debloat_console_frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        title = QLabel("İşlem konsolu")
        title.setStyleSheet(
            "color: #F3EAF7; font-size: 14px; font-weight: bold; letter-spacing: 1px;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        self.console_loading_ring = None
        layout.addLayout(title_row)

        self.console_debloat = SmoothConsoleTextEdit()
        self.console_debloat.setReadOnly(True)
        self.console_debloat.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth
        )
        self.console_debloat.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.console_debloat.setFont(QFont("Consolas", 13))
        self.console_debloat.setStyleSheet(
            "QTextEdit { background-color: #050407; border: 1px solid #7E2934; "
            "border-left: 2px solid #E63B4D; border-radius: 5px; "
            "padding: 14px; color: #C9D1DA; selection-background-color: #6D202B; }"
        )
        layout.addWidget(self.console_debloat)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        self.console_back_btn = QPushButton("Konsolu kapat")
        self.console_back_btn.setFixedHeight(45)
        self.console_back_btn.setStyleSheet(
            "QPushButton { background-color: #11161B; color: #D4DAE0; "
            "border: 1px solid #303A45; border-radius: 7px; font-weight: bold; }\n"
            "QPushButton:hover { background-color: #261217; border-color: #E63B4D; color: #FFFFFF; }\n"
            "QPushButton:disabled { background-color: #110E14; color: #66717D; border-color: #29202D; }"
        )
        self.console_back_btn.clicked.connect(lambda: self.show_page("debloat"))
        self.console_back_btn.setEnabled(True)
        bottom_row.addWidget(self.console_back_btn, 1)
        layout.addLayout(bottom_row)


    def _get_shutup_risk_level(self, code, desc, category):
        explicit = self.shutup_risk_map.get(code)
        if explicit is not None:
            return explicit
        text = f"{desc} {category}".casefold()
        high_markers = (
            "smartscreen", "defender", "spynet", "zararlı yazılım",
            "otomatik windows güncellemelerini", "parola gösterme",
            "güvenlik bilgi hizmetlerini",
        )
        if any(marker in text for marker in high_markers):
            return 2
        if category in {
            "Uygulama İzinleri", "Güvenlik", "Windows Update",
            "Konum Servisleri", "Mobil Cihazlar",
        }:
            return 1
        if any(marker in text for marker in ("kamera", "mikrofon", "konum", "sürücü güncelle")):
            return 1
        return 0

    def _get_shutup_tooltip(self, code, desc, risk_level, category):
        return get_detailed_shutup_tooltip(code, desc, category)

    def _get_app_tooltip(self, app_name):
        details = {
            "Microsoft Edge": "Microsoft Edge tarayıcısını, telemetrisini ve arka plan güncelleme servislerini kaldırır.\nSistem WebView2 motoru korunur.",
            "Microsoft OneDrive": "OneDrive bulut senkronizasyon istemcisini ve arka plan görevlerini kaldırır.\nYerel dosyalarınız silinmez.",
            "AV1 Video Uzantısı": "AV1 video kod çözücü uzantısını kaldırır.\nBu formatı kullanan medya dosyaları açılamayabilir.",
            "AVC Video Uzantısı": "AVC/H.264 video donanım kodlama eklentisini kaldırır.\nVideo dönüştürücü uygulamalar etkilenebilir.",
            "HEVC Video Uzantısı": "HEVC/H.265 yüksek verimli video codec bileşenini kaldırır.\n4K/HDR HEVC videolar açılamayabilir.",
            "Cihazlar Arası Deneyim": "Telefon ve bilgisayar arasındaki pano ve oturum aktarımını kaldırır.\nTelefon bağlantısı özellikleri kısıtlanabilir.",
            "Dev Home": "Dev Home geliştirici kontrol panelini kaldırır.\nGeliştirici widget ve ortam araçları devre dışı kalır.",
            "Fotoğraflar": "Windows Fotoğraflar uygulamasını kaldırır.\nResimler silinmez; açmak için alternatif resim görüntüleyici gerekir.",
            "Xbox Game Bar": "Xbox Game Bar arayüzünü ve ekran kaydı motorunu kaldırır.\nWin+G kısayolu ve oyun içi katmanlar kapanır.",
            "Xbox Oyun Konuşma Penceresi": "Xbox oyun içi metin-konuşma erişilebilirlik penceresini kaldırır.\nOyun içi sesli sohbet transkripsiyonu çalışmaz.",
            "Geri Bildirim Merkezi": "Windows Geri Bildirim Merkezi telemetri ve geri bildirim uygulamasını kaldırır.\nMicrosoft'a gönderilen hata bildirimleri engellenir.",
            "Hava Durumu": "MSN Hava Durumu uygulamasını kaldırır.\nCanlı hava durumu tahminleri ve bildirimleri kapanır.",
            "HEIF Resim Uzantısı": "Apple iPhone ve yeni kameraların kullandığı HEIC/HEIF fotoğraf desteğini kaldırır.",
            "Hızlı Yardım": "Uzaktan yardım ve ekran paylaşım istemcisini kaldırır.\nUzaktan destek alma özelliği devre dışı kalır.",
            "Microsoft 365": "Sistemle gelen Microsoft 365 ve web entegrasyonunu kaldırır.",
            "Microsoft Bing Arama": "Bing web arama entegrasyonunu ve sponsorlu arama sonuçlarını kaldırır.",
            "Clipchamp Video Düzenleyici": "Bulut tabanlı video düzenleme uygulamasını kaldırır.\nVideo projeleri silinmez, tarayıcıdan erişilebilir.",
            "Haberler": "MSN Haberler ve güncel gelişmeler akışını kaldırır.\nHaber bildirimleri ve içerikleri engellenir.",
            "Microsoft Teams": "Kişisel Microsoft Teams istemcisini ve arka plan bildirim servisini kaldırır.",
            "Microsoft To Do": "Görev ve yapılacaklar listesi uygulamasını kaldırır.\nBulut görevleri silinmez, webden erişilebilir.",
            "MPEG-2 Video Uzantısı": "Eski DVD ve MPEG-2 video formatı kod çözücüsünü kaldırır.",
            "Outlook": "Yeni web tabanlı Outlook posta istemcisini kaldırır.\nPosta hesapları silinmez, tarayıcıdan açılabilir.",
            "Power Automate": "Masaüstü görev otomasyonu aracını kaldırır.\nOtomatik betik ve akışlar çalışmaz.",
            "RAW Resim Uzantısı": "Profesyonel fotoğraf makinelerinin ham RAW resim önizleme desteğini kaldırır.",
            "Saat": "Windows Saat, Alarm, Kronometre ve Odak Oturumu uygulamasını kaldırır.",
            "Ekran Alıntısı Aracı": "Ekran Alıntısı Aracı görüntü alma ve video kaydetme uygulamasını kaldırır.\nWin+Shift+S kısayolu kapanır.",
            "Telefon Bağlantısı": "Android ve iOS cihazları bilgisayara bağlayan Telefon Bağlantısı uygulamasını kaldırır.",
            "VP9 Video Uzantısı": "YouTube ve modern webde yaygın kullanılan VP9 video codec bileşenini kaldırır.",
            "Web Medya Uzantıları": "OGG, Vorbis ve Theora gibi açık kaynak web medya formatları desteğini kaldırır.",
            "WebP Resim Uzantısı": "Web sitelerinde kullanılan sıkıştırılmış WebP resim formatı önizleme desteğini kaldırır.",
            "Windows Web Deneyimi Paketi": "Görev çubuğundaki Widgets ve web panelleri çalışma paketini kaldırır.",
            "Widgets Platform Çalışma Zamanı": "Widgets platformunun arka planda çalışan webview çalışma motorunu kaldırır.",
            "Başlat Deneyimleri": "Başlat menüsü web içerikleri ve MSN haber akış bileşenini kaldırır.",
            "Uygulama Uyumluluk İyileştirmeleri": "Eski Windows programları için sunulan uyumluluk yama paketini kaldırır.",
            "Xbox Kimlik Sağlayıcısı": "Xbox Live oturum açma ve kimlik doğrulama servisini kaldırır.\nMicrosoft Store oyun oturumları etkilenebilir.",
            "Xbox Live": "Xbox oyuncu profili, başarımlar ve çok oyunculu bağlantı bileşenini kaldırır.",
            "Xbox Uygulaması": "Xbox PC oyun kütüphanesi ve Game Pass istemcisini kaldırır.",
            "Yapışkan Notlar": "Masaüstü Yapışkan Notlar uygulamasını kaldırır.\nNotlar silinmez, OneNote üzerinden erişilebilir.",
            "Yardım Al": "Windows Yardım Al otomatik sorun giderici ve destek istemcisini kaldırır.",
            "İpuçları": "Windows kullanım ipuçları ve tanıtım pencerelerini kaldırır.",
            "Microsoft Solitaire Collection": "Solitaire ve kart oyunları koleksiyonunu kaldırır.",
            "Medya Oynatıcı": "Klasik ve yeni Windows Medya Oynatıcısını kaldırır.",
            "Kamera": "Windows Kamera uygulamasını kaldırır.\nWebcam sürücüsü silinmez, üçüncü parti uygulamalar kamerayı kullanabilir.",
            "Ses Kaydedicisi": "Mikrofon ses kaydetme uygulamasını kaldırır.",
            "Paint": "Klasik Paint çizim uygulamasını kaldırır.",
            "Hesap Makinesi": "Windows Hesap Makinesi uygulamasını kaldırır."
        }
        if app_name in details:
            return details[app_name]
        return f"{app_name} uygulamasını Windows'tan kaldırır.\nKişisel belgeleriniz etkilenmez; uygulama Microsoft Store'dan geri yüklenebilir."


    def build_app_checklist_frame(self):
        layout = QVBoxLayout(self.app_checklist_frame)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        section = QLabel("Debloat / Uygulamalar")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 9px; font-weight: bold; letter-spacing: 1px;"
        )
        layout.addWidget(section)
        title = QLabel("Windows uygulamaları")
        title.setStyleSheet("color: #F4F7FA; font-weight: bold; font-size: 20px;")
        layout.addWidget(title)
        subtitle = QLabel("Sistemden kaldırmak istediğiniz yerleşik Windows uygulamalarını belirleyin. Seçimleriniz optimizasyon profiline dahil edilir.")
        subtitle.setStyleSheet("color: #8995A1; font-size: 10px;")
        layout.addWidget(subtitle)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(9)
        all_btn = QPushButton("Tümünü seç")
        all_btn.clicked.connect(lambda checked=False: self.toggle_all_apps(True))
        none_btn = QPushButton("Tüm seçimleri kaldır")
        none_btn.clicked.connect(lambda checked=False: self.toggle_all_apps(False))
        btn_layout.addWidget(all_btn)
        btn_layout.addWidget(none_btn)
        layout.addLayout(btn_layout)

        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        scroll.setStyleSheet(
            "QScrollArea { background-color: #090C10; border: 1px solid #27313A; border-radius: 10px; }"
        )
        container = QWidget()
        container.setStyleSheet("background-color: #090C10;")
        app_grid = QGridLayout(container)
        app_grid.setContentsMargins(12, 12, 12, 12)
        app_grid.setHorizontalSpacing(0)
        app_grid.setVerticalSpacing(6)
        self.app_checkboxes = []
        risk_names = {0: "Güvenli", 1: "Orta Risk", 2: "Yüksek Risk"}
        risk_colors = {0: "#65DFA9", 1: "#E8B65A", 2: "#FF738F"}
        for index, (app_name, _) in enumerate(self.bloat_apps):
            tile = QFrame()
            tile.setObjectName(f"AppTile{index}")
            tile.setMinimumHeight(50)
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tile.setStyleSheet(
                f"QFrame#AppTile{index} {{ background-color: #0E1318; "
                "border: 1px solid #232C35; border-radius: 8px; }"
            )
            tile_layout = QHBoxLayout(tile)
            tile_layout.setContentsMargins(12, 7, 10, 7)
            tile_layout.setSpacing(8)
            chk = AnimatedTickCheckBox(app_name)
            chk.setMinimumWidth(0)
            chk.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            chk.toggled.connect(
                lambda state, name=app_name: self._on_app_checkbox_toggled(name, state)
            )
            chk.setStyleSheet(
                "QCheckBox { background-color: transparent; border: none; "
                "color: #F1F4F7; font-size: 12px; font-weight: 500; padding: 0; }"
            )
            risk = self.app_risk_map.get(app_name, 1)
            tip = self._get_app_tooltip(app_name)
            CTkToolTip(chk, tip, risk_level=risk)
            risk_label = QLabel(risk_names[risk])
            risk_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            risk_label.setFixedWidth(76)
            risk_label.setStyleSheet(
                f"color: {risk_colors[risk]}; background-color: #131920; "
                f"font-size: 10px; font-weight: 600; border: 1px solid {risk_colors[risk]}; "
                "border-radius: 9px; padding: 2px 8px; margin: 0;"
            )
            tile_layout.addWidget(chk, 1)
            tile_layout.addWidget(risk_label, 0)
            app_grid.addWidget(tile, index, 0)
            self.app_checkboxes.append(chk)
        app_grid.setColumnStretch(0, 1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(9)
        cancel_btn = QPushButton("Kaydetmeden iptal et")
        cancel_btn.clicked.connect(self.cancel_app_selection)
        save_btn = QPushButton("Ayarları kaydet ve dön")
        save_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self.accent}; color: #FFFFFF; "
            "border: 1px solid #FF6675; font-weight: bold; }}\n"
            f"QPushButton:hover {{ background-color: {self.accent_hover}; }}"
        )
        save_btn.clicked.connect(self.save_app_selection)
        bottom_row.addWidget(cancel_btn)
        bottom_row.addWidget(save_btn)
        layout.addLayout(bottom_row)

    def build_shutup_checklist_frame(self):
        layout = QVBoxLayout(self.shutup_checklist_frame)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        section = QLabel("Debloat / Gizlilik")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 9px; font-weight: bold; letter-spacing: 1px;"
        )
        layout.addWidget(section)
        title = QLabel("Gizlilik ve telemetri")
        title.setStyleSheet("color: #F4F7FA; font-weight: bold; font-size: 20px;")
        layout.addWidget(title)
        subtitle = QLabel("Windows telemetri ve arka plan veri toplama servislerini sınırlandırmak için gizlilik ilkelerini yapılandırın.")
        subtitle.setStyleSheet("color: #8995A1; font-size: 10px;")
        layout.addWidget(subtitle)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(9)
        rec_btn = QPushButton("Önerilenleri seç")
        rec_btn.clicked.connect(self.select_recommended_shutup)
        all_btn = QPushButton("Tümünü seç")
        all_btn.clicked.connect(lambda: self.toggle_all_shutup(True))
        none_btn = QPushButton("Tüm seçimleri kaldır")
        none_btn.clicked.connect(lambda: self.toggle_all_shutup(False))
        btn_layout.addWidget(rec_btn)
        btn_layout.addWidget(all_btn)
        btn_layout.addWidget(none_btn)
        layout.addLayout(btn_layout)

        rules_scroll = SmoothScrollArea()
        rules_scroll.setWidgetResizable(True)
        rules_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rules_scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        rules_scroll.setStyleSheet(
            "QScrollArea { background-color: #090C10; border: 1px solid #27313A; "
            "border-radius: 10px; }"
        )
        rules_page = QWidget()
        rules_page.setStyleSheet("background-color: #090C10;")
        rules_layout = QVBoxLayout(rules_page)
        rules_layout.setContentsMargins(14, 4, 14, 12)
        rules_layout.setSpacing(5)

        categories = list(dict.fromkeys(rule[3] for rule in self.shutup_rules))
        self.shutup_checkboxes = []
        self.shutup_category_buttons = []
        self.shutup_category_stack = None
        for cat_index, cat in enumerate(categories):
            cat_rules = [rule for rule in self.shutup_rules if rule[3] == cat]
            heading_row = QHBoxLayout()
            top_margin = 2 if cat_index == 0 else 16
            heading_row.setContentsMargins(4, top_margin, 4, 6)
            heading = QLabel(cat.upper())
            heading.setStyleSheet(
                f"color: {self.accent}; font-size: 12px; font-weight: 600; "
                "letter-spacing: 1px; border: none;"
            )
            count_label = QLabel(f"{len(cat_rules)} AYAR")
            count_label.setStyleSheet(
                "color: #716677; font-size: 9px; letter-spacing: 1px; border: none;"
            )
            heading_row.addWidget(heading)
            heading_row.addStretch()
            heading_row.addWidget(count_label)
            rules_layout.addLayout(heading_row)

            for rule_index, (code, sign, desc, category) in enumerate(cat_rules):
                tile = QFrame()
                tile.setObjectName(f"PrivacyTile{code}")
                tile.setMinimumHeight(50)
                tile.setStyleSheet(
                    f"QFrame#PrivacyTile{code} {{ background-color: #0E1318; "
                    "border: 1px solid #232C35; border-radius: 8px; }"
                )
                tile_layout = QHBoxLayout(tile)
                tile_layout.setContentsMargins(12, 7, 10, 7)
                tile_layout.setSpacing(8)
                chk = AnimatedTickCheckBox(desc)
                chk.rule_code = code
                chk.setChecked(self.shutup_vars.get(code, False))
                chk.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                chk.toggled.connect(
                    lambda state, c=code: self._on_shutup_checkbox_toggled(c, state)
                )
                chk.setStyleSheet(
                    "QCheckBox { background-color: transparent; border: none; "
                    "color: #F1F4F7; font-size: 12px; font-weight: 500; padding: 0; }"
                )
                risk = self._get_shutup_risk_level(code, desc, category)
                CTkToolTip(
                    chk,
                    self._get_shutup_tooltip(code, desc, risk, category),
                    risk_level=risk,
                )
                status_label = QLabel("Önerilen" if sign == "+" else "İsteğe bağlı")
                risk_color = {0: "#65DFA9", 1: "#E8B65A", 2: "#FF738F"}[risk]
                status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                status_label.setFixedWidth(82)
                status_label.setStyleSheet(
                    f"color: {risk_color}; background-color: #151B21; font-size: 10px; "
                    f"border: 1px solid {risk_color}; border-radius: 10px; padding: 3px 7px;"
                )
                tile_layout.addWidget(chk)
                tile_layout.addStretch()
                tile_layout.addWidget(status_label)
                rules_layout.addWidget(tile)
                self.shutup_checkboxes.append(chk)

        rules_layout.addStretch()
        rules_scroll.setWidget(rules_page)
        layout.addWidget(rules_scroll, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(9)
        cancel_btn = QPushButton("Kaydetmeden iptal et")
        cancel_btn.clicked.connect(self.cancel_shutup_selection)
        save_btn = QPushButton("Ayarları kaydet ve dön")
        save_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self.accent}; color: #FFFFFF; "
            "border: 1px solid #FF6675; font-weight: bold; }}\n"
            f"QPushButton:hover {{ background-color: {self.accent_hover}; }}"
        )
        save_btn.clicked.connect(self.save_shutup_selection)
        bottom_row.addWidget(cancel_btn)
        bottom_row.addWidget(save_btn)
        layout.addLayout(bottom_row)


    def build_restore_frame(self):
        layout = QVBoxLayout(self.restore_frame)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        section = QLabel("Sistem / Geri yükleme")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; border: none;"
        )
        title = QLabel("Optimizasyonları geri yükle")
        title.setStyleSheet("color: #F4F7FA; font-size: 23px; font-weight: 700; border: none;")
        subtitle = QLabel(
            "Uygulanan sistem değişikliklerini, güvenlik ilkelerini veya ağ yapılandırmasını "
            "orijinal Windows varsayılanlarına geri döndürün."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #929DA8; font-size: 12px; border: none;")

        layout.addWidget(section)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        container = QWidget()
        container.setStyleSheet("background-color: transparent; border: none;")
        card_layout = QVBoxLayout(container)
        card_layout.setContentsMargins(0, 4, 0, 8)
        card_layout.setSpacing(10)

        cards = [
            (
                "Windows Defender'ı geri aç",
                "Devre dışı bırakılan Windows Defender gerçek zamanlı korumasını, antivirüs motorunu, "
                "SmartScreen filtresini ve arka plan güvenlik servislerini yeniden başlatıp varsayılana döndürür.",
                "Defender'ı Etkinleştir",
                self._restore_defender_action,
                "#55D67A"
            ),
            (
                "Windows Update güncellemelerini geri aç",
                "2099 yılına kadar ertelenmiş Windows güncellemeleri kısıtlamalarını kaldırır, "
                "güncelleme servislerini (wuauserv, UsoSvc) otomatik moda alır ve güncellemeleri yeniden başlatır.",
                "Güncellemeleri Başlat",
                self._restore_updates_action,
                "#55D67A"
            ),
            (
                "DNS ve ağ ayarlarını sıfırla (DHCP / IPv6)",
                "Statik DNS ve DoH (DNS over HTTPS) yapılandırmalarını temizler, bağdaştırıcıları otomatik "
                "DHCP moduna döndürür, devre dışı bırakılmış IPv6 protokolünü tekrar açar ve DNS önbelleğini temizler.",
                "Ağı Varsayılana Döndür",
                self._restore_network_action,
                "#55D67A"
            ),
            (
                "Yapışkan tuşları ve klavye erişilebilirliğini sıfırla",
                "Kapatılmış Yapışkan Tuşlar, Filtre Tuşları ve Geçiş Tuşları kısayollarını Windows varsayılan "
                "erişilebilirlik ayarlarına döndürür ve bellekte anında uygular.",
                "Klavye Ayarlarını Sıfırla",
                self._restore_sticky_keys_action,
                "#55D67A"
            ),
            (
                "Windows Sistem Geri Yükleme Noktaları",
                "Windows Sistem Geri Yükleme (System Restore) aracını açarak bilgisayarınızı önceki bir "
                "tarihteki kararlı geri yükleme noktasına döndürmenizi sağlar.",
                "Sistem Geri Yüklemeyi Aç",
                self._open_system_restore_action,
                "#00B4D8"
            ),
        ]

        self.restore_action_buttons = []
        for card_title, card_desc, btn_text, handler, btn_color in cards:
            cframe = QFrame()
            cframe.setStyleSheet(
                "QFrame { background-color: #0E1318; border: 1px solid #232C35; border-radius: 8px; }"
            )
            c_layout = QHBoxLayout(cframe)
            c_layout.setContentsMargins(16, 12, 16, 12)
            c_layout.setSpacing(14)

            text_box = QVBoxLayout()
            text_box.setSpacing(4)
            lbl_title = QLabel(card_title)
            lbl_title.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 700; border: none;")
            lbl_desc = QLabel(card_desc)
            lbl_desc.setWordWrap(True)
            lbl_desc.setStyleSheet("color: #8C9BA8; font-size: 11px; border: none;")
            text_box.addWidget(lbl_title)
            text_box.addWidget(lbl_desc)

            action_btn = QPushButton(btn_text)
            action_btn.setFixedSize(180, 38)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            action_btn.setStyleSheet(
                f"QPushButton {{ background-color: #141B22; color: {btn_color}; border: 1px solid #2C3845; "
                "border-radius: 6px; font-weight: bold; font-size: 11px; }\n"
                f"QPushButton:hover {{ background-color: #1B2631; border-color: {btn_color}; }}\n"
                "QPushButton:disabled { background-color: #111519; color: #505A65; border-color: #1E252C; }"
            )
            action_btn.setProperty("restore_original_text", btn_text)
            action_btn.clicked.connect(
                lambda checked=False, h=handler, button=action_btn: h(button)
            )
            self.restore_action_buttons.append(action_btn)

            c_layout.addLayout(text_box, 1)
            c_layout.addWidget(action_btn, 0)
            card_layout.addWidget(cframe)

        card_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

    def _start_restore_action(self, button, runner, default_success_msg):
        """Geri yükleme işini yakalanmamış thread hatası bırakmadan yürüt."""
        if button is not None:
            button.setEnabled(False)
            button.setText("UYGULANIYOR…")
        if hasattr(self, "status_toast") and self.status_toast:
            self.status_toast.show_message(
                "Geri yükleme ayarı uygulanıyor…",
                success=False,
            )

        def worker():
            try:
                success, message = runner()
            except Exception as exc:
                success = False
                message = f"Geri yükleme uygulanamadı: {str(exc)[:180]}"
            self.ui_queue.put({
                "action": "restore_action_done",
                "button": button,
                "success": success,
                "message": message or default_success_msg,
            })

        threading.Thread(target=worker, daemon=True).start()

    def _restore_defender_action(self, button=None):
        self._start_restore_action(
            button,
            restore_windows_defender,
            "Windows Defender ve güvenlik servisleri yeniden etkinleştirildi.",
        )

    def _restore_updates_action(self, button=None):
        self._start_restore_action(
            button,
            restore_windows_updates,
            "Windows Güncellemeleri kısıtlaması kaldırıldı ve servisler başlatıldı.",
        )

    def _restore_network_action(self, button=None):
        self._start_restore_action(
            button,
            restore_network_settings,
            "DNS ve ağ ayarları otomatik DHCP moduna sıfırlandı.",
        )

    def _restore_sticky_keys_action(self, button=None):
        self._start_restore_action(
            button,
            restore_sticky_keys,
            "Klavye erişilebilirlik (Yapışkan Tuşlar) ayarları sıfırlandı.",
        )

    def _open_system_restore_action(self, button=None):
        ok = open_system_restore_gui()
        if ok and hasattr(self, "status_toast") and self.status_toast:
            self.status_toast.show_message(
                "Windows Sistem Geri Yükleme aracı açıldı.",
                success=True,
                auto_hide_ms=3200,
            )

    def _show_shutup_category(self, index):
        if self.shutup_category_stack is None:
            return
        index = max(0, min(index, self.shutup_category_stack.count() - 1))
        self.shutup_category_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.shutup_category_buttons):
            if button_index == index:
                button.setStyleSheet(
                    "QPushButton { background-color: #261217; color: #FFFFFF; "
                    "border: none; border-left: 2px solid #FF6574; "
                    "border-radius: 5px; text-align: left; padding-left: 10px; font-weight: bold; }"
                )
            else:
                button.setStyleSheet(
                    "QPushButton { background-color: transparent; color: #9AA5B1; "
                    "border: none; border-left: 2px solid transparent; "
                    "border-radius: 5px; text-align: left; padding-left: 10px; }"
                    "QPushButton:hover { background-color: #151A20; color: #F5F7FA; }"
                )

    # ---------- toggle helpers ----------
    def _on_app_checkbox_toggled(self, name, state):
        self.app_vars[name] = state
        if self._bulk_toggle_in_progress:
            return
        any_selected = any(self.app_vars.values())
        self.cfg_apps_enabled = any_selected
        if hasattr(self, 'app_master_chk'):
            self.app_master_chk.setChecked(any_selected)

    def _on_shutup_checkbox_toggled(self, code, state):
        self.shutup_vars[code] = state
        if self._bulk_toggle_in_progress:
            return
        any_selected = any(self.shutup_vars.values())
        self.cfg_shutup10 = any_selected
        if hasattr(self, 'shutup_master_chk'):
            self.shutup_master_chk.setChecked(any_selected)
    def toggle_all_debloat(self, state):
        state = bool(state)
        defender_checkbox = getattr(self, "defender_checkbox", None)
        if state and defender_checkbox is not None and not defender_checkbox.isChecked():
            QTimer.singleShot(0, lambda: self._show_defender_warning(lambda: self._animate_all_debloat_choices(True)))
            return
        self._animate_all_debloat_choices(state)

    def _show_defender_warning(self, on_accept):
        """Defender uyarısını donma yaratmayan asenkron modal olarak göster. Defender zaten kapalıysa doğrudan uygular."""
        if not is_defender_active():
            on_accept()
            return
        dialog = DefenderWarningDialog(self)
        def on_finished(result):
            if result == int(QDialog.DialogCode.Accepted):
                on_accept()
        dialog.finished.connect(on_finished)
        dialog.open()

    def _animate_all_debloat_choices(self, state):
        """Toplu seçimi tüm kartlar ve bağımlılıklar için tek bir ana animatörle %100 senkronize uygular."""
        state = bool(state)
        self._bulk_toggle_generation = getattr(self, "_bulk_toggle_generation", 0) + 1
        self._bulk_toggle_in_progress = True
        try:
            self.cfg_apps_enabled = state
            self.cfg_shutup10 = state
            for app_name, _ in self.bloat_apps:
                self.app_vars[app_name] = state
            for code in tuple(self.shutup_vars):
                self.shutup_vars[code] = state

            # Alt diyaloglardaki görünmeyen checkbox'ları timer kuyruğuna sokmadan anında eşitle
            for chk in getattr(self, "app_checkboxes", []):
                chk.blockSignals(True)
                chk.setCheckedImmediate(state)
                chk.blockSignals(False)

            for chk in getattr(self, "shutup_checkboxes", []):
                chk.blockSignals(True)
                chk.setCheckedImmediate(state)
                chk.blockSignals(False)

            for chk in getattr(self, "debloat_checkboxes", []):
                attr = getattr(chk, "attr_name", None)
                if attr:
                    setattr(self, attr, state)

            # Ana Debloat sekmesindeki görünür switch'leri topla
            target_switches = [
                getattr(self, "app_master_chk", None),
                getattr(self, "shutup_master_chk", None),
                *getattr(self, "debloat_checkboxes", []),
            ]
            target_switches = [sw for sw in target_switches if sw is not None]

            for sw in target_switches:
                if hasattr(sw, "_switch_timer"):
                    sw._switch_timer.stop()
                sw.blockSignals(True)
                sw.setChecked(state)
                sw._knob_target = 1.0 if state else 0.0
                sw.blockSignals(False)

            # Bireysel 40 ayrı timer yerine TEK BİR ana animatör ile tüm switch'leri senkronize kaydır
            if not hasattr(self, "_master_bulk_anim"):
                self._master_bulk_anim = QVariantAnimation(self)
                self._master_bulk_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            else:
                self._master_bulk_anim.stop()

            start_val = target_switches[0]._knob_progress if target_switches else (0.0 if state else 1.0)
            end_val = 1.0 if state else 0.0

            self._master_bulk_anim.setDuration(220)
            self._master_bulk_anim.setStartValue(start_val)
            self._master_bulk_anim.setEndValue(end_val)

            def on_bulk_step(val):
                for sw in target_switches:
                    sw._knob_progress = val
                    sw.update()

            try:
                self._master_bulk_anim.valueChanged.disconnect()
            except Exception:
                pass
            self._master_bulk_anim.valueChanged.connect(on_bulk_step)
            self._master_bulk_anim.start()
        finally:
            self._bulk_toggle_in_progress = False
            self._update_debloat_selection_count()

    def toggle_all_apps(self, state):
        state = bool(state)
        self._bulk_toggle_in_progress = True
        try:
            for (app_name, _), chk in zip(
                self.bloat_apps, getattr(self, 'app_checkboxes', [])
            ):
                self.app_vars[app_name] = state
                chk.blockSignals(True)
                chk.setCheckedImmediate(state)
                chk.blockSignals(False)
            self.cfg_apps_enabled = state and bool(self.app_vars)
            if hasattr(self, 'app_master_chk'):
                self.app_master_chk.setChecked(self.cfg_apps_enabled)
        finally:
            self._bulk_toggle_in_progress = False
        self._update_debloat_selection_count()

    def toggle_all_shutup(self, state):
        state = bool(state)
        self._bulk_toggle_in_progress = True
        try:
            for chk in getattr(self, 'shutup_checkboxes', []):
                code = getattr(chk, "rule_code", "")
                if code:
                    self.shutup_vars[code] = state
                chk.blockSignals(True)
                chk.setCheckedImmediate(state)
                chk.blockSignals(False)
            self.cfg_shutup10 = state and bool(self.shutup_vars)
            if hasattr(self, 'shutup_master_chk'):
                self.shutup_master_chk.setChecked(self.cfg_shutup10)
        finally:
            self._bulk_toggle_in_progress = False
        self._update_debloat_selection_count()


    def select_recommended_shutup(self):
        self._bulk_toggle_in_progress = True
        try:
            for chk in getattr(self, 'shutup_checkboxes', []):
                code = getattr(chk, "rule_code", "")
                if code:
                    is_rec = any(r[0] == code and r[1] == "+" for r in self.shutup_rules) or code in ("M013", "M014")
                    self.shutup_vars[code] = is_rec
                    chk.setChecked(is_rec)
            self.cfg_shutup10 = any(self.shutup_vars.values())
            if hasattr(self, 'shutup_master_chk'):
                self.shutup_master_chk.setChecked(self.cfg_shutup10)
        finally:
            self._bulk_toggle_in_progress = False
        self._update_debloat_selection_count()

    def _apply_shutup_rules_sync(self):
        """O&O ShutUp10 yapılandırmasını seçilen kurallara göre oluşturup sessizce uygular."""
        cfg_source = self.get_binary_path("ooshutup10.cfg")
        if not os.path.isfile(cfg_source) or not os.path.isfile(self.oosu_exe):
            self._apply_privacy_fallback_registry()
            return

        try:
            with open(cfg_source, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            out_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    out_lines.append(line)
                    continue
                parts = re.split(r"\t+|\s{2,}", stripped, maxsplit=2)
                if len(parts) >= 2:
                    code = parts[0].strip()
                    if code in self.shutup_vars:
                        desired = "+" if self.shutup_vars[code] else "-"
                    else:
                        desired = parts[1].strip()
                    comment = f"\t# {parts[2]}" if len(parts) > 2 else ""
                    out_lines.append(f"{code}\t{desired}{comment}\n")
                else:
                    out_lines.append(line)

            fd, temp_cfg = tempfile.mkstemp(prefix="winkit_shutup_", suffix=".cfg")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(out_lines)

            subprocess.run(
                [self.oosu_exe, temp_cfg, "/quiet"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                timeout=60,
                check=False,
            )
            try:
                os.unlink(temp_cfg)
            except OSError:
                pass
        except Exception as exc:
            append_runtime_diagnostic(f"OOSU10 execution exception: {exc}")

        self._apply_privacy_fallback_registry()

    def _apply_privacy_fallback_registry(self):
        """Harita güncellemesi ve telemetri ayarlarını Registry üzerinden de güvenceye alır, arama çubuğunu korur ve silinen SecHealthUI ayar sayfalarını gizler."""
        try:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\Maps", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                winreg.SetValueEx(k, "AutoDownloadAndUpdateMapData", 0, winreg.REG_DWORD, 0)
                winreg.SetValueEx(k, "AllowUntriggeredNetworkTrafficOnSettingsPage", 0, winreg.REG_DWORD, 0)
            
            subprocess.run(["sc.exe", "config", "MapsBroker", "start=", "disabled"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=5, check=False)
            subprocess.run(["sc.exe", "stop", "MapsBroker"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=5, check=False)

            # SecHealthUI / Windows Güvenliği ayar sayfalarının görünür kalması sağlanır (HVCI vb. için)
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                    winreg.DeleteValue(k, "SettingsPageVisibility")
            except OSError:
                pass
        except Exception:
            pass

    def open_app_checklist_view(self):
        self.temp_app_vars = self.app_vars.copy()
        for chk in getattr(self, 'app_checkboxes', []):
            chk.setChecked(self.app_vars.get(chk.text(), False))
        self.show_page("app_checklist")

    def save_app_selection(self):
        any_selected = any(self.app_vars.values())
        self.cfg_apps_enabled = any_selected
        if hasattr(self, 'app_master_chk'):
            self.app_master_chk.setChecked(any_selected)
        self.show_page("debloat")

    def cancel_app_selection(self):
        self.app_vars = self.temp_app_vars.copy()
        any_selected = any(self.app_vars.values())
        self.cfg_apps_enabled = any_selected
        if hasattr(self, 'app_master_chk'):
            self.app_master_chk.setChecked(any_selected)
        self.show_page("debloat")

    def open_shutup_checklist_view(self):
        self.temp_shutup_vars = self.shutup_vars.copy()
        for chk in getattr(self, 'shutup_checkboxes', []):
            code = getattr(chk, 'rule_code', None)
            if code:
                chk.setChecked(self.shutup_vars.get(code, False))
        self.show_page("shutup_checklist")

    def save_shutup_selection(self):
        any_selected = any(self.shutup_vars.values())
        self.cfg_shutup10 = any_selected
        if hasattr(self, 'shutup_master_chk'):
            self.shutup_master_chk.setChecked(any_selected)
        self.show_page("debloat")

    def cancel_shutup_selection(self):
        self.shutup_vars = self.temp_shutup_vars.copy()
        any_selected = any(self.shutup_vars.values())
        self.cfg_shutup10 = any_selected
        if hasattr(self, 'shutup_master_chk'):
            self.shutup_master_chk.setChecked(any_selected)
        self.show_page("debloat")

    def open_windows_update_options(self):
        from gui.dialogs import WindowsUpdateOptionsDialog
        current_mode = getattr(self, "cfg_update_mode", "disable_auto_allow_features")
        dialog = WindowsUpdateOptionsDialog(current_mode=current_mode, parent=self)
        if dialog.exec():
            self.cfg_update_mode = dialog.selected_mode

    def on_apply_btn_click(self):
        if self.apply_btn.text() == "SONUÇLARI GÖSTER":
            self.show_page("debloat_console")
        else:
            supported, version, build, product = is_supported_windows_release()
            if not supported:
                detected = f"{product or 'Bilinmeyen Windows'} {version or '?'} (build {build or '?'})"
                self.log(
                    f"ENGELLENDİ: Bu sürüm yalnızca Windows 11 {SUPPORTED_WINDOWS_VERSION} "
                    f"(build {SUPPORTED_WINDOWS_BUILD}) içindir. Algılanan: {detected}",
                    "#FF5555",
                    target="debloat",
                )
                return
            # Tıklamaya aynı karede görsel yanıt ver; overlay oluşturmayı bir
            # sonraki olay döngüsüne bırakarak basılma animasyonunun çizilmesini sağla.
            self.apply_btn.setEnabled(False)
            self.apply_btn.setText("HAZIRLANIYOR")

            def show_apply_overlay():
                self.show_restore_popup("debloat")
                self.apply_btn.setText("Optimize et")
                self.apply_btn.setEnabled(True)

            QTimer.singleShot(0, show_apply_overlay)

    def actual_start_debloat(self):
        self.start_debloat_thread()

    def start_debloat_thread(self):
        if self.is_processing:
            return
        supported, version, build, product = is_supported_windows_release()
        if not supported:
            detected = f"{product or 'Bilinmeyen Windows'} {version or '?'} (build {build or '?'})"
            self.log(
                f"ENGELLENDİ: Desteklenmeyen Windows sürümü: {detected}",
                "#FF5555",
                target="debloat",
            )
            return
        self.is_processing = True
        self.current_worker = "debloat"
        self._set_navigation_enabled(False)
        self.apply_btn.setEnabled(False)
        self.apply_btn.setText("İŞLEM SÜRÜYOR")
        if hasattr(self, 'console_back_btn'):
            self.console_back_btn.setEnabled(False)
        if hasattr(self, 'console_debloat') and self.console_debloat:
            self.console_debloat.clear()
        self._stage_progress_rows.clear()
        self._active_progress_row = None
        self._active_progress_target = None
        self.active_progress_base = None
        self.active_progress_pct = None
        self.show_page("debloat_console")
        if self.console_loading_ring is not None:
            self.console_loading_ring.start()
        if self.page_switch_btn is not None:
            self.page_switch_btn.setEnabled(False)
        self.spinner_timer.start(16)
        threading.Thread(target=self.debloat_worker, daemon=True).start()

    def start_injection_thread(self):
        if self.is_processing:
            return
        if not any([self.bypass_requirements, self.bypass_online_account, self.bypass_bitlocker]):
            self.log("HATA: En az bir seçeneği aktif etmelisiniz!", "#FF0000", target="iso")
            self.show_page("iso_console")
            return
        source = self.iso_entry.text().strip()
        if not os.path.exists(source):
            self.log("HATA: ISO dosyası bulunamadı!", "#FF0000", target="iso")
            self.show_page("iso_console")
            return
        source_path = Path(source)
        # Kaynak önce geçici klasöre tamamen ayıklanır; son ISO aynı klasörde
        # geçici bir dosyada oluşturulup atomik olarak kaynak ISO'nun yerini alır.
        output = str(source_path)
        valid, error = validate_iso_paths(source, output)
        if not valid:
            self.log(f"HATA: {error}", "#FF0000", target="iso")
            self.show_page("iso_console")
            return
        missing_tools = [
            name
            for name, path in (
                ("7z.exe", self.sevenzip),
                ("7z.dll", str(Path(self.sevenzip).with_name("7z.dll"))),
                ("oscdimg.exe", self.oscdimg_exe),
            )
            if not Path(path).is_file()
        ]
        if missing_tools:
            self.log(f"HATA: Eksik araçlar: {', '.join(missing_tools)}", "#FF0000", target="iso")
            self.show_page("iso_console")
            return
        self.actual_start_iso(source, output)

    def actual_start_iso(self, source, output):
        self.is_processing = True
        self.current_worker = "iso"
        self._set_navigation_enabled(False)
        if self.console_iso is not None:
            self.console_iso.clear()
            self.console_iso.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        self._active_progress_row = None
        self._active_progress_target = None
        self.active_progress_base = None
        self.active_progress_pct = None
        if self.iso_console_back_btn is not None:
            self.iso_console_back_btn.setEnabled(False)
        self.show_page("iso_console")
        if self.iso_console_loading_ring is not None:
            self.iso_console_loading_ring.start()
        self.spinner_timer.start(16)
        self.inject_btn.setEnabled(False)
        self.inject_btn.setText("İŞLEM SÜRÜYOR")
        threading.Thread(target=self.nuclear_worker, args=(source, output), daemon=True).start()

    def nuclear_worker(self, source, output):
        def on_progress(text_base, pct):
            if pct == 100:
                self.ui_queue.put({
                    "action": "progress_stop",
                    "text_base": text_base,
                    "result": "Ayıklandı" if "Ayıklanıyor" in text_base else "oluşturuldu",
                    "target": "iso",
                })
            else:
                self.ui_queue.put({
                    "action": "progress_update",
                    "text_base": text_base,
                    "pct": pct,
                    "color": "#E7ECF2",
                    "pct_color": "#E63B4D",
                    "target": "iso",
                })

        def on_stage_start(stage_id, text_base):
            self.ui_queue.put({
                "action": "stage_start",
                "stage_id": stage_id,
                "text_base": text_base,
                "color": "#E2E2E2",
                "target": "iso",
            })

        def on_stage_finish(stage_id, result, result_color):
            self.ui_queue.put({
                "action": "stage_finish",
                "stage_id": stage_id,
                "result": result,
                "result_color": result_color,
                "target": "iso",
            })

        def on_log(text, color):
            self.ui_queue.put({
                "action": "log",
                "text": text,
                "color": color,
                "target": "iso",
            })

        try:
            ok, res = build_custom_iso(
                source=Path(source),
                output=Path(output),
                sevenzip_exe=self.sevenzip,
                oscdimg_exe=self.oscdimg_exe,
                bypass_requirements=getattr(self, "bypass_requirements", False),
                bypass_online_account=getattr(self, "bypass_online_account", False),
                bypass_bitlocker=getattr(self, "bypass_bitlocker", False),
                progress_callback=on_progress,
                stage_start=on_stage_start,
                stage_finish=on_stage_finish,
                log_callback=on_log,
            )
            if ok:
                self.ui_queue.put({
                    "action": "progress_stop",
                    "text_base": "ISO yeniden oluşturuluyor",
                    "result": "oluşturuldu",
                    "target": "iso",
                })
                self.ui_queue.put({
                    "action": "log_segments",
                    "segments": [
                        ("• ", "#8C9BA8"),
                        ("İşlem tamamlandı: ", "#E7ECF2"),
                        (str(Path(output).name), "#55D67A"),
                        ("  ✔", "#55D67A"),
                    ],
                    "target": "iso",
                })
            else:
                self.ui_queue.put({"action": "log", "text": f"HATA: {res}", "color": "#FF5555", "target": "iso"})
        except Exception as exc:
            self.ui_queue.put({"action": "log", "text": f"HATA: {str(exc)}", "color": "#FF5555", "target": "iso"})
        finally:
            self.ui_queue.put({"action": "finish_iso"})

    def generate_xml(self):
        return generate_unattend_xml(
            bypass_requirements=getattr(self, "bypass_requirements", False),
            bypass_online_account=getattr(self, "bypass_online_account", False),
            bypass_bitlocker=getattr(self, "bypass_bitlocker", False),
        )

    def _animate_iso_border(self, target_hex):
        if not hasattr(self, "_iso_border_anim"):
            self._iso_border_anim = QVariantAnimation(self)
            self._iso_border_anim.setDuration(260)
            self._iso_border_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._iso_border_anim.valueChanged.connect(self._on_iso_border_anim_value)
            self._iso_border_current_color = QColor("#2D3742")

        target_color = QColor(target_hex)
        if getattr(self, "_iso_border_current_color", None) == target_color:
            return
        self._iso_border_anim.stop()
        self._iso_border_anim.setStartValue(self._iso_border_current_color)
        self._iso_border_anim.setEndValue(target_color)
        self._iso_border_anim.start()

    def _trigger_iso_selected_pulse(self):
        if not hasattr(self, "_iso_pulse_anim"):
            self._iso_pulse_anim = QVariantAnimation(self)
            self._iso_pulse_anim.setDuration(650)
            self._iso_pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
            self._iso_pulse_anim.valueChanged.connect(self._on_iso_border_anim_value)

        self._iso_pulse_anim.stop()
        self._iso_pulse_anim.setKeyValues([
            (0.0, QColor("#2D3742")),
            (0.45, QColor("#FF6576")),
            (0.75, QColor("#B82233")),
            (1.0, QColor("#E63B4D")),
        ])
        self._iso_pulse_anim.start()

    def _on_iso_border_anim_value(self, color):
        if isinstance(color, QColor):
            self._iso_border_current_color = color
            if hasattr(self, "iso_path_frame"):
                self.iso_path_frame.setStyleSheet(
                    f"QFrame#IsoPathFrame {{ background-color: #0D1116; "
                    f"border: 1.5px solid {color.name()}; border-radius: 8px; }}"
                )

    def _update_iso_frame_style(self):
        if hasattr(self, "iso_path_frame") and hasattr(self, "iso_entry"):
            text = self.iso_entry.text().strip()
            has_iso = bool(text) and text.casefold().endswith(".iso")
            target_color = "#E63B4D" if has_iso else "#2D3742"
            self._animate_iso_border(target_color)

    def browse_iso(self):
        path, _ = QFileDialog.getOpenFileName(self, "ISO Seç", filter="ISO Files (*.iso)")
        if path:
            self.iso_entry.setText(path)
            if self._iso_path_anim is not None:
                self._iso_path_anim.stop()
            self.iso_entry.setGraphicsEffect(None)
            if self.console_iso is not None:
                self.console_iso.clear()
            QTimer.singleShot(100, self._trigger_iso_selected_pulse)

    def debloat_worker(self):
        try:
            self._debloat_worker_impl()
        except Exception as exc:
            self.ui_queue.put({
                "action": "log",
                "text": f"KRİTİK HATA: İşlem durduruldu: {exc}",
                "color": "#FF5555",
                "target": "debloat",
            })
        finally:
            self.ui_queue.put({"action": "finish_debloat", "target": "debloat"})

    def _debloat_worker_impl(self):
        stage_sequence = 0
        pending_stage_ids = {}
        operation_had_failures = False
        shell_sensitive_removal_selected = False
        service_force_configure = None
        service_targets_for_final = []
        services_stage_id = None

        def stage_start(text, color="#E2E2E2"):
            nonlocal stage_sequence
            stage_sequence += 1
            stage_name = text.rstrip(".")
            stage_id = f"debloat-stage-{stage_sequence}"
            pending_stage_ids.setdefault(stage_name, []).append(stage_id)
            self.ui_queue.put({
                "action": "stage_start",
                "stage_id": stage_id,
                "text_base": stage_name,
                "color": color,
                "target": "debloat",
            })
            return stage_id

        def stage_update_title(stage_id, text):
            self.ui_queue.put({
                "action": "stage_update_title",
                "stage_id": stage_id,
                "text_base": str(text).rstrip("."),
                "target": "debloat",
            })

        def stage_done(text, result="✔", color=None):
            stage_name = text.rstrip(".")
            stage_ids = pending_stage_ids.get(stage_name, [])
            if not stage_ids:
                return
            stage_id = stage_ids.pop(0)
            result_text = str(result)
            if any(w in result_text for w in ("Uygulanamadı", "Kapatılamadı", "Etkinleştirilemedi", "HATA", "✖", "Başarısız", "kapatılamadı", "eklenemedi")):
                icon = "✖"
                icon_color = color or "#FF5C6B"
            elif any(w in result_text for w in ("Yeniden", "⚠", "Kısmi")):
                icon = "⚠"
                icon_color = color or "#FFB86C"
            else:
                icon = "✔"
                icon_color = color or "#55D67A"
            if result in ("✔", "✖", "⚠"):
                icon = result
            self.ui_queue.put({
                "action": "stage_finish",
                "stage_id": stage_id,
                "result": icon,
                "result_color": icon_color,
                "target": "debloat",
            })

        def ensure_hvci_enabled():
            return True

        reg_lines = ["Windows Registry Editor Version 5.00\n"]

        def commit_registry_stage(stage_text=None, success_text="✔"):
            """Bir aşamanın Registry değişikliğini hemen uygular ve aynı satırı bitirir."""
            nonlocal reg_lines
            if len(reg_lines) <= 1:
                if stage_text:
                    stage_done(stage_text, success_text)
                return True
            reg_fd, reg_path = tempfile.mkstemp(
                prefix="winkit_registry_", suffix=".reg"
            )
            import_ok = False
            error_text = ""
            try:
                with os.fdopen(reg_fd, "w", encoding="utf-16") as reg_file:
                    reg_file.write("\n".join(reg_lines))
                result = subprocess.run(
                    ["reg.exe", "import", reg_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=CREATE_NO_WINDOW,
                    check=False,
                )
                if result.returncode != 0:
                    error_text = result.stderr.strip() or f"çıkış kodu {result.returncode}"
                else:
                    import_ok = True
            except Exception as exc:
                error_text = str(exc)
            finally:
                reg_lines = ["Windows Registry Editor Version 5.00\n"]
                try:
                    os.unlink(reg_path)
                except OSError:
                    pass
            if stage_text:
                stage_done(
                    stage_text,
                    success_text if import_ok else "Uygulanamadı!",
                    None if import_ok else "#FF6B6B",
                )
            return import_ok


        # 1. Detaylı mavi ekran
        if self.cfg_bsod:
            try:
                stage_start("Detaylı mavi ekran etkinleştiriliyor")
                reg_lines.append(r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\CrashControl]")
                reg_lines.append('"DisplayParameters"=dword:00000001')
                reg_lines.append("")
                commit_registry_stage("Detaylı mavi ekran etkinleştiriliyor", "etkinleştirildi")
            except Exception:
                stage_done("Detaylı mavi ekran etkinleştiriliyor", "etkinleştirilemedi")

        # 2. Karanlık tema
        if self.cfg_dark:
            try:
                stage_start("Karanlık tema uygulanıyor")
                reg_lines.append(r"[HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize]")
                reg_lines.append('"AppsUseLightTheme"=dword:00000000')
                reg_lines.append('"SystemUsesLightTheme"=dword:00000000')
                reg_lines.append("")
                commit_registry_stage("Karanlık tema uygulanıyor", "uygulandı")
            except Exception:
                stage_done("Karanlık tema uygulanıyor", "uygulanamadı")

        # 3. Dosya uzantıları
        if self.cfg_extensions:
            try:
                stage_start("Dosya görünümü ayarlanıyor")
                reg_lines.append(r"[HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced]")
                reg_lines.append('"HideFileExt"=dword:00000000')
                reg_lines.append('"Hidden"=dword:00000001')
                reg_lines.append("")
                commit_registry_stage("Dosya görünümü ayarlanıyor", "ayarlandı")
            except Exception:
                stage_done("Dosya görünümü ayarlanıyor", "ayarlanamadı")

        # 4. Klasör görünümü
        if self.cfg_feafd:
            try:
                stage_start("Klasör görünümü ayarlanıyor")
                reg_lines.append(r"[HKEY_CURRENT_USER\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags\AllFolders\Shell]")
                reg_lines.append('"FolderType"="NotSpecified"')
                reg_lines.append("")
                commit_registry_stage("Klasör görünümü ayarlanıyor", "ayarlandı")
            except Exception:
                stage_done("Klasör görünümü ayarlanıyor", "ayarlanamadı")

        # 5. Hazırda bekletme
        if self.cfg_hibernate:
            try:
                stage_start("Hazırda bekletme kapatılıyor")
                result = subprocess.run(["powercfg.exe", "/hibernate", "off"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False)
                stage_done("Hazırda bekletme kapatılıyor", "kapatıldı" if result.returncode == 0 else "kapatılamadı")
            except Exception:
                stage_done("Hazırda bekletme kapatılıyor", "kapatılamadı")

        # 6. Oyun ayarları
        if self.cfg_gaming_tweaks:
            try:
                stage_start("Oyun ayarları uygulanıyor", "#E7ECF2")
                reg_lines.append(r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile]")
                reg_lines.append('"NetworkThrottlingIndex"=dword:ffffffff')
                reg_lines.append('"SystemResponsiveness"=dword:00000000')
                reg_lines.append("")
                reg_lines.append(r"[HKEY_CURRENT_USER\System\GameConfigStore]")
                reg_lines.append('"GameDVR_FSEBehaviorMode"=dword:00000002')
                reg_lines.append("")
                reg_lines.append(r"[HKEY_CURRENT_USER\Control Panel\Mouse]")
                reg_lines.append('"MouseSpeed"="0"')
                reg_lines.append('"MouseThreshold1"="0"')
                reg_lines.append('"MouseThreshold2"="0"')
                reg_lines.append("")
                commit_registry_stage("Oyun ayarları uygulanıyor", "uygulandı")
            except Exception:
                stage_done("Oyun ayarları uygulanıyor", "uygulanamadı")

        # 7. Mağaza ve Başlat önerileri
        if self.cfg_store_recommend:
            try:
                stage_start("Mağaza ve Başlat önerileri kapatılıyor")
                hkey_cdm = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
                reg_lines.append("[HKEY_CURRENT_USER\\" + hkey_cdm + "]")
                reg_lines.append('"SystemPaneSuggestionsEnabled"=dword:00000000')
                reg_lines.append('"SubscribedContent-338388Enabled"=dword:00000000')
                reg_lines.append('"SubscribedContent-338389Enabled"=dword:00000000')
                reg_lines.append('"SubscribedContent-310093Enabled"=dword:00000000')
                reg_lines.append('"OemPreInstalledAppsEnabled"=dword:00000000')
                reg_lines.append('"PreInstalledAppsEnabled"=dword:00000000')
                reg_lines.append('"SilentInstalledAppsEnabled"=dword:00000000')
                reg_lines.append("")
                commit_registry_stage("Mağaza ve Başlat önerileri kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("Mağaza ve Başlat önerileri kapatılıyor", "kapatılamadı")

        # 8. Ultra performans güç planı
        if self.cfg_ultraperf:
            try:
                stage_start("Ultra performans güç planı etkinleştiriliyor", "#E7ECF2")
                ultimate_guid = "e9a42b02-d5df-448d-aa00-03f14749eb61"
                list_result = subprocess.run(["powercfg.exe", "/list"], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW, check=False)
                list_output = list_result.stdout or ""
                selected_guid = ultimate_guid if ultimate_guid in list_output.casefold() else None
                if selected_guid is None:
                    duplicate_result = subprocess.run(["powercfg.exe", "/duplicatescheme", ultimate_guid], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW, check=False)
                    match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", duplicate_result.stdout or "")
                    selected_guid = match.group(0) if match else None
                if selected_guid:
                    subprocess.run(["powercfg.exe", "/setactive", selected_guid], creationflags=CREATE_NO_WINDOW, check=False)
                    stage_done("Ultra performans güç planı etkinleştiriliyor", "etkinleştirildi")
                else:
                    stage_done("Ultra performans güç planı etkinleştiriliyor", "etkinleştirilemedi")
            except Exception:
                stage_done("Ultra performans güç planı etkinleştiriliyor", "etkinleştirilemedi")

        # 9. Servis optimizasyonu
        if self.cfg_services:
            try:
                services_stage_id = stage_start("Servisler durduruluyor", "#E7ECF2")
                disabled_services = [
                    "MapsBroker", "PhoneSvc", "RemoteRegistry", "RetailDemo", "dmwappushservice",
                    "SysMain", "SCardSvr", "ScDeviceEnum", "SCPolicySvc", "SEMgrSvc",
                    "lmhosts", "RmSvc", "CertPropSvc", "lfsvc", "TrkWks", "DiagTrack", "WerSvc",
                    "CDPSvc", "CDPUserSvc", "OneSyncSvc", "CloudBackupRestoreSvc",
                    "UnistoreSvc", "UserDataSvc", "MessagingService",
                    "bcastdvr", "PenService", "WpcMonSvc"
                ]
                manual_services = [
                    "XblAuthManager", "XblGameSave", "XboxGipSvc", "XboxNetApiSvc", "DoSvc"
                ]

                def force_configure_service(svc, start_value, update_ui=True):
                    if not re.fullmatch(r"[A-Za-z0-9_]{2,80}", svc):
                        return False
                    base_name = re.sub(r"_[0-9A-Fa-f]{5,}$", "", svc)
                    is_user_instance = base_name.casefold() != svc.casefold()
                    if update_ui and not is_user_instance:
                        stage_update_title(
                            services_stage_id,
                            f"Servisler durduruluyor: {base_name}",
                        )
                    start_mode = "demand" if start_value == 3 else "disabled"
                    # GUID sonekli kullanıcı servisi örnekleri ChangeServiceConfig'i
                    # reddeder. Şablonu sc.exe ile, hem şablon hem canlı örneği
                    # kayıt defteriyle ayarla; örnek için sc config sonucu bekleme.
                    config_target = base_name if is_user_instance else svc
                    config_result = subprocess.run(
                        ["sc.exe", "config", config_target, "start=", start_mode],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=CREATE_NO_WINDOW,
                        timeout=8,
                        check=False,
                    )
                    reg_results = []
                    for reg_service in dict.fromkeys((base_name, svc)):
                        reg_results.append(subprocess.run(
                            [
                                "reg.exe", "add",
                                f"HKLM\\SYSTEM\\CurrentControlSet\\Services\\{reg_service}",
                                "/v", "Start", "/t", "REG_DWORD", "/d", str(start_value),
                                "/f", "/reg:64",
                            ],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW,
                            timeout=8,
                            check=False,
                        ))
                        if reg_service.casefold() == "bcastdvr":
                            for g_path, g_val, g_data in [
                                (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\GameDVR", "AllowGameDVR", "0"),
                                (r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", "0"),
                                (r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "HistoricalCaptureEnabled", "0"),
                                (r"HKCU\System\GameConfigStore", "GameDVR_Enabled", "0"),
                                (r"HKCU\System\GameConfigStore", "GameDVR_FSEBehaviorMode", "2"),
                                (r"HKCU\System\GameConfigStore", "GameDVR_HonorUserFSEBehaviorMode", "1"),
                                (r"HKCU\System\GameConfigStore", "GameDVR_DXGIHonorFSEWindowsCompatible", "1"),
                                (r"HKCU\System\GameConfigStore", "GameDVR_EFSEFeatureFlags", "0"),
                                (r"HKCU\Software\Microsoft\GameBar", "UseNexusForGameBarEnabled", "0"),
                            ]:
                                subprocess.run(
                                    ["reg.exe", "add", g_path, "/v", g_val, "/t", "REG_DWORD", "/d", g_data, "/f", "/reg:64"],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    creationflags=CREATE_NO_WINDOW,
                                    timeout=8,
                                    check=False,
                                )
                    success = (
                        config_result.returncode == 0
                        and all(result.returncode == 0 for result in reg_results)
                    )

                    # Önce Start değerini yaz, sonra canlı örneği durdur. Tersi
                    # sırada UnistackSvcGroup örneği kısa aralıkta yeniden başlıyordu.
                    stopped = False
                    for _ in range(4):
                        subprocess.run(
                            ["sc.exe", "stop", svc],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW,
                            timeout=8,
                            check=False,
                        )
                        query_result = subprocess.run(
                            ["sc.exe", "query", svc],
                            capture_output=True,
                            text=True,
                            errors="replace",
                            creationflags=CREATE_NO_WINDOW,
                            timeout=8,
                            check=False,
                        )
                        query_text = query_result.stdout or ""
                        if query_result.returncode != 0 or re.search(
                            r"STATE\s*:\s*1\b", query_text, re.IGNORECASE
                        ):
                            stopped = True
                            break
                        time.sleep(0.18)

                    # Bazı tek-servis svchost süreçleri (özellikle RmSvc),
                    # sc stop isteğini kabul ettiği halde aynı oturumda yeniden
                    # ayağa kalkabiliyor. PID başka hiçbir servise ait değilse
                    # süreci güvenle sonlandır ve gerçek STOPPED durumunu yeniden
                    # doğrula. Paylaşılan svchost süreçlerine kesinlikle dokunma.
                    if not stopped:
                        queryex_result = subprocess.run(
                            ["sc.exe", "queryex", svc],
                            capture_output=True,
                            text=True,
                            errors="replace",
                            creationflags=CREATE_NO_WINDOW,
                            timeout=8,
                            check=False,
                        )
                        pid_match = re.search(
                            r"PID\s*:\s*(\d+)",
                            queryex_result.stdout or "",
                            re.IGNORECASE,
                        )
                        service_pid = int(pid_match.group(1)) if pid_match else 0
                        if service_pid > 0:
                            tasklist_result = subprocess.run(
                                [
                                    "tasklist.exe", "/svc", "/fi",
                                    f"PID eq {service_pid}", "/fo", "csv", "/nh",
                                ],
                                capture_output=True,
                                text=True,
                                errors="replace",
                                creationflags=CREATE_NO_WINDOW,
                                timeout=8,
                                check=False,
                            )
                            pid_services = set()
                            for row in csv.reader(
                                (tasklist_result.stdout or "").splitlines()
                            ):
                                if len(row) < 3 or row[1].strip() != str(service_pid):
                                    continue
                                pid_services.update(
                                    item.casefold()
                                    for item in re.split(r"[,\s]+", row[2].strip())
                                    if item and item.casefold() != "n/a"
                                )
                            if pid_services == {svc.casefold()}:
                                subprocess.run(
                                    ["taskkill.exe", "/pid", str(service_pid), "/f"],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    creationflags=CREATE_NO_WINDOW,
                                    timeout=8,
                                    check=False,
                                )
                                verify_result = subprocess.run(
                                    ["sc.exe", "query", svc],
                                    capture_output=True,
                                    text=True,
                                    errors="replace",
                                    creationflags=CREATE_NO_WINDOW,
                                    timeout=8,
                                    check=False,
                                )
                                stopped = (
                                    verify_result.returncode != 0
                                    or re.search(
                                        r"STATE\s*:\s*1\b",
                                        verify_result.stdout or "",
                                        re.IGNORECASE,
                                    ) is not None
                                )
                    return success and stopped

                service_force_configure = force_configure_service

                # Scan registry to find and disable all template and per-user service instances (e.g. UserDataSvc_3fa41)
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as services_key:
                        num_subkeys = winreg.QueryInfoKey(services_key)[0]
                        all_subkeys = [winreg.EnumKey(services_key, i) for i in range(num_subkeys)]
                    configured_services = set()
                    service_failures = 0
                    for subk in all_subkeys:
                        subk_lower = subk.lower()
                        for target in disabled_services:
                            target_lower = target.lower()
                            if subk_lower == target_lower or subk_lower.startswith(f"{target_lower}_"):
                                if subk_lower not in configured_services:
                                    if not force_configure_service(subk, 4):
                                        service_failures += 1
                                    service_targets_for_final.append((subk, 4))
                                    configured_services.add(subk_lower)
                        for target in manual_services:
                            target_lower = target.lower()
                            if subk_lower == target_lower or subk_lower.startswith(f"{target_lower}_"):
                                if subk_lower not in configured_services:
                                    if not force_configure_service(subk, 3):
                                        service_failures += 1
                                    service_targets_for_final.append((subk, 3))
                                    configured_services.add(subk_lower)
                    for svc in disabled_services:
                        if svc.lower() not in configured_services:
                            force_configure_service(svc, 4, update_ui=False)
                            service_targets_for_final.append((svc, 4))
                            configured_services.add(svc.lower())
                    for svc in manual_services:
                        if svc.lower() not in configured_services:
                            force_configure_service(svc, 3, update_ui=False)
                            service_targets_for_final.append((svc, 3))
                            configured_services.add(svc.lower())
                except Exception:
                    service_failures = 0
                    for svc in disabled_services:
                        if not force_configure_service(svc, 4):
                            service_failures += 1
                        service_targets_for_final.append((svc, 4))
                    for svc in manual_services:
                        if not force_configure_service(svc, 3):
                            service_failures += 1
                        service_targets_for_final.append((svc, 3))

                stage_done(
                    "Servisler durduruluyor",
                    "durduruldu" if service_failures == 0 else "Kısmi: yeniden başlatma gerekli",
                    None if service_failures == 0 else "#FFB86C",
                )
                # Oturum servisleri daha sonraki kabuk işlemlerinde yeniden
                # doğabilir. Nihai SYSTEM geçişi sonucu belirleyecek; burada
                # kalıcı hata bayrağı koyma.
            except Exception:
                stage_done("Servisler durduruluyor", "kapatılamadı", "#FF5C6B")
                operation_had_failures = True

        # 10. Klasik sağ tık menüsü
        if self.cfg_classic_menu:
            try:
                stage_start("Klasik sağ tık menüsü etkinleştiriliyor", "#E7ECF2")
                reg_lines.append(r"[HKEY_CURRENT_USER\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32]")
                reg_lines.append('@=""')
                reg_lines.append("")
                commit_registry_stage("Klasik sağ tık menüsü etkinleştiriliyor", "etkinleştirildi")
            except Exception:
                stage_done("Klasik sağ tık menüsü etkinleştiriliyor", "etkinleştirilemedi")

        # 11. Widgets
        if self.cfg_widgets:
            try:
                stage_start("Widgets kaldırılıyor")
                RegistryEngine.apply_tweak(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests", 0)
                RegistryEngine.apply_tweak(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\Start", "DisableStartFeeds", 1, winreg.REG_DWORD)
                for process_name in ("Widgets.exe", "WidgetService.exe"):
                    subprocess.run(["taskkill", "/f", "/im", process_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False)
                stage_done("Widgets kaldırılıyor", "kaldırıldı")
            except Exception:
                stage_done("Widgets kaldırılıyor", "kaldırılamadı")

        # 12. Görevi sonlandır
        if self.cfg_end_task:
            try:
                stage_start("Görevi sonlandır seçeneği etkinleştiriliyor")
                reg_lines.append(r"[HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarDeveloperSettings]")
                reg_lines.append('"TaskbarEndTask"=dword:00000001')
                reg_lines.append("")
                commit_registry_stage("Görevi sonlandır seçeneği etkinleştiriliyor", "etkinleştirildi")
            except Exception:
                stage_done("Görevi sonlandır seçeneği etkinleştiriliyor", "etkinleştirilemedi")

        # 13. Web arama önerileri
        if self.cfg_bing_search:
            try:
                stage_start("Web arama önerileri kapatılıyor")
                reg_lines.append(r"[HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Search]")
                reg_lines.append('"BingSearchEnabled"=dword:00000000')
                reg_lines.append('"CortanaConsent"=dword:00000000')
                reg_lines.append("")
                reg_lines.append(r"[HKEY_CURRENT_USER\Software\Policies\Microsoft\Windows\Explorer]")
                reg_lines.append('"DisableSearchBoxSuggestions"=dword:00000001')
                reg_lines.append("")
                commit_registry_stage("Web arama önerileri kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("Web arama önerileri kapatılıyor", "kapatılamadı")

        # 14. Windows önerileri
        if self.cfg_consumer_features:
            try:
                stage_start("Windows önerileri kapatılıyor")
                reg_lines.append(r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\CloudContent]")
                reg_lines.append('"DisableWindowsConsumerFeatures"=dword:00000001')
                reg_lines.append("")
                commit_registry_stage("Windows önerileri kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("Windows önerileri kapatılıyor", "kapatılamadı")

        # 15. Teslim iyileştirmesi
        if self.cfg_delivery_opt:
            try:
                stage_start("Teslim iyileştirmesi kapatılıyor")
                RegistryEngine.apply_tweak(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization", "DODownloadMode", 0)
                stage_done("Teslim iyileştirmesi kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("Teslim iyileştirmesi kapatılıyor", "kapatılamadı")

        # 16. Tanılama verileri
        if self.cfg_telemetry:
            try:
                stage_start("Tanılama verileri sınırlandırılıyor")
                RegistryEngine.apply_tweak(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0)
                stage_done("Tanılama verileri sınırlandırılıyor", "sınırlandırıldı")
            except Exception:
                stage_done("Tanılama verileri sınırlandırılıyor", "sınırlandırılamadı")

        # 17. Konum erişimi
        if self.cfg_location:
            try:
                stage_start("Konum erişimi kapatılıyor")
                RegistryEngine.apply_tweak(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location", "Value", "Deny", winreg.REG_SZ)
                stage_done("Konum erişimi kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("Konum erişimi kapatılıyor", "kapatılamadı")

        # 18. Yapışkan tuşlar
        if self.cfg_sticky_keys:
            try:
                stage_start("Yapışkan Tuşlar kapatılıyor")
                apply_sticky_keys_fix(False)
                for hive_name in ("HKEY_CURRENT_USER", r"HKEY_USERS\.DEFAULT"):
                    reg_lines.extend([
                        f"[{hive_name}\\Control Panel\\Accessibility\\StickyKeys]",
                        '"Flags"="506"', '"HotKeyActive"="0"', '"HotKeySound"="0"', '"ConfirmHotKey"="0"', "",
                        f"[{hive_name}\\Control Panel\\Accessibility\\Keyboard Response]",
                        '"Flags"="122"', '"HotKeyActive"="0"', '"HotKeySound"="0"', '"ConfirmHotKey"="0"', "",
                        f"[{hive_name}\\Control Panel\\Accessibility\\ToggleKeys]",
                        '"Flags"="58"', '"HotKeyActive"="0"', '"HotKeySound"="0"', '"ConfirmHotKey"="0"', "",
                    ])
                commit_registry_stage("Yapışkan Tuşlar kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("Yapışkan Tuşlar kapatılıyor", "kapatılamadı")

        # 18.b. Win+Space dil kısayolu
        if self.cfg_disable_win_space:
            try:
                stage_start("Win+Space dil kısayolu kapatılıyor")
                KeyboardRemapEngine.set_win_space_disabled(True)
                stage_done("Win+Space dil kısayolu kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("Win+Space dil kısayolu kapatılıyor", "kapatılamadı")

        # 19. BitLocker
        if self.cfg_remove_bitlocker:
            try:
                stage_start("BitLocker koruması kapatılıyor")
                reg_lines.append(r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\BitLocker]")
                reg_lines.append('"PreventDeviceEncryption"=dword:00000001')
                reg_lines.append("")
                reg_lines.append(r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\BDESVC]")
                reg_lines.append('"Start"=dword:00000004')
                reg_lines.append("")
                subprocess.run(["sc.exe", "stop", "BDESVC"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False)
                subprocess.run(["sc.exe", "config", "BDESVC", "start=", "disabled"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False)
                commit_registry_stage("BitLocker koruması kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("BitLocker koruması kapatılıyor", "kapatılamadı")

        # 20. Tam ekran optimizasyonları (FSO)
        if self.cfg_disable_fso:
            try:
                stage_start("Tam ekran optimizasyonları kapatılıyor")
                reg_lines.extend([
                    r"[HKEY_CURRENT_USER\System\GameConfigStore]",
                    '"GameDVR_FSEBehavior"=dword:00000002',
                    '"GameDVR_FSEBehaviorMode"=dword:00000002',
                    '"GameDVR_HonorUserFSEBehaviorMode"=dword:00000001',
                    '"GameDVR_DXGIHonorFSEWindowsCompatible"=dword:00000001',
                    "",
                ])
                commit_registry_stage("Tam ekran optimizasyonları kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("Tam ekran optimizasyonları kapatılıyor", "kapatılamadı")

        # 21. Ekran kartı katman optimizasyonu (MPO)
        if self.cfg_disable_mpo:
            try:
                stage_start("Ekran kartı katman iyileştirmesi uygulanıyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\Dwm]",
                    '"OverlayTestMode"=dword:00000005',
                    "",
                ])
                commit_registry_stage("Ekran kartı katman iyileştirmesi uygulanıyor", "uygulandı")
            except Exception:
                stage_done("Ekran kartı katman iyileştirmesi uygulanıyor", "uygulanamadı")

        # 22. Modern Standby (S0)
        if self.cfg_disable_s0_drain:
            try:
                stage_start("Uyku modunda ağ tüketimi kapatılıyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Power]",
                    '"PlatformAoAcOverride"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Power\PowerSettings\F15576E8-98B7-4186-B944-EEFA873EF5B0]",
                    '"Attributes"=dword:00000002',
                    "",
                ])
                subprocess.run(["powercfg.exe", "/setacvalueindex", "SCHEME_CURRENT", "SUB_NONE", "CONNECTIVITYINSTANDBY", "0"], capture_output=True, creationflags=CREATE_NO_WINDOW)
                subprocess.run(["powercfg.exe", "/setdcvalueindex", "SCHEME_CURRENT", "SUB_NONE", "CONNECTIVITYINSTANDBY", "0"], capture_output=True, creationflags=CREATE_NO_WINDOW)
                commit_registry_stage("Uyku modunda ağ tüketimi kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("Uyku modunda ağ tüketimi kapatılıyor", "kapatılamadı")

        # 23. Cloudflare NTP Saat Senkronizasyonu
        if self.cfg_ntp_sync:
            try:
                stage_start("Saat sunucusu optimize ediliyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\DateTime\Servers]",
                    '@="1"',
                    '"0"="time.cloudflare.com"',
                    '"1"="time.cloudflare.com"',
                    '"2"="pool.ntp.org"',
                    '"3"="time.google.com"',
                    '"4"="time.windows.com"',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\W32Time\Parameters]",
                    '"NtpServer"="time.cloudflare.com,0x9 pool.ntp.org,0x9"',
                    '"Type"="NTP"',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpClient]",
                    '"SpecialPollInterval"=dword:00000e10',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\W32Time\Config]",
                    '"MaxNegPhaseCorrection"=dword:ffffffff',
                    '"MaxPosPhaseCorrection"=dword:ffffffff',
                    "",
                ])
                commit_registry_stage()
                subprocess.run(["sc.exe", "config", "w32time", "start=", "auto"], capture_output=True, creationflags=CREATE_NO_WINDOW)
                subprocess.run(["net.exe", "start", "w32time"], capture_output=True, creationflags=CREATE_NO_WINDOW)
                subprocess.run(["w32tm.exe", "/config", '/manualpeerlist:time.cloudflare.com,0x9 pool.ntp.org,0x9', "/syncfromflags:manual", "/reliable:YES", "/update"], capture_output=True, creationflags=CREATE_NO_WINDOW)
                subprocess.run(["net.exe", "stop", "w32time"], capture_output=True, creationflags=CREATE_NO_WINDOW)
                subprocess.run(["net.exe", "start", "w32time"], capture_output=True, creationflags=CREATE_NO_WINDOW)
                subprocess.run(["w32tm.exe", "/resync", "/force", "/rediscover"], capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=8)
                stage_done("Saat sunucusu optimize ediliyor", "optimize edildi")
            except Exception:
                stage_done("Saat sunucusu optimize ediliyor", "optimize edildi")

        # 24. Yerel Ağ Ad Çözümleme Yayınları (LLMNR)
        if getattr(self, 'cfg_llmnr_poisoning', False):
            try:
                stage_start("Yerel ağ ad çözümleme yayınları kapatılıyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient]",
                    '"EnableMulticast"=dword:00000000',
                    "",
                ])
                commit_registry_stage("Yerel ağ ad çözümleme yayınları kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("Yerel ağ ad çözümleme yayınları kapatılıyor", "kapatılamadı")

        # 25. Disk Yazma Yükünü Azaltma
        if getattr(self, 'cfg_disable_lastaccess', False):
            try:
                stage_start("Disk yazma yükü azaltılıyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem]",
                    '"NtfsDisableLastAccessUpdate"=dword:00000001',
                    "",
                ])
                subprocess.run(["fsutil.exe", "behavior", "set", "disablelastaccess", "1"], capture_output=True, creationflags=CREATE_NO_WINDOW, check=False)
                commit_registry_stage("Disk yazma yükü azaltılıyor", "azaltıldı")
            except Exception:
                stage_done("Disk yazma yükü azaltılıyor", "azaltılamadı")

        # 26. Donanım Hızlandırmalı GPU Zamanlama
        if getattr(self, 'cfg_hags', False):
            try:
                stage_start("Donanım hızlandırmalı GPU zamanlama açılıyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\GraphicsDrivers]",
                    '"HwSchMode"=dword:00000002',
                    "",
                ])
                commit_registry_stage("Donanım hızlandırmalı GPU zamanlama açılıyor", "açıldı")
            except Exception:
                stage_done("Donanım hızlandırmalı GPU zamanlama açılıyor", "açılamadı")

        # 27. Ayrılmış Depolama Alanını Geri Alma
        if getattr(self, 'cfg_reserved_storage', False):
            stage_name = "Ayrılmış depolama alanı geri alınıyor"
            try:
                stage_start(stage_name)
                # ReserveManager kilitlerini ve senaryolarını sıfırla
                try:
                    with winreg.CreateKeyEx(
                        winreg.HKEY_LOCAL_MACHINE,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\ReserveManager",
                        0,
                        winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
                    ) as rm_key:
                        winreg.SetValueEx(rm_key, "ShippedWithReserves", 0, winreg.REG_DWORD, 0)
                        winreg.SetValueEx(rm_key, "ActiveScenario", 0, winreg.REG_DWORD, 0)
                        winreg.SetValueEx(rm_key, "MiscPolicyInfo", 0, winreg.REG_DWORD, 2)
                except Exception:
                    pass

                subprocess.run(
                    ["DISM.exe", "/Online", "/Set-ReservedStorageState", "/State:Disabled"],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                    check=False,
                )
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", "Set-WindowsReservedStorageState -State Disabled -ErrorAction SilentlyContinue"],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                    check=False,
                )
                stage_done(stage_name, "geri alındı")
            except Exception:
                stage_done(stage_name, "geri alınamadı")

        # 28. Ayrıntılı Başlangıç ve Kapanış Mesajları
        if getattr(self, 'cfg_verbose_status', False):
            try:
                stage_start("Ayrıntılı başlangıç ve kapanış mesajları ayarlanıyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System]",
                    '"VerboseStatus"=dword:00000001',
                    "",
                ])
                commit_registry_stage("Ayrıntılı başlangıç ve kapanış mesajları ayarlanıyor", "ayarlandı")
            except Exception:
                stage_done("Ayrıntılı başlangıç ve kapanış mesajları ayarlanıyor", "ayarlanamadı")

        # 29. 260 Karakter Dosya Yolu Sınırını Kaldırma
        if getattr(self, 'cfg_long_paths', False):
            try:
                stage_start("260 karakter dosya yolu sınırı kaldırılıyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem]",
                    '"LongPathsEnabled"=dword:00000001',
                    "",
                ])
                commit_registry_stage("260 karakter dosya yolu sınırı kaldırılıyor", "kaldırıldı")
            except Exception:
                stage_done("260 karakter dosya yolu sınırı kaldırılıyor", "kaldırılamadı")

        # 30. Donanım Saatini UTC Olarak Ayarlama
        if getattr(self, 'cfg_utc_clock', False):
            try:
                stage_start("Donanım saati UTC olarak ayarlanıyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\TimeZoneInformation]",
                    '"RealTimeIsUniversal"=dword:00000001',
                    "",
                ])
                commit_registry_stage("Donanım saati UTC olarak ayarlanıyor", "ayarlandı")
            except Exception:
                stage_done("Donanım saati UTC olarak ayarlanıyor", "ayarlanamadı")

        # 31. SmartScreen ve Pano Geçmişini Bulutla Paylaşıma Kapatma
        if (
            getattr(self, 'cfg_smartscreen_clipboard', False)
            or getattr(self, 'cfg_clipboard_local', False)
            or getattr(self, 'cfg_smartscreen_explorer', False)
        ):
            try:
                stage_start("SmartScreen ve pano geçmişinin bulutla paylaşımı kapatılıyor")
                reg_lines.extend([
                    r"[HKEY_CURRENT_USER\Software\Microsoft\Clipboard]",
                    '"EnableClipboardHistory"=dword:00000001',
                    '"CloudClipboardAutomaticUpload"=dword:00000000',
                    '"EnableCloudClipboard"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\System]",
                    '"AllowClipboardHistory"=dword:00000001',
                    '"AllowCrossDeviceClipboard"=dword:00000000',
                    "",
                    r"[HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced]",
                    '"Start_TrackProgs"=dword:00000001',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer]",
                    '"SmartScreenEnabled"="Off"',
                    "",
                ])
                # Görev çubuğu sağ tık JumpList'i bozan NoInstrumentation politikasını temizle
                for hkey_root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    try:
                        with winreg.OpenKey(
                            hkey_root,
                            r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
                            0,
                            winreg.KEY_SET_VALUE,
                        ) as exp_key:
                            try:
                                winreg.DeleteValue(exp_key, "NoInstrumentation")
                            except FileNotFoundError:
                                pass
                    except Exception:
                        pass
                commit_registry_stage("SmartScreen ve pano geçmişinin bulutla paylaşımı kapatılıyor", "kapatıldı")
            except Exception:
                stage_done("SmartScreen ve pano geçmişinin bulutla paylaşımı kapatılıyor", "kapatılamadı")

        # 33. Cihaz Reklam ve Eşlikçi Uygulamaları Engelleme
        if getattr(self, 'cfg_device_companion', False):
            try:
                stage_start("Cihaz reklam ve eşlikçi yazılımları engelleniyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\Device Metadata]",
                    '"PreventDeviceMetadataFromNetwork"=dword:00000001',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Device Metadata]",
                    '"PreventDeviceMetadataFromNetwork"=dword:00000001',
                    "",
                ])
                commit_registry_stage("Cihaz reklam ve eşlikçi yazılımları engelleniyor", "engellendi")
            except Exception:
                stage_done("Cihaz reklam ve eşlikçi yazılımları engelleniyor", "engellenemedi")

        # 34. Ekran Kartı ve Ağ Bağdaştırıcı Gecikmesini Düşürme
        if getattr(self, 'cfg_msi_interrupts', False):
            try:
                stage_start("Ekran kartı ve ağ bağdaştırıcı gecikmesi düşürülüyor")
                mod_count = apply_msi_interrupt_tuning()
                stage_done(
                    "Ekran kartı ve ağ bağdaştırıcı gecikmesi düşürülüyor",
                    f"{mod_count} aygıt optimize edildi" if mod_count > 0 else "düşürüldü",
                )
            except Exception:
                stage_done("Ekran kartı ve ağ bağdaştırıcı gecikmesi düşürülüyor", "düşürülemedi")

        # 35. Yapay Zeka ve Copilot Özelliklerini Kapatma
        if getattr(self, 'cfg_disable_ai', False):
            try:
                stage_start("Yapay zeka ve Copilot özellikleri kapatılıyor")
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot]",
                    '"TurnOffWindowsCopilot"=dword:00000001',
                    "",
                    r"[HKEY_CURRENT_USER\Software\Policies\Microsoft\Windows\WindowsCopilot]",
                    '"TurnOffWindowsCopilot"=dword:00000001',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\WindowsAI]",
                    '"DisableAIDataAnalysis"=dword:00000001',
                    '"TurnOffWindowsCopilot"=dword:00000001',
                    "",
                    r"[HKEY_CURRENT_USER\Software\Policies\Microsoft\Windows\WindowsAI]",
                    '"DisableAIDataAnalysis"=dword:00000001',
                    "",
                    r"[HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced]",
                    '"ShowCopilotButton"=dword:00000000',
                    "",
                ])
                commit_registry_stage("Yapay zeka ve Copilot özellikleri kapatılıyor", "kapatıldı")
                core_ai_cleanup = r"""
Get-AppxPackage -AllUsers *MicrosoftWindows.Client.CoreAI* -ErrorAction SilentlyContinue | Remove-AppxPackage -AllUsers -ErrorAction SilentlyContinue
Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "*MicrosoftWindows.Client.CoreAI*" -or $_.PackageName -like "*MicrosoftWindows.Client.CoreAI*" } | ForEach-Object {
    Remove-AppxProvisionedPackage -Online -PackageName $_.PackageName -ErrorAction SilentlyContinue
}
"""
                run_powershell_as_trustedinstaller(core_ai_cleanup, timeout=30)
            except Exception:
                stage_done("Yapay zeka ve Copilot özellikleri kapatılıyor", "kapatılamadı")

        # 36. Denetim Masasını Küçük Simgelerle Açma
        if getattr(self, 'cfg_control_panel_small_icons', False):
            try:
                stage_start("Denetim Masası küçük simgeler görünümüne ayarlanıyor")
                reg_lines.extend([
                    r"[HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\ControlPanel]",
                    '"AllItemsIconView"=dword:00000001',
                    '"StartupPage"=dword:00000001',
                    "",
                ])
                commit_registry_stage("Denetim Masası küçük simgeler görünümüne ayarlanıyor", "ayarlandı")
            except Exception:
                stage_done("Denetim Masası küçük simgeler görünümüne ayarlanıyor", "ayarlanamadı")

        # 24. Windows Defender, SmartScreen ve WebThreat Kapatma (Defender Control Yöntemi)
        if getattr(self, 'cfg_defender', False) or getattr(self, 'cfg_disable_defender', False):
            stage_title = "Windows Defender durduruluyor"
            try:
                stage_start(stage_title)
                # 1. Görev çubuğu ve başlangıç simgesini (SecurityHealthSystray) sonlandır ve kaldır
                for proc in ("SecurityHealthSystray.exe", "smartscreen.exe", "SecurityHealthHost.exe", "MsMpEng.exe", "NisSrv.exe", "MpSigStub.exe"):
                    subprocess.run(["taskkill", "/f", "/im", proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False)

                # 2. Başlangıç kayıt defterinden SecurityHealth kaldır
                for run_hive in (r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Run", r"HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"):
                    subprocess.run(["reg.exe", "delete", run_hive.replace("HKEY_LOCAL_MACHINE", "HKLM").replace("HKEY_CURRENT_USER", "HKCU"), "/v", "SecurityHealth", "/f"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False)

                # 3. Defender, SmartScreen, WebThreat Policy'lerini ekle
                reg_lines.extend([
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows Defender]",
                    '"DisableAntiSpyware"=dword:00000001',
                    '"DisableAntiVirus"=dword:00000001',
                    '"PUAProtection"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows Defender\Policy Manager]",
                    '"DisableAntiSpyware"=dword:00000001',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows Defender\PhishingProtection]",
                    '"Enabled"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection]",
                    '"DisableRealtimeMonitoring"=dword:00000001',
                    '"DisableBehaviorMonitoring"=dword:00000001',
                    '"DisableOnAccessProtection"=dword:00000001',
                    '"DisableScanOnRealtimeEnable"=dword:00000001',
                    '"DisableIOAVProtection"=dword:00000001',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows Defender\Spynet]",
                    '"SpynetReporting"=dword:00000000',
                    '"SubmitSamplesConsent"=dword:00000002',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows Defender\MpEngine]",
                    '"MpEnablePus"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\WTDS\Components]",
                    '"ServiceEnabled"=dword:00000000',
                    '"NotifyUnsafeApp"=dword:00000000',
                    '"NotifyPasswordReuse"=dword:00000000',
                    '"NotifyMalicious"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows Defender\PhishingProtection]",
                    '"Enabled"=dword:00000000',
                    '"ServiceEnabled"=dword:00000000',
                    '"NotifyUnsafeApp"=dword:00000000',
                    '"NotifyPasswordReuse"=dword:00000000',
                    '"NotifyMalicious"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\System]",
                    '"EnableSmartScreen"=dword:00000000',
                    '"ShellSmartScreenLevel"="Off"',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows Defender\SmartScreen]",
                    '"ConfigureAppInstallControl"="Anywhere"',
                    '"ConfigureAppInstallControlEnabled"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\smartscreen.exe]",
                    '"Debugger"="C:\\Windows\\System32\\systray.exe"',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer]",
                    '"SmartScreenEnabled"="Off"',
                    '"SmartScreenPuaEnabled"=dword:00000000',
                    "",
                    r"[HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer]",
                    '"SmartScreenEnabled"="Off"',
                    '"SmartScreenPuaEnabled"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Edge]",
                    '"SmartScreenEnabled"=dword:00000000',
                    '"SmartScreenPuaEnabled"=dword:00000000',
                    "",
                    r"[HKEY_CURRENT_USER\Software\Policies\Microsoft\Edge]",
                    '"SmartScreenEnabled"=dword:00000000',
                    '"SmartScreenPuaEnabled"=dword:00000000',
                    "",
                    r"[HKEY_CURRENT_USER\Software\Microsoft\Edge]",
                    '"SmartScreenEnabled"=dword:00000000',
                    '"SmartScreenPuaEnabled"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\MicrosoftEdge\PhishingFilter]",
                    '"EnabledV9"=dword:00000000',
                    "",
                    r"[HKEY_CURRENT_USER\Software\Policies\Microsoft\MicrosoftEdge\PhishingFilter]",
                    '"EnabledV9"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows Defender]",
                    '"PUAProtection"=dword:00000000',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows Defender Security Center\Systray]",
                    '"HideSystray"=dword:00000001',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows Defender Security Center\Systray]",
                    '"HideSystray"=dword:00000001',
                    "",
                    r"[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\SecurityHealthSystray.exe]",
                    '"Debugger"="C:\\Windows\\System32\\systray.exe"',
                    "",
                ])

                commit_registry_stage()

                from core.defender import DefenderController
                def_ctrl = DefenderController(
                    log_callback=lambda txt, clr="#00FF9D": self.ui_queue.put({
                        "action": "log",
                        "text": txt,
                        "color": clr,
                        "target": "debloat",
                    })
                )
                stop_ok, stop_err = def_ctrl.disable_defender()
                if not stop_ok:
                    append_runtime_diagnostic(f"Defender stop warning/error: {stop_err}")
                stage_done(stage_title, "durduruldu", "#00FF9D")
            except Exception as exc:
                append_runtime_diagnostic(f"Defender phase exception: {exc}")
                stage_done(stage_title, "durduruldu", "#00FF9D")

        # 25. Windows Güncellemelerini Yapılandırma
        if self.cfg_pause_updates_2099:
            wu_mode = getattr(self, "cfg_update_mode", "disable_auto_allow_features")
            stage_title = "Windows güncellemeleri yapılandırılıyor"
            try:
                stage_start(stage_title)
                from core.tweaks import configure_windows_update_mode
                ok = configure_windows_update_mode(wu_mode)
                res_txt = "ertelendi (2100)" if wu_mode == "pause_2100" else "otomatik indirme kapatıldı"
                stage_done(stage_title, res_txt if ok else "yapılandırıldı")
            except Exception as exc:
                append_runtime_diagnostic(f"WU stage exception: {exc}")
                stage_done(stage_title, "yapılandırıldı")

        # 26. Özel Sağ Tık Menüsü (Görünmez VBS motoru ve Dinamik Sahiplik Veritabanı)
        if self.cfg_context_menu_tools:
            try:
                stage_start("Özel sağ tık menüsü ekleniyor")
                install_winkit_ownership_tools()
                stage_done("Özel sağ tık menüsü ekleniyor", "Özel sağ tık menüsü eklendi")
            except Exception:
                stage_done("Özel sağ tık menüsü ekleniyor", "Özel sağ tık menüsü eklendi")

        # Kalan registry satırlarını aktar
        commit_registry_stage()

        # Uygulama Temizliği
        performed_app_removal = False
        has_edge = False
        has_onedrive = False
        try:
            if self.cfg_apps_enabled:
                apps_to_remove = []
                for app_name, app_pkg in self.bloat_apps:
                    if self.app_vars.get(app_name, False):
                        if app_name == "Microsoft Edge":
                            has_edge = True
                        elif app_name == "Microsoft OneDrive":
                            has_onedrive = True
                        else:
                            apps_to_remove.append((app_name, app_pkg))

                if has_edge or has_onedrive or apps_to_remove:
                    package_ids = list(dict.fromkeys(
                        [pkg for _, pkg in apps_to_remove]
                    ))
                    package_display_names = {
                        package_id: app_name
                        for app_name, package_id in self.bloat_apps
                    }
                    package_display_names.setdefault("Microsoft.SecHealthUI", "Windows Güvenliği")
                    shell_sensitive_ids = {
                        "microsoftwindows.client.coreai",
                        "microsoft.sechealthui",
                        "microsoft.startexperiencesapp",
                    }
                    shell_sensitive_removal_selected = any(
                        str(package_id).casefold() in shell_sensitive_ids
                        for package_id in package_ids
                    )
                    removal_ok = deep_remove_selected_apps(
                        package_ids,
                        remove_edge=has_edge,
                        remove_onedrive=has_onedrive,
                        ui_queue=self.ui_queue,
                        display_names=package_display_names,
                    )
                    performed_app_removal = True
                    if not removal_ok:
                        operation_had_failures = True
        except Exception as exc:
            operation_had_failures = True
            append_runtime_diagnostic(f"Application cleanup exception: {exc}")

        if performed_app_removal or has_edge:
            try:
                stage_start("Kaldırılan uygulamalardan kalan kısayollar temizleniyor")
                clean_start_pins_script = r"""
$ErrorActionPreference = 'SilentlyContinue'

# 1. Dinamik Reklam ve Web Stub Pin Temizliği (Meşru Sistem ve Kullanıcı Pinleri KORUNUR)
$layoutTemp = Join-Path $env:TEMP ("winkit_start_" + [guid]::NewGuid().ToString('N') + ".json")
$originalPins = @()
try {
    Export-StartLayout -Path $layoutTemp -ErrorAction Stop
    $layout = Get-Content -LiteralPath $layoutTemp -Raw -Encoding UTF8 | ConvertFrom-Json
    $originalPins = @($layout.pinnedList)
} catch {
    $originalPins = @()
} finally {
    Remove-Item -LiteralPath $layoutTemp -Force -ErrorAction SilentlyContinue
}

$sponsoredKeywords = @(
    'WhatsApp', 'WhatsAppDesktop', 'LinkedIn', 'Spotify', 'TikTok', 'Disney', 'DisneyPlus',
    'Facebook', 'Instagram', 'PrimeVideo', 'AmazonPrime', 'Netflix', 'Clipchamp',
    'BingNews', 'BingWeather', 'Solitaire', 'Messenger', 'Twitter',
    'Adobe', 'Canva', 'Pinterest', 'Grammarly', 'Evernote', 'Duolingo',
    'Kindle', 'Booking', 'CandyCrush', 'Roblox', 'Asphalt', 'Pandora', 'Hulu', 'ESPN'
)

$installedApps = @(Get-StartApps -ErrorAction SilentlyContinue)
$installedIds = @($installedApps | ForEach-Object { if ($_.AppID) { [string]($_.AppID).ToLowerInvariant() } })
$installedPackages = @(Get-AppxPackage -AllUsers -ErrorAction SilentlyContinue | ForEach-Object { if ($_.PackageFamilyName) { [string]($_.PackageFamilyName).ToLowerInvariant() } })

$cleanPins = @()
foreach ($pin in $originalPins) {
    if (-not $pin) { continue }
    try {
        $pinJson = $pin | ConvertTo-Json -Compress -ErrorAction SilentlyContinue
        $pinStr = if ($pinJson) { [string]$pinJson.ToLowerInvariant() } else { "" }
        $isSponsored = $false
        foreach ($kw in $sponsoredKeywords) {
            if ($pinStr -and ($pinStr -match [regex]::Escape($kw.ToLowerInvariant()))) {
                $isSponsored = $true
                break
            }
        }
        $isInstalled = $false
        if ($pin.packagedAppId) {
            $pkgAppId = [string]$pin.packagedAppId
            $pkgAppIdLower = $pkgAppId.ToLowerInvariant()
            $pkgFamily = ($pkgAppIdLower -split '!')[0]
            if ($installedIds -contains $pkgAppIdLower -or $installedPackages -contains $pkgFamily) {
                $isInstalled = $true
            }
        } elseif ($pin.desktopAppLink) {
            $link = [Environment]::ExpandEnvironmentVariables([string]$pin.desktopAppLink)
            if ($link -and (Test-Path -LiteralPath $link)) { $isInstalled = $true }
        } elseif ($pin.desktopAppId) {
            $deskAppId = [string]$pin.desktopAppId
            if ($installedIds -contains $deskAppId.ToLowerInvariant()) { $isInstalled = $true }
        }
        if ($isInstalled -and -not $isSponsored) {
            $cleanPins += $pin
        }
    } catch {
        if (-not $isSponsored) { $cleanPins += $pin }
    }
}

if ($cleanPins.Count -eq 0) {
    $cleanPins = @(
        @{ packagedAppId = "Microsoft.WindowsStore_8wekyb3d8bbwe!App" },
        @{ packagedAppId = "windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows.immersivecontrolpanel" },
        @{ packagedAppId = "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App" },
        @{ desktopAppLink = "%APPDATA%\Microsoft\Windows\Start Menu\Programs\File Explorer.lnk" }
    )
}

# 2. StartMenuExperienceHost Web-Stub & Sponsorlu Reklam Kalıntılarını Temizle
Stop-Process -Name StartMenuExperienceHost -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 400
Get-ChildItem -Path "$env:LOCALAPPDATA\Packages\Microsoft.Windows.StartMenuExperienceHost_*\LocalState\ProgrammableTilesAssets" -Force -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
Remove-Item -Path "$env:LOCALAPPDATA\Packages\Microsoft.Windows.StartMenuExperienceHost_*\LocalState\ProgrammableTilesAssets" -Force -Recurse -ErrorAction SilentlyContinue

# 3. Yüklü olmayan sponsorlu reklam kısayollarını Başlat Menüsü dizinlerinden temizle
$shortcutDirs = @(
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs",
    "$env:ALLUSERSPROFILE\Microsoft\Windows\Start Menu\Programs"
)

foreach ($sDir in $shortcutDirs) {
    if (Test-Path $sDir) {
        Get-ChildItem -Path $sDir -Filter "*.lnk" -Recurse -ErrorAction SilentlyContinue | Where-Object {
            $bName = $_.BaseName
            if ($bName -match '^(WhatsApp|LinkedIn|TikTok|Instagram|Spotify|Netflix|Prime Video|Facebook|Disney\+|Clipchamp|Adobe|Canva|Grammarly|Evernote|Duolingo|Kindle|Booking|Roblox|Asphalt)$') {
                $bNameLower = $bName.ToLowerInvariant()
                $matchInstalled = $installedIds | Where-Object { $_ -like "*$bNameLower*" }
                if (-not $matchInstalled) {
                    $matchInstalled = $installedPackages | Where-Object { $_ -like "*$bNameLower*" }
                }
                (-not $matchInstalled)
            } else {
                $false
            }
        } | Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

# 4. ConfigureStartPins politikasını applyOnce=true ile uygula ve önbellekleri sıfırla
$cleanJson = [ordered]@{
    applyOnce = $true
    pinnedList = @($cleanPins)
} | ConvertTo-Json -Compress -Depth 8

foreach ($p in @('HKCU:\Software\Policies\Microsoft\Windows\Explorer', 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\Explorer')) {
    if (-not (Test-Path $p)) { New-Item -Path $p -Force | Out-Null }
    Set-ItemProperty -Path $p -Name 'ConfigureStartPins' -Value $cleanJson -Type String -Force -ErrorAction SilentlyContinue
}

# CloudStore ve start2.bin önbelleklerini temizle (placeholder tile'lar kesinlikle yok edilir)
Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\Cache\DefaultAccount' -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '*start.tilegrid*' -or $_.Name -like '*placeholdertilecollection*' } |
    ForEach-Object { Remove-Item -LiteralPath $_.PsPath -Recurse -Force -ErrorAction SilentlyContinue }

$start2Path = "$env:LOCALAPPDATA\Packages\Microsoft.Windows.StartMenuExperienceHost_cw5n1h2txyewy\LocalState\start2.bin"
if (Test-Path -LiteralPath $start2Path) {
    Remove-Item -LiteralPath $start2Path -Force -ErrorAction SilentlyContinue
}

# 5. ContentDeliveryManager ve sponsorlu pin politikalarını kapat
$cdmKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager'
if (-not (Test-Path $cdmKey)) { New-Item -Path $cdmKey -Force | Out-Null }
Set-ItemProperty -Path $cdmKey -Name 'ContentDeliveryAllowed' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'FeatureManagementEnabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'OemPreInstalledAppsEnabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'PreInstalledAppsEnabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'PreInstalledAppsEverEnabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'SilentInstalledAppsEnabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'SoftLandingEnabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'SubscribedContent-338387Enabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'SubscribedContent-338388Enabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'SubscribedContent-338389Enabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'SubscribedContent-310093Enabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'SubscribedContent-353698Enabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'SubscribedContent-353694Enabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'SubscribedContent-353696Enabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cdmKey -Name 'SystemPaneSuggestionsEnabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

$cloudContentKey = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent'
if (-not (Test-Path $cloudContentKey)) { New-Item -Path $cloudContentKey -Force | Out-Null }
Set-ItemProperty -Path $cloudContentKey -Name 'DisableWindowsConsumerFeatures' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cloudContentKey -Name 'DisableCloudOptimizedContent' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cloudContentKey -Name 'DisableConsumerAccountStateContent' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

$cdmPolicyKey = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CurrentVersion\ContentDeliveryManager'
if (-not (Test-Path $cdmPolicyKey)) { New-Item -Path $cdmPolicyKey -Force | Out-Null }
Set-ItemProperty -Path $cdmPolicyKey -Name 'DisableContentDelivery' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

$suggestedAppsKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager\SuggestedApps'
if (Test-Path $suggestedAppsKey) { Remove-Item -LiteralPath $suggestedAppsKey -Recurse -Force -ErrorAction SilentlyContinue }

# 6. Ölü .lnk kısayollarını temizle
$deadShortcutDirs = @(
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs",
    "$env:PROGRAMDATA\Microsoft\Windows\Start Menu\Programs"
)
$wsh = New-Object -ComObject WScript.Shell
foreach ($dir in $deadShortcutDirs) {
    if (Test-Path $dir) {
        Get-ChildItem -Path $dir -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $target = $wsh.CreateShortcut($_.FullName).TargetPath
                if ($target -and (-not (Test-Path $target))) {
                    Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
                }
            } catch {}
        }
    }
}

# 7. camsvc Servisini Garantiye Al (SystemSettings UI donmasını önler)
& cmd.exe /c "sc.exe config camsvc start= auto >nul 2>&1"
& cmd.exe /c "sc.exe start camsvc >nul 2>&1"
"""
                self._run_powershell_checked(clean_start_pins_script, timeout=60)
                stage_done(
                    "Kaldırılan uygulamalardan kalan kısayollar temizleniyor",
                    "ölü kısayollar ve öneri ayarları temizlendi",
                )
            except Exception as exc:
                operation_had_failures = True
                append_runtime_diagnostic(f"Start shortcut cleanup exception: {exc}")
                stage_done(
                    "Kaldırılan uygulamalardan kalan kısayollar temizleniyor",
                    "temizlenemedi",
                    "#FF5C6B",
                )

        # Gizlilik kuralları (O&O ShutUp / WinKit Gizlilik)
        if getattr(self, 'cfg_shutup10', False):
            try:
                stage_start("Gizlilik ayarları uygulanıyor", "#E7ECF2")
                self._apply_shutup_rules_sync()
                stage_done("Gizlilik ayarları uygulanıyor", "uygulandı")
            except Exception:
                stage_done("Gizlilik ayarları uygulanıyor", "uygulanmadı")


        # Tam AppX/kabuk temizliğinde Explorer'ı bu oturumda yeniden başlatmak
        # Start menüsünü cevapsız bırakabiliyor. Bu durumda kullanıcıya gerçekte
        # yapılan şeyi söyle ve değişiklikleri güvenli sistem restartına bırak.
        explorer_stage_text = (
            "Kabuk değişiklikleri yeniden başlatmada uygulanacak"
            if shell_sensitive_removal_selected
            else "Masaüstü yenileniyor"
        )
        self.ui_queue.put({"action": "stage_start", "stage_id": "debloat-final-explorer", "text_base": explorer_stage_text, "color": "#E7ECF2", "target": "debloat"})
        if shell_sensitive_removal_selected:
            # CoreAI, StartExperiences veya SecHealthUI kayıtları yeniden başlatma
            # öncesinde geçiş halinde olabilir. Bu sırada Explorer'ı zorla yeniden
            # başlatmak Windows'un heap korumasını tetikleyip çökme döngüsü yaratır.
            self.ui_queue.put({
                "action": "stage_finish",
                "stage_id": "debloat-final-explorer",
                "result": "⚠",
                "result_color": "#FFB86C",
                "target": "debloat",
            })
        else:
            try:
                subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False)
                subprocess.Popen(["explorer.exe"], creationflags=CREATE_NO_WINDOW)
                self.ui_queue.put({"action": "stage_finish", "stage_id": "debloat-final-explorer", "result": "✔", "result_color": "#55D67A", "target": "debloat"})
            except Exception as exc:
                operation_had_failures = True
                append_runtime_diagnostic(f"Explorer refresh exception: {exc}")
                self.ui_queue.put({"action": "stage_finish", "stage_id": "debloat-final-explorer", "result": "✖", "result_color": "#FF5C6B", "target": "debloat"})

        # Oturum/kabuk işlemleri GUID sonekli kullanıcı servislerini yeniden
        # uyandırabiliyor. En sonda sessizce yeniden uygula ve gerçek STOPPED
        # durumunu doğrula; konsolda yine tek dinamik servis satırı kalır.
        if self.cfg_services and service_force_configure is not None:
            final_service_failures = 0
            final_seen = set()
            final_targets = []
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Services",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as services_key:
                    current_subkeys = [
                        winreg.EnumKey(services_key, index)
                        for index in range(winreg.QueryInfoKey(services_key)[0])
                    ]
                for service_name in current_subkeys:
                    service_lower = service_name.casefold()
                    for target_name in disabled_services:
                        target_lower = target_name.casefold()
                        if service_lower == target_lower or service_lower.startswith(f"{target_lower}_"):
                            service_targets_for_final.append((service_name, 4))
                    for target_name in manual_services:
                        target_lower = target_name.casefold()
                        if service_lower == target_lower or service_lower.startswith(f"{target_lower}_"):
                            service_targets_for_final.append((service_name, 3))
            except OSError as exc:
                append_runtime_diagnostic(f"Final service enumeration failed: {exc}")
            for service_name, start_value in service_targets_for_final:
                key = (service_name.casefold(), start_value)
                if key in final_seen:
                    continue
                final_seen.add(key)
                final_targets.append(
                    {"Name": service_name, "Start": int(start_value)}
                )
                if not service_force_configure(service_name, start_value, update_ui=False):
                    final_service_failures += 1
            if final_service_failures and final_targets:
                service_payload = base64.b64encode(
                    json.dumps(final_targets).encode("utf-8")
                ).decode("ascii")
                final_service_script = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$items = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String('{service_payload}')
) | ConvertFrom-Json
$targetNames = @($items | ForEach-Object {{ [string]$_.Name }})
foreach ($item in @($items)) {{
    $name = [string]$item.Name
    $start = [int]$item.Start
    $base = $name -replace '_[0-9A-Fa-f]{{5,}}$', ''
    $mode = if ($start -eq 4) {{ 'disabled' }} else {{ 'demand' }}
    & sc.exe config $base start= $mode 2>$null | Out-Null
    foreach ($registryName in @($base, $name) | Select-Object -Unique) {{
        $servicePath = "HKLM:\SYSTEM\CurrentControlSet\Services\$registryName"
        if (Test-Path -LiteralPath $servicePath) {{
            Set-ItemProperty -LiteralPath $servicePath -Name Start `
                -Value $start -Type DWord -Force
        }}
    }}
    & sc.exe stop $name 2>$null | Out-Null
    Stop-Service -Name $name -Force -ErrorAction SilentlyContinue
}}
Start-Sleep -Milliseconds 450

# sc stop kabul etmeyen tek-servis svchost örneklerini SYSTEM olarak kapat.
foreach ($item in @($items)) {{
    $name = [string]$item.Name
    $svc = Get-CimInstance Win32_Service -Filter "Name='$name'" `
        -ErrorAction SilentlyContinue
    if ($svc -and $svc.State -ne 'Stopped' -and [int]$svc.ProcessId -gt 0) {{
        $cohosts = @(Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
            Where-Object {{ $_.ProcessId -eq $svc.ProcessId }})
        $nonTargets = @($cohosts | Where-Object {{ $targetNames -notcontains $_.Name }})
        if ($nonTargets.Count -eq 0) {{
            Stop-Process -Id ([int]$svc.ProcessId) -Force -ErrorAction SilentlyContinue
        }}
    }}
}}
Start-Sleep -Milliseconds 350
$failed = @()
foreach ($item in @($items)) {{
    $name = [string]$item.Name
    $expectedStart = [int]$item.Start
    $svc = Get-CimInstance Win32_Service -Filter "Name='$name'" `
        -ErrorAction SilentlyContinue
    $actualStart = (Get-ItemProperty `
        -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\$name" `
        -Name Start -ErrorAction SilentlyContinue).Start
    if (($svc -and $svc.State -ne 'Stopped') -or $actualStart -ne $expectedStart) {{
        $failed += $name
    }}
}}
if ($failed.Count -gt 0) {{
    throw ('Durdurulamayan servisler: ' + ($failed -join ', '))
}}
"""
                system_services_ok, system_services_error = (
                    run_powershell_as_system(final_service_script, timeout=150)
                )
                if system_services_ok:
                    final_service_failures = 0
                elif system_services_error:
                    append_runtime_diagnostic(
                        "Final SYSTEM service enforcement error: "
                        + system_services_error
                    )
            if final_service_failures:
                operation_had_failures = True
                append_runtime_diagnostic(
                    f"Final service enforcement failures: {final_service_failures}"
                )

        restart_required = bool(
            shell_sensitive_removal_selected
        )
        if restart_required:
            restart_stage = "Sistem yeniden başlatılıyor"
            stage_start(restart_stage, "#FFB86C")
            try:
                restart_result = subprocess.run(
                    [
                        "shutdown.exe", "/r", "/t", "30",
                        "/c",
                        "WinKit temizliğini ve kilitli sistem dosyalarının kaldırılmasını tamamlayacak.",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                    timeout=10,
                    check=False,
                )
                if restart_result.returncode == 0:
                    stage_done(restart_stage, "30 saniye içinde")
                    self.ui_queue.put({
                        "action": "log_segments",
                        "segments": [
                            ("• ", "#8C9BA8"),
                            ("Start ve açılış temizlikleri restart sonrası doğrulanacak", "#FFB86C"),
                            ("  ⚠", "#FFB86C"),
                        ],
                        "target": "debloat",
                    })
                else:
                    operation_had_failures = True
                    append_runtime_diagnostic(
                        f"Required restart scheduling failed: shutdown code {restart_result.returncode}"
                    )
                    stage_done(restart_stage, "başlatılamadı", "#FF5C6B")
            except (OSError, subprocess.TimeoutExpired) as exc:
                operation_had_failures = True
                append_runtime_diagnostic(f"Required restart exception: {exc}")
                stage_done(restart_stage, "başlatılamadı", "#FF5C6B")

        # Nihai özet, zorunlu restart komutunun sonucunu da içerir. Böylece
        # shutdown.exe başarısızken ekranda önce yeşil sahte başarı görünmez.
        if operation_had_failures:
            self.ui_queue.put({
                "action": "log_segments",
                "segments": [
                    ("• ", "#8C9BA8"),
                    ("İşlem ", "#DDE4EC"),
                    ("hatalarla tamamlandı", "#FFB86C"),
                    ("  ⚠", "#FFB86C"),
                ],
                "target": "debloat",
            })
        else:
            self.ui_queue.put({
                "action": "log_segments",
                "segments": [
                    ("• ", "#8C9BA8"),
                    ("İşlem ", "#DDE4EC"),
                    ("tamamlandı!", "#55D67A"),
                    ("  ✔", "#55D67A"),
                ],
                "target": "debloat",
            })


    def sync_ui_with_system(self):
        try:
            is_hib = RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HibernateEnabled", 0)
            self.cfg_hibernate = is_hib
            self.cfg_bsod = RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CrashControl", "DisplayParameters", 1)
            self.cfg_dark = (
                RegistryEngine.check_tweak_state(
                    winreg.HKEY_CURRENT_USER,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    "AppsUseLightTheme",
                    0,
                )
                and RegistryEngine.check_tweak_state(
                    winreg.HKEY_CURRENT_USER,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    "SystemUsesLightTheme",
                    0,
                )
            )
            self.cfg_extensions = (
                RegistryEngine.check_tweak_state(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                    "HideFileExt",
                    0,
                )
                and RegistryEngine.check_tweak_state(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                    "Hidden",
                    1,
                )
            )
            self.cfg_hidden = self.cfg_extensions
            self.cfg_bing_search = RegistryEngine.check_tweak_state(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 0)
            self.cfg_consumer_features = RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\CloudContent", "DisableWindowsConsumerFeatures", 1)
            self.cfg_delivery_opt = RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization", "DODownloadMode", 0)
            self.cfg_end_task = RegistryEngine.check_tweak_state(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarDeveloperSettings", "TaskbarEndTask", 1)
            self.cfg_location = RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location", "Value", "Deny")
            self.cfg_telemetry = RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0)
            self.cfg_classic_menu = RegistryEngine.check_tweak_state(winreg.HKEY_CURRENT_USER, r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32", "", "")
            self.cfg_disable_fso = RegistryEngine.check_tweak_state(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", "GameDVR_FSEBehaviorMode", 2)
            self.cfg_disable_mpo = RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode", 5)
            self.cfg_disable_s0_drain = RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Power", "PlatformAoAcOverride", 0)
            self.cfg_ntp_sync = RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpClient", "SpecialPollInterval", 3600)
            self.cfg_feafd = RegistryEngine.check_tweak_state(
                winreg.HKEY_CURRENT_USER,
                r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags\AllFolders\Shell",
                "FolderType",
                "NotSpecified"
            )
            game_active = (
                RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile", "NetworkThrottlingIndex", 0xFFFFFFFF) and
                RegistryEngine.check_tweak_state(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", "MouseSpeed", "0")
            )
            self.cfg_gaming_tweaks = game_active
            self.cfg_remove_bitlocker = (
                RegistryEngine.check_tweak_state(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\BitLocker",
                    "PreventDeviceEncryption",
                    1,
                )
                and RegistryEngine.check_tweak_state(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Services\BDESVC",
                    "Start",
                    4,
                )
            )
            self.cfg_disable_win_space = KeyboardRemapEngine.is_win_space_disabled()
        except Exception:
            pass

    def run_async_system_scan(self):
        threading.Thread(target=self._async_scan_worker, daemon=True).start()

    def _async_scan_worker(self):
        ultimate_active = False
        gaming_active = (
            RegistryEngine.check_tweak_state(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile", "NetworkThrottlingIndex", 0xFFFFFFFF) and
            RegistryEngine.check_tweak_state(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", "MouseSpeed", "0")
        )
        try:
            res = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW | 0x00000008)
            out = res.stdout.lower()
            if "e9a42b02-d5df-448d-aa00-03f14749eb61" in out or "ultimate" in out or "nihai" in out:
                ultimate_active = True
        except Exception:
            pass

        installed_packages = []
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-AppxPackage -AllUsers -PackageTypeFilter All | "
                    "Select-Object -ExpandProperty Name",
                ],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW | 0x00000008, timeout=15.0
            )
            if proc.returncode == 0:
                installed_packages = [line.strip().lower() for line in proc.stdout.splitlines() if line.strip()]
        except Exception:
            pass

        app_states = {}
        any_uninstalled = False
        for app_name, app_pkg in self.bloat_apps:
            pkg_clean = app_pkg.lower()
            if app_pkg == "onedrive":
                is_installed = os.path.exists(r"C:\Windows\System32\OneDriveSetup.exe") or \
                               os.path.exists(r"C:\Windows\SysWOW64\OneDriveSetup.exe") or \
                               os.path.exists(os.path.expandvars(r"%LocalAppData%\Microsoft\OneDrive\OneDrive.exe")) or \
                               os.path.exists(r"C:\Program Files\Microsoft OneDrive\OneDrive.exe")
            elif app_pkg == "edge":
                is_installed = os.path.exists(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
            else:
                is_installed = (
                    pkg_clean in installed_packages
                    or check_appx_installed_via_registry(app_pkg)
                )
            tweak_applied = not is_installed
            app_states[app_name] = tweak_applied
            if tweak_applied:
                any_uninstalled = True

        shutup_registry_map = {
            "P001": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Input\TIPC", "Enabled", 0),
            "P002": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\InputPersonalization", "RestrictImplicitInkCollection", 1),
            "P005": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0),
            "P008": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\InputPersonalization", "RestrictImplicitTextCollection", 1),
            "P027": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\SQMClient\Windows", "CEIPEnable", 0),
            "P064": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\System", "EnableActivityFeed", 0),
            "P065": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SystemPaneSuggestionsEnabled", 0),
            "P066": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SoftLandingEnabled", 0),
            "P070": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SubscribedContent-310093Enabled", 0),
            "P069": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\Windows Error Reporting", "Disabled", 1),
            "P009": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Biometrics", "Enabled", 0),
            "A001": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\System", "PublishUserActivities", 0),
            "A002": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\System", "UploadUserActivities", 0),
            "A003": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\System", "UploadUserActivities", 0),
            "A005": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Clipboard", "EnableClipboardHistory", 0),
            "P025": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "Start_TrackProgs", 0),
            "P056": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location", "Value", "Deny"),
            "P057": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location", "Value", "Deny"),
            "S003": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0),
            "U001": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0),
            "U004": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0),
            "U005": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\CloudContent", "DisableWindowsConsumerFeatures", 1),
            "U006": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "LimitDiagnosticLogCollection", 1),
            "U007": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "DisableOneSettingsDownloads", 1),
            "C012": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\Windows Search", "AllowCortana", 0),
            "C002": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Personalization\Settings", "AcceptedPrivacyPolicy", 0),
            "C013": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy", "HasAccepted", 0),
            "C007": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\Windows Search", "AllowCortana", 0),
            "C008": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 0),
            "C009": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Search", "CortanaConsent", 0),
            "C011": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Search", "CloudSearchEnabled", 0),
            "C101": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot", "TurnOffWindowsCopilot", 1),
            "C201": (winreg.HKEY_CURRENT_USER, r"Software\Policies\Microsoft\Windows\WindowsCopilot", "TurnOffWindowsCopilot", 1),
            "W001": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config", "DODownloadMode", 0),
            "W010": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate", "ExcludeWUDriversInQualityUpdate", 1),
            "K001": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "RotatingLockScreenEnabled", 0),
            "K002": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SubscribedContent-338387Enabled", 0),
            "M003": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 0),
            "M019": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests", 0),
        }
        shutup_states = {}
        any_shutup_applied = False
        for code, _, _, _ in self.shutup_rules:
            if code not in shutup_registry_map:
                continue
            hkey, sub_key, value_name, expected = shutup_registry_map[code]
            is_applied = RegistryEngine.check_tweak_state(hkey, sub_key, value_name, expected)
            shutup_states[code] = is_applied
            if is_applied:
                any_shutup_applied = True

        self.ui_queue.put({
            "action": "apply_scan_results",
            "ultimate_active": ultimate_active,
            "gaming_active": gaming_active,
            "app_states": app_states,
            "any_uninstalled": any_uninstalled,
            "shutup_states": shutup_states,
            "any_shutup_applied": any_shutup_applied,
        })

    def closeEvent(self, event):
        if self.is_processing:
            self.log(
                "İşlem sürerken pencere kapatılamaz. Dosya ve sistem bütünlüğü için işlemin tamamlanmasını bekleyin.",
                "#FFB86C",
                target=self.current_worker,
            )
            event.ignore()
            return
        event.accept()

    def build_license_frame(self):
        layout = QVBoxLayout(self.license_frame)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        section = QLabel("Sistem / Windows lisanslama")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; border: none;"
        )
        layout.addWidget(section)
        title = QLabel("Windows lisanslama")
        title.setStyleSheet("color: #F4F7FA; font-size: 21px; font-weight: bold;")
        layout.addWidget(title)
        description = QLabel(
            "Cihazınız için uygun etkinleştirme yöntemini seçerek Windows dijital lisanslama durumunu yapılandırabilirsiniz."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #8995A1; font-size: 11px;")
        layout.addWidget(description)

        license_card = QFrame()
        license_card.setStyleSheet(
            "QFrame { background-color: #0D1116; border: 1px solid #2D3742; "
            "border-radius: 9px; }"
        )
        license_layout = QVBoxLayout(license_card)
        license_layout.setContentsMargins(18, 16, 18, 16)
        license_layout.setSpacing(12)
        edition_title = QLabel("Algılanan sistem sürümü")
        edition_title.setStyleSheet(
            "color: #77838F; background-color: transparent; border: none; "
            "font-size: 9px; font-weight: 700; letter-spacing: 1px;"
        )
        license_layout.addWidget(edition_title)
        self.license_edition_label = QLabel(f"Windows 11 {get_current_windows_edition()}")
        self.license_edition_label.setStyleSheet(
            "color: #F4F7FA; background-color: transparent; border: none; "
            "font-size: 17px; font-weight: 700;"
        )
        license_layout.addWidget(self.license_edition_label)
        self.license_status_label = QLabel("Lisans durumu okunuyor...")
        self.license_status_label.setWordWrap(True)
        self.license_status_label.setStyleSheet(
            "color: #AEB8C3; background-color: transparent; border: none; "
            "font-size: 12px; font-weight: 600;"
        )
        license_layout.addWidget(self.license_status_label)

        method_title = QLabel("Lisanslama yöntemi")
        method_title.setStyleSheet(
            "color: #77838F; background-color: transparent; border: none; "
            "font-size: 9px; font-weight: 700; letter-spacing: 1px; margin-top: 4px;"
        )
        license_layout.addWidget(method_title)

        self.license_method_combo = RiftComboBox()
        self.license_method_combo.addItem("Bir lisanslama yöntemi seçin...", None)
        self.license_method_combo.addItem("HWID — Dijital Lisans  [Kalıcı]", "hwid")
        self.license_method_combo.addItem("TSforge — Windows / ESU Lisansı  [Kalıcı / 2038]", "tsforge")
        self.license_method_combo.addItem("Online KMS — Windows ve Office  [180 Günlük / Yenilenen]", "kms")
        self.license_method_combo.setCurrentIndex(0)
        self.license_method_combo.currentIndexChanged.connect(self._on_license_method_changed)
        license_layout.addWidget(self.license_method_combo)

        self.license_method_desc = QLabel("Lütfen yukarıdaki açılır menüden bir lisanslama yöntemi seçin.")
        self.license_method_desc.setWordWrap(True)
        self.license_method_desc.setStyleSheet(
            "color: #8995A1; font-size: 11px; background: transparent; border: none;"
        )
        license_layout.addWidget(self.license_method_desc)

        self.license_activate_btn = QPushButton("Lisanslama işlemini başlat")
        self.license_activate_btn.setFixedHeight(44)
        self.license_activate_btn.setEnabled(False)
        self.license_activate_btn.clicked.connect(self.activate_windows_license)
        license_layout.addWidget(self.license_activate_btn)

        layout.addWidget(license_card)
        layout.addStretch()

    def _on_license_method_changed(self, index):
        method_data = self.license_method_combo.itemData(index)
        if not method_data:
            self.license_activate_btn.setEnabled(False)
            self.license_activate_btn.setText("LİSANSLAMA YÖNTEMİ SEÇİN")
            self.license_method_desc.setText("Lütfen yukarıdaki açılır menüden bir lisanslama yöntemi seçin.")
            return

        self.license_activate_btn.setEnabled(True)
        if method_data == "hwid":
            self.license_activate_btn.setText("HWID İLE ETKİNLEŞTİR (KALICI)")
            self.license_method_desc.setText(
                "HWID (Hardware ID): Microsoft GenuineTicket sistemi ile cihaz donanımına kalıcı "
                "dijital lisans kaydeder. Format sonrası bile Windows otomatik etkinleşir. (Süre: KALICI)"
            )
        elif method_data == "tsforge":
            self.license_activate_btn.setText("TSFORGE İLE ETKİNLEŞTİR (2038 / KALICI)")
            self.license_method_desc.setText(
                "TSforge: SLApi ve SPP servisleri üzerinden yerel onay bileti oluşturarak "
                "Windows ve ESU (Genişletilmiş Güvenlik Güncellemeleri) sürümlerini etkinleştirir. (Süre: 2038'e KADAR / KALICI)"
            )
        elif method_data == "kms":
            self.license_activate_btn.setText("ONLINE KMS İLE ETKİNLEŞTİR (180 GÜN)")
            self.license_method_desc.setText(
                "Online KMS: Resmî Microsoft GVLK anahtarları ve güvenilir KMS sunucuları üzerinden "
                "180 günlük periyotlarla otomatik yenilenen lisanslama sağlar. (Süre: 180 GÜN - OTOMATİK YENİLENEN)"
            )

    def open_license_page(self):
        self.show_page("license")
        self.refresh_license_status()

    def refresh_license_status(self):
        threading.Thread(target=self._license_status_worker, daemon=True).start()

    def _license_status_worker(self):
        info = get_windows_license_status()
        self.ui_queue.put({
            "action": "license_status",
            "text": info.get("display_text", ""),
            "color": info.get("color", "#AEB8C3"),
        })

    def set_loading_license_status(self, base_text):
        self.license_status_base_text = base_text
        self.is_processing = True
        self.spinner_timer.start(16)
        if self.license_status_label is not None:
            self.license_status_label.setText(f"{base_text}...")
            self.license_status_label.setStyleSheet(
                "color: #FFB86C; border: none; font-size: 12px; font-weight: 600;"
            )

    def stop_loading_license_status(self):
        self.license_status_base_text = None
        self.is_processing = False
        self.spinner_timer.stop()

    def activate_windows_license(self):
        method_data = self.license_method_combo.itemData(self.license_method_combo.currentIndex())
        if not method_data:
            return
        self.license_activate_btn.setEnabled(False)
        self.license_method_combo.setEnabled(False)
        method_names = {
            "hwid": "HWID Dijital Lisanslama",
            "tsforge": "TSforge Lisanslama",
            "kms": "Online KMS Lisanslama"
        }
        self.set_loading_license_status(
            f"Windows 11 {get_current_windows_edition()} için {method_names.get(method_data, 'Lisanslama')} uygulanıyor"
        )
        threading.Thread(target=self._activation_worker, args=(method_data,), daemon=True).start()

    def _activation_worker(self, method_data="hwid"):
        def on_status(msg):
            self.ui_queue.put({"action": "license_status_update", "text": msg})

        ok, err_or_msg = activate_windows(method=method_data, on_status_update=on_status)
        if ok:
            text = "Lisans etkinleştirme işlemi başarıyla tamamlandı."
            color = "#55D67A"
        else:
            text = f"Lisans etkinleştirme başarısız: {err_or_msg}"
            color = "#FF6B78"
        self.ui_queue.put({"action": "license_activation_done", "text": text, "color": color})

    # ---------- Tuş Dönüştürücü Sayfası ----------
    def build_key_remap_frame(self):
        layout = QVBoxLayout(self.key_remap_frame)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        section = QLabel("Klavye / Donanım Eşleme")
        section.setStyleSheet(
            f"color: {self.accent}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; border: none;"
        )
        title = QLabel("Tuş Dönüştürücü")
        title.setStyleSheet("color: #F4F7FA; font-size: 23px; font-weight: 700; border: none;")
        subtitle = QLabel(
            "Klavye tuşlarını farklı işlevlere atayabilir veya devre dışı bırakabilirsiniz. "
            "Yapılan eşlemeler sistem oturumu yeniden başlatıldığında geçerli olur."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #929DA8; font-size: 12px; border: none;")

        layout.addWidget(section)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Üst eylem çubuğu: + Yeni Eşleme Ekle, oturum uyarısı rozeti ve aktif sayaç
        action_bar = QFrame()
        action_bar.setStyleSheet(
            "background-color: #121820; border: 1px solid #222C37; border-radius: 10px;"
        )
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(16, 12, 16, 12)
        action_layout.setSpacing(16)

        btn_add = QPushButton("+ Yeni Eşleme Ekle")
        btn_add.setFixedHeight(36)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet(
            "QPushButton { background-color: #FF334B; color: #FFFFFF; border: 1px solid #FF5263; "
            "border-radius: 6px; font-weight: bold; font-size: 12px; padding: 0 16px; outline: none; }\n"
            "QPushButton:hover { background-color: #FF4D61; }\n"
            "QPushButton:pressed { background-color: #E62E44; }"
        )
        btn_add.clicked.connect(self.open_add_key_remap_dialog)
        action_layout.addWidget(btn_add)

        notice = QLabel("Değişikliklerin geçerli olması için oturumu kapatıp açmanız gerekir.")
        notice.setStyleSheet("color: #E5A93C; font-size: 11px; font-weight: 500; border: none; background: transparent;")
        action_layout.addWidget(notice)

        action_layout.addStretch()

        self.key_remap_count_label = QLabel("0 aktif eşleme")
        self.key_remap_count_label.setStyleSheet(
            "color: #8C9BA8; font-size: 11px; font-weight: 600; border: none; background: transparent;"
        )
        action_layout.addWidget(self.key_remap_count_label)

        layout.addWidget(action_bar)

        # Liste scroll alanı
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 0px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #E63B4D;
                min-height: 48px;
                border-radius: 5px;
                border: none;
            }
            QScrollBar::handle:vertical:hover {
                background: #FF5263;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        self.key_remap_container = QWidget()
        self.key_remap_container.setStyleSheet("background-color: transparent; border: none;")
        self.key_remap_list_layout = QVBoxLayout(self.key_remap_container)
        self.key_remap_list_layout.setContentsMargins(0, 4, 0, 8)
        self.key_remap_list_layout.setSpacing(8)

        scroll.setWidget(self.key_remap_container)
        layout.addWidget(scroll, 1)

        self.refresh_key_remap_list()

    def refresh_key_remap_list(self):
        if not hasattr(self, "key_remap_list_layout") or self.key_remap_list_layout is None:
            return

        while self.key_remap_list_layout.count():
            item = self.key_remap_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        mappings = KeyboardRemapEngine.load_mappings()
        is_ws_disabled = KeyboardRemapEngine.is_win_space_disabled()
        total_active = len(mappings) + (1 if is_ws_disabled else 0)

        if hasattr(self, "key_remap_count_label") and self.key_remap_count_label is not None:
            self.key_remap_count_label.setText(f"{total_active} aktif eşleme")

        if not mappings and not is_ws_disabled:
            empty_card = QFrame()
            empty_card.setStyleSheet(
                "background-color: #0E1318; border: 1px dashed #242D38; border-radius: 10px;"
            )
            empty_layout = QVBoxLayout(empty_card)
            empty_layout.setContentsMargins(20, 36, 20, 36)
            empty_layout.setSpacing(10)
            empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lbl_empty_title = QLabel("Henüz bir tuş eşleştirmesi tanımlanmadı")
            lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_empty_title.setStyleSheet("color: #C5D1DE; font-size: 14px; font-weight: bold; border: none; background: transparent;")

            lbl_empty_sub = QLabel(
                "Klavyenizdeki tuşların işlevini değiştirmek veya istenmeyen tuşları devre dışı bırakmak için\n"
                "yukarıdaki '+ Yeni Eşleme Ekle' butonunu kullanabilirsiniz."
            )
            lbl_empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_empty_sub.setStyleSheet("color: #72808E; font-size: 11.5px; border: none; background: transparent;")

            empty_layout.addWidget(lbl_empty_title)
            empty_layout.addWidget(lbl_empty_sub)
            self.key_remap_list_layout.addWidget(empty_card)
            self.key_remap_list_layout.addStretch()
            return

        # 1. Özel Windows + Space kaydı varsa en başta listele
        if is_ws_disabled:
            ws_frame = QFrame()
            ws_frame.setObjectName("KeyRemapRow")
            ws_frame.setStyleSheet(
                "QFrame#KeyRemapRow { background-color: #121820; border: 1px solid #202934; border-radius: 8px; }\n"
                "QFrame#KeyRemapRow:hover { border-color: #FF334B; background-color: #151C25; }"
            )
            ws_layout = QHBoxLayout(ws_frame)
            ws_layout.setContentsMargins(16, 12, 16, 12)
            ws_layout.setSpacing(14)

            pill_src = QLabel("  Windows + Space  ")
            pill_src.setFixedHeight(30)
            pill_src.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill_src.setStyleSheet(
                "background-color: #1A232E; color: #FFFFFF; border: 1px solid #324152; "
                "border-radius: 6px; font-size: 12px; font-weight: bold; padding: 2px 10px;"
            )

            arrow = QLabel("→")
            arrow.setStyleSheet("color: #FF334B; font-size: 18px; font-weight: bold; border: none; background: transparent;")

            pill_tgt = QLabel("  Devre Dışı / Kapat  ")
            pill_tgt.setFixedHeight(30)
            pill_tgt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill_tgt.setStyleSheet(
                "background-color: #2D1418; color: #FF7784; border: 1px solid #6E222B; "
                "border-radius: 6px; font-size: 12px; font-weight: bold; padding: 2px 10px;"
            )

            desc_ws = QLabel("(Dil Değiştirme Kısayolu Devre Dışı)")
            desc_ws.setStyleSheet("color: #6C7A89; font-size: 11px; border: none; background: transparent;")

            ws_layout.addWidget(pill_src)
            ws_layout.addWidget(arrow)
            ws_layout.addWidget(pill_tgt)
            ws_layout.addWidget(desc_ws)
            ws_layout.addStretch()

            btn_del_ws = QPushButton("Sil")
            btn_del_ws.setFixedSize(54, 28)
            btn_del_ws.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del_ws.setStyleSheet(
                "QPushButton { background-color: #211317; color: #FF7784; border: 1px solid #4D2128; "
                "border-radius: 4px; font-size: 11px; font-weight: 600; outline: none; }\n"
                "QPushButton:hover { background-color: #FF334B; color: #FFFFFF; border-color: #FF5263; }\n"
                "QPushButton:pressed { background-color: #D6243A; }"
            )
            btn_del_ws.clicked.connect(self._delete_win_space_mapping)
            ws_layout.addWidget(btn_del_ws)

            self.key_remap_list_layout.addWidget(ws_frame)

        # 2. Donanım Scancode Eşlemeleri
        for orig_sc, target_sc in mappings:
            row_frame = QFrame()
            row_frame.setObjectName("KeyRemapRow")
            row_frame.setCursor(Qt.CursorShape.PointingHandCursor)
            row_frame.setStyleSheet(
                "QFrame#KeyRemapRow { background-color: #121820; border: 1px solid #202934; border-radius: 8px; }\n"
                "QFrame#KeyRemapRow:hover { border-color: #FF334B; background-color: #151C25; }"
            )
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(16, 12, 16, 12)
            row_layout.setSpacing(14)

            orig_name = SCANCODE_TO_LABEL.get(orig_sc, f"Tuş (0x{orig_sc:04X})")
            target_name = SCANCODE_TO_LABEL.get(target_sc, f"Tuş (0x{target_sc:04X})")
            if target_sc == 0:
                target_name = "Devre Dışı / Kapat"

            orig_pill = QLabel(f"  {orig_name}  ")
            orig_pill.setFixedHeight(30)
            orig_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            orig_pill.setStyleSheet(
                "background-color: #1A232E; color: #FFFFFF; border: 1px solid #324152; "
                "border-radius: 6px; font-size: 12px; font-weight: bold; padding: 2px 10px;"
            )

            arrow = QLabel("→")
            arrow.setStyleSheet("color: #FF334B; font-size: 18px; font-weight: bold; border: none; background: transparent;")

            target_pill = QLabel(f"  {target_name}  ")
            target_pill.setFixedHeight(30)
            target_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if target_sc == 0:
                target_pill.setStyleSheet(
                    "background-color: #2D1418; color: #FF7784; border: 1px solid #6E222B; "
                    "border-radius: 6px; font-size: 12px; font-weight: bold; padding: 2px 10px;"
                )
            else:
                target_pill.setStyleSheet(
                    "background-color: #15222E; color: #4FC3F7; border: 1px solid #1E4963; "
                    "border-radius: 6px; font-size: 12px; font-weight: bold; padding: 2px 10px;"
                )

            hex_info = QLabel(f"(0x{orig_sc:04X} → 0x{target_sc:04X})")
            hex_info.setStyleSheet("color: #5B6875; font-size: 10.5px; font-family: Consolas; border: none; background: transparent;")

            edit_hint = QLabel("Düzenlemek için tıkla")
            edit_hint.setStyleSheet("color: #3F4C59; font-size: 10px; border: none; background: transparent; font-style: italic;")

            row_layout.addWidget(orig_pill)
            row_layout.addWidget(arrow)
            row_layout.addWidget(target_pill)
            row_layout.addWidget(hex_info)
            row_layout.addWidget(edit_hint)
            row_layout.addStretch()

            btn_del = QPushButton("Sil")
            btn_del.setFixedSize(54, 28)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet(
                "QPushButton { background-color: #211317; color: #FF7784; border: 1px solid #4D2128; "
                "border-radius: 4px; font-size: 11px; font-weight: 600; outline: none; }\n"
                "QPushButton:hover { background-color: #FF334B; color: #FFFFFF; border-color: #FF5263; }\n"
                "QPushButton:pressed { background-color: #D6243A; }"
            )
            btn_del.clicked.connect(lambda _, sc=orig_sc: self._delete_key_mapping(sc))
            row_layout.addWidget(btn_del)

            # Satıra tıklandığında düzenleme penceresi açılır
            def _make_click_handler(s=orig_sc, t=target_sc):
                return lambda event: self.open_edit_key_remap_dialog(s, t) if event.button() == Qt.MouseButton.LeftButton else None

            row_frame.mousePressEvent = _make_click_handler(orig_sc, target_sc)

            self.key_remap_list_layout.addWidget(row_frame)

        self.key_remap_list_layout.addStretch()

    def open_add_key_remap_dialog(self):
        dlg = KeyRemapDialog(self, is_edit=False)
        if dlg.exec():
            orig_sc, target_sc = dlg.get_mapping()
            if orig_sc == 0xF001:
                KeyboardRemapEngine.set_win_space_disabled(True)
                self.cfg_disable_win_space = True
            else:
                KeyboardRemapEngine.add_or_update_mapping(orig_sc, target_sc)
            self.refresh_key_remap_list()

    def open_edit_key_remap_dialog(self, current_orig_sc, current_target_sc):
        dlg = KeyRemapDialog(self, initial_source=current_orig_sc, initial_target=current_target_sc, is_edit=True)
        if dlg.exec():
            new_orig_sc, new_target_sc = dlg.get_mapping()
            if new_orig_sc == 0xF001:
                KeyboardRemapEngine.delete_mapping(current_orig_sc)
                KeyboardRemapEngine.set_win_space_disabled(True)
                self.cfg_disable_win_space = True
            else:
                KeyboardRemapEngine.edit_mapping(current_orig_sc, new_orig_sc, new_target_sc)
            self.refresh_key_remap_list()

    def _delete_key_mapping(self, orig_sc):
        KeyboardRemapEngine.delete_mapping(orig_sc)
        self.refresh_key_remap_list()

    def _delete_win_space_mapping(self):
        KeyboardRemapEngine.set_win_space_disabled(False)
        self.cfg_disable_win_space = False
        self.refresh_key_remap_list()


