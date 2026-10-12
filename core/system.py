"""
WinKit - Core System Helpers & Diagnostics
Path utilities, runtime diagnostic logging, Start menu layout inspection,
pending file delete scheduling, and policy repair routines.
"""

import os
import sys
import time
import json
import base64
import ctypes
import shutil
import tempfile
import subprocess
import winreg
from pathlib import Path
from core.constants import CREATE_NO_WINDOW
from core.privileges import run_powershell_as_system


def is_admin() -> bool:
    """Returns True if the current process has administrative privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def deploy_winkit_silent():
    """Eski IFEO kalıntısı olan winkit_silent.exe dosyasını diske yazmaz, varsa temizler."""
    for target_dir in (
        os.environ.get("WINDIR", r"C:\Windows") + r"\System32",
        os.environ.get("WINDIR", r"C:\Windows"),
    ):
        target_path = Path(target_dir) / "winkit_silent.exe"
        try:
            if target_path.exists():
                target_path.unlink(missing_ok=True)
        except Exception:
            pass


def _powershell_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _normalized_path(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def _same_path(first, second):
    try:
        return _normalized_path(first) == _normalized_path(second)
    except (TypeError, ValueError, OSError):
        return False


def get_winkit_data_directory() -> Path:
    r"""WinKit log ve yapılandırma verileri için C:\ProgramData\WinKit dizinini döndürür."""
    try:
        p = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "WinKit"
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        return Path(r"C:\ProgramData\WinKit")


def get_documents_directory() -> Path:
    """Yönlendirilmiş/OneDrive Belgeler klasörü dâhil Windows bilinen yolunu döndürür."""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        # CSIDL_PERSONAL (5): kullanıcının gerçek Belgeler bilinen klasörü.
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer)
        if result == 0 and buffer.value:
            return Path(buffer.value)
    except Exception:
        pass
    return Path.home() / "Documents"


def append_runtime_diagnostic(message: str):
    r"""Kullanıcı konsoluna sızmaması gereken düşük seviye hata ayrıntısını C:\ProgramData\WinKit altına kaydet."""
    try:
        data_dir = get_winkit_data_directory()
        log_path = data_dir / "winkit_runtime_diagnostics.txt"
        with log_path.open("a", encoding="utf-8", newline="\n") as log_file:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_file.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def capture_filtered_start_pins_json(
    remove_package_ids=None,
    remove_edge=False,
    remove_onedrive=False,
    timeout=45,
):
    """Mevcut Start pinlerini, sponsorları ve seçili kaldırma hedeflerini süzerek yakala."""
    import re
    safe_remove_ids = []
    for raw_package_id in remove_package_ids or ():
        package_id = str(raw_package_id or "").strip()
        if package_id.casefold() == "microsoft.crossdevice":
            package_id = "MicrosoftWindows.CrossDevice"
        if re.fullmatch(r"[A-Za-z0-9._-]{2,120}", package_id):
            safe_remove_ids.append(package_id.casefold())
    quoted_remove_ids = ", ".join(
        "'" + package_id.replace("'", "''") + "'"
        for package_id in dict.fromkeys(safe_remove_ids)
    )
    script = r"""
