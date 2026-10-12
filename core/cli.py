"""
WinKit - Command Line Interface (CLI) Engine
Interactive and headless console mode for debloating, optimization,
and test routines.
"""

import os
import sys
import re
import time
import ctypes
import winreg
import json
import base64
import subprocess
from pathlib import Path

from core.constants import CREATE_NO_WINDOW
from core.privileges import (
    enable_process_privileges,
    run_powershell_as_system,
    run_powershell_as_trustedinstaller,
)
from core.system import (
    is_admin,
    append_runtime_diagnostic,
    get_winkit_data_directory,
    schedule_system_path_cleanup_on_boot,
)
from core.registry import is_defender_active
from core.context_menu import register_winkit_context_menu
from core.tweaks import apply_msi_interrupt_tuning
from core.shutup10 import load_oosu_config_rules

WINKIT_CLI_BANNER = r"""
$$\      $$\ $$\           $$\   $$\ $$\   $$\     
$$ | $\  $$ |\__|          $$ | $$  |\__|  $$ |    
$$ |$$$\ $$ |$$\ $$$$$$$\  $$ |$$  / $$\ $$$$$$\   
$$ $$ $$\$$ |$$ |$$  __$$\ $$$$$  /  $$ |\_$$  _|  
$$$$  _$$$$ |$$ |$$ |  $$ |$$  $$<   $$ |  $$ |    
$$$  / \$$$ |$$ |$$ |  $$ |$$ |\$$\  $$ |  $$ |$$\ 
$$  /   \$$ |$$ |$$ |  $$ |$$ | \$$\ $$ |  \$$$$  |
\__/     \__|\__|\__|  \__|\__|  \__|\__|   \____/ 
"""


def print_cli_banner():
    RED = "\033[91m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass
    print(f"{RED}{BOLD}{WINKIT_CLI_BANNER}{RESET}")
    print(f"{CYAN}      [ WinKit Advanced Windows Tweaker & Debloat Engine ]{RESET}\n")


def run_cli_test_mode(non_interactive=True):
    ctrl = WinKitCliDebloatController()
    return ctrl.run_test_profile()

def _cli_print(text):
    if not getattr(sys.stdout, "isatty", lambda: False)():
        text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_text = str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_text, flush=True)


class WinKitCliUiQueue:
    """CLI modunda UI kuyruğuna atılan mesajları formatlayıp konsola yansıtır."""

    def __init__(self):
        self.last_progress_text = ""

    def put(self, item):
        action = item.get("action")
        if action == "log":
            txt = str(item.get("text", "")).strip()
            col = item.get("color", "")
            if not txt:
                return
            if col in ("#FF5555", "#FF5C6B", "#E63B4D") or "HATA" in txt or "✖" in txt or "[!]" in txt:
                _cli_print(f"  \033[91m✖ {txt}\033[0m")
            elif col in ("#FFB86C", "#FFAA00") or "UYARI" in txt or "⚠" in txt:
                _cli_print(f"  \033[93m⚠ {txt}\033[0m")
            elif col in ("#55D67A", "#00ff66"):
                _cli_print(f"  \033[92m✔ {txt}\033[0m")
            else:
                _cli_print(f"  \033[90m• {txt}\033[0m")
        elif action == "log_segments":
            segs = item.get("segments", [])
            line = ""
            for text, hex_col in segs:
                if hex_col in ("#55D67A", "#00ff66"):
                    line += f"\033[92m{text}\033[0m"
                elif hex_col in ("#FFB86C", "#FFAA00"):
                    line += f"\033[93m{text}\033[0m"
                elif hex_col in ("#FF5C6B", "#FF5555", "#E63B4D"):
                    line += f"\033[91m{text}\033[0m"
                elif hex_col in ("#E2E2E2", "#DDE4EC", "#F4F7FA"):
                    line += f"\033[97m{text}\033[0m"
                else:
                    line += text
            if line.strip():
                _cli_print(f"  {line}")
        elif action == "progress_update":
            raw_base = str(item.get("text_base", "")).strip()
            if raw_base and raw_base != self.last_progress_text:
                self.last_progress_text = raw_base
                _cli_print(f"  \033[97m[•] {raw_base}\033[0m")
        elif action == "progress_stop":
            raw_base = str(item.get("text_base", "")).strip()
            result = str(item.get("result", "tamamlandı")).strip()
            _cli_print(f"    \033[92m✔ {raw_base} · {result}\033[0m")
        elif action == "stage_start":
            _cli_print(f"\n\033[96m[•]\033[0m \033[1m\033[97m{item.get('text_base', '')}...\033[0m")
        elif action == "stage_update_title":
            title = str(item.get('text_base', '')).strip()
            if not title or "Servisler durduruluyor" in title:
                pass
            else:
                _cli_print(f"  \033[90m--> {title}\033[0m")
        elif action == "stage_finish":
            res = item.get("result", "✔")
            if res in ("✔", "tamamlandı", "kaldırıldı", "temizlendi", "uygulandı"):
                _cli_print(f"    \033[92m✔ {res}\033[0m")
            elif res in ("⚠", "planlandı", "ertelenmiş"):
                _cli_print(f"    \033[93m⚠ {res}\033[0m")
            else:
                _cli_print(f"    \033[91m✖ {res}\033[0m")


