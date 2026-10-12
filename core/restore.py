"""
WinKit - Core System Restore and Component Reset Engine
Handles System Restore point creation, policy unpausing, Defender restoration,
network/DNS reset, and accessibility recovery.
"""

import os
import sys
import time
import winreg
import subprocess
from typing import Tuple, Optional, Callable

from core.constants import CREATE_NO_WINDOW, DETACHED_PROCESS
from core.system import append_runtime_diagnostic
from core.privileges import (
    run_powershell_checked,
    run_powershell_as_system,
)
from core.key_remap import apply_sticky_keys_fix


def is_system_restore_enabled(drive: str = "C:") -> bool:
    """
    Sistem Geri Yükleme korumasının belirtilen sürücüde veya sistem genelinde
    gerçekten etkin (ve gölge kopya alanının tahsis edilmiş) olup olmadığını kontrol eder.
    """
    clean_drive = drive.rstrip("\\")
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as k:
            try:
                disable_sr, _ = winreg.QueryValueEx(k, "DisableSR")
                if disable_sr == 1:
                    return False
            except OSError:
                pass
    except OSError:
        pass

    # Sürücü bazlı gerçek gölge depolama / SPP koruma durumunu sorgula
    try:
        ps_check = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$srKey = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore'
$dsr = (Get-ItemProperty -Path $srKey -Name 'DisableSR' -ErrorAction SilentlyContinue).DisableSR
if ($dsr -eq 1) {{ exit 1 }}

# vssadmin ile belirtilen sürücünün shadowstorage kaydını kontrol et
$vss = & vssadmin.exe list shadowstorage 2>$null
if ($vss -and ($vss -match '\({clean_drive}\)')) {{
    exit 0
}}