$ErrorActionPreference = 'Stop'
$removePackageTokens = @(__WINKIT_REMOVE_PACKAGE_IDS__)
$removeEdge = __WINKIT_REMOVE_EDGE__
$removeOneDrive = __WINKIT_REMOVE_ONEDRIVE__
$layoutPath = Join-Path $env:TEMP ("winkit_start_capture_" + [guid]::NewGuid().ToString('N') + '.json')
try {
    Export-StartLayout -Path $layoutPath -ErrorAction Stop
    $layout = Get-Content -LiteralPath $layoutPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $originalPins = @($layout.pinnedList)
    if ($originalPins.Count -eq 0) { return }

    $sponsoredKeywords = @(
        'WhatsApp', 'WhatsAppDesktop', 'LinkedIn', 'Spotify', 'TikTok', 'Disney', 'DisneyPlus',
        'Facebook', 'Instagram', 'PrimeVideo', 'AmazonPrime', 'Netflix', 'Clipchamp', 'OfficeHub',
        'BingNews', 'BingWeather', 'Xbox', 'Solitaire', 'Cortana', 'Messenger', 'Twitter',
        'Adobe', 'AdobeCreativeCloud', 'Canva', 'Pinterest', 'Grammarly', 'Evernote', 'Duolingo',
        'Kindle', 'Booking', 'CandyCrush', 'Roblox', 'Asphalt', 'Pandora', 'Hulu', 'ESPN',
        'AdobeExpress', 'Outlook', 'Teams', 'YourPhone', 'PhoneLink', 'DevHome', 'Copilot'
    )
    $installed = @(Get-StartApps -ErrorAction SilentlyContinue)
    $installedIds = @($installed | ForEach-Object { ([string]$_.AppID).ToLowerInvariant() })
    $installedText = (($installed | ForEach-Object { "$($_.Name)|$($_.AppID)" }) -join "`n").ToLowerInvariant()
    $packageText = ((Get-AppxPackage -AllUsers -ErrorAction SilentlyContinue | ForEach-Object {
        "$($_.Name)|$($_.PackageFamilyName)|$($_.PackageFullName)"
    }) -join "`n").ToLowerInvariant()
    $cleanPins = @()
    foreach ($pin in $originalPins) {
        $pinJson = $pin | ConvertTo-Json -Compress -Depth 8
        $pinJsonLower = $pinJson.ToLowerInvariant()
        $isSelectedForRemoval = $false
        foreach ($packageToken in $removePackageTokens) {
            if ($packageToken -and $pinJsonLower -like "*$packageToken*") {
                $isSelectedForRemoval = $true
                break
            }
        }
        if (-not $isSelectedForRemoval -and $removeEdge) {
            $isSelectedForRemoval = (
                $pinJsonLower -match 'microsoftedge|msedge|microsoft edge' -or
                $pinJsonLower -match 'microsoft[\\/]edge'
            )
        }
        if (-not $isSelectedForRemoval -and $removeOneDrive) {
            $isSelectedForRemoval = (
                $pinJsonLower -match 'onedrive|skydrive' -or
                $pinJsonLower -match 'microsoft[\\/]onedrive'
            )
        }
        if ($isSelectedForRemoval) { continue }

        $isSponsored = $false
        foreach ($keyword in $sponsoredKeywords) {
            if ($pinJsonLower -like "*$($keyword.ToLowerInvariant())*") {
                $isSponsored = $true
                break
            }
        }
        if ($isSponsored) { continue }

        $rawTarget = [string]($pin.packagedAppId ?? $pin.desktopAppId ?? $pin.desktopAppLink ?? '')
        if ([string]::IsNullOrWhiteSpace($rawTarget)) { continue }

        $cleanPins += $pin
    }
    [ordered]@{ pinnedList = $cleanPins } | ConvertTo-Json -Depth 8
} finally {
    if (Test-Path -LiteralPath $layoutPath) {
        Remove-Item -LiteralPath $layoutPath -Force -ErrorAction SilentlyContinue
    }
}
""".replace(
        "__WINKIT_REMOVE_PACKAGE_IDS__", quoted_remove_ids
    ).replace(
        "__WINKIT_REMOVE_EDGE__", "$true" if remove_edge else "$false"
    ).replace(
        "__WINKIT_REMOVE_ONEDRIVE__", "$true" if remove_onedrive else "$false"
    )

    try:
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=CREATE_NO_WINDOW,
            timeout=timeout,
            check=False,
        )
        stdout = (proc.stdout or "").strip()
        if proc.returncode == 0 and stdout.startswith("{") and stdout.endswith("}"):
            json.loads(stdout)
            return stdout
    except Exception as exc:
        append_runtime_diagnostic(f"Start layout capture exception: {exc}")
    return None


def schedule_system_path_cleanup_on_boot(paths, task_prefix="WinKit_BootCleanup"):
    """Kilitli hedefleri Windows NT kernel seviyesinde (PendingFileRenameOperations) açılışta sil."""
    normalized_paths = []
    seen = set()
    for raw_path in paths or ():
        path_text = os.path.normpath(os.path.expandvars(str(raw_path or "").strip()))
        if not path_text or path_text.casefold() in seen:
            continue
        seen.add(path_text.casefold())
        normalized_paths.append(path_text)

    # Eski ONSTART zamanlanmış görevlerini temizle
    try:
        q_res = subprocess.run(
            ["schtasks.exe", "/query", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=CREATE_NO_WINDOW,
            timeout=10,
            check=False,
        )
        if q_res.returncode == 0:
            for line in q_res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip().strip('"') for p in line.split('","')]
                if parts:
                    t_name = parts[0].lstrip('\\')
                    if "WinKit_BootCleanup" in t_name or "WinKit_DefenderCleanup" in t_name:
                        subprocess.run(
                            ["schtasks.exe", "/delete", "/tn", t_name, "/f"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW,
                            timeout=8,
                            check=False,
                        )
    except Exception:
        pass

    # BootCleanup klasörünü temizle
    cleanup_dir = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "WinKit" / "BootCleanup"
    if cleanup_dir.exists():
        shutil.rmtree(str(cleanup_dir), ignore_errors=True)

    if not normalized_paths:
        return True, ""

    paths_json = json.dumps(normalized_paths, ensure_ascii=False)
    b64_paths = base64.b64encode(paths_json.encode("utf-8")).decode("ascii")
    ps_code = rf"""