CliDebloatQueue = WinKitCliUiQueue


def get_instant_key():
    """Klavyeden basılan tuşu anında okur (Enter beklemez)."""
    import msvcrt
    try:
        ch = msvcrt.getwch()
        if ch in ('\x00', '\xe0'):
            ext = msvcrt.getwch()
            return f"EXT_{ord(ext)}"
        return ch
    except Exception:
        try:
            return sys.stdin.read(1)
        except Exception:
            return ""


def read_menu_action():
    """Tek tuş veya iki haneli rakam girişlerini (11, 27 vb.) akıllıca okur."""
    import msvcrt, time
    ch = get_instant_key()
    if not ch:
        return ""
    if ch in ('\r', '\n', ' '):
        return "RUN"
    if ch == '\x1b':
        return "EXIT"
    if ch.isdigit():
        first_digit = ch
        t_start = time.time()
        second_digit = ""
        while time.time() - t_start < 0.28:
            if msvcrt.kbhit():
                c2 = msvcrt.getwch()
                if c2.isdigit():
                    second_digit = c2
                    break
                else:
                    return first_digit
            time.sleep(0.01)
        if second_digit:
            return first_digit + second_digit
        return first_digit
    return ch.lower()


class WinKitCliDebloatController:
    """CLI modunda GUI Debloat sekmesinin tüm fonksiyonlarını birebir yöneten kontrolcü."""

    def __init__(self):
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
            ("Başlat Deneyimleri", "Microsoft.StartExperiencesApp"),
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
            ("Hesap Makinesi", "Microsoft.WindowsCalculator"),
        ]
        self.app_vars = {app[0]: True for app in self.bloat_apps}

        self.oosu_exe = self.get_binary_path("OOSU10.exe")
        cfg_path = self.get_binary_path("ooshutup10.cfg")
        config_rules = load_oosu_config_rules(cfg_path) if os.path.isfile(cfg_path) else []
        self.shutup_rules = config_rules if config_rules else []
        self.shutup_vars = {
            code: (sign == "+" or code in ("M013", "M014"))
            for code, sign, _, _ in self.shutup_rules
        }

        # Debloat anahtarları (Varsayılan: Önerilen Profil Açık)
        self.cfg_apps_enabled = True
        self.cfg_shutup10 = True
        self.cfg_telemetry = True
        self.cfg_bing_search = True
        self.cfg_consumer_features = True
        self.cfg_store_recommend = True
        self.cfg_location = True
        self.cfg_widgets = True
        self.cfg_delivery_opt = True
        self.cfg_services = True
        self.cfg_defender = False
        self.cfg_disable_defender = False
        self.cfg_purge_defender = False
        self.defender_mode = "disable"
        self.cfg_pause_updates_2099 = False
        self.cfg_classic_menu = True
        self.cfg_end_task = True
        self.cfg_context_menu_tools = True
        self.cfg_gaming_tweaks = True
        self.cfg_disable_fso = True
        self.cfg_disable_mpo = True
        self.cfg_disable_s0_drain = True
        self.cfg_ntp_sync = True
        self.cfg_ultraperf = False
        self.cfg_remove_bitlocker = False
        self.cfg_sticky_keys = True
        self.cfg_dark = True
        self.cfg_extensions = True
        self.cfg_bsod = True
        self.cfg_feafd = True
        self.cfg_hibernate = False
        self.cfg_wpbt = False
        self.cfg_remove_ai = False
        self.cfg_disable_ai = False
        self.cfg_llmnr_poisoning = True
        self.cfg_disable_lastaccess = True
        self.cfg_hags = True
        self.cfg_reserved_storage = False
        self.cfg_verbose_status = True
        self.cfg_long_paths = True
        self.cfg_utc_clock = False
        self.cfg_smartscreen_clipboard = True
        self.cfg_clipboard_local = True
        self.cfg_smartscreen_explorer = True
        self.cfg_device_companion = True
        self.cfg_msi_interrupts = False
        self.cfg_disable_win_space = False
        self.cfg_control_panel_small_icons = True

        self.ui_queue = CliDebloatQueue()

    def get_binary_path(self, filename):
        if hasattr(sys, "_MEIPASS"):
            bundled_path = os.path.join(sys._MEIPASS, filename)
            if os.path.exists(bundled_path):
                return bundled_path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(script_dir, filename)
        if os.path.exists(local_path):
            return local_path
        return os.path.abspath(filename)

    def _apply_shutup_rules_sync(self):
        from gui.app import WinKitApp
        return WinKitApp._apply_shutup_rules_sync(self)

    def _apply_privacy_fallback_registry(self):
        from gui.app import WinKitApp
        return WinKitApp._apply_privacy_fallback_registry(self)

    def _debloat_worker_impl(self):
        from gui.app import WinKitApp
        return WinKitApp._debloat_worker_impl(self)

    def _run_powershell_checked(self, script, timeout=120):
        from gui.app import WinKitApp
        return WinKitApp._run_powershell_checked(self, script, timeout=timeout)


    def set_recommended_preset(self):
        """Önerilen optimize debloat profilini yükler."""
        self.cfg_apps_enabled = True
        self.cfg_shutup10 = True
        self.cfg_telemetry = True
        self.cfg_bing_search = True
        self.cfg_consumer_features = True
        self.cfg_store_recommend = True
        self.cfg_location = True
        self.cfg_widgets = True
        self.cfg_delivery_opt = True
        self.cfg_services = True
        self.cfg_defender = False
        self.cfg_disable_defender = False
        self.cfg_purge_defender = False
        self.defender_mode = "disable"
        self.cfg_pause_updates_2099 = False
        self.cfg_classic_menu = True
        self.cfg_end_task = True
        self.cfg_context_menu_tools = True
        self.cfg_gaming_tweaks = True
        self.cfg_disable_fso = True
        self.cfg_disable_mpo = True
        self.cfg_disable_s0_drain = True
        self.cfg_ntp_sync = True
        self.cfg_ultraperf = False
        self.cfg_remove_bitlocker = False
        self.cfg_sticky_keys = True
        self.cfg_dark = True
        self.cfg_extensions = True
        self.cfg_bsod = True
        self.cfg_feafd = True
        self.cfg_hibernate = False
        self.cfg_disable_win_space = False
        for app in self.bloat_apps:
            self.app_vars[app[0]] = True
        for code, sign, _, _ in self.shutup_rules:
            self.shutup_vars[code] = (sign == "+" or code in ("M013", "M014"))

    def set_full_debloat_purge_preset(self):
        """Tüm uygulamaları seçer, gizlilikte önerilenleri uygular, tüm ayarları açar ve Defender'ı durdurur."""
        for app in self.bloat_apps:
            self.app_vars[app[0]] = True
        for code, sign, _, _ in self.shutup_rules:
            self.shutup_vars[code] = (sign == "+" or code in ("M013", "M014"))
        for attr in [
            "cfg_apps_enabled", "cfg_shutup10", "cfg_telemetry", "cfg_bing_search",
            "cfg_consumer_features", "cfg_store_recommend", "cfg_location", "cfg_widgets",
            "cfg_delivery_opt", "cfg_services", "cfg_classic_menu", "cfg_end_task",
            "cfg_context_menu_tools", "cfg_gaming_tweaks", "cfg_disable_fso", "cfg_disable_mpo",
            "cfg_disable_s0_drain", "cfg_ntp_sync", "cfg_sticky_keys", "cfg_dark",
            "cfg_extensions", "cfg_bsod", "cfg_feafd", "cfg_hibernate", "cfg_remove_bitlocker",
            "cfg_ultraperf", "cfg_pause_updates_2099", "cfg_defender", "cfg_disable_win_space"
        ]:
            setattr(self, attr, True)

    def toggle_all(self):
        """Tüm seçenekleri (Defender, Ultra Perf, BitLocker, Hibernate vb. dahil) tersine çevirir."""
        all_attrs = [
            "cfg_apps_enabled", "cfg_shutup10", "cfg_telemetry", "cfg_bing_search",
            "cfg_consumer_features", "cfg_store_recommend", "cfg_location", "cfg_widgets",
            "cfg_delivery_opt", "cfg_services", "cfg_defender", "cfg_pause_updates_2099",
            "cfg_classic_menu", "cfg_end_task", "cfg_context_menu_tools", "cfg_extensions",
            "cfg_bsod", "cfg_dark", "cfg_feafd", "cfg_hibernate", "cfg_remove_bitlocker",
            "cfg_gaming_tweaks", "cfg_disable_fso", "cfg_disable_mpo", "cfg_disable_s0_drain",
            "cfg_ntp_sync", "cfg_ultraperf", "cfg_disable_win_space"
        ]
        new_val = not all(getattr(self, a, False) for a in all_attrs)
        for attr in all_attrs:
            setattr(self, attr, new_val)
        for app in self.bloat_apps:
            self.app_vars[app[0]] = new_val

    def toggle_defender(self):
        """Defender durumunu değiştirir (Defender Control yöntemiyle anında durdurma)."""
        self.cfg_defender = not self.cfg_defender

    def app_checklist_menu(self):
        page = 0
        per_page = 10
        total_pages = (len(self.bloat_apps) + per_page - 1) // per_page
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print("=" * 80)
            print(f"   \033[96m[ WinKit CLI - Windows Uygulamaları Seçim Listesi (Sayfa {page+1}/{total_pages}) ]\033[0m")
            print("=" * 80)
            start_idx = page * per_page
            end_idx = min(start_idx + per_page, len(self.bloat_apps))
            current_slice = self.bloat_apps[start_idx:end_idx]
            
            key_labels = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
            for i, (name, pkg) in enumerate(current_slice):
                chk = "\033[92m[X]\033[0m" if self.app_vars.get(name, False) else "\033[90m[ ]\033[0m"
                k_label = key_labels[i] if i < len(key_labels) else f"{i+1}"
                print(f"  [{k_label}] {chk} {name:<36} \033[90m({pkg})\033[0m")
            print("-" * 80)
            print("  \033[97m[A] Tümünü Seç (All)\033[0m          \033[97m[K] Tümünü Kaldır (None)\033[0m")
            print("  \033[94m[> / + / N] Sonraki Sayfa\033[0m     \033[94m[< / - / P] Önceki Sayfa\033[0m")
            print("  \033[93m[B / ESC / ENTER] Geri Dön (Debloat Menüsü)\033[0m")
            print("-" * 80)
            print("  \033[90m(Rakam tuşlayarak anında açıp kapatabilir, N/P ile sayfa değiştirebilirsiniz)\033[0m")

            c = get_instant_key()
            if not c:
                continue
            c_low = c.lower() if isinstance(c, str) else ""

            if c in ('\r', '\n', '\x1b') or c_low in ("b", "q", "exit", "ext_27"):
                break
            elif c_low in ("a",):
                for app in self.bloat_apps:
                    self.app_vars[app[0]] = True
            elif c_low in ("k", "c"):
                for app in self.bloat_apps:
                    self.app_vars[app[0]] = False
            elif c in (">", "+", ".", "n", "N", "ext_77", "ext_80"):
                page = (page + 1) % total_pages
            elif c in ("<", "-", ",", "p", "P", "ext_75", "ext_72"):
                page = (page - 1 + total_pages) % total_pages
            elif c.isdigit():
                digit_idx = 9 if c == "0" else int(c) - 1
                if 0 <= digit_idx < len(current_slice):
                    app_name = current_slice[digit_idx][0]
                    self.app_vars[app_name] = not self.app_vars.get(app_name, False)

    def shutup_checklist_menu(self):
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print("=" * 75)
            print("         \033[96m[ WinKit CLI - O&O ShutUp10 Gizlilik Kuralları ]\033[0m")
            print("=" * 75)
            rec_count = sum(1 for code in self.shutup_vars if self.shutup_vars[code])
            print(f"  Aktif Kural Sayısı: \033[92m{rec_count}/{len(self.shutup_rules)}\033[0m")
            print("-" * 75)
            print("  \033[92m[1] Önerilen Ayarları Yükle (+ M013/M014 Harita Trafik Koruması)\033[0m")
            print("  \033[93m[2] Tüm Gizlilik Kurallarını Aç (Maksimum Gizlilik)\033[0m")
            print("  \033[90m[3] Tüm Kuralları Kapat (Varsayılan Windows)\033[0m")
            print("  \033[97m[B / 0 / ESC] Geri Dön\033[0m")
            print("-" * 75)
            print("  \033[90m(Tuşa bastığınız anda işlem uygulanır)\033[0m")

            c = read_menu_action()
            if c in ("b", "0", "exit", "EXT_27"):
                break
            elif c == "1":
                for code, sign, _, _ in self.shutup_rules:
                    self.shutup_vars[code] = (sign == "+" or code in ("M013", "M014"))
            elif c == "2":
                for code in self.shutup_vars:
                    self.shutup_vars[code] = True
            elif c == "3":
                for code in self.shutup_vars:
                    self.shutup_vars[code] = False

    def run_test_profile(self):
        """Otomasyonlu test koşusu (canlı çıktı ile)."""
        print_cli_banner()
        print("\033[93m[*] WinKit Otonom Test Paketi (Debloat Motoru) Başlatılıyor...\033[0m")
        self.set_full_debloat_purge_preset()
        try:
            self._debloat_worker_impl()
            print("\n\033[92m========================================================\033[0m")
            print("\033[92m[BAŞARILI] WinKit Debloat ve Sistem Optimizasyonu Tamamlandı.\033[0m")
            print("\033[93mSistem 30 saniye içinde otomatik olarak yeniden başlatılacaktır.\033[0m")
            print("\033[92m========================================================\033[0m\n")
            return 0
        except Exception as exc:
            print(f"\n\033[91m[HATA] Test paketi başarısız: {exc}\033[0m\n")
            return 1

    def run_test_stop_profile(self):
        """Otomasyonlu test koşusu (Defender 'Komple Durdur' modunda)."""
        print_cli_banner()
        print("\033[93m[*] WinKit Otonom Test Paketi (Defender Durdurma Modu) Başlatılıyor...\033[0m")
        self.set_recommended_preset()
        self.cfg_defender = True
        self.cfg_purge_defender = False
        self.defender_mode = "disable"
        try:
            self._debloat_worker_impl()
            print("\n\033[92m========================================================\033[0m")
            print("\033[92m[BAŞARILI] WinKit Debloat (Defender Durdurma Modu) Tamamlandı.\033[0m")
            print("\033[92m========================================================\033[0m\n")
            return 0
        except Exception as exc:
            print(f"\n\033[91m[HATA] Test paketi başarısız: {exc}\033[0m\n")
            return 1

    def run_test_purge_profile(self):
        """Otomasyonlu test koşusu (Defender Durdurma Modu)."""
        return self.run_test_stop_profile()

    def run_test_purge_full_profile(self):
        """Otomasyonlu test koşusu (Defender Durdurma Modu)."""
        return self.run_test_stop_profile()

    def run_test_def_disable_only(self):
        """Yalnızca Defender Durdurma (Defender Control Yöntemi) modunu doğrudan çalıştırır."""
        print_cli_banner()
        print("\033[93m[*] WinKit Yalnızca Defender Durdurma (Defender Control) Modu Başlatılıyor...\033[0m")
        self.cfg_apps_enabled = False
        self.cfg_shutup10 = False
        self.cfg_telemetry = False
        self.cfg_bing_search = False
        self.cfg_consumer_features = False
        self.cfg_store_recommend = False
        self.cfg_location = False
        self.cfg_widgets = False
        self.cfg_delivery_opt = False
        self.cfg_services = False
        self.cfg_classic_menu = False
        self.cfg_end_task = False
        self.cfg_context_menu_tools = False
        self.cfg_gaming_tweaks = False
        self.cfg_disable_fso = False
        self.cfg_disable_mpo = False
        self.cfg_disable_s0_drain = False
        self.cfg_ntp_sync = False
        self.cfg_ultraperf = False
        self.cfg_sticky_keys = False
        self.cfg_dark = False
        self.cfg_extensions = False
        self.cfg_bsod = False
        self.cfg_feafd = False
        self.cfg_hibernate = False
        self.cfg_disable_win_space = False
        self.cfg_defender = True
        self.cfg_disable_defender = True
        self.defender_mode = "disable"
        try:
            self._debloat_worker_impl()
            print("\n\033[92m========================================================\033[0m")
            print("\033[92m[BAŞARILI] Defender Durdurma Modu Tamamlandı.\033[0m")
            print("\033[92m========================================================\033[0m\n")
            return 0
        except Exception as exc:
            print(f"\n\033[91m[HATA] Defender durdurma başarısız: {exc}\033[0m\n")
            return 1

    def run_test_def_purge_only(self):
        """Yalnızca Defender Durdurma modunu doğrudan çalıştırır."""
        return self.run_test_def_disable_only()

    def run_test_def_purge_full_only(self):
        """Yalnızca Defender Durdurma modunu doğrudan çalıştırır."""
        return self.run_test_def_disable_only()

    def run_test_restore_profile(self):
        """Otomasyonlu test koşusu (Defender Geri Yükleme)."""
        print_cli_banner()
        print("\033[93m[*] WinKit Otonom Test Paketi (Defender Geri Yükleme) Başlatılıyor...\033[0m")
        try:
            system_script = r"""
$ErrorActionPreference = 'SilentlyContinue'
Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender' -Name 'DisableAntiSpyware' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender' -Name 'DisableAntiVirus' -ErrorAction SilentlyContinue
Remove-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender Security Center' -Recurse -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' -Name 'EnableSmartScreen' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
$shs = 'HKLM:\SYSTEM\CurrentControlSet\Services\SecurityHealthService'
if (-not (Test-Path $shs)) { New-Item -Path $shs -Force | Out-Null }
Set-ItemProperty -Path $shs -Name 'DisplayName' -Value 'Windows Security Service' -Type String -Force
Set-ItemProperty -Path $shs -Name 'ImagePath' -Value "$env:WINDIR\system32\SecurityHealthService.exe" -Type ExpandString -Force
Set-ItemProperty -Path $shs -Name 'Type' -Value 16 -Type DWord -Force
Set-ItemProperty -Path $shs -Name 'Start' -Value 2 -Type DWord -Force
Set-ItemProperty -Path $shs -Name 'ObjectName' -Value 'LocalSystem' -Type String -Force
& sc.exe config SecurityHealthService start=auto 2>$null | Out-Null
& sc.exe start SecurityHealthService 2>$null | Out-Null
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\WinDefend' -Name 'Start' -Value 2 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\WdNisSvc' -Name 'Start' -Value 3 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Sense' -Name 'Start' -Value 3 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\WdBoot' -Name 'Start' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\WdFilter' -Name 'Start' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\WdNisDrv' -Name 'Start' -Value 3 -Type DWord -Force -ErrorAction SilentlyContinue
& sc.exe config WinDefend start=auto 2>$null | Out-Null
& sc.exe start WinDefend 2>$null | Out-Null
& sc.exe config WdNisSvc start=demand 2>$null | Out-Null
& sc.exe start WdNisSvc 2>$null | Out-Null
Get-ChildItem -Path "$env:WINDIR\SystemApps" -Filter "*SecHealthUI*" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $manifest = Join-Path $_.FullName "AppxManifest.xml"
    if (Test-Path $manifest) {
        Add-AppxPackage -Register -DisableDevelopmentMode $manifest -ErrorAction SilentlyContinue
    }
}
"""
            run_powershell_as_system(system_script, timeout=60)
            user_script = r"""
$ErrorActionPreference = 'SilentlyContinue'
Set-MpPreference -DisableRealtimeMonitoring $false -DisableBehaviorMonitoring $false -DisableIOAVProtection $false -DisableScriptScanning $false -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run' -Name 'SecurityHealth' -Value '%systemroot%\system32\SecurityHealthSystray.exe' -Type ExpandString -Force -ErrorAction SilentlyContinue
Start-Process -FilePath "$env:WINDIR\system32\SecurityHealthSystray.exe" -ErrorAction SilentlyContinue
"""
            self._run_powershell_checked(user_script, timeout=120)
            print("\n\033[92m========================================================\033[0m")
            print("\033[92m[BAŞARILI] WinKit Defender Geri Yükleme Tamamlandı.\033[0m")
            print("\033[92m========================================================\033[0m\n")
            return 0
        except Exception as exc:
            print(f"\n\033[91m[HATA] Geri yükleme testi başarısız: {exc}\033[0m\n")
            return 1

    def run_interactive_menu(self):
        print_cli_banner()
        if not is_admin():
            print("\033[91m[HATA] Bu işlem için Yönetici (Administrator) yetkileri gereklidir.\033[0m")
            return 1

        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            sel_apps_count = sum(1 for v in self.app_vars.values() if v)
            chk_apps = "\033[92m[X]\033[0m" if self.cfg_apps_enabled else "\033[90m[ ]\033[0m"
            chk_shut = "\033[92m[X]\033[0m" if self.cfg_shutup10 else "\033[90m[ ]\033[0m"

            def c(val):
                return "\033[92m[X]\033[0m" if val else "\033[90m[ ]\033[0m"

            if self.cfg_defender:
                def_status = "\033[92m[X] DURDUR - Defender Control Yöntemiyle Anında Durdurulur\033[0m"
            else:
                def_status = "\033[90m[ ] KORUNUYOR - Varsayılan, Değişiklik Yok\033[0m"

            print("=" * 80)
            print("          \033[91m\033[1m[ WinKit CLI - Debloat & Sistem Optimizasyonu ]\033[0m")
            print("=" * 80)
            print("\033[93m[ ANA MODÜLLER ]\033[0m")
            print(f"  [1]  {chk_apps} Windows Uygulamaları Temizliği ({sel_apps_count} Seçili) \033[94m-> [U] Liste\033[0m")
            print(f"  [2]  {chk_shut} O&O ShutUp10 Gizlilik & Telemetri          \033[94m-> [S] Kurallar\033[0m")

            print("\n\033[93m[ GİZLİLİK VE TELEMETRİ ]\033[0m")
            print(f"  [3]  {c(self.cfg_telemetry)} Telemetri ve Tanılama Verilerini Kapat")
            print(f"  [4]  {c(self.cfg_bing_search)} Başlat Menüsü Web Aramalarını ve Bing Önerilerini Engelle")
            print(f"  [5]  {c(self.cfg_consumer_features)} Tüketici Özelliklerini Kapat (Sponsorlu Uygulama & Reklamlar)")
            print(f"  [6]  {c(self.cfg_store_recommend)} Microsoft Store Önerilen Arama Sonuçlarını Kapat")
            print(f"  [7]  {c(self.cfg_location)} Konum Takibini ve İzinlerini Kapat")
            print(f"  [8]  {c(self.cfg_widgets)} Haberler ve İlgi Alanlarını Kaldır (Widgets)")
            print(f"  [9]  {c(self.cfg_delivery_opt)} Teslimat İyileştirmesini Kapat (P2P Bant Genişliği)")

            print("\n\033[93m[ SİSTEM VE KULLANILABİLİRLİK ]\033[0m")
            print(f"  [10] {c(self.cfg_services)} Gereksiz Arka Plan Servislerini Kapat")
            print(f"  [11] {def_status} \033[94m[D] Değiştir\033[0m")
            print(f"  [12] {c(self.cfg_pause_updates_2099)} Windows Güncellemelerini 2099'a Kadar Duraklat")
            print(f"  [13] {c(self.cfg_classic_menu)} Klasik Sağ Tık Menüsünü Geri Getir")
            print(f"  [14] {c(self.cfg_end_task)} Görev Çubuğuna 'Görevi Sonlandır' Ekle")
            print(f"  [15] {c(self.cfg_context_menu_tools)} Sağ Tık Menüsüne 'WinKit Araçları' Ekle (Sahiplik & Zorla Silme)")
            print(f"  [16] {c(self.cfg_extensions)} Dosya Uzantılarını ve Gizli Dosyaları Göster")
            print(f"  [17] {c(self.cfg_bsod)} Detaylı Mavi Ekran (BSOD Hata Ayrıntıları)")
            print(f"  [18] {c(self.cfg_dark)} Windows Karanlık Tema Zorla")
            print(f"  [19] {c(self.cfg_feafd)} Dosya Gezgini Klasör Keşfini Kapat (FEAFD)")
            print(f"  [20] {c(self.cfg_hibernate)} Hazırda Bekletmeyi Kapat (hiberfil.sys)")
            print(f"  [21] {c(self.cfg_remove_bitlocker)} BitLocker Cihaz Şifrelemesini Askıya Al")

            print("\n\033[93m[ OYUN VE PERFORMANS ]\033[0m")
            print(f"  [22] {c(self.cfg_gaming_tweaks)} Oyun Gecikmesi İyileştirmeleri (Multimedya & Ağ Önceliği)")
            print(f"  [23] {c(self.cfg_disable_fso)} Tam Ekran Optimizasyonlarını Kapat (FSO)")
            print(f"  [24] {c(self.cfg_disable_mpo)} Ekran Kartı Katman İyileştirmesi (MPO)")
            print(f"  [25] {c(self.cfg_disable_s0_drain)} Uyku Modunda Ağ Tüketimini Kapat (Modern Standby S0)")
            print(f"  [26] {c(self.cfg_ntp_sync)} Saat Sunucusunu Optimize Et (NTP Sync)")
            print(f"  [27] {c(self.cfg_ultraperf)} Ultra Performans Güç Planını Aktif Et")

            print("-" * 80)
            print("  \033[97m[A] Önerilen Profil\033[0m         \033[97m[T] Tümünü Aç / Kapat\033[0m")
            print("  \033[97m[U] Uygulamaları Düzenle\033[0m    \033[97m[S] ShutUp10 Düzenle\033[0m    \033[91m[D] Defender Durdur/Koru\033[0m")
            print("  \033[92m\033[1m[R / ENTER / BOŞLUK] SEÇİLEN DEBLOAT İŞLEMLERİNİ BAŞLAT\033[0m")
            print("  \033[94m[G] WinKit GUI Arayüzünü Başlat\033[0m    \033[90m[0 / Q / ESC] Çıkış\033[0m")
            print("-" * 80)
            print("  \033[90m(Anında tepki: Numarayı veya kısayol harfini tuşlamanız yeterlidir)\033[0m")

            action = read_menu_action()

            if action in ("0", "q", "exit"):
                break
            elif action == "g":
                return "LAUNCH_GUI"
            elif action == "a":
                self.set_recommended_preset()
            elif action == "t":
                self.toggle_all()
            elif action in ("d", "11"):
                self.toggle_defender()
            elif action == "u":
                self.app_checklist_menu()
            elif action == "s":
                self.shutup_checklist_menu()
            elif action == "RUN":
                # Onay ve Güvenlik Uyarısı
                os.system('cls' if os.name == 'nt' else 'clear')
                print_cli_banner()
                print("\n  \033[93m╔═════════════════════════════════════════════════════════════════════════════╗\033[0m")
                print("  \033[93m║                             ⚠ DİKKAT VE ONAY                                ║\033[0m")
                print("  \033[93m╠═════════════════════════════════════════════════════════════════════════════╣\033[0m")
                print("  \033[97m║  Seçilen Debloat ve Sistem Optimizasyon işlemleri uygulanacaktır.           ║\033[0m")
                print("  \033[97m║  Bu işlem seçili Windows uygulamalarını ve telemetri bileşenlerini temizler.║\033[0m")
                if self.cfg_defender:
                    print("  \033[93m║  UYARI: Windows Defender Defender Control yöntemiyle anında durdurulacaktır. ║\033[0m")
                print("  \033[93m║                                                                             ║\033[0m")
                print("  \033[92m\033[1m║  İşlemleri başlatmak için: [E] (Evet)                                       ║\033[0m")
                print("  \033[90m║  İptal edip menüye dönmek için: [H / ESC / Herhangi bir tuş]                ║\033[0m")
                print("  \033[93m╚═════════════════════════════════════════════════════════════════════════════╝\033[0m\n")

                print("  \033[1mKararınız [E/H]:\033[0m ", end="", flush=True)
                ans = get_instant_key().lower()
                if ans not in ('e', 'y', '\r', '\n'):
                    print(f"{ans} (İptal edildi, menüye dönülüyor...)")
                    import time
                    time.sleep(0.6)
                    continue

                print(f"{ans}\n")
                print("\n\033[92m========================================================\033[0m")
                print("\033[92m[*] WinKit Debloat Motoru Başlatılıyor...\033[0m")
                print("\033[92m========================================================\033[0m")
                try:
                    self._debloat_worker_impl()
                except Exception as exc:
                    print(f"\n\033[91m[KRİTİK HATA] {exc}\033[0m")
                print("\n\033[92m========================================================\033[0m")
                print("\033[92m[BAŞARILI] Debloat ve Sistem Optimizasyonu Tamamlandı.\033[0m")
                print("\033[93mDeğişikliklerin oturması için sistem 30 saniye içinde yeniden başlatılacaktır.\033[0m")
                print("\033[92m========================================================\033[0m\n")
            elif action.isdigit():
                idx = int(action)
                attr_map = {
                    1: "cfg_apps_enabled",
                    2: "cfg_shutup10",
                    3: "cfg_telemetry",
                    4: "cfg_bing_search",
                    5: "cfg_consumer_features",
                    6: "cfg_store_recommend",
                    7: "cfg_location",
                    8: "cfg_widgets",
                    9: "cfg_delivery_opt",
                    10: "cfg_services",
                    11: "cfg_defender",
                    12: "cfg_pause_updates_2099",
                    13: "cfg_classic_menu",
                    14: "cfg_end_task",
                    15: "cfg_context_menu_tools",
                    16: "cfg_extensions",
                    17: "cfg_bsod",
                    18: "cfg_dark",
                    19: "cfg_feafd",
                    20: "cfg_hibernate",
                    21: "cfg_remove_bitlocker",
                    22: "cfg_gaming_tweaks",
                    23: "cfg_disable_fso",
                    24: "cfg_disable_mpo",
                    25: "cfg_disable_s0_drain",
                    26: "cfg_ntp_sync",
                    27: "cfg_ultraperf",
                }
                target_attr = attr_map.get(idx)
                if target_attr:
                    if target_attr == "cfg_defender":
                        self.toggle_defender()
                    else:
                        setattr(self, target_attr, not getattr(self, target_attr, False))
        return 0


