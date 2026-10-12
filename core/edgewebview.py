"""
WinKit Core Edge & WebView2 Module
Implements surgical Edge browser cleanup while strictly preserving the WebView2 runtime.

Rules:
- Program Files (x86)\\Microsoft\\EdgeWebView\\Application:
  - WebView2 runtime is strictly PRESERVED as-is.
- All other directories in Program Files (x86)\\Microsoft (Edge, EdgeCore, EdgeUpdate, etc.) are DELETED.
- Program Files\\Microsoft Edge directories are DELETED (EdgeWebView preserved if present).
- User AppData Edge directories are DELETED.
- Edge browser shortcuts, file associations (.htm, .html, .pdf, .svg), and ARP uninstall entries are cleaned without touching WebView2 runtime registration.
"""

import os
import re
import shutil
import subprocess
import winreg
from pathlib import Path
from typing import Callable, Optional
from core.privileges import run_powershell_as_trustedinstaller, run_powershell_as_system

CREATE_NO_WINDOW = 0x08000000

def _force_delete_path(path: Path) -> bool:
    """Force remove file or directory using takeown and icacls if needed."""
    if not path.exists():
        return True
    try:
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
            return True
        elif path.is_dir():
            shutil.rmtree(str(path), ignore_errors=True)
            if not path.exists():
                return True
    except Exception:
        pass

    # Windows permission override
    try:
        subprocess.run(["takeown.exe", "/f", str(path), "/a", "/r", "/d", "y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=10)
        subprocess.run(["icacls.exe", str(path), "/inheritance:e", "/grant:r", "*S-1-5-32-544:(OI)(CI)F", "/t", "/c", "/q"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=10)
        subprocess.run(["cmd.exe", "/d", "/c", f'rd /s /q "{path}"'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=10)
    except Exception:
        pass
    return not path.exists()

def clean_edge_preserve_webview(log_callback: Optional[Callable[[str, str], None]] = None) -> bool:
    """
    Executes precise cleanup of Microsoft Edge browser while strictly retaining WebView2 runtime.
    """
    def log(msg: str, color: str = "#00FF9D"):
        if log_callback:
            log_callback(msg, color)

    log("[*] Edge ve WebView2 cerrahi temizliği başlatılıyor...", "#00E5FF")

    # 1. Stop all Edge and WebView2 processes that lock Edge files
    edge_procs = [
        "msedge.exe", "MicrosoftEdgeUpdate.exe", "identity_helper.exe",
        "pwahelper.exe", "msedgewebview2.exe", "widgets.exe"
    ]
    for proc in edge_procs:
        try:
            subprocess.run(["taskkill.exe", "/f", "/im", proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=5)
        except Exception:
            pass

    # 2. Stop and delete EdgeUpdate services
    for svc in ["edgeupdate", "edgeupdatem", "MicrosoftEdgeElevationService"]:
        try:
            subprocess.run(["sc.exe", "stop", svc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=5)
            subprocess.run(["sc.exe", "delete", svc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=5)
        except Exception:
            pass

    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    users_dir = Path(os.environ.get("SystemDrive", "C:") + r"\Users")

    # 3. WebView2 Runtime klasörünü koru (Sürüm kontrolü / < 150 mantığı kaldırıldı)
    # Target: Program Files (x86)\Microsoft\EdgeWebView\Application
    ewv_app_dir = program_files_x86 / "Microsoft" / "EdgeWebView" / "Application"
    if ewv_app_dir.is_dir():
        for entry in ewv_app_dir.iterdir():
            if entry.is_dir():
                if entry.name.lower() in ["installer", "setup"]:
                    _force_delete_path(entry)
                else:
                    log(f"[+] WebView2 runtime korundu: {entry.name}", "#00FF9D")

    # 4. Clean everything in Program Files (x86)\Microsoft and Program Files\Microsoft except EdgeWebView
    for base_ms in [program_files_x86 / "Microsoft", program_files / "Microsoft"]:
        if base_ms.is_dir():
            for child in base_ms.iterdir():
                if child.is_dir() and child.name.lower() != "edgewebview":
                    log(f"[-] Microsoft artık klasörü siliniyor: {child.name}", "#FFB86C")
                    _force_delete_path(child)

    # 5. Clean ProgramData Edge / EdgeUpdate
    for pd_target in [
        program_data / "Microsoft" / "EdgeUpdate",
        program_data / "Microsoft" / "Edge",
        program_data / "Microsoft" / "EdgeCore",
    ]:
        if pd_target.exists():
            _force_delete_path(pd_target)

    # 6. Clean User AppData Edge directories
    if users_dir.is_dir():
        for u in users_dir.iterdir():
            if u.is_dir() and not u.name.lower() in ["public", "default", "default user", "all users"]:
                for sub in [
                    u / "AppData" / "Local" / "Microsoft" / "Edge",
                    u / "AppData" / "Local" / "Microsoft" / "EdgeCore",
                    u / "AppData" / "Local" / "Microsoft" / "EdgeUpdate",
                ]:
                    if sub.exists():
                        _force_delete_path(sub)

    # 7. Clean Edge shortcuts from Desktop, Start Menu, and Startup
    edge_shortcuts = ["Microsoft Edge.lnk", "Edge.lnk", "MSEdge.lnk"]
    shortcut_dirs = [
        users_dir / "Public" / "Desktop",
        program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
    ]
    if users_dir.is_dir():
        for u in users_dir.iterdir():
            if u.is_dir():
                shortcut_dirs.extend([
                    u / "Desktop",
                    u / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs",
                    u / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
                ])

    for s_dir in shortcut_dirs:
        if s_dir.is_dir():
            for sc in edge_shortcuts:
                sc_path = s_dir / sc
                if sc_path.exists():
                    _force_delete_path(sc_path)

    # 8. Clean Startup / Run registry entries for msedge
    for hive, sub_k in [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    ]:
        try:
            with winreg.OpenKey(hive, sub_k, 0, winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY) as k:
                num_vals = winreg.QueryInfoKey(k)[1]
                vals_to_del = []
                for vi in range(num_vals):
                    vn, vd, _ = winreg.EnumValue(k, vi)
                    if any(edge_tok in vn.lower() or (isinstance(vd, str) and edge_tok in vd.lower()) for edge_tok in ["msedge", "edge", "edgeupdate"]):
                        vals_to_del.append(vn)
                for vn in vals_to_del:
                    winreg.DeleteValue(k, vn)
        except OSError:
            pass

    # 9. Clean Edge Browser Registry App Paths & StartMenuInternet
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for path_k in (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            r"SOFTWARE\Clients\StartMenuInternet\Microsoft Edge",
            r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet\Microsoft Edge",
        ):
            try:
                winreg.DeleteKey(hive, path_k)
            except OSError:
                pass

    # 10. Clean ARP uninstall keys for Edge Browser only (GUID {56EB18F8-B008-4CBD-B6D2-8C97FE7E9062})
    edge_stable_guid = "{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}"
    for uninstall_root in (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, uninstall_root, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as root_k:
                num_subs = winreg.QueryInfoKey(root_k)[0]
                for i in range(num_subs):
                    sub_name = winreg.EnumKey(root_k, i)
                    if edge_stable_guid.lower() in sub_name.lower():
                        try:
                            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, f"{uninstall_root}\\{sub_name}")
                        except OSError:
                            pass
        except OSError:
            pass

    # 11. HIDE WebView2 from Windows Settings -> Installed Apps (SystemComponent = 1)
    for u_path in (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Microsoft EdgeWebView",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Microsoft EdgeWebView",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Microsoft Edge WebView2 Runtime",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Microsoft Edge WebView2 Runtime",
    ):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, u_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                winreg.SetValueEx(k, "SystemComponent", 0, winreg.REG_DWORD, 1)
        except OSError:
            pass

    # 12. Varsayılan Uygulamalar (Default Apps) ve dosya ilişkilendirmelerindeki hayalet Edge kayıtlarını temizle
    clean_edge_associations(log_callback=log_callback)

    log("[+] Edge temizliği tamamlandı; WebView2 runtime güvenceye alındı.", "#00FF9D")
    return True

def clean_edge_associations(log_callback: Optional[Callable[[str, str], None]] = None) -> bool:
    """
    Kullanıcı Seçimi Koruma Sürücüsü'nü (UCPD) devre dışı bırakır,
    HKCU ve tüm kullanıcı SID'leri (HKU S-1-5-21-*) altındaki .htm, .html, .pdf, .svg
    UserChoice izin kilitlerini (DACL) kaldırarak hayalet Microsoft Edge ilişkilendirmelerini siler.
    """
    def log(msg: str, color: str = "#00FF9D"):
        if log_callback:
            log_callback(msg, color)

    log("[*] Varsayılan uygulamalardaki hayalet Edge ilişkilendirmeleri temizleniyor...", "#00E5FF")

    ps_script = r"""
$ErrorActionPreference = 'SilentlyContinue'

if (-not (Get-PSDrive -Name HKCR -ErrorAction SilentlyContinue)) {
    New-PSDrive -Name HKCR -PSProvider Registry -Root HKEY_CLASSES_ROOT -ErrorAction SilentlyContinue | Out-Null
}
if (-not (Get-PSDrive -Name HKU -ErrorAction SilentlyContinue)) {
    New-PSDrive -Name HKU -PSProvider Registry -Root HKEY_USERS -ErrorAction SilentlyContinue | Out-Null
}

# 1. UCPD (User Choice Protection Driver) servisini ve görevini kapat
& sc.exe stop ucpd 2>$null | Out-Null
& sc.exe config ucpd start= disabled 2>$null | Out-Null
& reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\UCPD" /v Start /t REG_DWORD /d 4 /f /reg:64 2>$null | Out-Null
& schtasks.exe /change /tn "\Microsoft\Windows\AppModel\UCPD\Shell" /disable 2>$null | Out-Null

# 2. Kullanıcı kovanlarını tespit et (HKCU + HKU S-1-5-21-*)
$userHives = @('HKCU:')
Get-ChildItem -Path 'HKU:\' -ErrorAction SilentlyContinue | Where-Object {
    $_.PSChildName -match '^S-1-5-21-' -and -not $_.PSChildName.EndsWith('_Classes')
} | ForEach-Object {
    $userHives += "HKU:\$($_.PSChildName)"
}

$exts = @('.htm', '.html', '.shtml', '.xht', '.xhtml', '.pdf', '.svg')
$protos = @('http', 'https', 'microsoft-edge', 'microsoft-edge-holographic')

function Remove-UserChoiceKey($ucPath) {
    if (Test-Path -LiteralPath $ucPath) {
        try {
            $acl = Get-Acl -LiteralPath $ucPath -ErrorAction SilentlyContinue
            if ($acl) {
                $adminSid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-32-544")
                $acl.SetOwner($adminSid)
                $rule = New-Object System.Security.AccessControl.RegistryAccessRule($adminSid, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
                $acl.ResetAccessRule($rule)
                Set-Acl -LiteralPath $ucPath -AclObject $acl -ErrorAction SilentlyContinue
            }
        } catch {}
        Remove-Item -LiteralPath $ucPath -Recurse -Force -ErrorAction SilentlyContinue
        $regKey = $ucPath -replace '^HKU:\\', 'HKU\' -replace '^HKCU:\\', 'HKCU\' -replace '^HKLM:\\', 'HKLM\'
        & reg.exe delete "$regKey" /f /reg:64 2>$null | Out-Null
    }
}

foreach ($uh in $userHives) {
    # Dosya uzantıları UserChoice temizliği
    foreach ($ext in $exts) {
        $ucPath = "$uh\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$ext\UserChoice"
        if (Test-Path -LiteralPath $ucPath) {
            $progId = (Get-ItemProperty -LiteralPath $ucPath -Name 'ProgId' -ErrorAction SilentlyContinue).ProgId
            if (-not $progId -or $progId -like '*MSEdge*' -or $progId -like '*Edge*') {
                Remove-UserChoiceKey $ucPath
            }
        }

        # OpenWithProgids altından MSEdge değerlerini temizle
        $owpPath = "$uh\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$ext\OpenWithProgids"
        if (Test-Path -LiteralPath $owpPath) {
            Get-ItemProperty -LiteralPath $owpPath -ErrorAction SilentlyContinue | Get-Member -MemberType NoteProperty | Where-Object {
                $_.Name -like '*MSEdge*' -or $_.Name -like '*Edge*'
            } | ForEach-Object {
                Remove-ItemProperty -LiteralPath $owpPath -Name $_.Name -Force -ErrorAction SilentlyContinue
            }
        }
    }

    # URL Protokolleri UserChoice temizliği
    foreach ($pr in $protos) {
        $ucPath = "$uh\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\$pr\UserChoice"
        if (Test-Path -LiteralPath $ucPath) {
            Remove-UserChoiceKey $ucPath
        }
    }
}

# 3. HKCR, HKLM ve kullanıcı kovanlarındaki MSEdge ProgID'lerini yok et
$msedgeProgIds = @('MSEdgeHTM', 'MSEdgePDF', 'MSEdgeMHT', 'MSEdgeBHO')
foreach ($pid in $msedgeProgIds) {
    Remove-Item -LiteralPath "HKCR:\$pid" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "HKLM:\SOFTWARE\Classes\$pid" -Recurse -Force -ErrorAction SilentlyContinue
    & reg.exe delete "HKCR\$pid" /f /reg:64 2>$null | Out-Null
    & reg.exe delete "HKLM\SOFTWARE\Classes\$pid" /f /reg:64 2>$null | Out-Null
    foreach ($uh in $userHives) {
        Remove-Item -LiteralPath "$uh\Software\Classes\$pid" -Recurse -Force -ErrorAction SilentlyContinue
        $uhReg = $uh -replace '^HKU:\\', 'HKU\' -replace '^HKCU:\\', 'HKCU\'
        & reg.exe delete "$uhReg\Software\Classes\$pid" /f /reg:64 2>$null | Out-Null
    }
}

# 4. RegisteredApplications içerisinden Microsoft Edge'i kaldır
Remove-ItemProperty -Path 'HKLM:\SOFTWARE\RegisteredApplications' -Name 'Microsoft Edge' -Force -ErrorAction SilentlyContinue
Remove-ItemProperty -Path 'HKLM:\SOFTWARE\WOW6432Node\RegisteredApplications' -Name 'Microsoft Edge' -Force -ErrorAction SilentlyContinue
foreach ($uh in $userHives) {
    Remove-ItemProperty -Path "$uh\Software\RegisteredApplications" -Name 'Microsoft Edge' -Force -ErrorAction SilentlyContinue
}
"""
    ok, _ = run_powershell_as_trustedinstaller(ps_script, timeout=45)
    if not ok:
        ok, _ = run_powershell_as_system(ps_script, timeout=45)

    if ok:
        log("[+] Hayalet Edge ilişkilendirmeleri ve UCPD başarıyla temizlendi.", "#00FF9D")
    else:
        log("[!] Hayalet Edge ilişkilendirmeleri temizlenirken uyarı oluştu.", "#FFB86C")
    return ok

surgical_edge_cleanup = clean_edge_preserve_webview