# Alternatif: root/default:SystemRestoreConfig sorgula
$cfg = Get-CimInstance -Namespace root/default -ClassName SystemRestoreConfig -ErrorAction SilentlyContinue
if ($cfg -and $cfg.DiskPercent -gt 0) {{
    exit 0
}}
exit 1
"""
        res = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", ps_check],
            capture_output=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        )
        return res.returncode == 0
    except Exception:
        pass

    return False


def enable_system_restore(drive: str = "C:") -> Tuple[bool, str]:
    """Belirtilen sürücüde Sistem Geri Yükleme korumasını etkinleştirir ve gölge alanını tahsis eder."""
    clean_drive = drive.rstrip("\\")
    ps_cmd = (
        "& sc.exe config vss start= demand 2>$null | Out-Null; "
        "& sc.exe start vss 2>$null | Out-Null; "
        "& sc.exe config swprv start= demand 2>$null | Out-Null; "
        "& sc.exe start swprv 2>$null | Out-Null; "
        "& sc.exe config sppsvc start= delayed-auto 2>$null | Out-Null; "
        "& sc.exe start sppsvc 2>$null | Out-Null; "
        "foreach ($path in @("
        "'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\SystemRestore',"
        "'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\SystemRestore',"
        "'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows NT\\CurrentVersion\\SystemRestore'"
        ")) { "
        "if (-not (Test-Path $path)) { New-Item -Path $path -Force 2>$null | Out-Null }; "
        "Set-ItemProperty -Path $path -Name 'DisableSR' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue; "
        "Set-ItemProperty -Path $path -Name 'SystemRestorePointCreationFrequency' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue; "
        "} "
        f"Enable-ComputerRestore -Drive '{clean_drive}\\' -ErrorAction SilentlyContinue; "
        f"& vssadmin.exe resize shadowstorage /for={clean_drive} /on={clean_drive} /maxsize=5% 2>$null | Out-Null"
    )
    try:
        subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        )
        return is_system_restore_enabled(clean_drive), ""
    except Exception as exc:
        return False, str(exc)


def create_system_restore_point(
    description: Optional[str] = None,
    timeout: int = 60,
    enable_if_disabled: bool = False
) -> Tuple[bool, str]:
    """
    Sistem Geri Yükleme noktası oluşturur. 24 saatlik sıklık kısıtlamasını
    ve VSS servis kilitlerini otomatik olarak aşar.
    Koruması kapalıysa ve enable_if_disabled=False ise işlem yapmaz.
    """
    system_drive = os.environ.get("SystemDrive", "C:")
    drive_letter = system_drive.rstrip("\\")

    if not enable_if_disabled and not is_system_restore_enabled(drive_letter):
        append_runtime_diagnostic("System restore skipped: protection is disabled on drive.")
        return False, "Sistem Geri Yükleme koruması kapalı."

    if enable_if_disabled and not is_system_restore_enabled(drive_letter):
        ok, err = enable_system_restore(drive_letter)
        if not ok:
            append_runtime_diagnostic(f"Failed to enable system restore: {err}")

    # 24 saatlik sınırı kaldır (SystemRestorePointCreationFrequency = 0)
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore",
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
        ) as k:
            winreg.SetValueEx(k, "SystemRestorePointCreationFrequency", 0, winreg.REG_DWORD, 0)
    except Exception:
        pass

    date_str = time.strftime("%d-%m-%y")
    desc = description or f"WinKit-{date_str}"
    
    enable_cmd = ""
    if enable_if_disabled:
        enable_cmd = (
            f"& vssadmin.exe add shadowstorage /for={drive_letter} /on={drive_letter} /maxsize=5% 2>$null | Out-Null; "
            f"& vssadmin.exe resize shadowstorage /for={drive_letter} /on={drive_letter} /maxsize=5% 2>$null | Out-Null; "
            f"Enable-ComputerRestore -Drive '{drive_letter}\\' -ErrorAction SilentlyContinue; "
        )

    ps_script = (
        "$ErrorActionPreference = 'Stop'; "
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "& sc.exe config vss start= demand 2>$null | Out-Null; "
        "& sc.exe start vss 2>$null | Out-Null; "
        "& sc.exe config swprv start= demand 2>$null | Out-Null; "
        "& sc.exe start swprv 2>$null | Out-Null; "
        "foreach ($path in @("
        "'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\SystemRestore',"
        "'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows NT\\CurrentVersion\\SystemRestore'"
        ")) { "
        "if (-not (Test-Path $path)) { New-Item -Path $path -Force | Out-Null }; "
        "Set-ItemProperty -Path $path -Name 'DisableSR' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue; "
        "Set-ItemProperty -Path $path -Name 'SystemRestorePointCreationFrequency' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue; "
        "} "
        f"{enable_cmd}"
        f"Checkpoint-Computer -Description '{desc}' -RestorePointType 'MODIFY_SETTINGS' -ErrorAction Stop; "
        f"$pt = Get-ComputerRestorePoint -ErrorAction SilentlyContinue | Select-Object -Last 1; "
        f"if (-not $pt -or $pt.Description -ne '{desc}') {{ exit 1 }}; "
        "exit 0"
    )

    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            err_detail = (result.stderr or result.stdout or "").strip()
            append_runtime_diagnostic(f"Checkpoint-Computer error: {err_detail}")
            return False, f"Sistem geri yükleme noktası oluşturulamadı: {err_detail[:120]}"
        else:
            append_runtime_diagnostic(f"System restore point created successfully: {desc}")
            return True, desc
    except subprocess.TimeoutExpired:
        append_runtime_diagnostic(f"Checkpoint-Computer timed out after {timeout}s")
        return False, "Geri yükleme noktası zaman aşımına uğradı."
    except Exception as exc:
        return False, str(exc)


def restore_windows_defender() -> Tuple[bool, str]:
    """Windows Defender servislerini, sürücülerini ve arayüzünü yeniden etkinleştirir."""
    system_script = r"""
$ErrorActionPreference = 'SilentlyContinue'

# 1. Başlangıç koruma görevini ve IFEO kaydını temizle
& schtasks.exe /delete /tn "WinKit_DefenderEnforcer" /f 2>$null | Out-Null
Remove-Item 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\SecurityHealthSystray.exe' -Recurse -Force -ErrorAction SilentlyContinue

# 2. Registry ilkelerini temizle
Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender' -Name 'DisableAntiSpyware' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender' -Name 'DisableAntiVirus' -ErrorAction SilentlyContinue
Remove-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender\SmartScreen' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender\PhishingProtection' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender Security Center' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WTDS' -Recurse -Force -ErrorAction SilentlyContinue

