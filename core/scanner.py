"""
WinKit Core Deep Scanner Module
Provides high-performance, multi-threaded 40-depth filesystem and registry scanning
with strict loop/junction protection and zero false-positive isolation.
"""

import os
import sys
import re
import winreg
import concurrent.futures
from pathlib import Path
from typing import Callable, Optional, Set, List, Dict, Any

# Windows attribute constant for Reparse Points (Junctions, Symlinks, Mount Points)
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400

# Critical system entities that must NEVER be touched under any condition
CRITICAL_WHITELIST_TOKENS = {
    "notepad",
    "calc",
    "calculator",
    "mspaint",
    "explorer",
    "shellexperiencehost",
    "startmenuexperiencehost",
    "systemsettings",
    "windowsstore",
    "windowsterminal",
    "cmd",
    "powershell",
    "ntoskrnl",
    "winlogon",
    "csrss",
    "svchost",
    "services",
    "lsass",
    "taskmgr",
    "regedit",
}

def is_reparse_point_or_symlink(entry: os.DirEntry) -> bool:
    """Detect if directory entry is a Junction, Symlink or Reparse Point to avoid infinite loops."""
    try:
        if entry.is_symlink():
            return True
        stat_res = entry.stat(follow_symlinks=False)
        attrs = getattr(stat_res, "st_file_attributes", 0)
        if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
            return True
    except Exception:
        return True
    return False

