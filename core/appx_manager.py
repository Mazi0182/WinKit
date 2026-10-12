"""
WinKit Core AppX Manager Module
Handles safe, permanent removal of AppX and Provisioned packages.
Ensures CoreAI is nuked while core system components (like CBS COM interfaces) remain stable.
"""

import subprocess
import re
from typing import Callable, Optional, List, Set

CREATE_NO_WINDOW = 0x08000000

# Critical core packages that should NEVER be removed
PROTECTED_CORE_PACKAGES = {
    "microsoftwindows.client.core",
    "microsoft.windows.shellexperiencehost",
    "microsoft.windows.startmenuexperiencehost",
    "microsoft.windows.search",
    "microsoft.windowsappruntime",
    "microsoft.windowsstore",
    "microsoft.ui.xaml",
    "microsoft.vclibs",
    "microsoft.net.native.framework",
    "microsoft.net.native.runtime",
    "microsoft.directx.direct3d12",
}

class AppxManager:
    """
    Manages AppX package enumeration and clean, non-resurrecting removal.
    """
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback

    def log(self, text: str, color: str = "#00FF9D"):
        if self.log_callback:
            self.log_callback(text, color)

    def remove_packages(self, package_names_or_ids: List[str]) -> List[str]:
        """
        Permanently removes both user-installed and provisioned AppX packages.
        Returns the list of successfully removed package names.
        """
        self.log("[*] AppX paket temizliği başlatılıyor...", "#00E5FF")

        targets_to_remove: List[str] = []
        for pkg in package_names_or_ids:
            clean_pkg = str(pkg).strip()
            if not clean_pkg:
                continue
            if clean_pkg.lower() in PROTECTED_CORE_PACKAGES:
                self.log(f"[!] Korunan sistem paketi atlandı: {clean_pkg}", "#FFB86C")
                continue
            targets_to_remove.append(clean_pkg)

        if not targets_to_remove:
            self.log("[!] Silinecek AppX paketi seçilmedi.", "#FFB86C")
            return []

        removed_successfully: List[str] = []

        for target in targets_to_remove:
            self.log(f"[-] Paket kaldırılıyor: {target}", "#00E5FF")
            # 1. Remove Provisioned Package (Prevents reinstallation for new users)
            ps_provisioned = rf"""
$ErrorActionPreference = 'SilentlyContinue'
Get-AppxProvisionedPackage -Online | Where-Object {{
    $_.DisplayName -like '*{target}*' -or $_.PackageName -like '*{target}*'
}} | ForEach-Object {{
    Remove-AppxProvisionedPackage -Online -PackageName $_.PackageName -ErrorAction SilentlyContinue | Out-Null
}}
"""
            try:
                subprocess.run(
                    ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_provisioned],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                    timeout=25,
                )
            except Exception:
                pass

            # 2. Remove Installed Package for All Users
            ps_installed = rf"""
$ErrorActionPreference = 'SilentlyContinue'
Get-AppxPackage -AllUsers | Where-Object {{
    $_.Name -like '*{target}*' -or $_.PackageFullName -like '*{target}*'
}} | ForEach-Object {{
    Remove-AppxPackage -AllUsers -Package $_.PackageFullName -ErrorAction SilentlyContinue | Out-Null
}}
"""
            try:
                res = subprocess.run(
                    ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_installed],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                    timeout=30,
                )
                if res.returncode == 0:
                    removed_successfully.append(target)
                    self.log(f"[+] Başarıyla kaldırıldı: {target}", "#00FF9D")
                else:
                    self.log(f"[!] Kaldırma uyarısı ({target})", "#FFB86C")
            except Exception as e:
                self.log(f"[!] Kaldırma hatası ({target}): {e}", "#FF6B6B")

        self.log(f"[OK] AppX aşaması bitti: {len(removed_successfully)} paket temizlendi.", "#00FF9D")
        return removed_successfully