# 3. SmartScreen politikasını sıfırla
Set-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' -Name 'EnableSmartScreen' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' -Name 'ShellSmartScreenLevel' -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer' -Name 'SmartScreenEnabled' -Value 'RequireAdmin' -Type String -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer' -Name 'SmartScreenPuaEnabled' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

# 3. SecurityHealthService'i onar ve başlat
& sc.exe query SecurityHealthService 2>$null | Out-Null
if ($LASTEXITCODE -eq 1060) {
    & sc.exe create SecurityHealthService binPath= "%systemroot%\system32\SecurityHealthService.exe" start= auto DisplayName= "Windows Security Service" 2>$null | Out-Null
}
$shs = 'HKLM:\SYSTEM\CurrentControlSet\Services\SecurityHealthService'
if (-not (Test-Path $shs)) { New-Item -Path $shs -Force | Out-Null }
Set-ItemProperty -Path $shs -Name 'DisplayName' -Value 'Windows Security Service' -Type String -Force
Set-ItemProperty -Path $shs -Name 'ImagePath' -Value "$env:WINDIR\system32\SecurityHealthService.exe" -Type ExpandString -Force
Set-ItemProperty -Path $shs -Name 'Type' -Value 16 -Type DWord -Force
Set-ItemProperty -Path $shs -Name 'Start' -Value 2 -Type DWord -Force
Set-ItemProperty -Path $shs -Name 'ObjectName' -Value 'LocalSystem' -Type String -Force
Set-ItemProperty -Path $shs -Name 'LaunchProtected' -Value 2 -Type DWord -Force -ErrorAction SilentlyContinue
& sc.exe config SecurityHealthService start=auto 2>$null | Out-Null
& sc.exe start SecurityHealthService 2>$null | Out-Null

# 4. Defender servislerini etkinleştir ve başlat
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

# 5. SecHealthUI paketini yeniden kaydet
Get-ChildItem -Path "$env:WINDIR\SystemApps" -Filter "*SecHealthUI*" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $manifest = Join-Path $_.FullName "AppxManifest.xml"
    if (Test-Path $manifest) {
        Add-AppxPackage -Register -DisableDevelopmentMode $manifest -ErrorAction SilentlyContinue
    }
}

& fltmc.exe load WdFilter 2>$null | Out-Null

# 6. WSC servisini yenile
& sc.exe stop wscsvc 2>$null | Out-Null
Start-Sleep -Milliseconds 200
& sc.exe start wscsvc 2>$null | Out-Null
"""
    user_script = r"""
$ErrorActionPreference = 'SilentlyContinue'
Set-MpPreference -DisableRealtimeMonitoring $false -DisableBehaviorMonitoring $false -DisableIOAVProtection $false -DisableScriptScanning $false -ErrorAction SilentlyContinue
Set-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run' -Name 'SecurityHealth' -Value '%systemroot%\system32\SecurityHealthSystray.exe' -Type ExpandString -Force -ErrorAction SilentlyContinue
Start-Process -FilePath "$env:WINDIR\system32\SecurityHealthSystray.exe" -ErrorAction SilentlyContinue
"""
    try:
        run_powershell_as_system(system_script, timeout=60)
        run_powershell_checked(user_script, timeout=60)
        return True, "Windows Defender ve güvenlik servisleri yeniden etkinleştirildi."
    except Exception as exc:
        return False, f"Windows Defender geri yüklenemedi: {exc}"


def restore_windows_updates() -> Tuple[bool, str]:
    """Windows Güncellemeleri kısıtlamalarını kaldırır ve servisleri başlatır."""
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$p = 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings'
Remove-ItemProperty -Path $p -Name 'PauseUpdatesStartTime' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path $p -Name 'PauseUpdatesExpiryTime' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path $p -Name 'PauseFeatureUpdatesStartTime' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path $p -Name 'PauseFeatureUpdatesEndTime' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path $p -Name 'PauseQualityUpdatesStartTime' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path $p -Name 'PauseQualityUpdatesEndTime' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path $p -Name 'FlightSettingsMaxPauseDays' -ErrorAction SilentlyContinue

& sc.exe config wuauserv start=auto 2>$null | Out-Null
& sc.exe start wuauserv 2>$null | Out-Null
& sc.exe config UsoSvc start=demand 2>$null | Out-Null
& sc.exe start UsoSvc 2>$null | Out-Null
"""
    try:
        run_powershell_checked(script, timeout=60)
        return True, "Windows Güncellemeleri kısıtlaması kaldırıldı ve servisler başlatıldı."
    except Exception as exc:
        return False, f"Güncelleme servisleri geri yüklenemedi: {exc}"