$pathsJson = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64_paths}'))
$paths = ConvertFrom-Json $pathsJson
Add-Type -ErrorAction SilentlyContinue -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class WinKitPendingDel {{
    [DllImport("ntdll.dll")]
    public static extern int RtlAdjustPrivilege(int privilege, bool enable, bool currentThread, out bool enabled);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool MoveFileEx(string existingFile, string newFile, int flags);
    public static void EnablePrivileges() {{
        bool en;
        RtlAdjustPrivilege(9, true, false, out en);
        RtlAdjustPrivilege(17, true, false, out en);
        RtlAdjustPrivilege(18, true, false, out en);
    }}
}}
'@
[WinKitPendingDel]::EnablePrivileges()

foreach ($path in $paths) {{
    if (-not (Test-Path -LiteralPath $path)) {{ continue }}
    $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    if ($item -and $item.PSIsContainer) {{
        $children = @(
            Get-ChildItem -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue |
                Sort-Object {{ $_.FullName.Length }} -Descending
        )
        foreach ($c in $children) {{
            [WinKitPendingDel]::MoveFileEx($c.FullName, $null, 4) | Out-Null
        }}
        [WinKitPendingDel]::MoveFileEx([string]$path, $null, 4) | Out-Null
    }} else {{
        [WinKitPendingDel]::MoveFileEx([string]$path, $null, 4) | Out-Null
    }}
}}
"""
    res_ok, res_err = run_powershell_as_system(ps_code, timeout=40)
    if not res_ok:
        try:
            kernel32 = ctypes.windll.kernel32
            for p in normalized_paths:
                if os.path.isdir(p):
                    for root, dirs, files in os.walk(p, topdown=False):
                        for f in files:
                            kernel32.MoveFileExW(os.path.join(root, f), None, 4)
                        for d in dirs:
                            kernel32.MoveFileExW(os.path.join(root, d), None, 4)
                kernel32.MoveFileExW(p, None, 4)
        except Exception:
            pass
    return True, "Kernel seviyesinde işaretlendi"


def repair_stale_start_pin_policy():
    """Eski WinKit sürümlerinden kalan ve Start hostunu kilitleyen politikayı temizle."""
    policy_path = r"Software\Policies\Microsoft\Windows\Explorer"
    removed = False
    for root_hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(
                root_hive,
                policy_path,
                0,
                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
            ) as policy_key:
                for value_name in ("ConfigureStartPinsJSON", "ConfigureStartPins"):
                    try:
                        winreg.DeleteValue(policy_key, value_name)
                        removed = True
                    except FileNotFoundError:
                        pass
        except OSError:
            pass
    if removed:
        try:
            layout_dir = (
                Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
                / "WinKit"
                / "StartLayout"
            )
            for filename in ("CleanStartPins.json", "VerifyStartPins.json"):
                try:
                    (layout_dir / filename).unlink()
                except OSError:
                    pass
        except OSError:
            pass
        try:
            subprocess.run(
                ["gpupdate.exe", "/target:user", "/force"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                timeout=45,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    return removed
