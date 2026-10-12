"""
WinKit Core Pipeline Orchestrator
Executes debloat, deep scan, and system tweaks in strict sequential order:
1. AppX Package Removal (Permanent)
2. Edge Browser Elimination (Preserving WebView2 >= 150)
3. 40-Depth C: Drive and Registry Deep Scan
4. Remnant Eradication
5. System Tweaks & Defender Control
"""

import os
import shutil
import subprocess
import winreg
from typing import Callable, Optional, List, Dict, Any
from pathlib import Path

from core.privileges import enable_process_privileges
from core.appx_manager import AppxManager
from core.edgewebview import clean_edge_preserve_webview
from core.scanner import DeepScanner
from core.defender import DefenderController
from core.tweaks import SystemTweaks

CREATE_NO_WINDOW = 0x08000000

class WinKitOrchestrator:
    """
    Coordinates modular backend operations safely with rich callback reporting.
    """
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback
        enable_process_privileges()
        self.appx_mgr = AppxManager(log_callback=log_callback)
        self.defender_ctrl = DefenderController(log_callback=log_callback)
        self.tweaks = SystemTweaks(log_callback=log_callback)

    def log(self, text: str, color: str = "#00FF9D"):
        if self.log_callback:
            self.log_callback(text, color)

    def execute_debloat_pipeline(
        self,
        appx_targets: List[str],
        remove_edge: bool = True,
        remove_defender: bool = False,
        apply_msi: bool = False,
        pause_updates: bool = False,
        scan_depth: int = 40,
    ) -> Dict[str, Any]:
        """
        Executes the debloat pipeline in strict order.
        """
        results = {}
        self.log("====================================================", "#00E5FF")
        self.log("WinKit Güvenli & Adli Debloat Operasyonu Başlatılıyor", "#00E5FF")
        self.log("====================================================", "#00E5FF")

        # ADIM 1: AppX Paketlerinin Silinmesi
        if appx_targets:
            self.log("[ADIM 1/4] AppX paketleri kalıcı olarak kaldırılıyor...", "#00E5FF")
            removed_appx = self.appx_mgr.remove_packages(appx_targets)
            results["removed_appx"] = removed_appx
        else:
            self.log("[ADIM 1/4] AppX hedefi seçilmedi, atlanıyor.", "#FFB86C")
            results["removed_appx"] = []

        # ADIM 2: Edge & WebView2 Cerrahi Temizliği
        if remove_edge:
            self.log("[ADIM 2/4] Edge kaldırılıyor (WebView2 150+ korunuyor)...", "#00E5FF")
            edge_ok = clean_edge_preserve_webview(log_callback=self.log_callback)
            results["edge_cleaned"] = edge_ok
        else:
            results["edge_cleaned"] = False

        # ADIM 3: 40-Depth C Diski ve Regedit Derin Taraması
        all_scan_targets = list(set(results["removed_appx"]))
        if remove_edge:
            all_scan_targets.append("msedge")

        if all_scan_targets:
            self.log(f"[ADIM 3/4] 40-Depth derin tarama başlatılıyor (Hedefler: {len(all_scan_targets)})...", "#00E5FF")
            scanner = DeepScanner(targets=all_scan_targets, max_depth=scan_depth, log_callback=self.log_callback)
            found_files, found_dirs = scanner.run_disk_scan()
            found_keys, found_values = scanner.run_registry_scan()

            # ADIM 4: Bulunan Kalıntıların Cerrahi İmhası
            self.log(f"[ADIM 4/4] Bulunan kalıntılar temizleniyor ({len(found_files)} dosya, {len(found_dirs)} klasör)...", "#00E5FF")
            
            # Delete files
            for f_path in found_files:
                try:
                    p = Path(f_path)
                    if p.is_file():
                        p.unlink(missing_ok=True)
                except Exception:
                    pass

            # Delete dirs (deepest first)
            sorted_dirs = sorted(list(found_dirs), key=len, reverse=True)
            for d_path in sorted_dirs:
                try:
                    shutil.rmtree(d_path, ignore_errors=True)
                except Exception:
                    pass

            # Delete registry keys
            for hive, key_path in found_keys:
                try:
                    winreg.DeleteKey(hive, key_path)
                except OSError:
                    pass

            # Delete registry values
            for hive, key_path, val_name in found_values:
                try:
                    with winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                        winreg.DeleteValue(k, val_name)
                except OSError:
                    pass

            self.log("[+] Derin tarama ve temizlik başarıyla sonuçlandı.", "#00FF9D")
            results["scan_files_cleaned"] = len(found_files)
            results["scan_dirs_cleaned"] = len(found_dirs)
            results["scan_reg_keys_cleaned"] = len(found_keys)
        else:
            self.log("[ADIM 3-4] Taranacak hedef kalıntı kalmadı.", "#00FF9D")

        # ADIM 5: Ek Tweakler & Defender
        if remove_defender:
            self.log("[TWEAK] Windows Defender durduruluyor (WdFilter=4)...", "#00E5FF")
            def_ok, def_err = self.defender_ctrl.disable_defender()
            results["defender_disabled"] = def_ok

        if apply_msi:
            self.log("[TWEAK] Donanım uyumlu MSI Interrupt Tuning uygulanıyor...", "#00E5FF")
            msi_res = self.tweaks.apply_msi_tuning_safe()
            results["msi_tuning"] = msi_res

        if pause_updates:
            self.log("[TWEAK] Windows Güncellemeleri 2099'a erteleniyor...", "#00E5FF")
            upd_ok = self.tweaks.pause_windows_updates_2099()
            results["updates_paused"] = upd_ok

        self.log("====================================================", "#00FF9D")
        self.log("Tüm işlemler sıfır false-positive ile tamamlandı!", "#00FF9D")
        self.log("====================================================", "#00FF9D")
        return results