def restore_network_settings() -> Tuple[bool, str]:
    """DNS ve ağ ayarlarını otomatik DHCP moduna sıfırlar ve IPv6'yı açar."""
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' })
foreach ($adapter in $adapters) {
    Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ResetServerAddresses -ErrorAction SilentlyContinue
    Enable-NetAdapterBinding -Name $adapter.Name -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue
}
Remove-DnsClientDohServerAddress -ServerAddress '1.1.1.1' -ErrorAction SilentlyContinue
Remove-DnsClientDohServerAddress -ServerAddress '1.0.0.1' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters' -Name 'DisabledComponents' -ErrorAction SilentlyContinue
Remove-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters' -Name 'EnableAutoDoh', 'DnsOverHttps' -ErrorAction SilentlyContinue
Get-ChildItem -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters\Interfaces' -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-ItemProperty -Path $_.PSPath -Name 'DnsOverHttps', 'EnableDoh', 'DohTemplate', 'DnsOverHttpsAutoUpgrade', 'DnsOverHttpsAllowFallbackToUdp', 'ServerAddresses' -ErrorAction SilentlyContinue
}
Get-ChildItem -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\InterfaceSpecificParameters' -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -Path "$($_.PSPath)\DohInterfaceSettings" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$($_.PSPath)\DohProfileSettings" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $_.PSPath -Name 'DnsOverHttps', 'DohFlags' -ErrorAction SilentlyContinue
}
Get-ChildItem -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces' -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-ItemProperty -Path $_.PSPath -Name 'DnsOverHttps', 'EnableDoh', 'DohTemplate' -ErrorAction SilentlyContinue
}
Clear-DnsClientCache -ErrorAction SilentlyContinue
& ipconfig.exe /flushdns 2>$null | Out-Null
"""
    try:
        run_powershell_checked(script, timeout=60)
        return True, "DNS ve ağ ayarları otomatik DHCP moduna sıfırlandı."
    except Exception as exc:
        return False, f"Ağ ayarları sıfırlanamadı: {exc}"


def restore_sticky_keys() -> Tuple[bool, str]:
    """Klavye erişilebilirlik (Yapışkan Tuşlar) ayarlarını varsayılana döndürür."""
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
foreach ($h in @('HKCU:', 'Registry::HKEY_USERS\.DEFAULT')) {
    Set-ItemProperty -Path "$h\Control Panel\Accessibility\StickyKeys" -Name "Flags" -Value "510" -Force -ErrorAction SilentlyContinue
    Set-ItemProperty -Path "$h\Control Panel\Accessibility\Keyboard Response" -Name "Flags" -Value "126" -Force -ErrorAction SilentlyContinue
    Set-ItemProperty -Path "$h\Control Panel\Accessibility\ToggleKeys" -Name "Flags" -Value "58" -Force -ErrorAction SilentlyContinue
}
"""
    try:
        apply_sticky_keys_fix(enable_sticky=True)
        run_powershell_checked(script, timeout=60)
        return True, "Klavye erişilebilirlik (Yapışkan Tuşlar) ayarları sıfırlandı."
    except Exception as exc:
        return False, f"Yapışkan tuşlar sıfırlanamadı: {exc}"


def open_system_restore_gui() -> bool:
    """Windows Sistem Geri Yükleme arayüzünü (rstrui.exe) başlatır."""
    try:
        subprocess.Popen(["rstrui.exe"], creationflags=CREATE_NO_WINDOW)
        return True
    except Exception:
        return False
