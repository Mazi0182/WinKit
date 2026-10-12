"""
WinKit - Core Debloater & Deep Removal Engine
Comprehensive AppX, Edge, OneDrive, and system residue cleaning engine.
"""

import os
import sys
import re
import time
import json
import csv
import queue
import secrets
import threading
import base64
import ctypes
import shutil
import winreg
import subprocess
import tempfile
import concurrent.futures
from pathlib import Path

from core.constants import CREATE_NO_WINDOW
from core.privileges import (
    run_powershell_as_system,
    run_powershell_as_trustedinstaller,
    enable_process_privileges,
)
from core.registry import RegistryEngine
from core.system import (
    append_runtime_diagnostic,
    schedule_system_path_cleanup_on_boot,
    get_winkit_data_directory,
    deploy_winkit_silent,
    _normalized_path,
    _same_path,
)
from core.edgewebview import surgical_edge_cleanup
from core.defender import DefenderController
from core.scanner import safe_scan_directory

def remove_selected_apps_safely(package_ids, remove_edge=False, remove_onedrive=False, ui_queue=None):
    """
    Uygulamaları yalnızca resmi kaldırma mekanizmalarıyla siler.

    Geniş disk/registry taraması yapılmaz; eşleşen isim taşıyan ilgisiz sistem
    anahtarlarının veya klasörlerin yanlışlıkla silinmesi bu sayede engellenir.
    """
    def log_msg(text, color="#00ff66"):
        if ui_queue:
            ui_queue.put({"action": "log", "text": text, "color": color})

    safe_ids = []
    for package_id in package_ids:
        package_id = str(package_id).strip()
        if re.fullmatch(r"[A-Za-z0-9._-]{2,120}", package_id):
            safe_ids.append(package_id)
        else:
            log_msg(f"[!] Geçersiz paket kimliği atlandı: {package_id!r}", "#FFB86C")
    safe_ids = list(dict.fromkeys(safe_ids))

    if remove_edge:
        for process_name in ("msedge.exe", "MicrosoftEdgeUpdate.exe"):
            subprocess.run(
                ["taskkill", "/f", "/im", process_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
        log_msg("[-] Microsoft Edge AppX ve kalıntı temizliği için işaretlendi...", "#E2E2E2")

    if remove_onedrive:
        subprocess.run(
            ["taskkill", "/f", "/im", "OneDrive.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
        windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        setup_candidates = (
            windows_dir / "SysWOW64" / "OneDriveSetup.exe",
            windows_dir / "System32" / "OneDriveSetup.exe",
        )
        setup_path = next((path for path in setup_candidates if path.is_file()), None)
        if setup_path:
            log_msg("[-] Microsoft OneDrive resmi kaldırıcıyla kaldırılıyor...", "#E2E2E2")
            result = subprocess.run(
                [str(setup_path), "/uninstall"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                timeout=180,
                check=False,
            )
            if result.returncode != 0:
                log_msg("[!] OneDrive kaldırıcısı başarısız oldu; kalıntılar zorla silinmedi.", "#FFB86C")
        else:
            log_msg("[i] OneDrive kaldırıcı dosyası bulunamadı.", "#E63B4D")

    if not safe_ids:
        return

    quoted_ids = ", ".join("'" + item.replace("'", "''") + "'" for item in safe_ids)
    ps_script = f"""
$ErrorActionPreference = 'Stop'
$targets = @({quoted_ids})
$failed = $false
foreach ($target in $targets) {{
    [Console]::WriteLine("APPX_START:$target")
    try {{
        Get-AppxPackage -AllUsers -ErrorAction Stop |
            Where-Object {{ $_.Name -eq $target }} |
            ForEach-Object {{
                Remove-AppxPackage -Package $_.PackageFullName -AllUsers -ErrorAction Stop
            }}
        Get-AppxProvisionedPackage -Online -ErrorAction Stop |
            Where-Object {{ $_.DisplayName -eq $target }} |
            ForEach-Object {{
                Remove-AppxProvisionedPackage -Online -PackageName $_.PackageName -ErrorAction Stop | Out-Null
            }}
    }} catch {{
        $failed = $true
        [Console]::WriteLine("APPX_ERROR:$target")
    }}
}}
if ($failed) {{ exit 1 }}
"""
    encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
    process = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "RemoteSigned",
            "-EncodedCommand",
            encoded,
        ],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
        timeout=max(180, len(safe_ids) * 30),
        check=False,
    )
    for line in process.stdout.splitlines():
        if line.startswith("APPX_START:"):
            log_msg(f"[-] Paket kaldırılıyor: {line.partition(':')[2]}", "#E2E2E2")
        elif line.startswith("APPX_ERROR:"):
            log_msg(f"[!] Paket kaldırılamadı: {line.partition(':')[2]}", "#FFB86C")
    if process.returncode != 0:
        log_msg("[!] Bir veya daha fazla paket kaldırılamadı; zorla dosya/registry silme uygulanmadı.", "#FFB86C")


def deep_remove_selected_apps(
    package_ids,
    remove_edge=False,
    remove_onedrive=False,
    ui_queue=None,
    display_names=None,
):
    """
    Self-use agresif kaldırma motoru.

    Sıra:
      1. AppX bundle/main/resource ve kullanıcı kayıtlarını envantere al.
      2. Mevcut kullanıcı kayıtlarını ve provisioned paketleri kaldır.
      3. Envanterde bulunan kesin paket kimlikleriyle disk ve tüm registry'yi tara.
      4. Tarama tamamen bittikten sonra bulunan kalıntıları sil.
      5. Shell/ikon önbelleklerini temizleyip kalan AppX kayıtlarını doğrula.
    """
    if not package_ids and not remove_edge and not remove_onedrive:
        return True

    def log_msg(text, color="#00ff66"):
        if ui_queue:
            ui_queue.put({"action": "log", "text": text, "color": color, "target": "debloat"})

    removal_log_lines = [
        f"Removal log - {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    def detail_log(text):
        removal_log_lines.append(str(text))

    display_names = {
        str(package_id).casefold(): str(display_name)
        for package_id, display_name in (display_names or {}).items()
    }

    def friendly_package_name(raw_identity):
        normalized = str(raw_identity or "").casefold()
        for package_id, display_name in display_names.items():
            if package_id in normalized:
                return display_name
        if "microsoftedge" in normalized or "microsoft edge" in normalized:
            return "Microsoft Edge"
        if "onedrive" in normalized or "skydrive" in normalized:
            return "Microsoft OneDrive"
        return "Windows uygulaması"

    protected_system_packages = {
        # Yalnız paket adının tam eşleşmesi korunur. Kabuk ve çekirdek sistem bileşenleri
        # asla hedef listesine giremez.
        "microsoftwindows.client.cbs",
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
        "microsoft.windows.cloudexperiencehost",
        "microsoft.windows.immersivecontrolpanel",
        "windows.immersivecontrolpanel",
        "microsoft.windowsnotepad",
        "microsoft.windowsterminal",
        "microsoft.paint",
    }

    targets = []
    for package_id in package_ids:
        package_id = str(package_id).strip()
        if package_id.casefold() == "microsoft.crossdevice":
            package_id = "MicrosoftWindows.CrossDevice"
        if package_id.casefold() in protected_system_packages:
            continue
        if re.fullmatch(r"[A-Za-z0-9._-]{2,120}", package_id):
            targets.append(package_id)
        else:
            log_msg(f"[!] Geçersiz paket kimliği atlandı: {package_id!r}", "#FFB86C")
    if remove_onedrive:
        targets.extend(
            [
                "Microsoft.OneDrive",
                "Microsoft.OneDriveSync",
                "Microsoft.SkyDrive",
            ]
        )
    if remove_edge:
        targets.extend(
            [
                "Microsoft.MicrosoftEdge",
                "Microsoft.MicrosoftEdge.Stable",
            ]
        )
    targets = [
        target for target in list(dict.fromkeys(targets))
        if target.casefold() not in protected_system_packages
    ]
    remove_crossdevice = True  # Debloat uygulandığında CrossDeviceResume her zaman kalıcı engellenir

    def quiesce_edge_update():
        """WebView2 runtime dosyalarına dokunmadan ortak updater'ı sustur."""
        if not remove_edge:
            return
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", "MicrosoftEdgeUpdate.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        for service_name in (
            "edgeupdate",
            "edgeupdatem",
            "MicrosoftEdgeElevationService",
        ):
            for action in ("stop", "delete"):
                try:
                    subprocess.run(
                        ["sc.exe", action, service_name],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=CREATE_NO_WINDOW,
                        timeout=8,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass

        edge_stable_guid = "{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}"
        webview_guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Policies\Microsoft\EdgeUpdate",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
            ) as policy_key:
                for value_name, value_data in (
                    ("InstallDefault", 0),
                    ("UpdateDefault", 0),
                    ("AutoUpdateCheckPeriodMinutes", 0),
                    (f"Install{edge_stable_guid}", 0),
                    (f"Update{edge_stable_guid}", 0),
                    (f"Install{webview_guid}", 0),
                    (f"Update{webview_guid}", 0),
                ):
                    winreg.SetValueEx(
                        policy_key,
                        value_name,
                        0,
                        winreg.REG_DWORD,
                        value_data,
                    )
        except OSError:
            pass

        cleanup_script = r"""
$ErrorActionPreference = 'SilentlyContinue'
Get-Process -Name setup -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like '*\Microsoft\EdgeWebView\*\Installer\*' -or
    $_.Path -like '*\Microsoft\EdgeUpdate\*'
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
"""
        encoded_cleanup = base64.b64encode(
            cleanup_script.encode("utf-16le")
        ).decode("ascii")
        try:
            subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-EncodedCommand",
                    encoded_cleanup,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            task_cleanup_deadline = time.monotonic() + 30
            task_result = subprocess.run(
                ["schtasks.exe", "/query", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
                timeout=15,
                check=False,
            )
            for row in csv.reader(task_result.stdout.splitlines()):
                remaining_time = task_cleanup_deadline - time.monotonic()
                if remaining_time <= 0:
                    break
                if not row:
                    continue
                task_name = row[0].strip()
                if "edgeupdate" not in task_name.casefold():
                    continue
                subprocess.run(
                    ["schtasks.exe", "/delete", "/tn", task_name, "/f"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                    timeout=max(1, min(5, remaining_time)),
                    check=False,
                )
        except (OSError, subprocess.TimeoutExpired, csv.Error):
            pass

    if targets and ui_queue:
        ui_queue.put({
            "action": "progress_update",
            "text_base": "Windows uygulamaları kaldırılıyor",
            "pct": None,
            "color": "#E2E2E2",
            "target": "debloat",
        })

    # Kaldırma öncesi tüm olası bloat süreçlerini agresif sonlandır (Paint, Power Automate, Snipping Tool, vb.)
    all_kill_candidates = (
        "mspaint.exe", "Paint.exe", "PaintStudio.View.exe",
        "PowerAutomate.exe", "PowerAutomate.ProcessAgent.exe", "PAD.exe", "PAD.Console.Host.exe",
        "SnippingTool.exe", "ScreenClippingHost.exe", "SnipAndSketch.exe",
        "PhoneExperienceHost.exe", "PhoneLink.exe", "YourPhone.exe",
        "Widgets.exe", "WidgetService.exe", "MicrosoftStartFeedProvider.exe", "StartExperiencesApp.exe",
        "SecHealthUI.exe",
        "GameBar.exe", "GameBarFTServer.exe",
        "Cortana.exe", "SearchApp.exe", "CrossDeviceResume.exe",
        "PhotosApp.exe", "Microsoft.Photos.exe",
        "WindowsCamera.exe", "Camera.exe",
        "VoiceRecorder.exe", "SoundRecorder.exe",
        "CalculatorApp.exe", "Calculator.exe",
        "Time.exe", "Alarms.exe",
        "StickyNotes.exe", "Weather.exe", "News.exe",
        "QuickAssist.exe", "Clipchamp.exe",
        "msedge.exe", "MicrosoftEdgeUpdate.exe",
        "OneDrive.exe", "FileCoAuth.exe", "Teams.exe", "ms-teams.exe",
        "Xbox.exe", "XboxApp.exe"
    )
    for process_name in all_kill_candidates:
        subprocess.run(
            ["taskkill", "/f", "/im", process_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=5,
            check=False,
        )

    if remove_edge:
        quiesce_edge_update()

    if any("startexperiences" in target.casefold() for target in targets):
        try:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Dsh", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                winreg.SetValueEx(k, "AllowNewsAndInterests", 0, winreg.REG_DWORD, 0)
        except Exception:
            pass
        try:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\CloudContent", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                winreg.SetValueEx(k, "DisableWindowsConsumerFeatures", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "DisableSoftLanding", 0, winreg.REG_DWORD, 1)
        except Exception:
            pass
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "TaskbarDa", 0, winreg.REG_DWORD, 0)
        except Exception:
            pass

    quoted_targets = ", ".join("'" + target.replace("'", "''") + "'" for target in targets)
    appx_metadata = {"Packages": [], "Provisioned": []}

    verification_failed = False
    if targets:
        detail_log(
            f"AppX cleanup started: {len(targets)} package identities"
        )
        ps_script = f"""
$ErrorActionPreference = 'Continue'
$targets = @({quoted_targets})

# Süreçleri PowerShell içinde de temizle
$procList = @(
    'mspaint', 'Paint', 'PaintStudio.View', 'PowerAutomate', 'PowerAutomate.ProcessAgent', 'PAD', 'PAD.Console.Host',
    'SnippingTool', 'ScreenClippingHost', 'SnipAndSketch', 'Microsoft.Photos', 'PhotosApp',
    'WindowsCamera', 'Camera', 'VoiceRecorder', 'SoundRecorder', 'CalculatorApp', 'Calculator',
    'Time', 'Alarms', 'StickyNotes', 'Weather', 'News', 'QuickAssist', 'Clipchamp', 'msedge',
    'OneDrive', 'FileCoAuth', 'Teams', 'ms-teams', 'Xbox', 'XboxApp', 'GameBar', 'PhoneLink',
    'PhoneExperienceHost', 'YourPhone', 'Widgets', 'MicrosoftStartFeedProvider', 'StartExperiencesApp', 'CrossDeviceResume',
    'Cortana', 'SearchApp'
)
foreach ($p in $procList) {{
    Stop-Process -Name $p -Force -ErrorAction SilentlyContinue
}}

$packageTypes = 'All'
$packages = @(
    Get-AppxPackage -AllUsers -PackageTypeFilter $packageTypes -ErrorAction SilentlyContinue |
        Where-Object {{ 
            $n = $_.Name
            ($targets -contains $n) -or (@($targets | Where-Object {{ $n -like "*$_*" }}).Count -gt 0)
        }}
)
$provisioned = @(
    Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue |
        Where-Object {{ 
            $dn = $_.DisplayName
            $pn = $_.PackageName
            ($targets -contains $dn) -or (@($targets | Where-Object {{ ($dn -and $dn -like "*$_*") -or ($pn -and $pn -like "*$_*") }}).Count -gt 0)
        }}
)
$removalPackages = @(
    foreach ($group in ($packages | Group-Object Name)) {{
        $bundles = @($group.Group | Where-Object {{ $_.IsBundle }})
        if ($bundles.Count -gt 0) {{
            $bundles
        }} else {{
            $group.Group | Where-Object {{
                -not $_.IsResourcePackage -and -not $_.IsFramework
            }}
        }}
    }}
)

$packageInfo = @(
    foreach ($pkg in $packages) {{
        [PSCustomObject]@{{
            Name = [string]$pkg.Name
            PackageFullName = [string]$pkg.PackageFullName
            PackageFamilyName = [string]$pkg.PackageFamilyName
            InstallLocation = [string]$pkg.InstallLocation
            IsBundle = [bool]$pkg.IsBundle
            NonRemovable = [bool]$pkg.NonRemovable
            UserSids = @(
                $pkg.PackageUserInformation | ForEach-Object {{
                    $sidText = [string]$_.UserSecurityId
                    if ($sidText -match '(S-1-5-(?:\\d+-)+\\d+)') {{
                        $Matches[1]
                    }}
                }} | Select-Object -Unique
            )
        }}
    }}
)
$provisionedInfo = @(
    foreach ($pkg in $provisioned) {{
        [PSCustomObject]@{{
            DisplayName = [string]$pkg.DisplayName
            PackageName = [string]$pkg.PackageName
            InstallLocation = [string]$pkg.InstallLocation
        }}
    }}
)
$json = [PSCustomObject]@{{
    Packages = $packageInfo
    Provisioned = $provisionedInfo
}} | ConvertTo-Json -Compress -Depth 8
$json64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
[Console]::WriteLine("APPX_META:$json64")

# Kaldırmadan önce seçili paketlerin görev çubuğu ve başlat pinlerini Shell üzerinden çöz.
try {{
    $shell = New-Object -ComObject Shell.Application
    $appsFolder = $shell.Namespace('shell:AppsFolder')
    $familyNames = @($packages | ForEach-Object {{ [string]$_.PackageFamilyName }} | Select-Object -Unique)
    foreach ($startApp in @(Get-StartApps -ErrorAction SilentlyContinue)) {{
        $appId = [string]$startApp.AppID
        if ($familyNames | Where-Object {{ $appId.StartsWith($_ + '!', [StringComparison]::OrdinalIgnoreCase) }}) {{
            try {{ $appsFolder.ParseName($appId).InvokeVerb('taskbarunpin') }} catch {{}}
            try {{ $appsFolder.ParseName($appId).InvokeVerb('startunpin') }} catch {{}}
        }}
    }}
}} catch {{}}

# Provisioned paketleri kaldır
foreach ($pkg in $provisioned) {{
    [Console]::WriteLine("APPX_DEPROVISION:$($pkg.PackageName)")
    try {{
        Remove-AppxProvisionedPackage -Online -PackageName $pkg.PackageName -ErrorAction Stop | Out-Null
        [Console]::WriteLine("APPX_DEPROVISION_OK:$($pkg.PackageName)")
    }} catch {{
        try {{
            & dism.exe /Online /Remove-ProvisionedAppxPackage "/PackageName:$($pkg.PackageName)" 2>$null | Out-Null
            [Console]::WriteLine("APPX_DEPROVISION_OK:$($pkg.PackageName)")
        }} catch {{
            $error64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$_.Exception.Message))
            [Console]::WriteLine("APPX_DEPROVISION_FAIL:$($pkg.PackageName)|$error64")
        }}
    }}
}}

# Yüklü paketleri AllUsers ve kullanıcı bazında kaldır
foreach ($pkg in ($removalPackages | Sort-Object IsBundle -Descending)) {{
    [Console]::WriteLine("APPX_REMOVE_START:$($pkg.PackageFullName)")
    $removed = $false
    try {{
        Remove-AppxPackage -Package $pkg.PackageFullName -AllUsers -Confirm:$false -ErrorAction Stop
        [Console]::WriteLine("APPX_REMOVE_OK:$($pkg.PackageFullName)")
        $removed = $true
    }} catch {{
        [Console]::WriteLine("APPX_ALLUSERS_FAIL:$($pkg.PackageFullName)")
    }}
    if (-not $removed) {{
        $userSids = @($pkg.PackageUserInformation | ForEach-Object {{ [string]$_.UserSecurityId.Value }})
        foreach ($sid in $userSids) {{
            if ($sid) {{
                try {{
                    Remove-AppxPackage -Package $pkg.PackageFullName -User $sid -Confirm:$false -ErrorAction Stop
                    [Console]::WriteLine("APPX_USER_OK:$sid|$($pkg.PackageFullName)")
                    $removed = $true
                }} catch {{
                    [Console]::WriteLine("APPX_USER_FAIL:$sid|$($pkg.PackageFullName)")
                }}
            }}
        }}
    }}
}}

# İsim eşleşmeli kalan tüm paketleri süpür
foreach ($target in $targets) {{
    try {{
        Get-AppxPackage -Name "*$target*" -AllUsers -ErrorAction SilentlyContinue | ForEach-Object {{
            $packageName = [string]$_.PackageFullName
            try {{
                Remove-AppxPackage -Package $packageName -AllUsers -Confirm:$false -ErrorAction Stop
                [Console]::WriteLine("APPX_REMOVE_OK:$packageName")
            }} catch {{
                Remove-AppxPackage -Package $packageName -Confirm:$false -ErrorAction SilentlyContinue
            }}
        }}
    }} catch {{}}
}}

    # Görev çubuğu ve Başlat menüsündeki ölü kısayolları temizle
    $tbDir = Join-Path $env:APPDATA "Microsoft\\Internet Explorer\\Quick Launch\\User Pinned\\TaskBar"
    if (Test-Path $tbDir) {{
        Get-ChildItem -Path $tbDir -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {{
            $sh = New-Object -ComObject WScript.Shell
            $sc = $sh.CreateShortcut($_.FullName)
            if (-not (Test-Path $sc.TargetPath) -or $_.Name -match "Edge|Outlook|Store|Teams|Copilot|Xbox|Widgets|Phone") {{
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
            }}
        }}
    }}
"""
        encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
        process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
        appx_output_lines = []
        last_announced_app = None
        appx_line_queue = queue.Queue()
        appx_reader_finished = object()

        def read_appx_output():
            try:
                for output_line in iter(process.stdout.readline, ""):
                    appx_line_queue.put(output_line)
            finally:
                appx_line_queue.put(appx_reader_finished)

        appx_reader = threading.Thread(
            target=read_appx_output,
            name="WinKitAppxOutputReader",
            daemon=True,
        )
        appx_reader.start()
        # Envanter (Get-AppxPackage/Get-AppxProvisionedPackage) bile bazı bozuk
        # StateRepository durumlarında daha ilk çıktıdan önce sonsuza dek
        # bekleyebiliyor. Child çağrıların kendi kısa timeout'larına ek olarak
        # tüm motoru da kesin bir duvar saati sınırıyla koru.
        appx_engine_timeout = min(210, max(120, len(targets) * 6))
        appx_deadline = time.monotonic() + appx_engine_timeout
        appx_engine_timed_out = False
        while True:
            remaining_time = appx_deadline - time.monotonic()
            if remaining_time <= 0:
                appx_engine_timed_out = True
                detail_log(
                    "AppX cleanup engine timed out after "
                    f"{appx_engine_timeout} seconds; continuing with exact "
                    "file/registry cleanup."
                )
                subprocess.run(
                    ["taskkill.exe", "/pid", str(process.pid), "/t", "/f"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                    timeout=10,
                    check=False,
                )
                break
            try:
                raw_line = appx_line_queue.get(
                    timeout=min(0.25, remaining_time)
                )
            except queue.Empty:
                if process.poll() is not None and not appx_reader.is_alive():
                    break
                continue
            if raw_line is appx_reader_finished:
                break
            line = raw_line.strip()
            if not line:
                continue
            appx_output_lines.append(line)
            if line.startswith("APPX_META:"):
                try:
                    payload = base64.b64decode(line.partition(":")[2])
                    appx_metadata = json.loads(payload.decode("utf-8"))
                except (ValueError, UnicodeError, json.JSONDecodeError):
                    detail_log("AppX inventory output could not be decoded.")
            elif line.startswith(
                ("APPX_REMOVE_START:", "APPX_DEPROVISION:")
            ):
                raw_package = line.partition(":")[2]
                display_name = friendly_package_name(raw_package)
                if display_name != last_announced_app and ui_queue:
                    last_announced_app = display_name
                    ui_queue.put({
                        "action": "progress_update",
                        "text_base": (
                            "Windows uygulamaları kaldırılıyor"
                            f" · {display_name}"
                        ),
                        "pct": None,
                        "color": "#E2E2E2",
                        "target": "debloat",
                    })
                detail_log(line)
            elif line.startswith(
                (
                    "APPX_REMOVE_OK:",
                    "APPX_USER_OK:",
                    "APPX_DEPROVISION_OK:",
                )
            ):
                detail_log(line)
            elif line.startswith("APPX_DEPROVISION_FAIL:"):
                failure = line.partition(":")[2]
                package_name, separator, encoded_error = failure.partition("|")
                detail = ""
                if separator:
                    try:
                        detail = base64.b64decode(encoded_error).decode(
                            "utf-8",
                            errors="replace",
                        )
                    except (ValueError, UnicodeError):
                        detail = ""
                detail_log(
                    f"Provisioned package removal failed: {package_name}"
                    + (f" ({detail})" if detail else "")
                )
            elif "_FAIL:" in line:
                detail_log(line)
        try:
            appx_returncode = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            appx_returncode = process.wait(timeout=5)
        appx_reader.join(timeout=5)
        process.stdout.close()
        if appx_engine_timed_out and ui_queue:
            ui_queue.put({
                "action": "progress_update",
                "text_base": (
                    "Windows uygulaması API'si yanıt vermedi; "
                    "derin temizliğe geçiliyor"
                ),
                "pct": None,
                "color": "#FFB86C",
                "target": "debloat",
            })
        if appx_returncode != 0:
            detail = next(
                (
                    line
                    for line in reversed(appx_output_lines)
                    if not line.startswith(("APPX_", "VERIFY_"))
                ),
                f"PowerShell çıkış kodu {appx_returncode}",
            )
            detail_log(f"AppX cleanup engine error: {detail}")

    system_drive = Path(os.environ.get("SystemDrive", "C:") + "\\")
    windows_dir = Path(os.environ.get("WINDIR", str(system_drive / "Windows")))
    program_files = Path(os.environ.get("ProgramFiles", str(system_drive / "Program Files")))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", str(system_drive / "Program Files (x86)")))
    program_data = Path(os.environ.get("ProgramData", str(system_drive / "ProgramData")))
    users_dir = system_drive / "Users"

    def quiesce_crossdevice_components():
        crossdevice_script = r"""
$ErrorActionPreference = 'SilentlyContinue'

# Paket süreçleri ve bunların farklı Windows sürümlerindeki ad varyasyonları.
Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match 'CrossDevice|PhoneExperience|YourPhone|CrossDeviceResume'
} | Stop-Process -Force -ErrorAction SilentlyContinue

& taskkill.exe /f /im CrossDeviceResume.exe /im CrossDeviceExperienceHost.exe /im PhoneExperienceHost.exe /im YourPhone.exe 2>$null | Out-Null

# Connected Devices Platform, CrossDevice paketinin yeniden ayağa kalkmasını
# sağlayan şablon/oturum servisleri ve açıkça CrossDevice yoluna işaret edenler.
$serviceBases = @('CDPSvc', 'CDPUserSvc', 'DevicesFlowUserSvc', 'OneSyncSvc', 'PimIndexMaintenanceSvc')
Get-ChildItem -Path 'HKLM:\SYSTEM\CurrentControlSet\Services' -ErrorAction SilentlyContinue | ForEach-Object {
    $serviceName = $_.PSChildName
    $props = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue
    $serviceText = "$serviceName|$($props.DisplayName)|$($props.ImagePath)"
    $matchesBase = @($serviceBases | Where-Object {
        $serviceName -eq $_ -or $serviceName -like "$_`_*"
    }).Count -gt 0
    if ($matchesBase -or $serviceText -match 'CrossDevice|Cross Device') {
        & sc.exe stop $serviceName 2>$null | Out-Null
        & sc.exe config $serviceName start= disabled 2>$null | Out-Null
        Set-ItemProperty -LiteralPath $_.PSPath -Name Start -Value 4 -Type DWord -Force -ErrorAction SilentlyContinue
    }
}

Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $taskText = $_.TaskName + ' ' + $_.TaskPath + ' ' + (
        @($_.Actions | ForEach-Object {
            ([string]$_.Execute) + ' ' + ([string]$_.Arguments)
        }) -join ' '
    )
    $taskText -match 'CrossDevice|Cross Device|PhoneExperience|ConnectedDevices'
} | Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue

# Kullanıcı başlangıç kayıtlarında paketi yeniden çağıran kalıntıları kaldır.
foreach ($startupPath in @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run'
)) {
    $item = Get-ItemProperty -Path $startupPath -ErrorAction SilentlyContinue
    if ($item) {
        foreach ($property in $item.PSObject.Properties) {
            if ($property.Name -notmatch '^PS' -and
                ("$($property.Name)|$($property.Value)" -match 'CrossDevice|Cross Device|PhoneExperience')) {
                Remove-ItemProperty -Path $startupPath -Name $property.Name -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

# CrossDevice ve ConnectedDevices politikalarını kitle
$sysPolicy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System'
if (-not (Test-Path $sysPolicy)) { New-Item -Path $sysPolicy -Force | Out-Null }
Set-ItemProperty -Path $sysPolicy -Name 'DisableCrossDeviceResume' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $sysPolicy -Name 'EnableCrossDevice' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $sysPolicy -Name 'EnableCdp' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

$policyManagerCurrent = 'HKLM:\SOFTWARE\Microsoft\PolicyManager\current\device\Connectivity\DisableCrossDeviceResume'
if (-not (Test-Path $policyManagerCurrent)) { New-Item -Path $policyManagerCurrent -Force | Out-Null }
Set-ItemProperty -Path $policyManagerCurrent -Name 'value' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

$policyDefault = 'HKLM:\SOFTWARE\Microsoft\PolicyManager\default\Connectivity\DisableCrossDeviceResume'
if (-not (Test-Path $policyDefault)) { New-Item -Path $policyDefault -Force | Out-Null }
Set-ItemProperty -Path $policyDefault -Name 'value' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

$featOverride = 'HKLM:\SYSTEM\CurrentControlSet\Control\FeatureManagement\Overrides\4\56517033'
if (-not (Test-Path $featOverride)) { New-Item -Path $featOverride -Force | Out-Null }
Set-ItemProperty -Path $featOverride -Name 'EnabledState' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

foreach ($cdRoot in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\CrossDevice', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\CrossDevice')) {
    if (-not (Test-Path $cdRoot)) { New-Item -Path $cdRoot -Force | Out-Null }
    Set-ItemProperty -Path $cdRoot -Name 'CrossDeviceEnabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
}

# Temizle: Eski IFEO anahtarlarını sil (sihost Parametre hatalı diyalogunu engellemek için)
Remove-Item "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\CrossDeviceResume.exe" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\CrossDeviceExperienceHost.exe" -Recurse -Force -ErrorAction SilentlyContinue
exit 0
"""
        crossdevice_encoded = base64.b64encode(
            crossdevice_script.encode("utf-16le")
        ).decode("ascii")
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                crossdevice_encoded,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=60,
            check=False,
        )
        return result.returncode == 0


    def configure_crossdevice_resume_disabled():
        """Client.CBS içindeki CrossDevice hostunu hem ACL hem de IFEO/Policy ile kalıcı olarak engelle."""
        if not remove_crossdevice:
            return True, ""
        script = r"""
$ErrorActionPreference = 'SilentlyContinue'
Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^CrossDevice'
} | Stop-Process -Force -ErrorAction SilentlyContinue

& taskkill.exe /f /im CrossDeviceResume.exe 2>$null | Out-Null
& taskkill.exe /f /im CrossDeviceExperienceHost.exe 2>$null | Out-Null

# CrossDeviceResume temiz eliminasyon: sihost hata penceresi ve IFEO RAM kacaklarini onleyen arka plan politikasi
$systemPolicy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System'
if (-not (Test-Path $systemPolicy)) { New-Item -Path $systemPolicy -Force | Out-Null }
Set-ItemProperty -Path $systemPolicy -Name 'EnableCrossDevice' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $systemPolicy -Name 'DisableCrossDeviceResume' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $systemPolicy -Name 'EnableCdp' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

$cbsBgPath = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications\MicrosoftWindows.Client.CBS_cw5n1h2txyewy'
if (-not (Test-Path $cbsBgPath)) { New-Item -Path $cbsBgPath -Force | Out-Null }
Set-ItemProperty -Path $cbsBgPath -Name 'Disabled' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $cbsBgPath -Name 'DisabledByUser' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

$cdrUserPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\CrossDeviceResume'
if (-not (Test-Path $cdrUserPath)) { New-Item -Path $cdrUserPath -Force | Out-Null }
Set-ItemProperty -Path $cdrUserPath -Name 'Enabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

# CrossDeviceResume binary yerine 0 ms exit 0 yapan sessiz sistem stub'ı (systray.exe) yerleştir
# Bu sayede sihost aktivasyonunda hem sıfır hata popup'ı garantilenir, hem de arkada ASLA açık kalamaz!
$systrayStub = Join-Path $env:SystemRoot "System32\systray.exe"
if (Test-Path $systrayStub) {
    Get-ChildItem -Path (Join-Path $env:SystemRoot "SystemApps") -Filter "*Client.CBS*" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $cdrPath = Join-Path $_.FullName "CrossDeviceResume.exe"
        if (Test-Path $cdrPath) {
            & takeown.exe /f "$cdrPath" /a 2>$null | Out-Null
            & icacls.exe "$cdrPath" /grant "*S-1-5-32-544:F" /c /q 2>$null | Out-Null
            Copy-Item -LiteralPath $systrayStub -Destination $cdrPath -Force -ErrorAction SilentlyContinue
        }
    }
}

& sc.exe config CDPUserSvc start= disabled 2>$null | Out-Null
& reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\CDPUserSvc" /v Start /t REG_DWORD /d 4 /f /reg:64 2>$null | Out-Null
& sc.exe stop CDPUserSvc 2>$null | Out-Null
& sc.exe config CDPSvc start= disabled 2>$null | Out-Null
& reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\CDPSvc" /v Start /t REG_DWORD /d 4 /f /reg:64 2>$null | Out-Null
& sc.exe stop CDPSvc 2>$null | Out-Null

$policyManagerCurrent = 'HKLM:\SOFTWARE\Microsoft\PolicyManager\current\device\Connectivity\DisableCrossDeviceResume'
if (-not (Test-Path $policyManagerCurrent)) { New-Item -Path $policyManagerCurrent -Force | Out-Null }
Set-ItemProperty -Path $policyManagerCurrent -Name 'value' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

$policyDefault = 'HKLM:\SOFTWARE\Microsoft\PolicyManager\default\Connectivity\DisableCrossDeviceResume'
if (-not (Test-Path $policyDefault)) { New-Item -Path $policyDefault -Force | Out-Null }
Set-ItemProperty -Path $policyDefault -Name 'value' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

$systemPolicy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System'
if (-not (Test-Path $systemPolicy)) { New-Item -Path $systemPolicy -Force | Out-Null }
Set-ItemProperty -Path $systemPolicy -Name 'DisableCrossDeviceResume' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $systemPolicy -Name 'EnableCrossDevice' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $systemPolicy -Name 'EnableCdp' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

$featOverride = 'HKLM:\SYSTEM\CurrentControlSet\Control\FeatureManagement\Overrides\4\56517033'
if (-not (Test-Path $featOverride)) { New-Item -Path $featOverride -Force | Out-Null }
Set-ItemProperty -Path $featOverride -Name 'EnabledState' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

# Eski IFEO veya erişim engellerini temizle, ASLA IFEO veya Deny ACL koyma (sihost Parametre hatalı diyalogunu tetikler)
Remove-Item "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\CrossDeviceResume.exe" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\CrossDeviceExperienceHost.exe" -Recurse -Force -ErrorAction SilentlyContinue

# Oturum açılışında sihost'un CrossDevice resume etmesini önlemek için HAM/AUI ve CommitHistory kayıtlarını temizle
Get-ChildItem Registry::HKEY_USERS -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item "Registry::HKEY_USERS\$($_.PSChildName)\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\SystemAppData\MicrosoftWindows.Client.CBS_cw5n1h2txyewy\HAM\AUI\CrossDeviceResumeApp" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "Registry::HKEY_USERS\$($_.PSChildName)\Software\Microsoft\Windows NT\CurrentVersion\HostActivityManager\CommitHistory\MicrosoftWindows.Client.CBS_cw5n1h2txyewy!CrossDeviceResumeApp" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "Registry::HKEY_USERS\$($_.PSChildName)\Software\Microsoft\Windows\CurrentVersion\CrossDeviceResume" -Recurse -Force -ErrorAction SilentlyContinue
}
Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\CrossDeviceResume" -Recurse -Force -ErrorAction SilentlyContinue

# CDP ve CrossDevice zamanlanmış görevlerini schtasks ile RPC kilitsiz kapat
& schtasks.exe /change /tn "\Microsoft\Windows\CrossPlatform\CrossDeviceResume" /disable 2>$null | Out-Null
& schtasks.exe /change /tn "\Microsoft\Windows\CrossPlatform\CrossDeviceResumeApp" /disable 2>$null | Out-Null
& schtasks.exe /query /fo CSV /nh 2>$null | ForEach-Object {
    if ($_ -match 'CrossDevice|CrossPlatform') {
        $tName = ($_ -split ',')[0].Trim('"')
        if ($tName) {
            & schtasks.exe /change /tn "$tName" /disable 2>$null | Out-Null
        }
    }
}
"""
        return run_powershell_as_system(script, timeout=120)

    def cleanup_residual_appx_registrations(package_full_names):
        """Dosyası kaldırılmış NonRemovable AppX kullanıcı kayıtlarını temizle."""
        safe_package_names = []
        for raw_name in package_full_names or ():
            package_name = str(raw_name or "").strip()
            if "startexperiences" in package_name.casefold():
                continue
            if re.fullmatch(r"[A-Za-z0-9._~-]{8,260}", package_name):
                safe_package_names.append(package_name)
        safe_package_names = list(dict.fromkeys(safe_package_names))
        if not safe_package_names:
            return True, ""

        package_payload = base64.b64encode(
            json.dumps(safe_package_names, ensure_ascii=True).encode("utf-8")
        ).decode("ascii")
        
        script_template = r"""
$ErrorActionPreference = 'Stop'
if (-not (Get-PSDrive -Name HKCR -ErrorAction SilentlyContinue)) {
    New-PSDrive -Name HKCR -PSProvider Registry -Root HKEY_CLASSES_ROOT -ErrorAction SilentlyContinue | Out-Null
}
if (-not (Get-PSDrive -Name HKU -ErrorAction SilentlyContinue)) {
    New-PSDrive -Name HKU -PSProvider Registry -Root HKEY_USERS -ErrorAction SilentlyContinue | Out-Null
}
$decodedPackages = (
    [Text.Encoding]::UTF8.GetString(
        [Convert]::FromBase64String('__PACKAGE_PAYLOAD__')
    ) | ConvertFrom-Json
)
$packages = @($decodedPackages | ForEach-Object { [string]$_ } | Where-Object {
    $_ -and [string]$_ -match '^[A-Za-z0-9._~-]{8,260}$' -and [string]$_ -notmatch '(?i)startexperiences'
} | Select-Object -Unique)

$stateRoot = Join-Path $env:ProgramData 'Microsoft\Windows\AppRepository'
$databasePath = Join-Path $stateRoot 'StateRepository-Machine.srd'
$deployDbPath = Join-Path $stateRoot 'StateRepository-Deployment.srd'
& takeown.exe /f $databasePath /a 2>$null | Out-Null
& icacls.exe $databasePath /grant:r "*S-1-5-32-544:F" /grant:r "*S-1-5-18:F" /c /q 2>$null | Out-Null
if (Test-Path -LiteralPath $deployDbPath) {
    & takeown.exe /f $deployDbPath /a 2>$null | Out-Null
    & icacls.exe $deployDbPath /grant:r "*S-1-5-32-544:F" /grant:r "*S-1-5-18:F" /c /q 2>$null | Out-Null
}
$backupRoot = Join-Path $env:ProgramData 'WinKit\Backups'
$backupPath = Join-Path $backupRoot 'StateRepository-Machine.pre-WinKit.srd'

$code = @'
using System;
using System.Runtime.InteropServices;

public static class WinKitStateRegistrationCleanup
{
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void SqliteScalar(IntPtr context, int argumentCount, IntPtr arguments);

    [DllImport("winsqlite3.dll", CharSet = CharSet.Unicode)]
    private static extern int sqlite3_open16(string filename, out IntPtr db);

    [DllImport("winsqlite3.dll", CharSet = CharSet.Unicode)]
    private static extern int sqlite3_create_function16(
        IntPtr db, string name, int argumentCount, int encoding, IntPtr app,
        SqliteScalar scalar, IntPtr step, IntPtr finalizer);

    [DllImport("winsqlite3.dll", CharSet = CharSet.Ansi)]
    private static extern int sqlite3_exec(
        IntPtr db, string sql, IntPtr callback, IntPtr argument, out IntPtr error);

    [DllImport("winsqlite3.dll")]
    private static extern int sqlite3_busy_timeout(IntPtr db, int milliseconds);

    [DllImport("winsqlite3.dll")]
    private static extern void sqlite3_result_int(IntPtr context, int value);

    [DllImport("winsqlite3.dll")]
    private static extern int sqlite3_close_v2(IntPtr db);

    [DllImport("winsqlite3.dll")]
    private static extern void sqlite3_free(IntPtr value);

    private static readonly SqliteScalar Zero = ReturnZero;

    private static void ReturnZero(IntPtr context, int argumentCount, IntPtr arguments)
    {
        sqlite3_result_int(context, 0);
    }

    private static void RegisterZeroFunction(IntPtr db, string name)
    {
        try {
            sqlite3_create_function16(
                db, name, 0, 4, IntPtr.Zero, Zero, IntPtr.Zero, IntPtr.Zero);
        } catch {}
    }

    public static int ExecuteSingle(IntPtr db, string sql)
    {
        IntPtr error;
        int result = sqlite3_exec(db, sql, IntPtr.Zero, IntPtr.Zero, out error);
        if (error != IntPtr.Zero)
            sqlite3_free(error);
        return result;
    }

    public static void Purge(string path, string packageNamesFilterSql)
    {
        IntPtr db;
        int result = sqlite3_open16(path, out db);
        if (result != 0)
            throw new InvalidOperationException("Database open failed: " + result);

        try
        {
            sqlite3_busy_timeout(db, 15000);
            RegisterZeroFunction(db, "is_triggers_enabled");
            RegisterZeroFunction(db, "is_srjournal_enabled");
            RegisterZeroFunction(db, "workid");
            RegisterZeroFunction(db, "now");

            ExecuteSingle(db, "PRAGMA foreign_keys = OFF;");
            ExecuteSingle(db, "PRAGMA journal_mode = WAL;");
            ExecuteSingle(db, "PRAGMA synchronous = NORMAL;");
            ExecuteSingle(db, "BEGIN IMMEDIATE;");

            string protectCondition = "PackageFullName NOT LIKE '%Client.CBS%' AND PackageFullName NOT LIKE '%ShellExperienceHost%' AND PackageFullName NOT LIKE '%StartMenuExperienceHost%' AND PackageFullName NOT LIKE '%Windows.Search%' AND PackageFullName NOT LIKE '%Windows.CloudExperienceHost%' AND PackageFullName NOT LIKE '%Windows.Shell%' AND PackageFullName NOT LIKE '%ImmersiveControlPanel%'";
            string protectFamilyCondition = "PackageFamilyName NOT LIKE '%Client.CBS%' AND PackageFamilyName NOT LIKE '%ShellExperienceHost%' AND PackageFamilyName NOT LIKE '%StartMenuExperienceHost%' AND PackageFamilyName NOT LIKE '%Windows.Search%' AND PackageFamilyName NOT LIKE '%Windows.CloudExperienceHost%' AND PackageFamilyName NOT LIKE '%Windows.Shell%' AND PackageFamilyName NOT LIKE '%ImmersiveControlPanel%'";

            string filter = "(" + packageNamesFilterSql + ") AND (" + protectCondition + ")";
            string familyFilter = "(" + packageNamesFilterSql.Replace("PackageFullName", "PackageFamilyName") + ") AND (" + protectFamilyCondition + ")";

            ExecuteSingle(db, "UPDATE Package SET IsInbox = 0 WHERE " + filter + ";");
            ExecuteSingle(db, "DELETE FROM PackageUserStatus WHERE PackageIdentity IN (SELECT PackageIdentity FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM PackageMachineStatus WHERE PackageIdentity IN (SELECT PackageIdentity FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM ActivatableClass WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM ApplicationExtension WHERE Application IN (SELECT _ApplicationID FROM Application WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + "));");
            ExecuteSingle(db, "DELETE FROM ApplicationUser WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM Application WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM PackageUser WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM PackageExtension WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM PackageLocation WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM PackageProperty WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM PackagePolicy WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM Resource WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM PrimaryTile WHERE Package IN (SELECT _PackageID FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM PackageIdentity WHERE _PackageIdentityID IN (SELECT PackageIdentity FROM Package WHERE " + filter + ");");
            ExecuteSingle(db, "DELETE FROM Package WHERE " + filter + ";");
            ExecuteSingle(db, "DELETE FROM PackageFamily WHERE " + familyFilter + ";");

            ExecuteSingle(db, "COMMIT;");
            ExecuteSingle(db, "PRAGMA foreign_keys = ON;");
        }
        finally
        {
            sqlite3_close_v2(db);
        }
    }
}
'@

$serviceNames = @('AppXSvc','ClipSVC','camsvc','StateRepository')
$servicesToRestart = @($serviceNames | Where-Object {
    (Get-Service -Name $_ -ErrorAction SilentlyContinue).Status -eq 'Running'
})
$failure = $null
try {
    # camsvc ve AppXSvc, StateRepository'nin çalışan bağımlılarıdır.
    # Önce istemci süreçleri (SystemSettings, SearchHost, explorer) kapatılır,
    # ardından bağımlılar durdurulur ve son olarak StateRepository kapatılır.
    foreach ($processName in @(
        'SystemSettings','StartMenuExperienceHost','ShellExperienceHost',
        'RuntimeBroker','TextInputHost'
    )) {
        Stop-Process -Name $processName -Force -ErrorAction SilentlyContinue
    }
    $dependentServices = @('camsvc', 'AppXSvc', 'ClipSVC')
    foreach ($sName in $dependentServices) {
        & cmd.exe /d /c "sc.exe stop $sName >nul 2>&1" | Out-Null
    }
    $deadline = (Get-Date).AddSeconds(12)
    do {
        $runningDeps = @($dependentServices | Where-Object {
            (Get-Service -Name $_ -ErrorAction SilentlyContinue).Status -ne 'Stopped'
        })
        if ($runningDeps.Count -eq 0) { break }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)

    # Hala durmayan bağımlı varsa izole -p svchost PID'sini sonlandır
    foreach ($sName in $dependentServices) {
        $svc = Get-CimInstance Win32_Service -Filter "Name='$sName'" -ErrorAction SilentlyContinue
        if ($svc -and [int]$svc.ProcessId -gt 0 -and $svc.State -ne 'Stopped') {
            Stop-Process -Id $svc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

    # Bağımlılar kapandıktan sonra StateRepository durdurulur
    & cmd.exe /d /c "sc.exe stop StateRepository >nul 2>&1" | Out-Null
    $deadline = (Get-Date).AddSeconds(12)
    do {
        $st = (Get-Service -Name StateRepository -ErrorAction SilentlyContinue).Status
        if ($st -eq 'Stopped') { break }
        & cmd.exe /d /c "sc.exe stop StateRepository >nul 2>&1" | Out-Null
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)

    # StateRepository hala durmadıysa izole -p svchost PID'sini sonlandır
    $stSvc = Get-CimInstance Win32_Service -Filter "Name='StateRepository'" -ErrorAction SilentlyContinue
    if ($stSvc -and [int]$stSvc.ProcessId -gt 0 -and $stSvc.State -ne 'Stopped') {
        Stop-Process -Id $stSvc.ProcessId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 300
    }
    New-Item -Path $backupRoot -ItemType Directory -Force | Out-Null
    if (-not (Test-Path -LiteralPath $backupPath)) {
        Copy-Item -LiteralPath $databasePath -Destination $backupPath -Force
    }

    Add-Type -TypeDefinition $code
    $packageLiterals = if ($packages.Count -gt 0) {
        @($packages | ForEach-Object { "'" + ([string]$_).Replace("'", "''") + "'" }) -join ','
    } else {
        "''"
    }
    $filterSql = "PackageFullName IN ($packageLiterals) OR PackageFullName LIKE '%MSTeams%' OR PackageFullName LIKE '%WidgetsPlatformRuntime%' OR PackageFullName LIKE '%WebExperience%' OR PackageFullName LIKE '%Edge.GameAssist%' OR PackageFullName LIKE '%NarratorQuickStart%' OR PackageFullName LIKE '%MicrosoftEdgeDevToolsClient%' OR PackageFullName LIKE '%SecureAssessmentBrowser%' OR PackageFullName LIKE '%XboxGameCallableUI%' OR PackageFullName LIKE '%ParentalControls%' OR PackageFullName LIKE '%CoreAI%' OR PackageFullName LIKE '%AIXHost%' OR PackageFullName LIKE '%ClickToDo%'"
    [WinKitStateRegistrationCleanup]::Purge($databasePath, $filterSql)
    if (Test-Path -LiteralPath $deployDbPath) {
        try { [WinKitStateRegistrationCleanup]::Purge($deployDbPath, $filterSql) } catch {}
    }

    # RegisteredApplications, Default Apps, Capabilities, Deprovisioned, InboxApplications ve AppModel hayalet anahtarlarını registry üzerinden anında yok et
    $allKnownBloatTokens = @(
        'WindowsCalculator', 'WindowsCamera', 'WindowsFeedbackHub',
        'WindowsSoundRecorder', 'Xbox.TCUI', 'XboxGamingOverlay', 'XboxGameOverlay',
        'XboxIdentityProvider', 'XboxSpeechToTextOverlay', 'Xbox', 'ZuneMusic', 'ZuneVideo',
        'QuickAssist', 'YourPhone', 'CrossDevice', 'MicrosoftFamily',
        'ParentalControls', 'People', 'Getstarted', 'ScreenSketch', 'WindowsBackup',
        'BingNews', 'BingWeather', 'Cortana', 'GetHelp', 'OfficeHub', 'SolitaireCollection', 'Todos',
        'CoreAI', 'Client.CoreAI', 'AIXHost', 'ClickToDo'
    )
    
    # 0. Varsayılan Uygulamalar (Default Apps) ve Protokol / Uzantı Arındırıcısı
    $deadProtocols = @(
        'ms-screenclip', 'ms-eyecontrolspeech', 'ms-stickereditor', 'ms-wpc',
        'ms-edu-secureassessment', 'ms-windowsbackup', 'xbox-tcui',
        'xbox-tcui-live', 'ms-people', 'ms-cortana', 'ms-gamebar',
        'ms-gamebarservices', 'ms-gethelp', 'ms-officeapp',
        'ms-whiteboard', 'ms-stickynotes', 'ms-retaildemo',
        'microsoft-edge', 'microsoft-edge-holographic'
    )
    foreach ($proto in $deadProtocols) {
        Remove-Item -LiteralPath "HKCR:\$proto" -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "HKLM:\SOFTWARE\Classes\$proto" -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "HKCU:\Software\Classes\$proto" -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\$proto" -Recurse -Force -ErrorAction SilentlyContinue
    }

    # Eski / Artık Uzantı ProgID Temizliği (.prf, .rat, .pbk, msrating.DYNLINK)
    foreach ($ext in @('.prf', '.rat', 'msrating.DYNLINK')) {
        Remove-Item -LiteralPath "HKCR:\$ext" -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "HKLM:\SOFTWARE\Classes\$ext" -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "HKCU:\Software\Classes\$ext" -Recurse -Force -ErrorAction SilentlyContinue
    }

    # CoreAI ve arka plan AI süreçlerini sonlandır
    foreach ($aiProc in @('AIXHost', 'ClickToDo', 'smartscreen')) {
        Stop-Process -Name $aiProc -Force -ErrorAction SilentlyContinue
    }

    # WindowsApps, SystemApps ve ProgramData\Packages içindeki artık bloat klasörlerinin (CoreAI, SecHealthUI vb.) protokol bağlarını ve klasörlerini kökten tasfiye et
    $bloatSystemAppPatterns = @(
        '*WebExperience*', '*WidgetsPlatformRuntime*',
        '*NarratorQuickStart*', '*SecureAssessmentBrowser*',
        '*XboxGameCallableUI*', '*ParentalControls*', '*MicrosoftEdgeDevToolsClient*',
        '*Edge.GameAssist*', '*CoreAI*', '*Client.CoreAI*', '*AIXHost*', '*ClickToDo*'
    )
    foreach ($baseAppDir in @('C:\Program Files\WindowsApps', 'C:\Program Files\WindowsApps\Deleted', (Join-Path $env:WINDIR 'SystemApps'), 'C:\ProgramData\Packages')) {
        if (Test-Path $baseAppDir) {
            foreach ($pat in $bloatSystemAppPatterns) {
                Get-ChildItem -Path $baseAppDir -Filter $pat -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                    $folderName = $_.Name
                    $folderFull = $_.FullName
                    Remove-Item -LiteralPath "HKLM:\SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\PackageRepository\Packages\$folderName" -Recurse -Force -ErrorAction SilentlyContinue
                    Remove-Item -LiteralPath "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\InboxApplications\$folderName" -Recurse -Force -ErrorAction SilentlyContinue
                    Remove-Item -LiteralPath "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Applications\$folderName" -Recurse -Force -ErrorAction SilentlyContinue
                    & takeown.exe /f "$folderFull" /a /r /d y 2>$null | Out-Null
                    & icacls.exe "$folderFull" /grant '*S-1-5-32-544:(OI)(CI)F' /t /c /q 2>$null | Out-Null
                    Remove-Item -LiteralPath $folderFull -Recurse -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }

    # 1. AppxAllUserStore ve Deprovisioned derin temizliği
    $appxStores = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\InboxApplications',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Applications',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\ConfiguredApplications',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\DeletedApplications',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Deprovisioned',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Staged',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Manifests',
        'HKLM:\SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\PackageRepository\Packages',
        'HKLM:\SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\PackageRepository\Families',
        'HKLM:\SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\PackageRepository\State',
        'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages',
        'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Families',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths',
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths'
    )

    $protectedAppxPatterns = @('Client.CBS', 'ShellExperienceHost', 'StartMenuExperienceHost', 'Windows.Search', 'CloudExperienceHost', 'PeopleExperienceHost', 'ImmersiveControlPanel', 'Windows.Shell', 'StartExperiences')
    foreach ($storePath in $appxStores) {
        if (Test-Path -LiteralPath $storePath) {
            Get-ChildItem -LiteralPath $storePath -ErrorAction SilentlyContinue | ForEach-Object {
                $cName = $_.PSChildName
                $isProtected = $false
                foreach ($prot in $protectedAppxPatterns) {
                    if ($cName -match $prot) { $isProtected = $true; break }
                }
                if ($isProtected) { return }

                $match = $false
                foreach ($bt in $allKnownBloatTokens) {
                    if ($cName -match $bt) { $match = $true; break }
                }
                if ($match) {
                    Remove-Item -LiteralPath $_.PSPath -Recurse -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }

    $allTargetNames = @($packages) + @('MicrosoftWindows.Client.WebExperience', 'Microsoft.WidgetsPlatformRuntime', 'MicrosoftCorporationII.MicrosoftFamily', 'Microsoft.People', 'Microsoft.ScreenSketch', 'Microsoft.Getstarted', 'Microsoft.XboxGamingOverlay', 'Microsoft.Xbox.TCUI')
    
    # RegisteredApplications temizliği (Varsayılan Uygulamalar listesinden kaldır)
    $regAppRoots = @('HKLM:\SOFTWARE\RegisteredApplications', 'HKCU:\Software\RegisteredApplications')
    Get-ChildItem -Path "Registry::HKEY_USERS" -ErrorAction SilentlyContinue | Where-Object {
        $_.PSChildName -match '^S-1-5-21-' -and -not $_.PSChildName.EndsWith('_Classes')
    } | ForEach-Object {
        $regAppRoots += "$($_.PSPath)\Software\RegisteredApplications"
        $regAppRoots += "$($_.PSPath)\Software\RegisteredApplications\PackagedApps"
    }
    foreach ($regAppRoot in ($regAppRoots | Select-Object -Unique)) {
        if (Test-Path $regAppRoot) {
            $props = (Get-ItemProperty -Path $regAppRoot -ErrorAction SilentlyContinue).psobject.properties
            foreach ($prop in $props) {
                if ($prop.Name -match '^PS') { continue }
                $propName = $prop.Name
                $propVal = [string]$prop.Value
                $shouldDelete = $false
                foreach ($tName in $allTargetNames) {
                    $token = ($tName -split '_')[0].Replace('Microsoft.', '')
                    if ($propName -match $token -or $propVal -match $token -or ($hasSecHealth -and ($propName -match 'SecHealth' -or $propVal -match 'SecHealth')) -or $propName -match 'FamilySafety|People|ScreenSketch|QuickAssist|Xbox' -or $propVal -match 'FamilySafety|People|ScreenSketch|QuickAssist|Xbox') {
                        $shouldDelete = $true
                        break
                    }
                }
                if ($shouldDelete) {
                    Remove-ItemProperty -Path $regAppRoot -Name $propName -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }

    # Hayalet Protokol ve URLAssociations Tasfiyesi (ms-wpc, ms-edu-secureassessment, xbox-tcui, edge)
    $ghostProtocols = @('ms-wpc', 'ms-edu-secureassessment', 'xbox-tcui', 'microsoft-edge', 'microsoft-edge-holographic', 'read')
    foreach ($proto in $ghostProtocols) {
        foreach ($hive in @('HKCR:\', 'HKLM:\SOFTWARE\Classes\', 'HKCU:\Software\Classes\')) {
            $pKey = "$hive$proto"
            if (Test-Path $pKey) { Remove-Item -LiteralPath $pKey -Recurse -Force -ErrorAction SilentlyContinue }
        }
        & reg.exe delete "HKCR\$proto" /f /reg:64 2>$null | Out-Null
        & reg.exe delete "HKLM\SOFTWARE\Classes\$proto" /f /reg:64 2>$null | Out-Null
        & reg.exe delete "HKCU\Software\Classes\$proto" /f /reg:64 2>$null | Out-Null
        & reg.exe delete "HKCU\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\$proto" /f 2>$null | Out-Null
        Get-ChildItem -Path "Registry::HKEY_USERS" -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -match '^S-1-5-21-' } | ForEach-Object {
            & reg.exe delete "HKU\$($_.PSChildName)\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\$proto" /f 2>$null | Out-Null
            & reg.exe delete "HKU\$($_.PSChildName)_Classes\$proto" /f 2>$null | Out-Null
        }
    }

    # 0. UCPD (User Choice Protection Driver) devredisi birakilarak UserChoice anahtarlarinin silinmesi saglanir
    & sc.exe stop ucpd 2>$null | Out-Null
    & sc.exe config ucpd start= disabled 2>$null | Out-Null
    & schtasks.exe /change /tn "\Microsoft\Windows\AppModel\UCPD\UCPD" /disable 2>$null | Out-Null
    & schtasks.exe /change /tn "\Microsoft\Windows\Shell\UCPD" /disable 2>$null | Out-Null

    # Alternatif Tarayıcı Tespiti (Varsayılan web tarayıcısı devri için)
    $installedBrowsers = @()
    foreach ($bKey in @('HKLM:\SOFTWARE\Clients\StartMenuInternet', 'HKCU:\Software\Clients\StartMenuInternet')) {
        if (Test-Path $bKey) {
            Get-ChildItem -LiteralPath $bKey -ErrorAction SilentlyContinue | ForEach-Object {
                if ($_.PSChildName -notmatch 'Microsoft Edge|IEXPLORE.EXE') {
                    $installedBrowsers += $_.PSChildName
                }
            }
        }
    }
    $fallbackBrowser = if ($installedBrowsers.Count -gt 0) { $installedBrowsers[0] } else { $null }

    # StartMenuInternet Edge kaydının tasfiyesi
    Remove-Item "HKLM:\SOFTWARE\Clients\StartMenuInternet\Microsoft Edge" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "HKCU:\Software\Clients\StartMenuInternet\Microsoft Edge" -Recurse -Force -ErrorAction SilentlyContinue
    if ($fallbackBrowser) {
        Set-ItemProperty -Path "HKLM:\SOFTWARE\Clients\StartMenuInternet" -Name '(default)' -Value $fallbackBrowser -Force -ErrorAction SilentlyContinue
        Set-ItemProperty -Path "HKCU:\Software\Clients\StartMenuInternet" -Name '(default)' -Value $fallbackBrowser -Force -ErrorAction SilentlyContinue
    } else {
        Set-ItemProperty -Path "HKLM:\SOFTWARE\Clients\StartMenuInternet" -Name '(default)' -Value '' -Force -ErrorAction SilentlyContinue
        Set-ItemProperty -Path "HKCU:\Software\Clients\StartMenuInternet" -Name '(default)' -Value '' -Force -ErrorAction SilentlyContinue
    }

    # Kullanıcı Kovanları (HKCU ve tüm aktif HKU profilleri)
    $userHives = @('HKCU:')
    Get-ChildItem -Path "HKU:\" -ErrorAction SilentlyContinue | Where-Object {
        $_.PSChildName -match '^S-1-5-21-' -and -not $_.PSChildName.EndsWith('_Classes')
    } | ForEach-Object {
        $userHives += "HKU:\$($_.PSChildName)"
    }

    # Sistemde hala yüklü olan tüm meşru paketlerin Family ve Name listesini al
    $installedAppxList = @(Get-AppxPackage -AllUsers -ErrorAction SilentlyContinue | ForEach-Object { $_.PackageFamilyName, $_.PackageFullName })

    # Korunan meşru sistem uygulamaları (Not Defteri, Terminal, Paint, Explorer, Store vb.) ASLA ölü sayılamaz
    $protectedAppNames = @('Microsoft.WindowsNotepad', 'Microsoft.WindowsTerminal', 'Microsoft.Paint', 'Microsoft.WindowsStore', 'windows.immersivecontrolpanel')

    # Bir ProgID'nin gerçekten ölü olup olmadığını (silinmiş uygulamaya ait veya hedefi olmayan) tespit eden akıllı fonksiyon:
    function Test-IsDeadProgId([string]$progId) {
        if (-not $progId) { return $false }
        if ($progId -match '(?i)^(MSEdgeHTM|MSEdgePDF|MSEdgeMHT|MSEdgeBHO|msrating\.DYNLINK)') { return $true }

        # Eğer AppX ile başlıyorsa hedef paketini adli olarak kontrol et
        if ($progId -match '(?i)^AppX') {
            $appPath = "HKCR:\$progId"
            if (-not (Test-Path -LiteralPath $appPath)) { return $true }

            $appName = (Get-ItemProperty -LiteralPath "$appPath\Application" -Name "ApplicationName" -ErrorAction SilentlyContinue).ApplicationName
            if (-not $appName) {
                $cmdVal = (Get-ItemProperty -LiteralPath "$appPath\Shell\open\command" -Name "(default)" -ErrorAction SilentlyContinue).'(default)'
                $appName = $cmdVal
            }
            if ($appName) {
                foreach ($prot in $protectedAppNames) {
                    if ($appName -match [regex]::Escape($prot)) { return $false }
                }
                foreach ($tName in $allTargetNames) {
                    $token = ($tName -split '_')[0]
                    if ($appName -match [regex]::Escape($token)) { return $true }
                }
                $isInstalled = $false
                foreach ($inst in $installedAppxList) {
                    if ($inst -and $appName -match [regex]::Escape(($inst -split '_')[0])) {
                        $isInstalled = $true
                        break
                    }
                }
                if (-not $isInstalled) { return $true }
            } else {
                return $true
            }
        }
        return $false
    }

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

    # 1. URL Protokolleri UserChoice ve Protokol Köklerinin Arındırılması
    $allProtocols = @('http', 'https', 'ftp', 'read', 'microsoft-edge', 'microsoft-edge-holographic', 'ms-screenclip', 'ms-stickynotes', 'ms-whiteboard', 'ms-gamebar', 'xbox-tcui', 'ms-people', 'ms-cortana', 'ms-gethelp', 'ms-officeapp', 'ms-windowsbackup', 'ms-wpc', 'ms-edu-secureassessment')
    foreach ($uh in $userHives) {
        foreach ($proto in $allProtocols) {
            $urlUc = "$uh\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\$proto\UserChoice"
            if (Test-Path -LiteralPath $urlUc) {
                $pVal = (Get-ItemProperty -LiteralPath $urlUc -Name "ProgId" -ErrorAction SilentlyContinue).ProgId
                if (Test-IsDeadProgId $pVal) {
                    Remove-UserChoiceKey $urlUc
                }
            }
        }
    }

    # 2. Dosya Uzantıları (FileExts) UserChoice, OpenWithProgids, OpenWithList Arındırılması (.txt, .ini, .log, .rtf KORUNUR)
    $allTargetExtensions = @(
        '.htm', '.html', '.shtml', '.xht', '.xhtml', '.pdf', '.svg', '.xml',
        '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.ico', '.webp', '.tif', '.tiff', '.heic', '.heif', '.avif',
        '.mp3', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.flac', '.wav', '.aac', '.m4a', '.wma', '.webm',
        '.prf', '.rat', '.pbk'
    )
    foreach ($uh in $userHives) {
        $fileExtsRoot = "$uh\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"
        if (Test-Path -LiteralPath $fileExtsRoot) {
            foreach ($ext in $allTargetExtensions) {
                $extPath = Join-Path $fileExtsRoot $ext
                if (Test-Path -LiteralPath $extPath) {
                    $ucPath = Join-Path $extPath "UserChoice"
                    if (Test-Path -LiteralPath $ucPath) {
                        $pVal = (Get-ItemProperty -LiteralPath $ucPath -Name "ProgId" -ErrorAction SilentlyContinue).ProgId
                        if (Test-IsDeadProgId $pVal) {
                            Remove-UserChoiceKey $ucPath
                        }
                    }
                    $owp = Join-Path $extPath "OpenWithProgids"
                    if (Test-Path -LiteralPath $owp) {
                        (Get-ItemProperty -LiteralPath $owp -ErrorAction SilentlyContinue).PSObject.Properties | Where-Object {
                            Test-IsDeadProgId $_.Name
                        } | ForEach-Object {
                            Remove-ItemProperty -LiteralPath $owp -Name $_.Name -Force -ErrorAction SilentlyContinue
                        }
                    }
                    $owl = Join-Path $extPath "OpenWithList"
                    if (Test-Path -LiteralPath $owl) {
                        (Get-ItemProperty -LiteralPath $owl -ErrorAction SilentlyContinue).PSObject.Properties | Where-Object {
                            $_.Value -match 'msedge|photoviewer|msrating'
                        } | ForEach-Object {
                            Remove-ItemProperty -LiteralPath $owl -Name $_.Name -Force -ErrorAction SilentlyContinue
                        }
                    }
                }
            }
        }
    }

    # 3. HKCR ve HKLM\Classes Seviyesinde Yetim ProgID Köklerinin ve Uzantı (Default) Değerlerinin Tasfiyesi
    $deadProgIdRoots = @('MSEdgeHTM', 'MSEdgePDF', 'MSEdgeMHT', 'MSEdgeBHO', 'msrating.DYNLINK')
    foreach ($dpr in $deadProgIdRoots) {
        foreach ($hive in @('HKCR:\', 'HKLM:\SOFTWARE\Classes\', 'HKCU:\Software\Classes\')) {
            $dpKey = "$hive$dpr"
            if (Test-Path -LiteralPath $dpKey) {
                Remove-Item -LiteralPath $dpKey -Recurse -Force -ErrorAction SilentlyContinue
                $regKey = $dpKey -replace '^HKCR:\\', 'HKCR\' -replace '^HKLM:\\', 'HKLM\' -replace '^HKCU:\\', 'HKCU\'
                & reg.exe delete "$regKey" /f /reg:64 2>$null | Out-Null
            }
        }
        foreach ($uh in $userHives) {
            $userClsKey = "$uh\Software\Classes\$dpr"
            if (Test-Path -LiteralPath $userClsKey) {
                Remove-Item -LiteralPath $userClsKey -Recurse -Force -ErrorAction SilentlyContinue
                $regKey = $userClsKey -replace '^HKU:\\', 'HKU\' -replace '^HKCU:\\', 'HKCU\'
                & reg.exe delete "$regKey" /f /reg:64 2>$null | Out-Null
            }
        }
    }

    # HKCR:\AppX* altındaki ölü kalıntı ProgID anahtarlarını sil
    Get-ChildItem -Path "HKCR:\" -Filter "AppX*" -ErrorAction SilentlyContinue | ForEach-Object {
        $pName = $_.PSChildName
        if (Test-IsDeadProgId $pName) {
            Remove-Item -LiteralPath "HKCR:\$pName" -Recurse -Force -ErrorAction SilentlyContinue
            & reg.exe delete "HKCR\$pName" /f /reg:64 2>$null | Out-Null
            foreach ($uh in $userHives) {
                $uhReg = $uh -replace '^HKU:\\', 'HKU\' -replace '^HKCU:\\', 'HKCU\'
                Remove-Item -LiteralPath "$uh\Software\Classes\$pName" -Recurse -Force -ErrorAction SilentlyContinue
                & reg.exe delete "$uhReg\Software\Classes\$pName" /f /reg:64 2>$null | Out-Null
            }
        }
    }

    foreach ($ext in $allTargetExtensions) {
        foreach ($hive in @('HKCR:\', 'HKLM:\SOFTWARE\Classes\', 'HKCU:\Software\Classes\')) {
            $kePath = "$hive$ext"
            if (Test-Path $kePath) {
                $defVal = (Get-ItemProperty -LiteralPath $kePath -Name '(default)' -ErrorAction SilentlyContinue).'(default)'
                if ($defVal -and (Test-IsDeadProgId $defVal)) {
                    Set-ItemProperty -LiteralPath $kePath -Name '(default)' -Value '' -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }

    # Not Defteri dosya ilişkilendirmesini güvenceye al (.txt, .ini, .log, .rtf)
    if (-not (Test-Path "HKCR:\.txt")) { New-Item -Path "HKCR:\.txt" -Force | Out-Null }
    $txtDef = (Get-ItemProperty -LiteralPath "HKCR:\.txt" -Name "(default)" -ErrorAction SilentlyContinue).'(default)'
    if (-not $txtDef -or $txtDef -eq '') {
        Set-ItemProperty -LiteralPath "HKCR:\.txt" -Name "(default)" -Value 'txtfile' -Force -ErrorAction SilentlyContinue
    }

    foreach ($pkgName in $allTargetNames) {
        $pkgFamily = ($pkgName -split '_')[0]
        $regTargets = @(
            "HKLM:\SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\PackageRepository\Packages\$pkgName",
            "HKLM:\SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\PackageRepository\State\$pkgName",
            "HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages\$pkgName",
            "HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Families\$pkgFamily",
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Applications\$pkgName",
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\InboxApplications\$pkgName",
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Staged\$pkgName",
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Deleted\$pkgName",
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$pkgName",
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\$pkgName",
            "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$pkgName"
        )
        foreach ($rt in $regTargets) {
            if (Test-Path -LiteralPath $rt) {
                Remove-Item -LiteralPath $rt -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
} catch {
    $failure = [string]$_.Exception.Message
} finally {
    for ($attempt = 0; $attempt -lt 6; $attempt++) {
        & sc.exe start StateRepository 2>$null | Out-Null
        $st = (Get-Service -Name StateRepository -ErrorAction SilentlyContinue).Status
        if ($st -eq 'Running') { break }
        Start-Sleep -Milliseconds 500
    }
    foreach ($serviceName in $servicesToRestart) {
        if ($serviceName -ne 'StateRepository') {
            & sc.exe start $serviceName 2>$null | Out-Null
        }
    }
    & sc.exe config camsvc start= auto 2>$null | Out-Null
    & sc.exe start camsvc 2>$null | Out-Null
}

if ($failure) {
    Write-Warning $failure
}

try {
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        if ((Get-Service -Name StateRepository -ErrorAction SilentlyContinue).Status `
            -eq 'Running') { break }
        Start-Sleep -Milliseconds 250
    }
    if ((Get-Service -Name StateRepository -ErrorAction SilentlyContinue).Status `
        -ne 'Running') {
        Write-Warning 'StateRepository did not reach Running after SCM restore.'
    }
    foreach ($package in $packages) {
        Get-AppxPackage -AllUsers -PackageTypeFilter Bundle,Framework,Main,Resource `
            -ErrorAction SilentlyContinue |
            Where-Object { $_.PackageFullName -eq $package } |
            Remove-AppxPackage -AllUsers -Confirm:$false -ErrorAction SilentlyContinue
    }
    $remainingPackages = @(Get-AppxPackage -AllUsers `
        -PackageTypeFilter Bundle,Framework,Main,Resource -ErrorAction SilentlyContinue |
        Where-Object { $packages -contains $_.PackageFullName })
    if ($remainingPackages.Count -gt 0) {
        Write-Warning ('Remaining packages: ' + (($remainingPackages | ForEach-Object {
            $_.PackageFullName
        }) -join '|'))
    }
} catch {
    Write-Warning ([string]$_.Exception.Message)
}
exit 0
"""
        script = script_template.replace("__PACKAGE_PAYLOAD__", package_payload)
        return run_powershell_as_trustedinstaller(script, timeout=300)

    if remove_crossdevice:
        deploy_winkit_silent()
        quiesce_crossdevice_components()
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Policies\Microsoft\Windows\System",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
            ) as policy_key:
                for value_name in (
                    "EnableCdp",
                    "EnableMmx",
                    "EnableActivityFeed",
                    "PublishUserActivities",
                    "UploadUserActivities",
                ):
                    winreg.SetValueEx(
                        policy_key,
                        value_name,
                        0,
                        winreg.REG_DWORD,
                        0,
                    )
        except OSError:
            pass

    if remove_edge:
        edge_unpin_script = """
try {
    $shell = New-Object -ComObject Shell.Application
    $appsFolder = $shell.Namespace('shell:AppsFolder')
    foreach ($appId in @(
        'MSEdge',
        'Microsoft.MicrosoftEdge_8wekyb3d8bbwe!MicrosoftEdge'
    )) {
        try { $appsFolder.ParseName($appId).InvokeVerb('taskbarunpin') } catch {}
    }
} catch {}
"""
        edge_unpin_encoded = base64.b64encode(
            edge_unpin_script.encode("utf-16le")
        ).decode("ascii")
        subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                edge_unpin_encoded,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=30,
            check=False,
        )
        for process_name in ("msedge.exe", "identity_helper.exe", "msedge_proxy.exe"):
            subprocess.run(
                ["taskkill", "/f", "/im", process_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
        if ui_queue:
            ui_queue.put({
                "action": "progress_update",
                "text_base": (
                    "Windows uygulamaları kaldırılıyor"
                    " · Microsoft Edge"
                ),
                "pct": None,
                "color": "#E2E2E2",
                "target": "debloat",
            })

    if remove_onedrive:
        for process_name in (
            "OneDrive.exe",
            "FileCoAuth.exe",
            "OneDrive.Sync.Service.exe",
            "OneDriveStandaloneUpdater.exe",
        ):
            subprocess.run(
                ["taskkill", "/f", "/im", process_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
        setup_path = next(
            (
                candidate
                for candidate in (
                    windows_dir / "SysWOW64" / "OneDriveSetup.exe",
                    windows_dir / "System32" / "OneDriveSetup.exe",
                )
                if candidate.is_file()
            ),
            None,
        )
        if setup_path:
            if ui_queue:
                ui_queue.put({
                    "action": "progress_update",
                    "text_base": (
                        "Windows uygulamaları kaldırılıyor"
                        " · Microsoft OneDrive"
                    ),
                    "pct": None,
                    "color": "#E2E2E2",
                    "target": "debloat",
                })
            subprocess.run(
                [str(setup_path), "/uninstall"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                timeout=240,
                check=False,
            )
        # Kaldırıcı updater/sync süreçlerini yeniden başlatabiliyor; tarama ve
        # dosya temizliği öncesinde ikinci kez kapat.
        for process_name in (
            "OneDrive.exe",
            "FileCoAuth.exe",
            "OneDrive.Sync.Service.exe",
            "OneDriveStandaloneUpdater.exe",
        ):
            subprocess.run(
                ["taskkill", "/f", "/im", process_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
    if targets and ui_queue:
        ui_queue.put({
            "action": "progress_stop",
            "text_base": "Windows uygulamaları kaldırılıyor",
            "result": "kaldırıldı",
            "target": "debloat",
        })

    package_tokens = {
        target.casefold()
        for target in targets
        if "startexperiences" not in target.casefold()
    }
    full_identity_tokens = set()
    exact_install_locations = set()
    deprovisioned_families = set()
    for package in appx_metadata.get("Packages") or []:
        for field in ("Name", "PackageFullName", "PackageFamilyName"):
            value = str(package.get(field) or "").strip()
            if value and "startexperiences" not in value.casefold():
                full_identity_tokens.add(value.casefold())
                if field == "PackageFamilyName":
                    deprovisioned_families.add(value)
        install_location = str(package.get("InstallLocation") or "").strip()
        if install_location and "startexperiences" not in install_location.casefold():
            exact_install_locations.add(Path(install_location))
    for package in appx_metadata.get("Provisioned") or []:
        for field in ("DisplayName", "PackageName"):
            value = str(package.get(field) or "").strip()
            if value and "startexperiences" not in value.casefold():
                full_identity_tokens.add(value.casefold())
        display_name = str(package.get("DisplayName") or "").strip()
        package_name = str(package.get("PackageName") or "").strip()
        publisher_id = package_name.rsplit("_", 1)[-1] if "_" in package_name else ""
        if display_name and re.fullmatch(r"[A-Za-z0-9]{8,20}", publisher_id):
            deprovisioned_families.add(f"{display_name}_{publisher_id}")
        install_location = str(package.get("InstallLocation") or "").strip()
        if install_location and "startexperiences" not in install_location.casefold():
            exact_install_locations.add(Path(install_location))

    if remove_edge:
        full_identity_tokens.update(
            {
                "microsoft.microsoftedge",
                "microsoftedge",
                "microsoft edge",
                "msedge",
            }
        )
    if remove_crossdevice:
        full_identity_tokens.update(
            {
                "microsoftwindows.crossdevice",
            }
        )
    if remove_onedrive:
        full_identity_tokens.update({"microsoft.onedrive", "microsoft onedrive", "onedrive"})

    # Revo Uninstaller standardında dinamik token genişletmesi
    expanded_tokens = set()
    for t in targets:
        tl = str(t).casefold()
        if "startexperiences" in tl:
            continue
        expanded_tokens.add(tl)
        for prefix in ("microsoft.", "microsoftwindows.", "microsoftcorporationii.", "windows."):
            if tl.startswith(prefix):
                sub = tl[len(prefix):]
                if len(sub) >= 4:
                    expanded_tokens.add(sub)

        if "sechealth" in tl or "defender" in tl:
            expanded_tokens.update({
                "sechealthui", "windowsdefender", "sechealthui.exe", "windows.sechealthui",
                "{d68ddc3a-831f-4fae-9e44-da132c1acf46}",
                "appx1sy7rwrc20ggq97a6x1mgmjat0rthy51",
                "appxb5yxv86nkhp530y0y50yxe69c1qwad1x",
                "appxe20yrenndd9ss1yt7r047971sex4f21n"
            })
        # Otomatik dinamik token genişletmesi
        cleaned_target = re.sub(r"^(?:microsoft\.|microsoftwindows\.|microsoftcorporationii\.|windows\.)", "", tl)
        if len(cleaned_target) >= 4:
            expanded_tokens.add(cleaned_target)
            expanded_tokens.add(f"{cleaned_target}.exe")
            expanded_tokens.add(f"{cleaned_target}app.exe")
            stem = re.sub(r"(app|desktop|extension|extensions|platformruntime|experience)$", "", cleaned_target)
            if len(stem) >= 4 and stem not in {
                "widgets", "gaming", "device", "experience", "runtime", "client",
                "service", "start", "cloud", "game", "core", "quick", "media",
                "video", "audio", "voice", "calc", "time", "sync", "assist", "update", "tools",
                "startexperiences", "startexperience"
            }:
                expanded_tokens.add(stem)
                expanded_tokens.add(f"{stem}.exe")
        if "crossdevice" in tl:
            expanded_tokens.update({"crossdeviceresume", "crossdeviceexperience", "crossdeviceresume.exe"})
        if "webexperience" in tl or "widgetsplatform" in tl:
            expanded_tokens.update({"webexperience", "widgetsplatformruntime", "widgetservice.exe"})
        if "quickassist" in tl:
            expanded_tokens.update({"quickassist", "quickassist.exe"})
        if "todos" in tl:
            expanded_tokens.update({"todos", "microsoft.todos"})
        if "weather" in tl:
            expanded_tokens.update({"bingweather", "weather.exe"})
        if "news" in tl:
            expanded_tokens.update({"bingnews", "news.exe"})
        if "photos" in tl:
            expanded_tokens.update({"photosapp.exe", "microsoft.photos"})
        if "camera" in tl:
            expanded_tokens.update({"windowscamera", "camera.exe"})
        if "calculator" in tl:
            expanded_tokens.update({"windowscalculator", "calculatorapp.exe"})
        if "soundrecorder" in tl:
            expanded_tokens.update({"windowssoundrecorder", "soundrecorder.exe"})
        if "solitaire" in tl:
            expanded_tokens.update({"solitairecollection", "solitaire"})
        if "powerautomate" in tl:
            expanded_tokens.update({"powerautomatedesktop", "powerautomate"})
        if "yourphone" in tl or "phone" in tl:
            expanded_tokens.update({"yourphone", "phonelink", "phoneexperiencehost"})
        if "coreai" in tl or "aix" in tl:
            expanded_tokens.update({"client.coreai", "coreai", "aixhost", "aixhost.exe", "clicktodo"})
        if "xbox" in tl or "gamebar" in tl or "gamingoverlay" in tl:
            expanded_tokens.update({"xboxgamingoverlay", "xboxgameoverlay", "bcastdvr"})

    full_identity_tokens.update(expanded_tokens)
    blocked_generic_tokens = {
        "microsoft", "windows", "system", "systemapps", "program files",
        "people", "paint", "news", "maps", "edge", "calling", "camera",
        "photos", "phone", "help", "store", "security", "certificates",
        "systemcertificates", "trustedpeople", "widgets", "gaming", "device",
        "experience", "runtime", "client", "service", "start", "cloud",
        "game", "core", "quick", "media", "video", "audio", "voice",
        "calc", "time", "sync", "assist", "update", "tools",
        "startexperience", "startexperiences", "startexperiencesapp",
    }
    full_identity_tokens = {
        token for token in full_identity_tokens
        if len(token) >= 4 and token not in blocked_generic_tokens
    }
    full_identity_tokens.update(
        token
        for token in package_tokens
        if len(token) >= 4 and token not in blocked_generic_tokens
    )
    identity_pattern = (
        re.compile(
            "|".join(
                re.escape(token)
                for token in sorted(
                    full_identity_tokens,
                    key=len,
                    reverse=True,
                )
            ),
        )
        if full_identity_tokens
        else None
    )
    protected_edge_tokens = (
        "webview2",
        "edgewebview",
        "microsoftedgeupdate",
        "\\edgeupdate",
        "/edgeupdate",
        "\\edgeupdate\\",
        "/edgeupdate/",
    )

    def text_matches_identity(value):
        if value is None:
            return False
        candidates = []
        if isinstance(value, bytes):
            try:
                candidates.append(value.decode("latin-1", errors="ignore").casefold())
            except Exception:
                pass
            # Taskband/Start önbelleği gibi REG_BINARY alanlarında UTF-16 metin
            # her zaman sıfırıncı bayttan başlamayabilir; iki hizalamayı da tara.
            for offset in (0, 1):
                try:
                    candidates.append(
                        value[offset:].decode("utf-16le", errors="ignore").casefold()
                    )
                except Exception:
                    pass
        else:
            candidates.append(str(value).casefold())

        for text in candidates:
            if remove_edge and any(protected in text for protected in protected_edge_tokens):
                return False
            if identity_pattern and identity_pattern.search(text):
                return True
            if remove_edge and re.search(r"(?<![a-z0-9])(msedge|microsoft\s+edge)(?![a-z0-9])", text):
                return True
            if remove_edge and (
                "\\microsoft\\edge" in text
                or "/microsoft/edge" in text
                or re.search(r"(^|[\\/])edge([\\/]|$)", text)
            ):
                return True
            if remove_onedrive and re.search(r"(?<![a-z0-9])onedrive(?![a-z0-9])", text):
                return True
        return False

    def path_matches_identity(path):
        path_text = str(path)
        if text_matches_identity(path_text):
            return True
        name = Path(path).name.casefold()
        for token in package_tokens:
            if name == token or name.startswith(token + "_"):
                return True
        return False

    search_roots = [
        (program_files, 15),
        (program_files_x86, 15),
        (program_data, 15),
        (program_data / "Packages", 15),
        (program_files / "WindowsApps", 15),
        (program_files / "WindowsApps" / "Deleted", 15),
        (windows_dir / "SystemApps", 12),
        (windows_dir / "System32" / "Tasks", 8),
        (windows_dir / "ShellExperiences", 8),
        (windows_dir / "Temp", 8),
        (windows_dir / "Installer", 8),
        (windows_dir / "Prefetch", 4),
        (windows_dir / "Downloaded Installations", 8),
        (windows_dir / "bcastdvr", 8),
        (windows_dir / "BrowserCore", 8),
        (windows_dir / "DiagTrack", 8),
        (windows_dir / "DigitalLocker", 8),
        (windows_dir / "InboxApps", 8),
    ]
    if users_dir.is_dir():
        try:
            user_dirs = list(users_dir.iterdir())
        except OSError:
            user_dirs = []
        for user_dir in user_dirs:
            if not user_dir.is_dir() or user_dir.name.casefold() in {
                "public", "default", "default user", "all users"
            }:
                continue
            search_roots.extend(
                [
                    (user_dir / "AppData" / "Local", 15),
                    (user_dir / "AppData" / "LocalLow", 15),
                    (user_dir / "AppData" / "Roaming", 15),
                    (user_dir / "Desktop", 5),
                    (user_dir / "AppData" / "Local" / "Packages", 15),
                ]
            )
    search_roots.extend(
        [
            (program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs", 10),
            (users_dir / "Public" / "Desktop", 5),
        ]
    )
    try:
        for item in Path(system_drive).iterdir():
            if item.is_dir() and item.name.casefold() not in {
                "windows", "$recycle.bin", "system volume information",
                "recovery", "msocache", "perflogs", "program files",
                "program files (x86)", "programdata", "users", "boot", "efi"
            }:
                search_roots.append((item, 5))
    except OSError:
        pass

    if remove_edge:
        # C:\Program Files (x86)\Microsoft altındaki EdgeWebView HARİÇ tüm klasörler silinir
        ms_x86 = program_files_x86 / "Microsoft"
        if ms_x86.is_dir():
            try:
                for sub in ms_x86.iterdir():
                    if sub.is_dir() and sub.name.casefold() != "edgewebview":
                        exact_install_locations.add(sub)
            except OSError:
                pass

        exact_install_locations.update(
            {
                program_files / "Microsoft" / "Edge",
                program_files / "Microsoft" / "EdgeCore",
                program_files / "Microsoft" / "EdgeUpdate",
                program_data / "Microsoft" / "EdgeUpdate",
            }
        )
        if users_dir.is_dir():
            for user_dir in user_dirs:
                exact_install_locations.update(
                    {
                        user_dir / "AppData" / "Local" / "Microsoft" / "Edge",
                        user_dir / "AppData" / "Local" / "Microsoft" / "EdgeCore",
                        user_dir / "AppData" / "Local" / "Microsoft" / "EdgeUpdate",
                    }
                )

        # Edge Application klasörlerindeki sürüm dizinleri silinir (EdgeWebView KESİNLİKLE DOKUNULMAZDIR)
        for base_edge in (
            program_files_x86 / "Microsoft" / "Edge" / "Application",
            program_files / "Microsoft" / "Edge" / "Application",
        ):
            if base_edge.is_dir():
                try:
                    for child in base_edge.iterdir():
                        if child.is_dir():
                            exact_install_locations.add(child)
                except Exception:
                    pass

    if remove_onedrive:
        exact_install_locations.update(
            {
                program_files / "Microsoft OneDrive",
                program_files_x86 / "Microsoft OneDrive",
                program_data / "Microsoft OneDrive",
                program_data / "Microsoft" / "OneDrive",
            }
        )
        if users_dir.is_dir():
            for user_dir in user_dirs:
                exact_install_locations.update(
                    {
                        user_dir / "AppData" / "Local" / "Microsoft" / "OneDrive",
                        user_dir / "AppData" / "Local" / "Microsoft" / "OneDriveStandaloneUpdater",
                        user_dir / "AppData" / "Roaming" / "Microsoft" / "OneDrive",
                    }
                )

    # ProgramData\Packages altındaki AI ve bloat klasörlerini doğrudan ekle
    pkg_data_dir = program_data / "Packages"
    if pkg_data_dir.is_dir():
        try:
            for pkg_dir in pkg_data_dir.iterdir():
                if pkg_dir.is_dir():
                    p_name = pkg_dir.name.casefold()
                    if any(ai_tok in p_name for ai_tok in ("coreai", "aix", "clicktodo")):
                        exact_install_locations.add(pkg_dir)
        except OSError:
            pass

    # Windows\SystemApps altındaki hedeflenen bloat klasörlerini doğrudan ekle
    sysapps_dir = windows_dir / "SystemApps"
    if sysapps_dir.is_dir():
        try:
            for sys_dir in sysapps_dir.iterdir():
                if sys_dir.is_dir():
                    s_name = sys_dir.name.casefold()
                    if any(tok in s_name for tok in ("xboxgamingoverlay", "xboxgameoverlay")):
                        exact_install_locations.add(sys_dir)
        except OSError:
            pass

    if users_dir.is_dir():
        for user_dir in user_dirs:
            user_pkgs = user_dir / "AppData" / "Local" / "Packages"
            if user_pkgs.is_dir():
                try:
                    for upkg in user_pkgs.iterdir():
                        if upkg.is_dir():
                            upkg_name = upkg.name.casefold()
                            if any(tok in upkg_name for tok in ("coreai", "aix")):
                                exact_install_locations.add(upkg)
                except OSError:
                    pass

    never_delete = {
        Path(system_drive),
        windows_dir,
        windows_dir / "System32",
        windows_dir / "SysWOW64",
        windows_dir / "WinSxS",
        windows_dir / "SystemApps",
        program_files,
        program_files_x86,
        program_data,
        users_dir,
        program_files / "Microsoft" / "EdgeWebView",
        program_files_x86 / "Microsoft" / "EdgeWebView",
    }

    # Bunlar seçilebilir uygulamalar değil, Başlat/Explorer kabuğunun çalışma
    # alanlarıdır. Koruma yalnız tam paket klasörü bileşenlerine uygulanır;
    # WindowsApps altındaki seçili bağımsız paketlerin kesin InstallLocation
    # klasörleri etkilenmez.
    protected_shell_path_components = (
        "microsoftwindows.client.cbs",
        "microsoftwindows.client.core",
        "microsoft.windows.shellexperiencehost",
        "microsoft.windows.startmenuexperiencehost",
        "microsoft.startexperiencesapp",
        "startexperiencesapp",
        "microsoft.windows.search",
        "microsoft.asynctextservice",
        "microsoft.windows.addsuggestedfolderstolibrarydialog",
        "microsoft.windowsappruntime",
        "microsoft.windowsstore",
        "microsoft.ui.xaml",
        "microsoft.vclibs",
        "microsoft.net.native",
        "_mei",
    )

    def path_has_protected_shell_component(path):
        try:
            parts = Path(path).parts
        except (TypeError, ValueError):
            return False
        for part in parts:
            component = str(part).casefold()
            if any(
                component == prefix
                or component.startswith(prefix + "_")
                or component.startswith(prefix + ".")
                or prefix in component
                for prefix in protected_shell_path_components
            ):
                return True
        return False

    def deletion_allowed(path):
        try:
            resolved = Path(path).resolve()
        except OSError:
            resolved = Path(path).absolute()
        res_str = str(resolved).casefold()
        # EdgeWebView ve kritik kabuk koruması: Hiçbir koşulda silinemez!
        if "edgewebview" in res_str or "_mei" in res_str:
            return False
        if "startexperiences" in res_str:
            return False
        if path_has_protected_shell_component(resolved):
            return False
        if any(_same_path(resolved, blocked) for blocked in never_delete):
            return False
        # Eğer kesin hedef olarak belirlenmişse doğrudan izin ver
        if any(_same_path(resolved, exact_location) for exact_location in exact_install_locations):
            return True

        # SystemApps KORUMASI: Korunan kabuk bileşenleri hariç, hedeflenen bloat kaldırılabilir
        try:
            rel_sysapps = resolved.relative_to((windows_dir / "SystemApps").resolve())
            if path_has_protected_shell_component(resolved):
                return False
            if len(rel_sysapps.parts) == 0:
                return False
            return True
        except ValueError:
            pass

        # WindowsApps KORUMASI: Korunan kabuk paketleri hariç, hedeflenen bloat kaldırılır
        try:
            rel_winapps = resolved.relative_to((program_files / "WindowsApps").resolve())
            if path_has_protected_shell_component(resolved):
                return False
            if len(rel_winapps.parts) == 0:
                return False
            return True
        except ValueError:
            pass

        # Windows KORUMASI: Sistem çekirdek dosyaları korunur, hedeflenen bloat kaldırılır
        try:
            rel = resolved.relative_to(windows_dir.resolve())
            if path_has_protected_shell_component(resolved):
                return False
            if len(rel.parts) == 0:
                return False
            first_part = rel.parts[0].casefold()
            if first_part in ("winsxs", "servicing"):
                return False
            if first_part in ("system32", "syswow64"):
                if len(rel.parts) == 1:
                    return False
                if len(rel.parts) >= 2 and rel.parts[1].casefold() == "tasks":
                    return True
                if len(rel.parts) == 2:
                    return path_matches_identity(resolved)
                return False
            # Windows altındaki hedeflenen bloat klasörleri (bcastdvr, BrowserCore, DiagTrack, Temp, Prefetch vb.)
            return True
        except ValueError:
            pass

        return not path_has_protected_shell_component(resolved)

    file_scan_deadline = None
    file_scan_deadline_reached = threading.Event()
    file_scan_stats_lock = threading.Lock()
    file_scan_stats = {"directories": 0, "files": 0, "last_progress": 0.0}

    def scan_directory(root, max_depth):
        found = []
        if not root.is_dir():
            return found
        visited_dirs = set()
        stack = [(root, 0)]
        local_dirs = 0
        local_files = 0

        def flush_file_stats():
            nonlocal local_dirs, local_files
            if local_dirs == 0 and local_files == 0:
                return
            progress_base = None
            now = time.monotonic()
            with file_scan_stats_lock:
                file_scan_stats["directories"] += local_dirs
                file_scan_stats["files"] += local_files
                local_dirs = 0
                local_files = 0
                if now - file_scan_stats["last_progress"] >= 0.25:
                    file_scan_stats["last_progress"] = now
                    progress_base = (
                        "Disk kalıntıları taranıyor · "
                        f"{file_scan_stats['directories']:,} klasör · "
                        f"{file_scan_stats['files']:,} dosya"
                    ).replace(",", ".")
            if progress_base and ui_queue:
                ui_queue.put(
                    {
                        "action": "progress_update",
                        "text_base": progress_base,
                        "pct": None,
                        "color": "#FFB86C",
                        "target": "debloat",
                    }
                )

        excluded_dir_names = {
            "windows", "system32", "syswow64", "winsxs", "servicing",
            "driverstore", "assembly", "node_modules", ".git", ".vscode",
            ".idea", "__pycache__", "package cache", "cache", "caches",
            "gpu_cache", "code cache", "shadercache", "webcache"
        }

        while stack:
            if (
                file_scan_deadline is not None
                and time.monotonic() >= file_scan_deadline
            ):
                file_scan_deadline_reached.set()
                flush_file_stats()
                return found
            current, depth = stack.pop()
            curr_str = str(current).casefold()
            if curr_str in visited_dirs:
                continue
            visited_dirs.add(curr_str)
            if depth > max_depth:
                continue
            local_dirs += 1
            if local_dirs >= 100 or local_files >= 500:
                flush_file_stats()
            try:
                entries = []
                with os.scandir(current) as directory_entries:
                    for entry_index, entry in enumerate(directory_entries):
                        if (
                            entry_index % 128 == 0
                            and file_scan_deadline is not None
                            and time.monotonic() >= file_scan_deadline
                        ):
                            file_scan_deadline_reached.set()
                            flush_file_stats()
                            return found
                        entries.append(entry)
            except (PermissionError, OSError):
                continue
            for entry in entries:
                item_path = Path(entry.path)
                if path_has_protected_shell_component(item_path):
                    continue
                if path_matches_identity(item_path) and deletion_allowed(item_path):
                    found.append(item_path)
                    continue
                if entry.is_file(follow_symlinks=False):
                    local_files += 1
                    ext = item_path.suffix.casefold()
                    if ext in (".lnk", ".url"):
                        try:
                            if text_matches_identity(entry.name) and deletion_allowed(item_path):
                                found.append(item_path)
                                continue
                            st_size = entry.stat(follow_symlinks=False).st_size
                            if st_size < 32768:
                                content = item_path.read_bytes()
                                if text_matches_identity(content) and deletion_allowed(item_path):
                                    found.append(item_path)
                                    continue
                        except Exception:
                            pass
                if entry.is_dir(follow_symlinks=False) and depth < max_depth:
                    try:
                        st = entry.stat(follow_symlinks=False)
                        if getattr(st, "st_file_attributes", 0) & 0x0400:
                            continue
                    except Exception:
                        continue
                    if entry.name.casefold() not in excluded_dir_names:
                        sub_str = str(item_path).casefold()
                        if sub_str not in visited_dirs:
                            stack.append((item_path, depth + 1))
        flush_file_stats()
        return found

    # Revo Uninstaller standardında hızlı ve sıfır yalancı pozitifli Registry tarayıcısı.
    # HKLM\SOFTWARE, HKCU\Software ve tüm HKU kullanıcı ve _Classes kovanları taranır.
    # Göreceli Win32 tanıtıcı (handle) yürütmesiyle yüzbinlerce kayıt saniyeler içinde taranır.
    registry_views = [winreg.KEY_WOW64_64KEY]
    deprovisioned_prefix = (
        r"software\microsoft\windows\currentversion\appx"
        r"\appxalluserstore\deprovisioned"
    )

    protected_registry_infrastructure = (
        r"\sam",
        r"\security",
        r"\system\currentcontrolset\control\session manager",
        r"\system\currentcontrolset\control\systeminformation",
        r"\system\currentcontrolset\control\minint",
        r"\bcd00000000",
        r"\microsoft\windows nt\currentversion\profilelist",
        r"\microsoft\windows\currentversion\component based servicing",
        r"\microsoft\windows\currentversion\sidebyside",
        r"\microsoft\windows\currentversion\winsxs",
        r"\microsoft\windows\currentversion\installer",
        r"\systemcertificates",
        r"\certificates",
        r"\appmodel\staterepository",
        r"\shell\update",
        r"\microsoft\policymanager",
        r"\microsoft\provisioning",
        r"\applicationassociationtoasts",
        r"\explorer\aam",
        r"\services\sharedaccess\parameters\firewallpolicy",
        r"\policies\microsoft\windows\system",
        r"\windows search\uninstalledstoreapps",
        r"\userchoice",
    )
    shared_container_markers = (
        r"\registeredapplications",
        r"\registeredapplications\packagedapps",
        r"\microsoft\windows\currentversion\run",
        r"\microsoft\windows\currentversion\runonce",
        r"\startupapproved",
        r"\fileexts",
        r"\shareddlls",
        r"\firewallrules",
        r"\policies\explorer",
        r"\policies\system",
        r"\installservice\state\categorycache",
        r"\appmodel\staterepository\cache",
        r"\appmodel\packagerepository",
        r"\microsoft\windowsruntime",
        r"\local settings\mrtcache",
        r"\backgroundaccessapplications",
        r"\notifications\settings",
        r"\notifications\quiethours",
        r"\pushnotifications\backup",
        r"\applicationassociationtoasts",
        r"\muicache",
        r"\featureusage",
        r"\app paths",
        r"\uninstall",
        r"\software\microsoft\windows\shell\associations",
        r"\urlassociations",
        r"\classes",
        r"\classes\clsid",
        r"\classes\interface",
        r"\classes\typelib",
        r"\classes\appid",
        r"\classes\record",
        r"\clsid",
        r"\interface",
        r"\typelib",
        r"\appid",
        r"\record",
        r"\component categories",
        r"\protocols",
        r"\systemfileassociations",
        r"\directory",
        r"\folder",
        r"\drive",
        r"\allfilesystemobjects",
        r"\unknown",
        r"\applications",
        r"\systemsettings\settingid",
        r"\capabilityaccessmanager\capabilities",
        r"\windows search\uninstalledstoreapps",
        r"\authentication\logonui\notifications\backgroundcapability",
        r"\security center\provider",
        r"\securitymanager\capauthz",
        r"\textservicesframework",
        r"\ctf",
        r"\inputmethod",
        r"\immersivecontrolpanel",
        r"\openwithlist",
        r"\openwithprogids",
    )
    known_structural_containers = {
        "classes", "clsid", "interface", "typelib", "appid", "record",
        "component categories", "mime", "protocols", "systemfileassociations",
        "directory", "folder", "drive", "allfilesystemobjects", "unknown",
        "applications", "mediatype", "local settings", "registeredapplications",
        "packagedapps", "packagerepository", "windowsruntime", "mrtcache", "urlassociations",
        "run", "runonce", "startupapproved", "fileexts", "shareddlls",
        "firewallrules", "policies", "explorer", "system", "staterepository",
        "cache", "backgroundaccessapplications", "notifications", "settings",
        "pushnotifications", "applicationassociationtoasts", "muicache",
        "featureusage", "app paths", "uninstall", "settingid", "capabilities",
        "uninstalledstoreapps", "backgroundcapability", "provider", "capauthz",
        "package", "windows search", "currentversion", "microsoft", "windows",
        "software", "services", "currentcontrolset", "textservicesframework",
        "ctf", "inputmethod", "immersivecontrolpanel", "openwithlist", "openwithprogids"
    }
    protected_registry_package_components = (
        "microsoftwindows.client.cbs",
        "microsoftwindows.client.core",
        "microsoft.windows.shellexperiencehost",
        "microsoft.windows.startmenuexperiencehost",
        "microsoft.windows.search",
        "microsoft.windows.cloudexperiencehost",
        "microsoft.windows.shell",
        "microsoft.startexperiencesapp",
        "startexperiencesapp",
        "microsoftstartfeedprovider",
        "immersivecontrolpanel",
        "windows.immersivecontrolpanel",
        "microsoft.windowsappruntime",
        "microsoft.windowsstore",
        "microsoft.ui.xaml",
        "microsoft.vclibs",
        "microsoft.net.native",
    )

    def is_shared_container(sub_key):
        norm = "\\" + sub_key.casefold().replace("/", "\\").strip("\\")
        last_part = norm.rsplit("\\", 1)[-1]
        if last_part in known_structural_containers or last_part.startswith(".") or last_part.endswith("_classes"):
            return True
        for marker in shared_container_markers:
            m = marker.casefold()
            if norm == m or norm.endswith(m):
                return True
        return False

    def is_system_clsid(cur_key):
        for sub in ("InProcServer32", "LocalServer32"):
            try:
                with winreg.OpenKey(cur_key, sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as sk:
                    v, _ = winreg.QueryValueEx(sk, "")
                    vl = str(v).casefold()
                    if any(sys_token in vl for sys_token in ("system32", "syswow64", "servicing", "winsxs", "microsoft.net", "assembly")):
                        return True
            except OSError:
                pass
        return False

    def check_appx_progid_match(cur_key):
        stack = [(cur_key, 0)]
        while stack:
            k, d = stack.pop()
            try:
                sk_cnt, val_cnt, _ = winreg.QueryInfoKey(k)
                for vi in range(val_cnt):
                    vn, vd, _ = winreg.EnumValue(k, vi)
                    v_str = str(vd).casefold()
                    if any(sys_token in v_str for sys_token in ("system32", "syswow64", "servicing", "winsxs", "microsoft.net", "assembly")):
                        continue
                    if text_matches_identity(vn) or text_matches_identity(vd):
                        return True
                if d < 3:
                    for si in range(sk_cnt):
                        try:
                            sname = winreg.EnumKey(k, si)
                            if text_matches_identity(sname):
                                return True
                            sub_k = winreg.OpenKey(k, sname, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
                            stack.append((sub_k, d + 1))
                        except OSError:
                            pass
            except OSError:
                pass
            finally:
                if k != cur_key:
                    try:
                        k.Close()
                    except Exception:
                        pass
        return False

    def check_clsid_match(cur_key):
        # YALNIZCA sunucu binary ve ProgID degerleri kontrol edilir.
        # "" (varsayilan baslik/aciklama) asla kontrol edilmez; aksi takdirde sistem COM
        # aciklamalarindaki genel kelimeler (People, Photos vb.) sistem siniflarini siler!
        for sub in ("InProcServer32", "LocalServer32", "ProgID"):
            try:
                with winreg.OpenKey(cur_key, sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as sk:
                    _, vc, _ = winreg.QueryInfoKey(sk)
                    for vi in range(vc):
                        vn, vd, _ = winreg.EnumValue(sk, vi)
                        v_str = str(vd).casefold()
                        if any(sys_token in v_str for sys_token in ("system32", "syswow64", "servicing", "winsxs", "microsoft.net", "assembly")):
                            return False
                        if path_has_protected_shell_component(v_str):
                            return False
                        if text_matches_identity(vn) or text_matches_identity(vd):
                            return True
            except OSError:
                pass
        return False

    def preserve_registry_path(hive_name, sub_key):
        normalized = sub_key.casefold().rstrip("\\")
        padded = "\\" + normalized
        path_components = re.split(r"[\\/]", normalized)
        return (
            any(
                (prefix == padded or padded.startswith(prefix + "\\"))
                if prefix in (r"\sam", r"\security")
                else (prefix in padded)
                for prefix in protected_registry_infrastructure
            )
            or any(
                component == family
                or component.startswith(family + "_")
                for component in path_components
                for family in protected_registry_package_components
            )
            or (
                hive_name == "HKLM"
                and (
                    normalized == deprovisioned_prefix
                    or normalized.startswith(deprovisioned_prefix + "\\")
                )
            )
        )


    reg_keys_to_delete = []
    reg_values_to_delete = []
    paths_to_delete = [
        path
        for path in exact_install_locations
        if path.exists() and deletion_allowed(path)
    ]

    if ui_queue:
        ui_queue.put(
            {
                "action": "progress_update",
                "text_base": "Kayıt defteri ve disk kalıntıları taranıyor",
                "pct": None,
                "color": "#FFB86C",
                "target": "debloat",
            }
        )

    shared_scan_deadline = time.monotonic() + 600
    file_scan_deadline = shared_scan_deadline
    registry_scan_deadline_reached = threading.Event()
    registry_lock = threading.Lock()
    registry_max_depth = 40
    registry_stats = {
        "processed": 0,
        "last_progress": 0.0,
    }
    scan_errors = []
    registry_worker_count = min(6, max(3, os.cpu_count() or 4))

    def scan_registry_root(hkey, hive_name, root_path, view_flag):
        local_keys = []
        local_vals = []
        local_processed = 0

        def flush_registry_stats():
            nonlocal local_processed
            if local_processed == 0:
                return
            progress_base = None
            now = time.monotonic()
            with registry_lock:
                registry_stats["processed"] += local_processed
                local_processed = 0
                if now - registry_stats["last_progress"] >= 0.25:
                    registry_stats["last_progress"] = now
                    progress_base = (
                        "Kayıt defteri taranıyor · "
                        f"{registry_stats['processed']:,} anahtar"
                    ).replace(",", ".")
            if progress_base and ui_queue:
                ui_queue.put({
                    "action": "progress_update",
                    "text_base": progress_base,
                    "pct": None,
                    "color": "#FFB86C",
                    "target": "debloat",
                })

        try:
            root_handle = winreg.OpenKey(hkey, root_path, 0, winreg.KEY_READ | view_flag)
        except OSError:
            return

        stack = [(root_path, root_handle, 0)]
        while stack:
            if registry_scan_deadline_reached.is_set() or time.monotonic() >= shared_scan_deadline:
                registry_scan_deadline_reached.set()
                while stack:
                    _, rem_k, _ = stack.pop()
                    try:
                        rem_k.Close()
                    except Exception:
                        pass
                break

            cur_path, cur_key, depth = stack.pop()
            try:
                local_processed += 1
                if local_processed >= 500:
                    flush_registry_stats()

                if preserve_registry_path(hive_name, cur_path):
                    continue

                sk_cnt, val_cnt, _ = winreg.QueryInfoKey(cur_key)
                cur_path_lower = cur_path.casefold()
                is_shared = is_shared_container(cur_path)

                for vi in range(val_cnt):
                    try:
                        vn, vd, _ = winreg.EnumValue(cur_key, vi)
                        # 1. Varsayılan (Default) değerler ASLA tek başına silinemez!
                        if not vn or vn == "":
                            continue
                        # 2. Sistem ikililerini gösteren değerler asla silinemez!
                        vd_s = str(vd).casefold()
                        if "system32" in vd_s or "syswow64" in vd_s or "servicing" in vd_s or "winsxs" in vd_s or path_has_protected_shell_component(vd_s):
                            continue
                        if "settingspagevisibility" in str(vn).casefold():
                            continue
                        vn_match = text_matches_identity(vn)
                        is_val_container = is_shared or any(c in cur_path_lower for c in (
                            "openwithprogids", "openwithlist", "run", "runonce", "startupapproved",
                            "shareddlls", "firewallrules", "muicache", "backgroundaccessapplications",
                            "uninstalltimes", "app paths", "registeredapplications", "packagedapps",
                            "fileexts", "search", "mrtcache", "urlassociations", "associations"
                        ))
                        vd_match = False
                        if is_val_container:
                            if isinstance(vd, bytes):
                                if len(vd) <= 65536:
                                    vd_match = text_matches_identity(vd)
                            else:
                                vd_match = text_matches_identity(vd)

                        if vn_match or (vd_match and is_val_container):
                            local_vals.append((hkey, hive_name, cur_path, vn, view_flag))
                            continue

                        # RegisteredApplications altında hedef anahtar bulunamayan ölü girdiler
                        if "registeredapplications" in cur_path_lower:
                            target_str = str(vd).strip().strip("\\")
                            target_exists = False
                            cands = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
                            if hive_name == "HKU" and cur_path:
                                user_sid_prefix = cur_path.split("\\", 1)[0]
                                try:
                                    with winreg.OpenKey(winreg.HKEY_USERS, f"{user_sid_prefix}\\{target_str}", 0, winreg.KEY_READ | view_flag):
                                        target_exists = True
                                except OSError:
                                    pass
                            for root_cand in cands:
                                if target_exists:
                                    break
                                try:
                                    with winreg.OpenKey(root_cand, target_str, 0, winreg.KEY_READ | view_flag):
                                        target_exists = True
                                        break
                                except OSError:
                                    pass
                            if not target_exists:
                                local_vals.append((hkey, hive_name, cur_path, vn, view_flag))
                    except OSError:
                        pass

                if depth < registry_max_depth:
                    for si in range(sk_cnt):
                        try:
                            child_name = winreg.EnumKey(cur_key, si)
                            child_path = f"{cur_path}\\{child_name}" if cur_path else child_name
                            if preserve_registry_path(hive_name, child_path):
                                continue
                            child_name_lower = child_name.casefold()
                            cur_path_lower = cur_path.casefold()

                            # Ağır veya bloat içermeyen sistem kovanlarını atla
                            if child_name_lower in {"interface", "typelib", "appid"} or cur_path_lower.endswith((r"\interface", r"\typelib", r"\appid")):
                                continue
                            if "installer\\userdata\\s-1-5-18\\components" in cur_path_lower:
                                continue
                            if "microsoft\\windows\\currentversion\\component based servicing" in cur_path_lower:
                                continue
                            if "microsoft\\windows\\currentversion\\sidebyside" in cur_path_lower:
                                continue

                            child_key = winreg.OpenKey(cur_key, child_name, 0, winreg.KEY_READ | view_flag)

                            is_direct_classes_child = (
                                cur_path_lower.endswith(r"\classes")
                                or cur_path_lower.endswith("_classes")
                                or cur_path_lower == "classes"
                                or hive_name == "HKCR"
                            )

                            if is_direct_classes_child and not child_name.startswith(".") and not child_name.startswith("{"):
                                if text_matches_identity(child_name) or (child_name.casefold().startswith("appx") and check_appx_progid_match(child_key)):
                                    local_keys.append((hkey, hive_name, child_path, view_flag))
                                    child_key.Close()
                                    continue

                            is_direct_clsid_child = cur_path_lower.endswith(r"\clsid")
                            if is_direct_clsid_child and child_name.startswith("{") and child_name.endswith("}"):
                                if not is_system_clsid(child_key) and check_clsid_match(child_key):
                                    local_keys.append((hkey, hive_name, child_path, view_flag))
                                child_key.Close()
                                continue

                            if cur_path_lower.endswith(r"\app paths"):
                                if text_matches_identity(child_name):
                                    local_keys.append((hkey, hive_name, child_path, view_flag))
                                    child_key.Close()
                                    continue

                            if cur_path_lower.endswith(r"\uninstall"):
                                if text_matches_identity(child_name):
                                    local_keys.append((hkey, hive_name, child_path, view_flag))
                                    child_key.Close()
                                    continue
                                try:
                                    _, u_vc, _ = winreg.QueryInfoKey(child_key)
                                    u_match = False
                                    for u_i in range(u_vc):
                                        u_vn, u_vd, _ = winreg.EnumValue(child_key, u_i)
                                        if u_vn.casefold() in ("displayname", "publisher", "installlocation", "uninstallstring", "displayicon"):
                                            if text_matches_identity(u_vd):
                                                u_match = True
                                                break
                                    if u_match:
                                        local_keys.append((hkey, hive_name, child_path, view_flag))
                                        child_key.Close()
                                        continue
                                except OSError:
                                    pass

                            if is_shared_container(child_path):
                                stack.append((child_path, child_key, depth + 1))
                                continue

                            if r"\appcontainer\mappings" in cur_path_lower:
                                try:
                                    m_val, _ = winreg.QueryValueEx(child_key, "Moniker")
                                    if text_matches_identity(m_val):
                                        local_keys.append((hkey, hive_name, child_path, view_flag))
                                        child_key.Close()
                                        continue
                                except OSError:
                                    pass

                            if (child_name.casefold() == "windowsdefender" or text_matches_identity(child_name)) and (
                                is_direct_classes_child or r"\urlassociations" in cur_path_lower or r"\extensions\windows.protocol" in cur_path_lower
                            ):
                                local_keys.append((hkey, hive_name, child_path, view_flag))
                                child_key.Close()
                                continue

                            if r"\packagerepository\extensions" in cur_path_lower:
                                if text_matches_identity(child_name) or (child_name.casefold().startswith("appx") and check_appx_progid_match(child_key)):
                                    local_keys.append((hkey, hive_name, child_path, view_flag))
                                    child_key.Close()
                                    continue

                            if r"\windowsruntime\activatableclassid" in cur_path_lower:
                                if child_name_lower.startswith("windows."):
                                    child_key.Close()
                                    continue
                                try:
                                    dll_p, _ = winreg.QueryValueEx(child_key, "DllPath")
                                    if dll_p and any(sys_dir in str(dll_p).casefold() for sys_dir in ("system32", "syswow64", "winsxs", "servicing")):
                                        child_key.Close()
                                        continue
                                except OSError:
                                    pass
                                if text_matches_identity(child_name):
                                    local_keys.append((hkey, hive_name, child_path, view_flag))
                                    child_key.Close()
                                    continue

                            if r"\appmodel\systemappdata" in cur_path_lower:
                                if text_matches_identity(child_name) or any(tok in child_name_lower for tok in ("aixhost", "clicktodo", "crossdevice")):
                                    local_keys.append((hkey, hive_name, child_path, view_flag))
                                    child_key.Close()
                                    continue

                            # İzole anahtarların (Default) ve diğer değer verilerini kontrol et
                            try:
                                def_val, _ = winreg.QueryValueEx(child_key, "")
                                if def_val and text_matches_identity(def_val):
                                    def_val_s = str(def_val).casefold()
                                    if not any(sp in def_val_s for sp in ("system32", "syswow64", "servicing", "winsxs")):
                                        if not path_has_protected_shell_component(def_val_s):
                                            local_keys.append((hkey, hive_name, child_path, view_flag))
                                            child_key.Close()
                                            continue
                            except OSError:
                                pass

                            if text_matches_identity(child_name):
                                if not child_name_lower.startswith("windows.") and not is_system_clsid(child_key):
                                    local_keys.append((hkey, hive_name, child_path, view_flag))
                                    child_key.Close()
                                    continue

                            stack.append((child_path, child_key, depth + 1))
                        except OSError:
                            pass
            except Exception as exc:
                with registry_lock:
                    scan_errors.append(f"Registry taraması: {exc}")
            finally:
                try:
                    cur_key.Close()
                except Exception:
                    pass

        flush_registry_stats()
        if local_keys or local_vals:
            with registry_lock:
                if local_keys:
                    reg_keys_to_delete.extend(local_keys)
                if local_vals:
                    reg_values_to_delete.extend(local_vals)

    def registry_scan_runner():
        try:
            ntdll = ctypes.windll.ntdll
            res = ctypes.c_ulong()
            for priv in (9, 17, 18, 20):
                ntdll.RtlAdjustPrivilege(ctypes.c_ulong(priv), ctypes.c_bool(True), ctypes.c_bool(False), ctypes.byref(res))
        except Exception:
            pass

        scan_roots = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as h_soft:
                sk_cnt = winreg.QueryInfoKey(h_soft)[0]
                for idx in range(sk_cnt):
                    sub = winreg.EnumKey(h_soft, idx)
                    sub_lower = sub.casefold()
                    if sub_lower in {"classes"}:
                        try:
                            with winreg.OpenKey(h_soft, sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as h_cls:
                                c_sk_cnt = winreg.QueryInfoKey(h_cls)[0]
                                for c_idx in range(c_sk_cnt):
                                    c_sub = winreg.EnumKey(h_cls, c_idx)
                                    c_sub_lower = c_sub.casefold()
                                    if c_sub_lower in {"interface", "typelib", "appid"}:
                                        continue
                                    scan_roots.append((winreg.HKEY_LOCAL_MACHINE, "HKLM", f"SOFTWARE\\Classes\\{c_sub}", winreg.KEY_WOW64_64KEY))
                        except OSError:
                            scan_roots.append((winreg.HKEY_LOCAL_MACHINE, "HKLM", f"SOFTWARE\\{sub}", winreg.KEY_WOW64_64KEY))
                    elif sub_lower in {"microsoft"}:
                        try:
                            with winreg.OpenKey(h_soft, sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as h_ms:
                                m_sk_cnt = winreg.QueryInfoKey(h_ms)[0]
                                for m_idx in range(m_sk_cnt):
                                    m_sub = winreg.EnumKey(h_ms, m_idx)
                                    m_sub_lower = m_sub.casefold()
                                    if m_sub_lower in {"windows", "windows nt"}:
                                        try:
                                            with winreg.OpenKey(h_ms, m_sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as h_win:
                                                w_sk_cnt = winreg.QueryInfoKey(h_win)[0]
                                                for w_idx in range(w_sk_cnt):
                                                    w_sub = winreg.EnumKey(h_win, w_idx)
                                                    w_sub_lower = w_sub.casefold()
                                                    if w_sub_lower in {"currentversion"}:
                                                        scan_roots.append((winreg.HKEY_LOCAL_MACHINE, "HKLM", f"SOFTWARE\\Microsoft\\{m_sub}\\CurrentVersion", winreg.KEY_WOW64_64KEY))
                                                    else:
                                                        scan_roots.append((winreg.HKEY_LOCAL_MACHINE, "HKLM", f"SOFTWARE\\Microsoft\\{m_sub}\\{w_sub}", winreg.KEY_WOW64_64KEY))
                                        except OSError:
                                            scan_roots.append((winreg.HKEY_LOCAL_MACHINE, "HKLM", f"SOFTWARE\\Microsoft\\{m_sub}", winreg.KEY_WOW64_64KEY))
                                    else:
                                        scan_roots.append((winreg.HKEY_LOCAL_MACHINE, "HKLM", f"SOFTWARE\\Microsoft\\{m_sub}", winreg.KEY_WOW64_64KEY))
                        except OSError:
                            scan_roots.append((winreg.HKEY_LOCAL_MACHINE, "HKLM", f"SOFTWARE\\{sub}", winreg.KEY_WOW64_64KEY))
                    else:
                        scan_roots.append((winreg.HKEY_LOCAL_MACHINE, "HKLM", f"SOFTWARE\\{sub}", winreg.KEY_WOW64_64KEY))
        except OSError:
            scan_roots.append((winreg.HKEY_LOCAL_MACHINE, "HKLM", "SOFTWARE", winreg.KEY_WOW64_64KEY))

        scan_roots.append((winreg.HKEY_LOCAL_MACHINE, "HKLM", r"SYSTEM\CurrentControlSet\Services", winreg.KEY_WOW64_64KEY))
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
                scan_roots.append((winreg.HKEY_CURRENT_USER, "HKCU", "Software", winreg.KEY_WOW64_64KEY))
        except OSError:
            pass

        try:
            with winreg.OpenKey(winreg.HKEY_USERS, "", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as hku_root:
                hku_keys = [
                    winreg.EnumKey(hku_root, idx)
                    for idx in range(winreg.QueryInfoKey(hku_root)[0])
                ]
            for user_sid in hku_keys:
                sid_lower = user_sid.casefold()
                if sid_lower in ("s-1-5-18", "s-1-5-19", "s-1-5-20"):
                    continue
                if sid_lower.endswith("_classes"):
                    cand = user_sid
                else:
                    cand = f"{user_sid}\\Software"
                try:
                    with winreg.OpenKey(winreg.HKEY_USERS, cand, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
                        scan_roots.append((winreg.HKEY_USERS, "HKU", cand, winreg.KEY_WOW64_64KEY))
                except OSError:
                    pass
        except OSError:
            pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=registry_worker_count) as reg_executor:
            reg_futures = [
                reg_executor.submit(scan_registry_root, hkey, hive_name, root_path, view_flag)
                for hkey, hive_name, root_path, view_flag in scan_roots
            ]
            for future in concurrent.futures.as_completed(reg_futures):
                try:
                    future.result()
                except Exception as exc:
                    scan_errors.append(f"Registry alt tarama: {exc}")

    def partition_file_scan_roots():
        partitioned = []
        split_again_names = {"windowsapps", "microsoft", "packages"}
        excluded_names = {
            "windows",
            "system32",
            "syswow64",
            "winsxs",
            "servicing",
            "driverstore",
            "assembly",
            "node_modules",
            ".git",
            ".vscode",
            ".idea",
            "__pycache__",
            "package cache",
            "cache",
            "caches",
            "gpu_cache",
            "code cache",
            "shadercache",
            "webcache",
        }
        frontier = [
            (Path(root), max_depth, 0)
            for root, max_depth in search_roots
            if Path(root).is_dir()
        ]
        while frontier:
            if time.monotonic() >= shared_scan_deadline:
                file_scan_deadline_reached.set()
                break
            current, remaining_depth, split_level = frontier.pop()
            if remaining_depth <= 0:
                partitioned.append((current, 0))
                continue
            try:
                entries = list(os.scandir(current))
            except (PermissionError, OSError):
                partitioned.append((current, remaining_depth))
                continue
            for entry_index, entry in enumerate(entries):
                if (
                    entry_index % 128 == 0
                    and time.monotonic() >= shared_scan_deadline
                ):
                    file_scan_deadline_reached.set()
                    break
                item_path = Path(entry.path)
                if path_matches_identity(item_path) and deletion_allowed(item_path):
                    paths_to_delete.append(item_path)
                    continue
                if not entry.is_dir(follow_symlinks=False):
                    continue
                name_lower = entry.name.casefold()
                if name_lower in excluded_names:
                    continue
                if (
                    split_level == 0
                    or (
                        split_level == 1
                        and name_lower in split_again_names
                    )
                ):
                    frontier.append(
                        (item_path, remaining_depth - 1, split_level + 1)
                    )
                else:
                    eff_depth = min(remaining_depth - 1, 2) if (split_level >= 1 and not path_matches_identity(item_path)) else (remaining_depth - 1)
                    partitioned.append((item_path, eff_depth))
        return partitioned

    # Eş zamanlı (concurrent) tarama mimarisi: Registry ve Disk I/O paralel yürütülür
    # 1. Aşama: Kayıt Defteri Kalıntı Taraması
    registry_scan_runner()

    # 2. Aşama: Disk Kalıntı Taraması
    partitioned_file_roots = partition_file_scan_roots()
    file_worker_count = min(6, max(3, os.cpu_count() or 4))

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=file_worker_count
    ) as file_executor:
        file_futures = [
            file_executor.submit(scan_directory, root, depth)
            for root, depth in partitioned_file_roots
        ]
        for future in concurrent.futures.as_completed(file_futures):
            try:
                paths_to_delete.extend(future.result())
            except Exception as exc:
                scan_errors.append(f"Dosya tarama görevi: {exc}")

    if file_scan_deadline_reached.is_set():
        scan_errors.append(
            "Dosya kalıntı taraması güvenli süre sınırında "
            "sonlandırıldı; kesin paket yolları yine temizlendi."
        )

    if ui_queue:
        ui_queue.put({
            "action": "progress_stop",
            "text_base": "Kayıt defteri ve disk kalıntıları taranıyor",
            "result": "tarandı",
            "result_color": "#00FF9D",
            "target": "debloat",
        })

    # AppxAllUserStore'un tamamı Start/Explorer için altyapıdır ve genel kimlik
    # taramasından korunur. Bununla birlikte seçilmiş paketin tam kayıtları da
    # bu ağacın altında yer alır. Yalnız envanterden gelen kesin PackageFullName
    # + kullanıcı SID çiftlerini ekleyerek CoreAI/SecHealthUI gibi NonRemovable
    # paketlerin dosyasız "zombi" kayda dönüşmesini önle.
    appx_store_root = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Appx"
        r"\AppxAllUserStore"
    )
    profile_sids = set()
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as profile_list_key:
            for index in range(winreg.QueryInfoKey(profile_list_key)[0]):
                candidate_sid = winreg.EnumKey(profile_list_key, index)
                if re.fullmatch(r"S-1-5-(?:\d+-){1,14}\d+", candidate_sid):
                    profile_sids.add(candidate_sid)
    except OSError:
        pass

    for package_info in appx_metadata.get("Packages", []):
        package_full_name = str(package_info.get("PackageFullName") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{8,260}", package_full_name):
            continue
        if "startexperiences" in package_full_name.casefold():
            continue
        package_family_name = str(
            package_info.get("PackageFamilyName") or ""
        ).strip()
        for store_branch in (
            "Applications",
            "InboxApplications",
            "Staged",
            "Deleted",
        ):
            reg_keys_to_delete.append(
                (
                    winreg.HKEY_LOCAL_MACHINE,
                    "HKLM",
                    f"{appx_store_root}\\{store_branch}\\{package_full_name}",
                    winreg.KEY_WOW64_64KEY,
                )
            )
        if re.fullmatch(r"[A-Za-z0-9._-]{6,180}", package_family_name):
            reg_keys_to_delete.append(
                (
                    winreg.HKEY_LOCAL_MACHINE,
                    "HKLM",
                    f"{appx_store_root}\\Config\\{package_family_name}",
                    winreg.KEY_WOW64_64KEY,
                )
            )
        package_user_sids = set(profile_sids)
        package_user_sids.update(package_info.get("UserSids", []))
        for raw_sid in package_user_sids:
            user_sid = str(raw_sid or "").strip()
            if not re.fullmatch(r"S-1-5-(?:\d+-){1,14}\d+", user_sid):
                continue
            for sid_branch in (user_sid, f"EndOfLife\\{user_sid}"):
                reg_keys_to_delete.append(
                    (
                        winreg.HKEY_LOCAL_MACHINE,
                        "HKLM",
                        f"{appx_store_root}\\{sid_branch}\\{package_full_name}",
                        winreg.KEY_WOW64_64KEY,
                    )
                )

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, appx_store_root, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as store_key:
            for branch in ("Applications", "InboxApplications", "Staged", "Deleted", "Config"):
                try:
                    with winreg.OpenKey(store_key, branch, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as branch_key:
                        num_sub = winreg.QueryInfoKey(branch_key)[0]
                        for bi in range(num_sub):
                            sub_name = winreg.EnumKey(branch_key, bi)
                            if text_matches_identity(sub_name):
                                reg_keys_to_delete.append((
                                    winreg.HKEY_LOCAL_MACHINE,
                                    "HKLM",
                                    f"{appx_store_root}\\{branch}\\{sub_name}",
                                    winreg.KEY_WOW64_64KEY,
                                ))
                except OSError:
                    pass
        for sid in profile_sids:
            for sid_branch in (sid, f"EndOfLife\\{sid}"):
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{appx_store_root}\\{sid_branch}", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as sid_key:
                        num_sub = winreg.QueryInfoKey(sid_key)[0]
                        for bi in range(num_sub):
                            sub_name = winreg.EnumKey(sid_key, bi)
                            if text_matches_identity(sub_name):
                                reg_keys_to_delete.append((
                                    winreg.HKEY_LOCAL_MACHINE,
                                    "HKLM",
                                    f"{appx_store_root}\\{sid_branch}\\{sub_name}",
                                    winreg.KEY_WOW64_64KEY,
                                ))
                except OSError:
                    pass
    except OSError:
        pass

    unique_paths = {}
    for path in paths_to_delete:
        try:
            key = _normalized_path(path)
        except (OSError, ValueError):
            continue
        if deletion_allowed(path):
            unique_paths[key] = Path(path)
    paths_to_delete = sorted(unique_paths.values(), key=lambda item: len(item.parts), reverse=True)

    unique_keys = {}
    for hkey, hive_name, sub_key, view_flag in reg_keys_to_delete:
        unique_keys[(hive_name, sub_key.casefold(), view_flag)] = (hkey, hive_name, sub_key, view_flag)
    selected_keys = []
    for item in sorted(unique_keys.values(), key=lambda value: value[2].count("\\")):
        _, hive_name, sub_key, view_flag = item
        prefix = sub_key.casefold() + "\\"
        if any(
            existing_hive == hive_name
            and existing_view == view_flag
            and prefix.startswith(existing_path.casefold() + "\\")
            for _, existing_hive, existing_path, existing_view in selected_keys
        ):
            continue
        selected_keys.append(item)
    reg_keys_to_delete = sorted(selected_keys, key=lambda item: item[2].count("\\"), reverse=True)

    key_prefixes = [
        (hive_name, sub_key.casefold(), view_flag)
        for _, hive_name, sub_key, view_flag in reg_keys_to_delete
    ]
    unique_values = {}
    for item in reg_values_to_delete:
        hkey, hive_name, sub_key, value_name, view_flag = item
        if any(
            hive_name == key_hive
            and view_flag == key_view
            and (
                sub_key.casefold() == key_path
                or sub_key.casefold().startswith(key_path + "\\")
            )
            for key_hive, key_path, key_view in key_prefixes
        ):
            continue
        unique_values[(hive_name, sub_key.casefold(), value_name.casefold(), view_flag)] = item
    reg_values_to_delete = list(unique_values.values())

    residual_stage_id = f"residual_cleanup_{secrets.token_hex(4)}"
    if ui_queue:
        ui_queue.put({
            "action": "stage_start",
            "stage_id": residual_stage_id,
            "text_base": "Bulunan kalıntılar temizleniyor",
            "color": "#E7ECF2",
            "target": "debloat",
        })
    for scan_error in scan_errors:
        detail_log(f"Scan warning: {scan_error}")
    detail_log(
        f"Scan result: {len(paths_to_delete)} files/directories, "
        f"{len(reg_keys_to_delete)} registry keys, "
        f"{len(reg_values_to_delete)} registry values."
    )
    detail_log(
        f"Registry scan processed {registry_stats['processed']} keys "
        f"across HKLM/HKU with {registry_worker_count} workers."
    )

    for process_name in (
        "SystemSettings.exe",
    ):
        subprocess.run(
            ["taskkill", "/f", "/im", process_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )

    def force_delete_path(path):
        if not path.exists() and not path.is_symlink():
            return True
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
            else:
                shutil.rmtree(path)
            if not path.exists():
                return True
        except OSError:
            pass

        # Native OS hizli silme denemesi (I/O darbogazini onler)
        try:
            if path.is_file() or path.is_symlink():
                subprocess.run(
                    ["cmd.exe", "/d", "/c", "del", "/f", "/q", "/a", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                    timeout=2,
                    check=False,
                )
            else:
                subprocess.run(
                    ["cmd.exe", "/d", "/c", "rd", "/s", "/q", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                    timeout=2,
                    check=False,
                )
            if not path.exists():
                return True
        except Exception:
            pass

        # Kilitli dosyalar bekletilmeden tekil TrustedInstaller / PendingDelete geçişine bırakılır
        return False

    deletion_workers = min(12, max(4, (os.cpu_count() or 4) * 2))
    detail_log(
        f"Deletion workers: {deletion_workers}; "
        f"registry workers: {registry_worker_count}; "
        f"file workers: {file_worker_count}."
    )

    # AppX/StateRepository önbelleklerini açık tutan süreç ve servisleri bırak.
    for process_name in (
        "SystemSettings.exe",
        "RuntimeBroker.exe",
        "Widgets.exe",
    ):
        subprocess.run(
            ["taskkill", "/f", "/im", process_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    for service_name in ("StateRepository", "AppXSvc", "ClipSVC"):
        subprocess.run(
            ["sc.exe", "stop", service_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=20,
            check=False,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=deletion_workers) as executor:
        path_results = list(executor.map(force_delete_path, paths_to_delete))
    deleted_paths = sum(1 for success in path_results if success)
    failed_paths = [
        path for path, success in zip(paths_to_delete, path_results) if not success
    ]
    pending_deletion_paths = []
    if failed_paths:
        path_payload = base64.b64encode(
            json.dumps(
                [str(path) for path in failed_paths],
                ensure_ascii=False,
            ).encode("utf-8")
        ).decode("ascii")
        protected_path_script = r"""
$paths = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String('__PATH_PAYLOAD__')
) | ConvertFrom-Json
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class PendingDelete {
    [DllImport("ntdll.dll")]
    public static extern int RtlAdjustPrivilege(
        int privilege, bool enable, bool currentThread, out bool enabled
    );
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool MoveFileEx(
        string existingFile, string newFile, int flags
    );
    public static void EnablePrivileges() {
        bool en;
        RtlAdjustPrivilege(9, true, false, out en);
        RtlAdjustPrivilege(17, true, false, out en);
        RtlAdjustPrivilege(18, true, false, out en);
    }
}
'@
[PendingDelete]::EnablePrivileges()
$scheduleFailures = 0
foreach ($path in @($paths)) {
    if (-not (Test-Path -LiteralPath $path)) {
        continue
    }
    & cmd.exe /d /c "rd /s /q `"$path`"" 2>$null | Out-Null
    if (Test-Path -LiteralPath $path) {
        & cmd.exe /d /c "del /f /q /a `"$path`"" 2>$null | Out-Null
    }
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $path) {
        if ((Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue) -is [System.IO.DirectoryInfo]) {
            Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
                try { [PendingDelete]::MoveFileEx($_.FullName, $null, 4) | Out-Null } catch {}
            }
            Get-ChildItem -LiteralPath $path -Recurse -Directory -Force -ErrorAction SilentlyContinue | Sort-Object { $_.FullName.Length } -Descending | ForEach-Object {
                try { [PendingDelete]::MoveFileEx($_.FullName, $null, 4) | Out-Null } catch {}
            }
        }
        try {
            if (-not [PendingDelete]::MoveFileEx([string]$path, $null, 4)) {
                $scheduleFailures++
            }
        } catch {
            $scheduleFailures++
        }
    }
}
""".replace("__PATH_PAYLOAD__", path_payload)
        detail_log(
            f"TrustedInstaller retry started for {len(failed_paths)} files/directories."
        )
        system_ok, system_error = run_powershell_as_trustedinstaller(
            protected_path_script,
            timeout=max(120, len(failed_paths) * 20),
        )
        retry_successes = [
            path for path in failed_paths if not path.exists()
        ]
        deleted_paths += len(retry_successes)
        failed_paths = [
            path for path in failed_paths if path.exists()
        ]
        if system_ok:
            pending_deletion_paths = list(failed_paths)
        elif system_error:
            detail_log(f"SYSTEM file cleanup error: {system_error}")
    unresolved_file_paths = [
        path
        for path in failed_paths
        if path not in pending_deletion_paths
    ]
    for path, success in zip(paths_to_delete, path_results):
        detail_log(
            f"[{'DELETED' if success or not path.exists() else 'FAILED'}] {path}"
        )
    for pending_path in pending_deletion_paths:
        detail_log(f"[PENDING REBOOT] {pending_path}")

    def fast_delete_registry_key(item):
        hkey, _, sub_key, view_flag = item
        try:
            RegistryEngine.delete_key_recursive(hkey, sub_key, view_flag)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False

    def fast_delete_registry_value(item):
        hkey, _, sub_key, value_name, view_flag = item
        try:
            with winreg.OpenKey(
                hkey,
                sub_key,
                0,
                winreg.KEY_SET_VALUE | view_flag,
            ) as key:
                winreg.DeleteValue(key, value_name)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=deletion_workers) as executor:
        key_results = list(executor.map(fast_delete_registry_key, reg_keys_to_delete))
        value_results = list(executor.map(fast_delete_registry_value, reg_values_to_delete))

    unresolved_keys = [
        item for item, success in zip(reg_keys_to_delete, key_results) if not success
    ]
    unresolved_values = [
        item for item, success in zip(reg_values_to_delete, value_results) if not success
    ]
    deleted_keys = len(reg_keys_to_delete) - len(unresolved_keys)
    deleted_values = len(reg_values_to_delete) - len(unresolved_values)

    def delete_protected_registry_batch(key_items, value_items):
        batch_items = []
        for index, (_, hive_name, sub_key, _) in enumerate(key_items):
            batch_items.append(
                {
                    "Id": f"K{index}",
                    "Kind": "Key",
                    "Hive": hive_name,
                    "Path": sub_key,
                    "Name": "",
                }
            )
        for index, (_, hive_name, sub_key, value_name, _) in enumerate(value_items):
            batch_items.append(
                {
                    "Id": f"V{index}",
                    "Kind": "Value",
                    "Hive": hive_name,
                    "Path": sub_key,
                    "Name": value_name,
                }
            )
        if not batch_items:
            return set(), set(), ""

        payload = base64.b64encode(
            json.dumps(batch_items, ensure_ascii=False).encode("utf-8")
        ).decode("ascii")
        result_fd, result_path = tempfile.mkstemp(
            prefix="winkit_registry_",
            suffix=".json",
        )
        os.close(result_fd)
        try:
            os.unlink(result_path)
        except OSError:
            pass
        escaped_result_path = result_path.replace("'", "''")
        system_script = f"""
$payload = '{payload}'
$resultPath = '{escaped_result_path}'
$items = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String($payload)
) | ConvertFrom-Json
$providerHives = @{{
    HKLM = 'HKEY_LOCAL_MACHINE'
    HKU = 'HKEY_USERS'
    HKCU = 'HKEY_CURRENT_USER'
    HKCR = 'HKEY_CLASSES_ROOT'
}}
$systemSid = New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')
$userSids = @(Get-ChildItem 'Registry::HKEY_USERS' -ErrorAction SilentlyContinue | Where-Object {{ $_.PSChildName -match '^S-1-5-21-' -and $_.PSChildName -notlike '*_Classes' }} | ForEach-Object {{ $_.PSChildName }})
$results = @()

function Remove-RegistryTarget {{
    param($Item, [string]$LiteralPath)
    $nativePath = if ($LiteralPath -like 'Registry::*') {{
        $LiteralPath.Substring(10)
    }} else {{
        "$($Item.Hive)\\$($Item.Path)"
    }}
    if ($Item.Kind -eq 'Key') {{
        & reg.exe delete $nativePath /f /reg:64 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {{
            return $true
        }}
        if (Test-Path -LiteralPath $LiteralPath) {{
            Remove-Item -LiteralPath $LiteralPath -Recurse -Force -ErrorAction Stop
        }}
        return (-not (Test-Path -LiteralPath $LiteralPath))
    }}
    if (-not (Test-Path -LiteralPath $LiteralPath)) {{
        return $true
    }}
    if ([string]::IsNullOrEmpty([string]$Item.Name)) {{
        & reg.exe delete $nativePath /ve /f /reg:64 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    }}
    & reg.exe delete $nativePath /v ([string]$Item.Name) /f /reg:64 2>$null |
        Out-Null
    if ($LASTEXITCODE -eq 0) {{
        return $true
    }}
    Remove-ItemProperty -LiteralPath $LiteralPath -Name ([string]$Item.Name) -Force -ErrorAction Stop
    return $true
}}

foreach ($item in @($items)) {{
    $targetPaths = @()
    if ([string]$item.Hive -eq 'HKCU') {{
        $targetPaths += "Registry::HKEY_CURRENT_USER\\$($item.Path)"
        foreach ($usid in $userSids) {{
            $targetPaths += "Registry::HKEY_USERS\\$usid\\$($item.Path)"
            if ([string]$item.Path -like "Software\\Classes*") {{
                $clsPath = [string]$item.Path
                if ($clsPath.Length -gt 17) {{
                    $targetPaths += "Registry::HKEY_USERS\\${{usid}}_Classes\\$($clsPath.Substring(17))"
                }}
            }}
        }}
    }} else {{
        $targetPaths += "Registry::$($providerHives[[string]$item.Hive])\\$($item.Path)"
    }}
    $targetPaths = @($targetPaths | Select-Object -Unique)
    $overallOk = $true
    $lastError = ''
    foreach ($literalPath in $targetPaths) {{
        $ok = $false
        $errorText = ''
        try {{
            $ok = Remove-RegistryTarget -Item $item -LiteralPath $literalPath
        }} catch {{
            $errorText = [string]$_.Exception.Message
        }}
        if (-not $ok) {{
            $overallOk = $false
            $lastError = $errorText
        }}
    }}
    $results += [PSCustomObject]@{{
        Id = [string]$item.Id
        Ok = [bool]$overallOk
        Error = $lastError
    }}
}}
@($results) | ConvertTo-Json -Compress -Depth 4 |
    Set-Content -LiteralPath $resultPath -Encoding UTF8 -Force
"""
        try:
            ti_ok, ti_error = run_powershell_as_trustedinstaller(
                system_script,
                timeout=max(120, len(batch_items) * 2),
            )
            if not ti_ok:
                system_ok, system_error = run_powershell_as_system(
                    system_script,
                    timeout=max(120, len(batch_items) * 2),
                )
                if not system_ok:
                    return set(), set(), ti_error or system_error
            try:
                raw_results = json.loads(
                    Path(result_path).read_text(
                        encoding="utf-8-sig",
                        errors="replace",
                    )
                )
            except (OSError, json.JSONDecodeError) as exc:
                return set(), set(), f"SYSTEM sonucu okunamadı: {exc}"
            if isinstance(raw_results, dict):
                raw_results = [raw_results]
            successful_ids = {
                str(item.get("Id"))
                for item in raw_results
                if item.get("Ok") is True
            }
            successful_keys = {
                int(item_id[1:])
                for item_id in successful_ids
                if re.fullmatch(r"K\d+", item_id)
            }
            successful_values = {
                int(item_id[1:])
                for item_id in successful_ids
                if re.fullmatch(r"V\d+", item_id)
            }
            return successful_keys, successful_values, ""
        finally:
            try:
                os.unlink(result_path)
            except OSError:
                pass

    if unresolved_keys or unresolved_values:
        detail_log(
            "Protected registry retry: "
            f"{len(unresolved_keys)} keys, "
            f"{len(unresolved_values)} values."
        )
        system_keys, system_values, system_error = delete_protected_registry_batch(
            unresolved_keys,
            unresolved_values,
        )
        deleted_keys += len(system_keys)
        deleted_values += len(system_values)
        unresolved_keys = [
            item for index, item in enumerate(unresolved_keys) if index not in system_keys
        ]
        unresolved_values = [
            item for index, item in enumerate(unresolved_values) if index not in system_values
        ]
        if system_error:
            detail_log(f"SYSTEM registry cleanup error: {system_error}")

    detail_log(
        f"Registry cleanup: {deleted_keys}/{len(reg_keys_to_delete)} keys, "
        f"{deleted_values}/{len(reg_values_to_delete)} values deleted."
    )
    unresolved_key_ids = {
        (hive_name, sub_key.casefold(), view_flag)
        for _, hive_name, sub_key, view_flag in unresolved_keys
    }
    unresolved_value_ids = {
        (
            hive_name,
            sub_key.casefold(),
            value_name.casefold(),
            view_flag,
        )
        for _, hive_name, sub_key, value_name, view_flag
        in unresolved_values
    }
    for _, hive_name, sub_key, view_flag in reg_keys_to_delete:
        state = (
            "FAILED"
            if (hive_name, sub_key.casefold(), view_flag)
            in unresolved_key_ids
            else "DELETED"
        )
        detail_log(f"[REG KEY {state}] {hive_name}\\{sub_key}")
    for _, hive_name, sub_key, value_name, view_flag in reg_values_to_delete:
        state = (
            "FAILED"
            if (
                hive_name,
                sub_key.casefold(),
                value_name.casefold(),
                view_flag,
            ) in unresolved_value_ids
            else "DELETED"
        )
        detail_log(
            f"[REG VALUE {state}] {hive_name}\\{sub_key} -> "
            f"{value_name or '(Default)'}"
        )

    # Windows'un kaldırılan inbox paketlerini sonraki kullanıcı/OOBE bakımında
    # yeniden kaydetmemesi için AppX'in resmi Deprovisioned işaretlerini koru/oluştur.
    deprovisioned_root = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Appx"
        r"\AppxAllUserStore\Deprovisioned"
    )
    for family_name in sorted(deprovisioned_families):
        if not re.fullmatch(r"[A-Za-z0-9._-]{6,180}", family_name):
            continue
        marker_path = f"{deprovisioned_root}\\{family_name}"
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_LOCAL_MACHINE,
                marker_path,
                0,
                winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY,
            ):
                pass
        except OSError:
            subprocess.run(
                ["reg.exe", "add", f"HKLM\\{marker_path}", "/f", "/reg:64"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
    if remove_onedrive:
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Policies\Microsoft\Windows\OneDrive",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
            ) as onedrive_policy:
                winreg.SetValueEx(
                    onedrive_policy,
                    "DisableFileSyncNGSC",
                    0,
                    winreg.REG_DWORD,
                    1,
                )
        except OSError:
            subprocess.run(
                [
                    "reg.exe",
                    "add",
                    r"HKLM\SOFTWARE\Policies\Microsoft\Windows\OneDrive",
                    "/v",
                    "DisableFileSyncNGSC",
                    "/t",
                    "REG_DWORD",
                    "/d",
                    "1",
                    "/f",
                    "/reg:64",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )

    cache_files = []
    if users_dir.is_dir():
        for user_dir in user_dirs:
            local_appdata = user_dir / "AppData" / "Local"
            explorer_cache = local_appdata / "Microsoft" / "Windows" / "Explorer"
            if explorer_cache.is_dir():
                cache_files.extend(explorer_cache.glob("iconcache*.db"))
            root_icon_cache = local_appdata / "IconCache.db"
            if root_icon_cache.is_file():
                cache_files.append(root_icon_cache)

    for cache_file in cache_files:
        force_delete_path(cache_file)

    if remove_edge:
        edge_lnk_names = ("Microsoft Edge.lnk", "Edge.lnk", "MSEdge.lnk")
        desktop_and_menu_dirs = [
            users_dir / "Public" / "Desktop",
            program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]
        if users_dir.is_dir():
            for user_dir in user_dirs:
                desktop_and_menu_dirs.extend([
                    user_dir / "Desktop",
                    user_dir / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs",
                    user_dir / "AppData" / "Roaming" / "Microsoft" / "Internet Explorer" / "Quick Launch",
                    user_dir / "AppData" / "Roaming" / "Microsoft" / "Internet Explorer" / "Quick Launch" / "User Pinned" / "TaskBar",
                    user_dir / "AppData" / "Roaming" / "Microsoft" / "Internet Explorer" / "Quick Launch" / "User Pinned" / "StartMenu",
                ])
        for pdir in desktop_and_menu_dirs:
            if pdir.is_dir():
                for lnk in edge_lnk_names:
                    force_delete_path(pdir / lnk)

        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for path_k in (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            ):
                try:
                    RegistryEngine.delete_key_recursive(hive, path_k, winreg.KEY_WOW64_64KEY)
                except OSError:
                    pass

        # Ayarlar > Yüklü uygulamalar'da kalan küçük Edge ARP girdisini temizle.
        # WebView2 Runtime girdisi ve {F301...} keşif kaydı özellikle korunur.
        edge_stable_guid = "{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}"
        uninstall_roots = (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        )
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for uninstall_root in uninstall_roots:
                try:
                    with winreg.OpenKey(
                        hive,
                        uninstall_root,
                        0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                    ) as root_key:
                        subkeys = [
                            winreg.EnumKey(root_key, index)
                            for index in range(winreg.QueryInfoKey(root_key)[0])
                        ]
                except OSError:
                    continue
                for subkey_name in subkeys:
                    subkey_path = f"{uninstall_root}\\{subkey_name}"
                    try:
                        with winreg.OpenKey(
                            hive,
                            subkey_path,
                            0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                        ) as app_key:
                            display_name = str(
                                winreg.QueryValueEx(app_key, "DisplayName")[0]
                            ).strip()
                    except OSError:
                        continue
                    normalized_name = display_name.casefold()
                    if "webview" in normalized_name:
                        continue
                    if normalized_name in {
                        "microsoft edge",
                        "microsoft edge update",
                    }:
                        try:
                            RegistryEngine.delete_key_recursive(
                                hive,
                                subkey_path,
                                winreg.KEY_WOW64_64KEY,
                            )
                        except OSError:
                            pass

        for edgeupdate_root in (
            r"SOFTWARE\Microsoft\EdgeUpdate",
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate",
        ):
            for branch in ("Clients", "ClientState", "ClientStateMedium"):
                browser_registration = (
                    f"{edgeupdate_root}\\{branch}\\{edge_stable_guid}"
                )
                try:
                    RegistryEngine.delete_key_recursive(
                        winreg.HKEY_LOCAL_MACHINE,
                        browser_registration,
                        winreg.KEY_WOW64_64KEY,
                    )
                except OSError:
                    pass
        quiesce_edge_update()
        edge_retry_script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$edgeNames = @(
    'Microsoft.MicrosoftEdge',
    'Microsoft.MicrosoftEdge.Stable'
)
Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue |
    Where-Object {
        $edgeNames -contains $_.DisplayName -and
        $_.DisplayName -notmatch 'WebView'
    } |
    ForEach-Object {
        Remove-AppxProvisionedPackage -Online -AllUsers `
            -PackageName $_.PackageName -ErrorAction SilentlyContinue | Out-Null
    }
Get-AppxPackage -AllUsers -PackageTypeFilter All -ErrorAction SilentlyContinue |
    Where-Object {
        $edgeNames -contains $_.Name -and $_.Name -notmatch 'WebView'
    } |
    Sort-Object IsBundle -Descending |
    ForEach-Object {
        $pkg = $_
        try {
            Remove-AppxPackage -Package $pkg.PackageFullName -AllUsers `
                -Confirm:$false -ErrorAction Stop
        } catch {
            foreach ($sid in @(
                $pkg.PackageUserInformation |
                    ForEach-Object { [string]$_.UserSecurityId.Value }
            )) {
                if ($sid) {
                    Remove-AppxPackage -Package $pkg.PackageFullName -User $sid `
                        -Confirm:$false -ErrorAction SilentlyContinue
                }
            }
        }
    }
"""
        edge_retry_encoded = base64.b64encode(
            edge_retry_script.encode("utf-16le")
        ).decode("ascii")
        subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                edge_retry_encoded,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=180,
            check=False,
        )
        detail_log("Edge AppX post-updater removal pass completed.")

    if remove_crossdevice:
        if quiesce_crossdevice_components():
            detail_log("CrossDevice processes, services and scheduled tasks were quiesced again after removal.")
        else:
            verification_failed = True
            detail_log("Final CrossDevice process/service cleanup returned an error.")
        crossdevice_policy_ok, crossdevice_policy_error = (
            configure_crossdevice_resume_disabled()
        )
        if crossdevice_policy_ok:
            detail_log(
                "CrossDeviceResume host and binary were permanently removed from Client.CBS and disk."
            )
        else:
            verification_failed = True
            detail_log(
                "CrossDeviceResume policy configuration failed: "
                + (crossdevice_policy_error or "unknown error")
            )

    verify_script = f"""
$targets = @({quoted_targets})
$packageTypes = 'All'
$remaining = @(
    Get-AppxPackage -AllUsers -PackageTypeFilter $packageTypes -ErrorAction SilentlyContinue |
        Where-Object {{ 
            $n = $_.Name
            $fn = $_.PackageFullName
            ($targets -contains $n) -or (@($targets | Where-Object {{ ($n -and $n -like "*$_*") -or ($fn -and $fn -like "*$_*") }}).Count -gt 0)
        }}
)
$remainingProvisioned = @(
    Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue |
        Where-Object {{ 
            $dn = $_.DisplayName
            $pn = $_.PackageName
            ($targets -contains $dn) -or (@($targets | Where-Object {{ ($dn -and $dn -like "*$_*") -or ($pn -and $pn -like "*$_*") }}).Count -gt 0)
        }}
)
[Console]::WriteLine("VERIFY_APPX:$($remaining.Count)")
[Console]::WriteLine("VERIFY_PROVISIONED:$($remainingProvisioned.Count)")
$verifyJson = [PSCustomObject]@{{
    AppX = @($remaining | ForEach-Object {{ [string]$_.PackageFullName }} | Select-Object -Unique)
    Provisioned = @($remainingProvisioned | ForEach-Object {{ [string]$_.PackageName }} | Select-Object -Unique)
}} | ConvertTo-Json -Compress -Depth 4
[Console]::WriteLine(
    "VERIFY_META:" +
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($verifyJson))
)
"""
    if targets:
        verify_encoded = base64.b64encode(
            verify_script.encode("utf-16le")
        ).decode("ascii")

        def run_appx_verification():
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-EncodedCommand",
                    verify_encoded,
                ],
                capture_output=True,
                text=True,
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
                timeout=180,
                check=False,
            )
            counts = {}
            metadata = {"AppX": [], "Provisioned": []}
            for output_line in result.stdout.splitlines():
                match = re.fullmatch(
                    r"(VERIFY_APPX|VERIFY_PROVISIONED):(\d+)",
                    output_line.strip(),
                )
                if match:
                    counts[match.group(1)] = int(match.group(2))
                elif output_line.startswith("VERIFY_META:"):
                    try:
                        metadata = json.loads(
                            base64.b64decode(
                                output_line.partition(":")[2]
                            ).decode("utf-8")
                        )
                    except (ValueError, UnicodeError, json.JSONDecodeError):
                        metadata = {"AppX": [], "Provisioned": []}
            return result, counts, metadata

        verify_result, remaining_counts, remaining_metadata = (
            run_appx_verification()
        )
        state_cleanup_deferred = False
        verification_output_complete = {
            "VERIFY_APPX",
            "VERIFY_PROVISIONED",
        }.issubset(remaining_counts)
        all_target_full_names = list(dict.fromkeys(
            [str(p.get("PackageFullName") or "").strip() for p in (appx_metadata.get("Packages") or []) if p.get("PackageFullName") and "startexperiences" not in str(p.get("PackageFullName")).casefold()]
            + [x for x in remaining_metadata.get("AppX", []) if "startexperiences" not in str(x).casefold()]
        ))
        if all_target_full_names or remaining_counts.get("VERIFY_APPX", 0) > 0:
            state_cleanup_ok, state_cleanup_error = (
                cleanup_residual_appx_registrations(all_target_full_names)
            )
            try:
                from core.edgewebview import clean_edge_associations
                clean_edge_associations(log_callback=detail_log)
            except Exception:
                pass
            if state_cleanup_ok:
                if state_cleanup_error.startswith("DEFERRED:"):
                    state_cleanup_deferred = True
                    detail_log(
                        "Residual AppX StateRepository cleanup was scheduled "
                        "for the automatic reboot: "
                        + state_cleanup_error.partition(":")[2]
                    )
                else:
                    detail_log(
                        "Residual AppX StateRepository user registrations were "
                        "removed after a local database backup."
                    )
                    verify_result, remaining_counts, remaining_metadata = (
                        run_appx_verification()
                    )
                    verification_output_complete = {
                        "VERIFY_APPX",
                        "VERIFY_PROVISIONED",
                    }.issubset(remaining_counts)
            else:
                detail_log(
                    "Residual AppX StateRepository cleanup failed: "
                    + (state_cleanup_error or "unknown error")
                )

        if verify_result.returncode != 0:
            verification_failed = True
            detail_log("Final AppX verification could not run.")
        elif not verification_output_complete:
            verification_failed = True
            detail_log("Final AppX verification output was incomplete.")
        elif any(remaining_counts.values()) and not state_cleanup_deferred:
            verification_failed = True
            detail_log(
                "Final AppX verification found remaining registrations: "
                f"AppX={remaining_counts.get('VERIFY_APPX', '?')}, "
                f"Provisioned={remaining_counts.get('VERIFY_PROVISIONED', '?')}. "
                f"Remaining: {remaining_metadata}"
            )
        elif state_cleanup_deferred:
            detail_log(
                "Final AppX registration verification was deferred until "
                "the automatic reboot."
            )
        else:
            detail_log("Final AppX verification: AppX=0, Provisioned=0.")

    remaining_special_apps = []
    if remove_edge and any(
        candidate.is_file()
        for candidate in (
            program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        )
    ):
        remaining_special_apps.append("Microsoft Edge")
    if remove_onedrive:
        onedrive_executables = [
            program_files / "Microsoft OneDrive" / "OneDrive.exe",
            program_files_x86 / "Microsoft OneDrive" / "OneDrive.exe",
        ]
        if users_dir.is_dir():
            onedrive_executables.extend(
                user_dir / "AppData" / "Local" / "Microsoft" / "OneDrive" / "OneDrive.exe"
                for user_dir in user_dirs
            )
        if any(candidate.is_file() for candidate in onedrive_executables):
            remaining_special_apps.append("Microsoft OneDrive")
    if remaining_special_apps:
        verification_failed = True
        detail_log(
            "Special applications with remaining executables: "
            + ", ".join(remaining_special_apps)
        )

    failed_deletions = (
        (
            len(paths_to_delete)
            - deleted_paths
            - len(pending_deletion_paths)
        )
        + (len(reg_keys_to_delete) - deleted_keys)
        + (len(reg_values_to_delete) - deleted_values)
    )
    is_critical_failure = bool(verification_failed or (len(paths_to_delete) - deleted_paths - len(pending_deletion_paths) > 20))
    if failed_deletions or verification_failed:
        detail_log(
            f"Cleanup completed: {deleted_paths} files/directories, "
            f"{deleted_keys} registry anahtarı, {deleted_values} registry değeri silindi; "
            f"{failed_deletions} deletions failed."
        )
    else:
        detail_log(
            f"Cleanup completed: {deleted_paths} files/directories, "
            f"{deleted_keys} registry keys, "
            f"{deleted_values} registry values deleted."
        )
    if ui_queue:
        ui_queue.put({
            "action": "stage_finish",
            "stage_id": residual_stage_id,
            "result": "⚠" if is_critical_failure else "✔",
            "result_color": "#FFB86C" if is_critical_failure else "#55D67A",
            "target": "debloat",
        })

    try:
        log_dir = get_winkit_data_directory()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "winkit_debloatlog.txt"
        # Windows mevcut dosya üzerine yazıldığında CreationTime değerini
        # korur. Her çalışma gerçekten yeni bir günlük dosyası oluştursun.
        if log_path.exists():
            log_path.unlink()
        log_path.write_text(
            "\n".join(removal_log_lines) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    return not is_critical_failure


def _legacy_deepscanner_disabled(app_names, ui_queue=None):
    """
    Revo Uninstaller mantığıyla, yalnızca belirli ve güvenli dizinlerde,
    ayrıca tüm ana registry hive'larında, çok katı filtrelemelerle tarama yapar.
    Sistem dosyalarına zarar gelmesi ihtimaline karşı Windows, System32 klasörlerine asla dokunmaz.
    """
    raise RuntimeError(
        "Güvenli olmayan derin tarayıcı devre dışı bırakıldı; "
        "remove_selected_apps_safely() kullanılmalıdır."
    )

    import os
    import re
    import shutil
    import winreg
    import subprocess
    import concurrent.futures
    import tempfile
    
    def log_msg(text, color="#00ff66"):
        if ui_queue:
            ui_queue.put({"action": "log", "text": text, "color": color})

    if not isinstance(app_names, list):
        app_names = [app_names]
    
    forbidden_terms = ["microsoft", "windows", "system", "intel", "amd", "nvidia"]
    filtered_names = []
    for name in app_names:
        if name.strip().lower() not in forbidden_terms and len(name.strip()) > 3:
            filtered_names.append(name.strip())
            
    if not filtered_names:
        return
    # PRE-CALCULATE match rules to avoid regex in loop for 1M registry keys
    match_rules = []
    for name in filtered_names:
        name_lower = name.lower()
        regex = re.compile(rf'(?<![a-z0-9]){re.escape(name_lower)}(?![a-z0-9])')
        name_clean = re.sub(r'[^a-z0-9]', '', name_lower)
        alt_name_clean = None
        if '.' in name_lower:
            alt_name_clean = re.sub(r'[^a-z0-9]', '', name_lower.split('.')[-1])
        elif name_lower.startswith("microsoft"):
            alt_name_clean = re.sub(r'[^a-z0-9]', '', name_lower[9:])
        if alt_name_clean in ["windows", "system", "microsoft", "intel", "amd", "nvidia", "app", "client", "host"]:
            alt_name_clean = None
            
        match_rules.append({
            "name_lower": name_lower,
            "regex": regex,
            "name_clean": name_clean,
            "alt_name_clean": alt_name_clean
        })

    def is_strict_match(text):
        if not text or not isinstance(text, str): return False
        text_lower = text.lower()
        
        # Kritik Sistem Uygulamalarını Koruma (Görev çubuğu, Başlat, Arama ve WebView2 bozulmalarını önler)
        whitelist = ["shellexperience", "startmenu", "windows.search", "webview2"]
        for w in whitelist:
            if w in text_lower:
                return False
                
        text_clean = re.sub(r'[^a-z0-9]', '', text_lower)
        for rule in match_rules:
            if rule["name_lower"] in text_lower:
                if rule["regex"].search(text_lower): return True
            if '.' in rule["name_lower"] and rule["name_lower"] in text_lower: return True
            
            nc = rule["name_clean"]
            if nc == "edge":
                if "edge" in text_clean and "webview" not in text_clean and "knowledge" not in text_clean and "edgecast" not in text_clean: return True
            elif nc == "onedrive":
                if "onedrive" in text_clean: return True
            elif nc == "copilot":
                if "copilot" in text_clean: return True
            elif nc == "msteams":
                if "teams" in text_clean: return True
                
            if nc in text_clean and len(nc) >= 6: return True
            anc = rule["alt_name_clean"]
            if anc and len(anc) >= 6 and anc in text_clean: return True
        return False

    # 1. Kapatılacak İşlemleri Belirle ve Kapat (taskkill)
    processes_to_kill = set()
    for name in filtered_names:
        processes_to_kill.add(f"{name}.exe")
        name_clean = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
        if name_clean == "edge" or name_clean == "msedge" or name_clean == "microsoftedge":
            processes_to_kill.update(["msedge.exe", "MicrosoftEdgeUpdate.exe", "identity_helper.exe", "msteams.exe"])
        elif "onedrive" in name_clean:
            processes_to_kill.update(["OneDrive.exe", "FileCoAuth.exe", "OneDrive.Sync.Service.exe", "FileSyncConfig.exe", "OneDriveStandaloneUpdater.exe"])
        elif "copilot" in name_clean:
            processes_to_kill.update(["Copilot.exe"])
        elif "cbs" in name_clean or "crossdevice" in name_clean or "experience" in name_clean:
            processes_to_kill.update(["CrossDeviceResume.exe", "Widgets.exe"])
            
    for proc in processes_to_kill:
        subprocess.run(f"taskkill /f /im {proc}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)

    for name in filtered_names:
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name)
        if len(clean_name) > 4:
            subprocess.run(f'powershell -NoProfile -Command "Get-Process | Where-Object {{$_.Name -match \'{clean_name}\'}} | Stop-Process -Force -ErrorAction SilentlyContinue"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)

    # 2. Yetki Fonksiyonları
    def get_owner(path):
        try:
            cmd = f'powershell -NoProfile -Command "(Get-Acl -LiteralPath \'{path}\').Owner"'
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, creationflags=0x08000000)
            return r.stdout.strip()
        except:
            return None

    def take_temp_ownership(path):
        if not os.path.exists(path): return None
        original_owner = get_owner(path)
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', os.path.basename(path) or "root")
        acl_path = os.path.join(tempfile.gettempdir(), f"acl_{safe_name}.txt")
        if os.path.exists(acl_path):
            try: os.remove(acl_path)
            except: pass
        
        subprocess.run(f'icacls "{path}" /save "{acl_path}" /c /q', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
        subprocess.run(f'takeown /f "{path}" /a', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
        subprocess.run(f'icacls "{path}" /grant Administrators:F /c /q', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
        
        return {"path": path, "owner": original_owner, "acl_path": acl_path}

    def restore_ownership_and_acl(backup_info):
        if not backup_info: return
        path = backup_info.get("path")
        owner = backup_info.get("owner")
        acl_path = backup_info.get("acl_path")
        
        if not os.path.exists(path):
            if acl_path and os.path.exists(acl_path):
                try: os.remove(acl_path)
                except: pass
            return
            
        if owner:
            subprocess.run(f'icacls "{path}" /setowner "{owner}" /c /q', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
        if acl_path and os.path.exists(acl_path):
            parent_dir = os.path.dirname(path)
            subprocess.run(f'icacls "{parent_dir}" /restore "{acl_path}" /c /q', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
            try: os.remove(acl_path)
            except: pass

    # 3. Klasör Tarama Tanımları
    sys_drive = os.environ.get('SystemDrive', 'C:')
    search_dirs = [
        (rf"{sys_drive}\Program Files", 3),
        (rf"{sys_drive}\Program Files (x86)", 3),
        (rf"{sys_drive}\Program Files\Microsoft", 3),
        (rf"{sys_drive}\Program Files (x86)\Microsoft", 3),
        (rf"{sys_drive}\Program Files\WindowsApps", 3),
        (rf"{sys_drive}\ProgramData", 3),
        (rf"{sys_drive}\ProgramData\Microsoft", 3),
        (rf"{sys_drive}\ProgramData\Microsoft\Windows\Start Menu\Programs", 4),
        (rf"{sys_drive}\Users\Public\Desktop", 2)
    ]
    
    users_dir = rf"{sys_drive}\Users"
    if os.path.exists(users_dir):
        for user in os.listdir(users_dir):
            if user.lower() not in ["public", "default", "default user", "all users"]:
                user_path = os.path.join(users_dir, user)
                search_dirs.extend([
                    (os.path.join(user_path, "AppData", "Local"), 5),
                    (os.path.join(user_path, "AppData", "Local", "Microsoft"), 5),
                    (os.path.join(user_path, "AppData", "Local", "Packages"), 4),
                    (os.path.join(user_path, "AppData", "LocalLow"), 5),
                    (os.path.join(user_path, "AppData", "Roaming"), 8),
                    (os.path.join(user_path, "AppData", "Roaming", "Microsoft"), 8),
                    (os.path.join(user_path, "Desktop"), 2),
                    (os.path.join(user_path, "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs"), 5),
                    (os.path.join(user_path, "AppData", "Roaming", "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar"), 4)
                ])
                
    def scan_directory(base_dir, current_depth=0, max_depth=4):
        bd_lower = base_dir.lower()
        if "apprepository" in bd_lower or "appmodel" in bd_lower or "appxalluserstore" in bd_lower:
            return [], None
        if current_depth > max_depth: return [], None
        if not os.path.exists(base_dir): return [], None
        items = []
        found_paths = []
        try:
            items = os.listdir(base_dir)
        except PermissionError:
            backup = take_temp_ownership(base_dir)
            try:
                items = os.listdir(base_dir)
            except Exception:
                pass
            finally:
                if backup:
                    restore_ownership_and_acl(backup)
        except Exception:
            return [], None

        for item in items:
            item_path = os.path.join(base_dir, item)
            item_lower = item.lower()
            if is_strict_match(item):
                found_paths.append(item_path)
            elif os.path.isdir(item_path):
                if item_lower not in ["windows", "system32", "winsxs", "temp", "syswow64", "node_modules", ".git", "microsoft.net", "servicing"]:
                    sub_paths, _ = scan_directory(item_path, current_depth + 1, max_depth)
                    found_paths.extend(sub_paths)
        return found_paths, None

    # 4. Registry Tarama Tanımları
    # 4. Registry Tarama Tanımları (Whitelist mantığı ve limitli derinlik)
    hives = [
        (winreg.HKEY_CLASSES_ROOT, "HKCR"),
        (winreg.HKEY_CURRENT_USER, "HKCU"),
        (winreg.HKEY_LOCAL_MACHINE, "HKLM"),
        (winreg.HKEY_USERS, "HKU"),
        (winreg.HKEY_CURRENT_CONFIG, "HKCC")
    ]

    def search_reg_hive(hkey, root_sub_key):
        fk, fv = [], []
        def _scan(sub_key, depth=0):
            if depth > 40: return # Köküne kadar taranırken recursion limitini aşmamak için belirli derinlik seviyesi (Sonsuz döngü riski azaltıldı)
            sub_lower = sub_key.lower() if sub_key else ""
            if "appxalluserstore" in sub_lower or "staterepository" in sub_lower or "packagedcom" in sub_lower: return
            try:
                with winreg.OpenKey(hkey, sub_key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                    info = winreg.QueryInfoKey(key)
                    subkeys = [winreg.EnumKey(key, i) for i in range(info[0])]
                    values = [winreg.EnumValue(key, i) for i in range(info[1])]
            except Exception:
                return
            for s in subkeys:
                current_path = f"{sub_key}\\{s}" if sub_key else s
                if is_strict_match(s):
                    fk.append((hkey, current_path))
                else:
                    _scan(current_path, depth + 1)
            for v in values:
                val_name, val_data = v[0], v[1]
                if is_strict_match(val_name) or is_strict_match(str(val_data)):
                    fv.append((hkey, sub_key, val_name))
        _scan(root_sub_key)
        return fk, fv

    def scan_hku():
        fk, fv = [], []
        try:
            with winreg.OpenKey(winreg.HKEY_USERS, "") as key:
                info = winreg.QueryInfoKey(key)
                for i in range(info[0]):
                    user_sid = winreg.EnumKey(key, i)
                    k, v = search_reg_hive(winreg.HKEY_USERS, user_sid)
                    fk.extend(k)
                    fv.extend(v)
        except Exception:
            pass
        return fk, fv
    # 5. Silme öncesi inatçı arka plan servislerini öldür
    for proc in processes_to_kill:
        subprocess.run(f"taskkill /f /im {proc}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    
    # Hızlı toplu taskkill (PowerShell ile her uygulama için ayrı Popen açmak aşırı geciktirir, tek komutta topladık)
    valid_kill_names = [re.sub(r'[^a-zA-Z0-9]', '', n) for n in filtered_names if len(re.sub(r'[^a-zA-Z0-9]', '', n)) > 4]
    if valid_kill_names:
        ps_kill_script = "$names = @(" + ", ".join(f"'{n.replace('\'', '\'\'')}'" for n in valid_kill_names) + "); foreach ($n in $names) { Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -match $n } | Stop-Process -Force -ErrorAction SilentlyContinue }"
        subprocess.run(f'powershell -NoProfile -Command "{ps_kill_script}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)

    # 6. PowerShell İle Resmi AppX ve Program Silme Aşaması (Dosya Kazımadan ÖNCE Yapılır)
    ps_script = """
    $ErrorActionPreference = 'SilentlyContinue'
    $names = __NAMES_ARRAY__
    [Console]::WriteLine("APPX_INIT:START")
    $uninstallPaths = @('HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall', 'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall', 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall')
    $uninstall = Get-ChildItem -Path $uninstallPaths -ErrorAction SilentlyContinue | Get-ItemProperty -ErrorAction SilentlyContinue
    [Console]::WriteLine("APPX_INIT:DONE")
    
    foreach ($name in $names) {
        [Console]::WriteLine("APPX_START:$name")
        
        # 1. Provisioned Paket Silinir (Canli sorgu)
        $provs = Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match $name -or $_.PackageName -match $name }
        if ($name -match "edge") {
            $provs = $provs | Where-Object { $_.DisplayName -notmatch "WebView" -and $_.DisplayName -notmatch "Knowledge" -and $_.DisplayName -notmatch "EdgeUpdate" }
        }
        if ($provs) { 
            $provs | ForEach-Object { Remove-AppxProvisionedPackage -Online -PackageName $_.PackageName -ErrorAction SilentlyContinue }
        }
        
        # 2. Canli Sistem Uzerinden Guncel Kullanici Paketleri Cekilir ve Silinir (Canli sorgu, genis kapsamli tarama)
        $pkgs = Get-AppxPackage -Name "*$name*" -AllUsers -ErrorAction SilentlyContinue
        $pkgs += Get-AppxPackage -AllUsers -ErrorAction SilentlyContinue | Where-Object { $_.Name -match $name -or $_.PackageFullName -match $name -or $_.PackageFamilyName -match $name }
        
        if ($name -match "edge") {
            $pkgs = $pkgs | Where-Object { $_.Name -notmatch "WebView" -and $_.Name -notmatch "Knowledge" -and $_.Name -notmatch "EdgeUpdate" }
        }
        if ($pkgs) { 
            $pkgs | Select-Object -Unique -Property PackageFullName | ForEach-Object { 
                Remove-AppxPackage -Package $_.PackageFullName -AllUsers -ErrorAction SilentlyContinue 
            }
            $pkgs | Select-Object -Unique -Property PackageFamilyName | ForEach-Object {
                if ($_.PackageFamilyName) {
                    Remove-AppxPackage $_.PackageFamilyName -AllUsers -ErrorAction SilentlyContinue
                }
            }
        }
        
        $uninstall | Where-Object { $_.DisplayName -match $name } | ForEach-Object {
            if ($_.QuietUninstallString) { Start-Process cmd -ArgumentList "/c", $_.QuietUninstallString -Wait -NoNewWindow }
            elseif ($_.UninstallString) { Start-Process cmd -ArgumentList "/c", $_.UninstallString -Wait -NoNewWindow }
        }
    }
    """
    
    import base64
    ps_script = ps_script.replace("__NAMES_ARRAY__", "@(" + ", ".join(f"'{n.replace('\'', '\'\'')}'" for n in filtered_names) + ")")
    ps_encoded = base64.b64encode(ps_script.encode('utf-16le')).decode('utf-8')
    cmd = f'powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {ps_encoded}'
    
    # PowerShell sürecini canlı dinleyip UI'a "tak tak tak" aktarıyoruz
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=0x08000000)
    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if line == "APPX_INIT:START":
            if ui_queue: ui_queue.put({"action": "log", "text": "[-] Sistem paketleri analiz ediliyor (Lütfen bekleyin)...", "color": "#E63B4D"})
        elif line == "APPX_INIT:DONE":
            if ui_queue: ui_queue.put({"action": "log", "text": "[-] Analiz tamamlandı, uygulamalar siliniyor...", "color": "#E63B4D"})
        elif line.startswith("APPX_START:"):
            app_name = line.split("APPX_START:")[1]
            if ui_queue: ui_queue.put({"action": "log", "text": f"[-] Sistemden siliniyor: {app_name}", "color": "#FF5555"})
    process.stdout.close()
    process.wait()
    
    # 7. Eşzamanlı (Multi-Threading) Kalıntı Tarama İşleminin Başlatılması (PowerShell Sonrası)
    safe_to_delete_paths = []
    restoration_backups = []
    reg_keys_to_delete = []
    reg_values_to_delete = []

    total_tasks = len(search_dirs)
    completed_tasks = 0
    reg_subtasks = []

    if ui_queue:
        ui_queue.put({"action": "log", "text": "Kalıntı Dosyalar İçin Derinlemesine Tarama Başlatılıyor...", "color": "#FFB86C"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        for root_hkey, name in hives:
            if name == "HKU":
                reg_subtasks.append(executor.submit(scan_hku))
            else:
                try:
                    with winreg.OpenKey(root_hkey, "") as key:
                        info = winreg.QueryInfoKey(key)
                        subkeys_found = False
                        for i in range(info[0]):
                            sub_name = winreg.EnumKey(key, i)
                            reg_subtasks.append(executor.submit(search_reg_hive, root_hkey, sub_name))
                            subkeys_found = True
                        if not subkeys_found:
                            reg_subtasks.append(executor.submit(search_reg_hive, root_hkey, ""))
                except Exception:
                    reg_subtasks.append(executor.submit(search_reg_hive, root_hkey, ""))

        total_tasks += len(reg_subtasks)
        future_to_dir = {executor.submit(scan_directory, d, 0, m): d for d, m in search_dirs}
        
        all_futures = list(future_to_dir.keys()) + reg_subtasks
        
        for future in concurrent.futures.as_completed(all_futures):
            completed_tasks += 1
            pct = int((completed_tasks / total_tasks) * 100)
            if pct > 100: pct = 100
            
            if ui_queue:
                ui_queue.put({"action": "progress_update", "text_base": "Sistem kalıntıları taranıyor", "pct": pct, "color": "#FFB86C"})
            
            if future in future_to_dir:
                paths, backup = future.result()
                safe_to_delete_paths.extend(paths)
                if backup:
                    restoration_backups.append(backup)
            else:
                k, v = future.result()
                reg_keys_to_delete.extend(k)
                reg_values_to_delete.extend(v)
                
    if ui_queue:
        ui_queue.put({"action": "progress_stop", "text_base": "Kalıntılar taranıyor", "result": "tarandı", "target": "debloat"})
        ui_queue.put({"action": "log", "text": "Bulunan Kalıntılar İmha Ediliyor (Sıralı İşlem)...", "color": "#E63B4D"})

    if is_strict_match("onedrive"):
        subprocess.run(fr"{sys_drive}\Windows\SysWOW64\OneDriveSetup.exe /uninstall", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)

    def take_ownership_and_delete(path):
        if not os.path.exists(path): return
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except Exception:
            if os.path.isfile(path):
                subprocess.run(f'takeown /f "{path}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                subprocess.run(f'icacls "{path}" /grant Administrators:F', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                try: os.remove(path)
                except Exception: pass
            elif os.path.isdir(path):
                subprocess.run(f'takeown /f "{path}" /r /d y', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                subprocess.run(f'icacls "{path}" /grant Administrators:F /t', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                try: shutil.rmtree(path, ignore_errors=True)
                except Exception: pass

    # Sıralı Silme
    for p in safe_to_delete_paths:
        log_msg(f"    [Dosya/Klasör] Siliniyor: {os.path.basename(p)}", "#FF8C00")
        take_ownership_and_delete(p)

    for backup in reversed(restoration_backups):
        restore_ownership_and_acl(backup)

    for hkey, current_path in reg_keys_to_delete:
        try:
            log_msg(f"    [Kayıt Defteri - Anahtar] Siliniyor: {current_path}", "#FF8C00")
            RegistryEngine.delete_key_recursive(hkey, current_path)
        except Exception:
            pass
            
    for hkey, sub_key, val_name in reg_values_to_delete:
        try:
            log_msg(f"    [Kayıt Defteri - Değer] Siliniyor: {val_name}", "#FF8C00")
            with winreg.OpenKey(hkey, sub_key, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
                winreg.DeleteValue(key, val_name)
        except Exception:
            pass

    if is_strict_match("edge"):
        try:
            edge_lnk = os.path.expandvars(r"%AppData%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Microsoft Edge.lnk")
            if os.path.exists(edge_lnk): os.remove(edge_lnk)
        except Exception:
            pass