def ensure_cli_console():
    """Konsol giriş/çıkışlarını ve UTF-8 ANSI desteğini bağlar."""
    if os.name == "nt":
        kernel32 = ctypes.windll.kernel32
        if kernel32.GetConsoleWindow() == 0:
            if not kernel32.AttachConsole(-1):
                kernel32.AllocConsole()

        try:
            h_out = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
                kernel32.SetConsoleMode(h_out, mode.value | 0x0004 | 0x0001)
            h_in = kernel32.GetStdHandle(-10)
            if kernel32.GetConsoleMode(h_in, ctypes.byref(mode)):
                kernel32.SetConsoleMode(h_in, mode.value | 0x0200)
        except Exception:
            pass

        if sys.stdin is None or not hasattr(sys.stdin, "read"):
            try:
                sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="ignore")
            except Exception:
                try:
                    sys.stdin = open("CONIN$", "r")
                except Exception:
                    pass
        if sys.stdout is None or not hasattr(sys.stdout, "write"):
            try:
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="ignore")
            except Exception:
                try:
                    sys.stdout = open("CONOUT$", "w")
                except Exception:
                    pass
        if sys.stderr is None or not hasattr(sys.stderr, "write"):
            try:
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="ignore")
            except Exception:
                try:
                    sys.stderr = open("CONOUT$", "w")
                except Exception:
                    pass

        try:
            import msvcrt
            os.system("")  # Windows Terminal VT100 init
            for std_fd in (-11, -12):
                h = kernel32.GetStdHandle(std_fd)
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                    kernel32.SetConsoleMode(h, mode.value | 0x0004 | 0x0001)
            if hasattr(sys.stdout, "fileno"):
                h_f = msvcrt.get_osfhandle(sys.stdout.fileno())
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(h_f, ctypes.byref(mode)):
                    kernel32.SetConsoleMode(h_f, mode.value | 0x0004 | 0x0001)
        except Exception:
            pass