class DeepScanner:
    """
    Advanced multi-threaded scanner for C: drive and Registry up to 40 depth.
    """
    def __init__(
        self,
        targets: List[str],
        max_depth: int = 40,
        log_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.raw_targets = targets
        self.max_depth = max_depth
        self.log_callback = log_callback
        
        # Build clean target tokens (lowercased)
        self.target_tokens: Set[str] = set()
        for t in targets:
            token = str(t).strip().lower()
            if len(token) >= 3 and token not in CRITICAL_WHITELIST_TOKENS:
                self.target_tokens.add(token)

        self.found_files: Set[str] = set()
        self.found_directories: Set[str] = set()
        self.found_reg_keys: List[tuple[int, str]] = []
        self.found_reg_values: List[tuple[int, str, str]] = []

    def log(self, text: str, color: str = "#00FF9D"):
        if self.log_callback:
            self.log_callback(text, color)

    def is_match(self, name: str) -> bool:
        """Strict matching against target tokens with whitelist defense."""
        low = name.lower()
        # Never match if whitelisted token is part of identity
        for wl in CRITICAL_WHITELIST_TOKENS:
            if wl in low:
                return False
                
        for token in self.target_tokens:
            # Word boundary or exact/package-style match
            pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
            if re.search(pattern, low):
                return True
        return False

    def scan_directory_tree(self, root_path: str, current_depth: int = 0, visited: Optional[Set[str]] = None) -> tuple[Set[str], Set[str]]:
        """
        Recursively scan a directory tree up to max_depth (40).
        Protects against Junction/Symlink infinite loops with follow_symlinks=False.
        """
        if visited is None:
            visited = set()

        local_files = set()
        local_dirs = set()

        if current_depth > self.max_depth:
            return local_files, local_dirs

        norm_root = os.path.normcase(os.path.abspath(root_path))
        if norm_root in visited:
            return local_files, local_dirs
        visited.add(norm_root)

        try:
            with os.scandir(root_path) as it:
                for entry in it:
                    try:
                        # CRITICAL: Prevent junction loop trap
                        if is_reparse_point_or_symlink(entry):
                            continue

                        if entry.is_file(follow_symlinks=False):
                            if self.is_match(entry.name):
                                local_files.add(entry.path)
                        elif entry.is_dir(follow_symlinks=False):
                            if self.is_match(entry.name):
                                local_dirs.add(entry.path)
                            # Recurse deeper into child directory
                            sub_f, sub_d = self.scan_directory_tree(entry.path, current_depth + 1, visited)
                            local_files.update(sub_f)
                            local_dirs.update(sub_d)
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass

        return local_files, local_dirs

    def run_disk_scan(self, search_roots: Optional[List[str]] = None) -> tuple[Set[str], Set[str]]:
        """
        Multi-threaded root disk scanning up to 40 depth.
        """
        if not search_roots:
            system_drive = os.environ.get("SystemDrive", "C:") + "\\"
            search_roots = [
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                os.environ.get("ProgramData", r"C:\ProgramData"),
                os.path.join(system_drive, "Users"),
                os.path.join(system_drive, "Windows", "SystemApps"),
                os.path.join(system_drive, "Windows", "Temp"),
            ]

        self.log(f"[*] 40-Depth C Diski derin taraması başlatılıyor ({len(search_roots)} ana kök)...", "#00E5FF")

        # Use ThreadPoolExecutor for multi-core fast traversal
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as executor:
            future_to_root = {
                executor.submit(self.scan_directory_tree, root, 0, set()): root
                for root in search_roots if os.path.exists(root)
            }
            for future in concurrent.futures.as_completed(future_to_root):
                root_name = future_to_root[future]
                try:
                    f_set, d_set = future.result()
                    self.found_files.update(f_set)
                    self.found_directories.update(d_set)
                    self.log(f"[+] {root_name} tarandı: {len(f_set)} dosya, {len(d_set)} klasör bulundu.", "#00FF9D")
                except Exception as exc:
                    self.log(f"[!] {root_name} tarama hatası: {exc}", "#FF6B6B")

        self.log(f"[OK] Disk taraması tamamlandı: Toplam {len(self.found_files)} dosya, {len(self.found_directories)} klasör.", "#00FF9D")
        return self.found_files, self.found_directories

    def scan_registry_branch(self, hive: int, subkey: str, depth: int = 0) -> None:
        """
        Recursively scan a registry subkey up to max_depth.
        Matches keys and values strictly without touching whitelisted or shared COM interfaces.
        """
        if depth > self.max_depth:
            return

        try:
            with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                num_subkeys, num_values, _ = winreg.QueryInfoKey(k)
                
                # Check values
                for i in range(num_values):
                    try:
                        v_name, v_data, _ = winreg.EnumValue(k, i)
                        # Check value name or data match
                        str_data = str(v_data)
                        if self.is_match(v_name) or self.is_match(str_data):
                            self.found_reg_values.append((hive, subkey, v_name))
                    except OSError:
                        continue

                # Recurse subkeys
                for j in range(num_subkeys):
                    try:
                        sub_name = winreg.EnumKey(k, j)
                        full_sub = f"{subkey}\\{sub_name}" if subkey else sub_name
                        if self.is_match(sub_name):
                            self.found_reg_keys.append((hive, full_sub))
                        self.scan_registry_branch(hive, full_sub, depth + 1)
                    except OSError:
                        continue
        except OSError:
            pass

    def run_registry_scan(self) -> tuple[List[tuple[int, str]], List[tuple[int, str, str]]]:
        """
        Scan targeted Registry branches for leftover references.
        Avoids shared core trees to prevent E_NOINTERFACE or Notepad breakage.
        """
        self.log("[*] Derin Regedit taraması başlatılıyor (Sıfır False-Positive güvencesi)...", "#00E5FF")

        target_roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes\AppUserModelId"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_CURRENT_USER, r"Software\Classes\AppUserModelId"),
        ]

        for hive, root in target_roots:
            self.scan_registry_branch(hive, root, depth=0)

        self.log(f"[OK] Regedit taraması tamamlandı: {len(self.found_reg_keys)} anahtar, {len(self.found_reg_values)} değer bulundu.", "#00FF9D")
        return self.found_reg_keys, self.found_reg_values


def safe_scan_directory(target_path, tokens, max_depth=40, log_callback=None):
    scanner = DeepScanner(tokens=tokens, max_depth=max_depth, log_callback=log_callback)
    return scanner.scan_filesystem_tree(Path(target_path))

