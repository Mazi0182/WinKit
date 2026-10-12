import os
import winreg
from typing import Callable, Optional
from core.privileges import run_powershell_as_trustedinstaller, run_powershell_as_system

class DefenderController:
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback

    def log(self, text: str, color: str = "#00FF9D"):
        if self.log_callback:
            self.log_callback(text, color)

    @staticmethod
    def is_tamper_protection_enabled() -> bool:
        """
        Windows Kurcalamaya Karşı Koruma (Tamper Protection) durumunu sorgular.
        TamperProtection != 0 ve != 4 ise veya anahtara erişim engelleniyorsa aktiftir.
        """
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows Defender\Features",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as k:
                val, _ = winreg.QueryValueEx(k, "TamperProtection")
                return val not in (0, 4)
        except Exception:
            return True

    def open_tamper_protection_settings(self):
        """
        Kullanıcının Kurcalamaya Karşı Korumayı kapatabilmesi için doğrudan ilgili ayar sayfasını açar.
        """
        self.log("[!] DİKKAT: Windows Kurcalamaya Karşı Koruma (Tamper Protection) devrede!", "#FFB86C")
        self.log("[*] Defender servislerinin durdurulabilmesi için Kurcalamaya Karşı Koruma kapatılmalıdır. Ayarlar sayfası açılıyor...", "#00E5FF")
        try:
            os.system("start windowsdefender://threatsettings")
        except Exception:
            pass

    def disable_defender(self) -> tuple[bool, str]:
        if self.is_tamper_protection_enabled():
            self.open_tamper_protection_settings()

        script = r"""
$ErrorActionPreference = 'SilentlyContinue'

if (-not (Get-PSDrive -Name HKCR -ErrorAction SilentlyContinue)) {
    New-PSDrive -Name HKCR -PSProvider Registry -Root HKEY_CLASSES_ROOT -ErrorAction SilentlyContinue | Out-Null
}
if (-not (Get-PSDrive -Name HKU -ErrorAction SilentlyContinue)) {
    New-PSDrive -Name HKU -PSProvider Registry -Root HKEY_USERS -ErrorAction SilentlyContinue | Out-Null
}

# 1. Tamper Protection devre dışı bırak
$tpPath = 'HKLM:\SOFTWARE\Microsoft\Windows Defender\Features'
if (-not (Test-Path $tpPath)) { New-Item -Path $tpPath -Force | Out-Null }
Set-ItemProperty -Path $tpPath -Name 'TamperProtection' -Value 4 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $tpPath -Name 'TamperProtectionSource' -Value 2 -Type DWord -Force -ErrorAction SilentlyContinue
& reg.exe add "HKLM\SOFTWARE\Microsoft\Windows Defender\Features" /v TamperProtection /t REG_DWORD /d 4 /f /reg:64 2>$null | Out-Null
& reg.exe add "HKLM\SOFTWARE\Microsoft\Windows Defender\Features" /v TamperProtectionSource /t REG_DWORD /d 2 /f /reg:64 2>$null | Out-Null

# 2. Minifilter sürücülerini çöz
& fltmc.exe unload WdFilter 2>$null | Out-Null
& fltmc.exe unload WdNisDrv 2>$null | Out-Null

# 3. Defender Grup İlkelerini ayarla
$defenderPolicy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender'
if (-not (Test-Path $defenderPolicy)) { New-Item -Path $defenderPolicy -Force | Out-Null }
Set-ItemProperty -Path $defenderPolicy -Name DisableAntiSpyware -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $defenderPolicy -Name DisableAntiVirus -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
& reg.exe add "$defenderPolicy" /v DisableAntiSpyware /t REG_DWORD /d 1 /f /reg:64 2>$null | Out-Null
& reg.exe add "$defenderPolicy" /v DisableAntiVirus /t REG_DWORD /d 1 /f /reg:64 2>$null | Out-Null

$rtPolicy = "$defenderPolicy\Real-Time Protection"
if (-not (Test-Path $rtPolicy)) { New-Item -Path $rtPolicy -Force | Out-Null }
foreach ($name in @('DisableRealtimeMonitoring','DisableBehaviorMonitoring','DisableOnAccessProtection','DisableScanOnRealtimeEnable','DisableIOAVProtection')) {
    Set-ItemProperty -Path $rtPolicy -Name $name -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
    & reg.exe add "$rtPolicy" /v $name /t REG_DWORD /d 1 /f /reg:64 2>$null | Out-Null
}

# 4. SecHealthUI (Windows Güvenliği) XAML arayüzünü koru (UILockdown ve PassiveMode kaldırılır; böylece siyah ekran oluşmaz, doğal kırmızı kalkan devreye girer)
foreach ($vtpKey in @(
    'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender Security Center\Virus and threat protection',
    'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender\UX Configuration'
)) {
    if (Test-Path $vtpKey) {
        Remove-ItemProperty -Path $vtpKey -Name 'UILockdown' -Force -ErrorAction SilentlyContinue
        & reg.exe delete "$vtpKey" /v UILockdown /f /reg:64 2>$null | Out-Null
    }
}

$defDirect = 'HKLM:\SOFTWARE\Microsoft\Windows Defender'
if (Test-Path $defDirect) {
    Remove-ItemProperty -Path $defDirect -Name 'PassiveMode' -Force -ErrorAction SilentlyContinue
    & reg.exe delete "$defDirect" /v PassiveMode /f /reg:64 2>$null | Out-Null
    Set-ItemProperty -Path $defDirect -Name DisableAntiSpyware -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
    Set-ItemProperty -Path $defDirect -Name DisableAntiVirus -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
    & reg.exe add "$defDirect" /v DisableAntiSpyware /t REG_DWORD /d 1 /f /reg:64 2>$null | Out-Null
    & reg.exe add "$defDirect" /v DisableAntiVirus /t REG_DWORD /d 1 /f /reg:64 2>$null | Out-Null
}

# 5. SmartScreen Kapatma (Explorer, System, Windows Defender SmartScreen, Edge PhishingFilter)
$machExp = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer'
if (-not (Test-Path $machExp)) { New-Item -Path $machExp -Force | Out-Null }
Set-ItemProperty -Path $machExp -Name 'SmartScreenEnabled' -Value 'Off' -Type String -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $machExp -Name 'SmartScreenPuaEnabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

$sysPol = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System'
if (-not (Test-Path $sysPol)) { New-Item -Path $sysPol -Force | Out-Null }
Set-ItemProperty -Path $sysPol -Name 'EnableSmartScreen' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $sysPol -Name 'ShellSmartScreenLevel' -Value 'Off' -Type String -Force -ErrorAction SilentlyContinue

$ssPol = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender\SmartScreen'
if (-not (Test-Path $ssPol)) { New-Item -Path $ssPol -Force | Out-Null }
Set-ItemProperty -Path $ssPol -Name 'ConfigureAppInstallControl' -Value 'Anywhere' -Type String -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $ssPol -Name 'ConfigureAppInstallControlEnabled' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

$phishPol = 'HKLM:\SOFTWARE\Policies\Microsoft\MicrosoftEdge\PhishingFilter'
if (-not (Test-Path $phishPol)) { New-Item -Path $phishPol -Force | Out-Null }
Set-ItemProperty -Path $phishPol -Name 'EnabledV9' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

# 6. SmartScreen AppHost (Microsoft Store Apps) Kapatma - HKLM ve tüm kullanıcı SID'leri
$appHostPaths = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppHost',
    'HKLM:\SOFTWARE\Policies\Microsoft\Windows\CurrentVersion\AppHost',
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\AppHost'
)
Get-ChildItem -Path 'Registry::HKEY_USERS' -ErrorAction SilentlyContinue | Where-Object {
    $_.PSChildName -match '^S-1-5-21-' -and -not $_.PSChildName.EndsWith('_Classes')
} | ForEach-Object {
    $appHostPaths += "$($_.PSPath)\Software\Microsoft\Windows\CurrentVersion\AppHost"
}
foreach ($ap in $appHostPaths) {
    if (-not (Test-Path $ap)) { New-Item -Path $ap -Force | Out-Null }
    Set-ItemProperty -Path $ap -Name 'EnableWebContentEvaluation' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
}

# 7. smartscreen.exe IFEO'sunu kaldır (Ayarlar appsfeatures-advanced COM kilitlenmesini engelle)
$ssIfeo = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\smartscreen.exe'
if (Test-Path $ssIfeo) {
    Remove-Item -LiteralPath $ssIfeo -Recurse -Force -ErrorAction SilentlyContinue
    & reg.exe delete "$ssIfeo" /f /reg:64 2>$null | Out-Null
}

# SecurityHealthSystray.exe: Run başlangıç anahtarlarını sil, HideSystray politikasını mühürle
Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run' -Name 'SecurityHealth' -Force -ErrorAction SilentlyContinue
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'SecurityHealth' -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path 'Registry::HKEY_USERS' -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -match '^S-1-5-21-' } | ForEach-Object {
    Remove-ItemProperty -Path "$($_.PSPath)\Software\Microsoft\Windows\CurrentVersion\Run" -Name 'SecurityHealth' -Force -ErrorAction SilentlyContinue
}
$stPolicy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender Security Center\Systray'
if (-not (Test-Path $stPolicy)) { New-Item -Path $stPolicy -Force | Out-Null }
Set-ItemProperty -Path $stPolicy -Name 'HideSystray' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
& reg.exe add "$stPolicy" /v HideSystray /t REG_DWORD /d 1 /f /reg:64 2>$null | Out-Null

$shIfeo = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\SecurityHealthSystray.exe'
if (Test-Path $shIfeo) {
    Remove-Item -LiteralPath $shIfeo -Recurse -Force -ErrorAction SilentlyContinue
    & reg.exe delete "$shIfeo" /f /reg:64 2>$null | Out-Null
}

# 8. Zamanlanmış Defender Görevlerini Devre Dışı Bırak
$tasks = @(
    "\Microsoft\Windows\Windows Defender\Windows Defender Cache Maintenance",
    "\Microsoft\Windows\Windows Defender\Windows Defender Cleanup",
    "\Microsoft\Windows\Windows Defender\Windows Defender Scheduled Scan",
    "\Microsoft\Windows\Windows Defender\Windows Defender Verification"
)
foreach ($t in $tasks) {
    & schtasks.exe /change /tn "$t" /disable 2>$null | Out-Null
}
$taskTree = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache\Tree\Microsoft\Windows\Windows Defender'
if (Test-Path $taskTree) {
    Get-ChildItem -Path $taskTree -ErrorAction SilentlyContinue | ForEach-Object {
        $id = (Get-ItemProperty $_.PSPath -Name 'Id' -ErrorAction SilentlyContinue).Id
        if ($id) {
            $taskEntry = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache\Tasks\$id"
            if (Test-Path $taskEntry) {
                Set-ItemProperty -Path $taskEntry -Name 'Actions' -Value ([byte[]]@()) -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

# 9. EPP Context Menu Shell Uzantılarını Temizle
$eppKeys = @(
    'HKCR:\*\shellex\ContextMenuHandlers\EPP',
    'HKLM:\SOFTWARE\Classes\*\shellex\ContextMenuHandlers\EPP',
    'HKCR:\Directory\shellex\ContextMenuHandlers\EPP',
    'HKLM:\SOFTWARE\Classes\Directory\shellex\ContextMenuHandlers\EPP',
    'HKCR:\Directory\Background\shellex\ContextMenuHandlers\EPP',
    'HKLM:\SOFTWARE\Classes\Directory\Background\shellex\ContextMenuHandlers\EPP',
    'HKCR:\Drive\shellex\ContextMenuHandlers\EPP',
    'HKLM:\SOFTWARE\Classes\Drive\shellex\ContextMenuHandlers\EPP',
    'HKCR:\CLSID\{09A47860-11B0-4DA5-AFA5-26D86198A780}',
    'HKLM:\SOFTWARE\Classes\CLSID\{09A47860-11B0-4DA5-AFA5-26D86198A780}'
)
foreach ($ek in $eppKeys) {
    if (Test-Path -LiteralPath $ek) { Remove-Item -LiteralPath $ek -Recurse -Force -ErrorAction SilentlyContinue }
    $ekRaw = $ek.Replace('HKCR:\', 'HKCR\').Replace('HKLM:\', 'HKLM\')
    & reg.exe delete $ekRaw /f /reg:64 2>$null | Out-Null
    & reg.exe delete $ekRaw /f /reg:32 2>$null | Out-Null
}

# 10. Defender ve İlgili Servisleri Durdur ve Devre Dışı Bırak (Start = 4)
$servicesToDisable = @('WinDefend', 'WdFilter', 'WdNisDrv', 'WdNisSvc', 'Sense', 'MDCoreSvc', 'webthreatdefsvc', 'MsCoreSvc', 'WdBoot')

# Önceki çalıştırmadan kalan olası Deny SetValue izin kilidini sıfırla (Start=4 yazabilmek için)
foreach ($svc in $servicesToDisable) {
    $svcRegPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$svc"
    if (Test-Path -LiteralPath $svcRegPath) {
        try {
            $acl = Get-Acl -LiteralPath $svcRegPath -ErrorAction SilentlyContinue
            if ($acl) {
                $adminSid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-32-544")
                $acl.SetOwner($adminSid)
                $ruleAdm = New-Object System.Security.AccessControl.RegistryAccessRule($adminSid, "FullControl", "Allow")
                $acl.ResetAccessRule($ruleAdm)
                Set-Acl -LiteralPath $svcRegPath -AclObject $acl -ErrorAction SilentlyContinue
            }
        } catch {}
    }
}

foreach ($svc in $servicesToDisable) {
    & sc.exe stop $svc 2>$null | Out-Null
    & sc.exe config $svc start= disabled 2>$null | Out-Null
    & sc.exe failure $svc reset= 0 actions= "" 2>$null | Out-Null
    & reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\$svc" /v Start /t REG_DWORD /d 4 /f /reg:64 2>$null | Out-Null
}

# 11. DACL HARDENING: Servis anahtarlarında SetValue yetkisini Deny yaparak Windows'un
# restart sonrası Start = 2 (Auto) yapmasını engelle (Sordum Defender Control yöntemi)
foreach ($svc in $servicesToDisable) {
    $svcRegPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$svc"
    if (Test-Path $svcRegPath) {
        try {
            $acl = Get-Acl -LiteralPath $svcRegPath
            $ruleSys = New-Object System.Security.AccessControl.RegistryAccessRule('NT AUTHORITY\SYSTEM', 'SetValue', 'Deny')
            $ruleAdm = New-Object System.Security.AccessControl.RegistryAccessRule('BUILTIN\Administrators', 'SetValue', 'Deny')
            $ruleTi  = New-Object System.Security.AccessControl.RegistryAccessRule('NT SERVICE\TrustedInstaller', 'SetValue', 'Deny')
            $acl.AddAccessRule($ruleSys)
            $acl.AddAccessRule($ruleAdm)
            $acl.AddAccessRule($ruleTi)
            Set-Acl -LiteralPath $svcRegPath -AclObject $acl -ErrorAction SilentlyContinue
        } catch {}
    }
}

# 12. Süreçleri sonlandır
& taskkill.exe /f /im MsMpEng.exe /im MpDefenderCoreService.exe /im NisSrv.exe /im SenseCncProxy.exe /im MsSense.exe /im smartscreen.exe /im SecurityHealthSystray.exe 2>$null | Out-Null

# 13. SecHealthUI (Windows Güvenliği) ve wscsvc'nin çalışmaya devam etmesini sağla
& reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\SecurityHealthService" /v Start /t REG_DWORD /d 2 /f /reg:64 2>$null | Out-Null
& sc.exe config SecurityHealthService start= auto 2>$null | Out-Null
& sc.exe start SecurityHealthService 2>$null | Out-Null
& reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\wscsvc" /v Start /t REG_DWORD /d 2 /f /reg:64 2>$null | Out-Null
& sc.exe config wscsvc start= auto 2>$null | Out-Null
& sc.exe start wscsvc 2>$null | Out-Null

# 14. WinKit_DefenderEnforcer başlangıç görevini temizle (flicker ve odak hırsızlığını engelle)
& schtasks.exe /delete /tn "WinKit_DefenderEnforcer" /f 2>$null | Out-Null
"""
        ok, err = run_powershell_as_trustedinstaller(script, timeout=60)
        if not ok:
            ok, err = run_powershell_as_system(script, timeout=60)

        if ok:
            return True, ""
        else:
            self.log(f"[!] Defender durdurma uyarısı: {err}", "#FF6B6B")
            return False, err

    def enable_def(self) -> tuple[bool, str]:
        self.log("[*] Defender ve SmartScreen yeniden etkinleştiriliyor...", "#00E5FF")

        script = r"""
$ErrorActionPreference = 'SilentlyContinue'

# 1. Başlangıç Koruma Görevini Sil
& schtasks.exe /delete /tn "WinKit_DefenderEnforcer" /f 2>$null | Out-Null

# 2. IFEO Debugger SmartScreen yönlendirmesini kaldır
$ifeoPath = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\smartscreen.exe'
if (Test-Path $ifeoPath) {
    Remove-Item -LiteralPath $ifeoPath -Recurse -Force -ErrorAction SilentlyContinue
    & reg.exe delete "$ifeoPath" /f /reg:64 2>$null | Out-Null
}

# 3. UILockdown ve PassiveMode kaldır
$wdscVtp = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender Security Center\Virus and threat protection'
if (Test-Path $wdscVtp) {
    Remove-ItemProperty -Path $wdscVtp -Name 'UILockdown' -Force -ErrorAction SilentlyContinue
    & reg.exe delete "$wdscVtp" /v UILockdown /f /reg:64 2>$null | Out-Null
}
$defUx = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender\UX Configuration'
if (Test-Path $defUx) {
    Remove-ItemProperty -Path $defUx -Name 'UILockdown' -Force -ErrorAction SilentlyContinue
    & reg.exe delete "$defUx" /v UILockdown /f /reg:64 2>$null | Out-Null
}
$defDirect = 'HKLM:\SOFTWARE\Microsoft\Windows Defender'
if (Test-Path $defDirect) {
    Remove-ItemProperty -Path $defDirect -Name 'PassiveMode' -Force -ErrorAction SilentlyContinue
    & reg.exe delete "$defDirect" /v PassiveMode /f /reg:64 2>$null | Out-Null
}

# 4. Defender Politikalarını Temizle
Remove-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System\EnableSmartScreen' -Force -ErrorAction SilentlyContinue

# 5. AppHost SmartScreen'i tekrar aç
$appHostPaths = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppHost',
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\AppHost'
)
Get-ChildItem -Path 'Registry::HKEY_USERS' -ErrorAction SilentlyContinue | Where-Object {
    $_.PSChildName -match '^S-1-5-21-' -and -not $_.PSChildName.EndsWith('_Classes')
} | ForEach-Object {
    $appHostPaths += "$($_.PSPath)\Software\Microsoft\Windows\CurrentVersion\AppHost"
}
foreach ($ap in $appHostPaths) {
    if (Test-Path $ap) {
        Remove-ItemProperty -Path $ap -Name 'EnableWebContentEvaluation' -Force -ErrorAction SilentlyContinue
    }
}

# 6. Servis anahtarlarındaki Deny SetValue DACL kuralını temizle
$allDefenderServices = @('WinDefend', 'WdFilter', 'WdNisDrv', 'WdNisSvc', 'Sense', 'MDCoreSvc', 'webthreatdefsvc', 'MsCoreSvc', 'WdBoot')
foreach ($svc in $allDefenderServices) {
    $svcRegPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$svc"
    if (Test-Path $svcRegPath) {
        try {
            $acl = Get-Acl -LiteralPath $svcRegPath
            $rules = @($acl.GetAccessRules($true, $false, [System.Security.Principal.NTAccount]))
            foreach ($r in $rules) {
                if ($r.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Deny) {
                    $acl.RemoveAccessRuleSpecific($r) | Out-Null
                }
            }
            Set-Acl -LiteralPath $svcRegPath -AclObject $acl -ErrorAction SilentlyContinue
        } catch {}
    }
}

# 7. Servislerin başlangıç değerlerini varsayılana getir ve başlat
$serviceStarts = @{
    'WinDefend' = 2
    'MDCoreSvc' = 2
    'WdFilter' = 0
    'WdBoot' = 0
    'WdNisDrv' = 3
    'WdNisSvc' = 3
    'Sense' = 3
    'webthreatdefsvc' = 3
    'SecurityHealthService' = 2
    'wscsvc' = 2
}

foreach ($svc in $serviceStarts.Keys) {
    $val = $serviceStarts[$svc]
    & reg.exe add "HKLM\SYSTEM\CurrentControlSet\Services\$svc" /v Start /t REG_DWORD /d $val /f /reg:64 2>$null | Out-Null
    $cfgStart = if ($val -eq 2) { 'auto' } elseif ($val -eq 3) { 'demand' } elseif ($val -eq 0) { 'boot' } else { 'auto' }
    & sc.exe config $svc start= $cfgStart 2>$null | Out-Null
}

# 8. Sürücü ve servisleri yükle / başlat
& fltmc.exe load WdFilter 2>$null | Out-Null
& sc.exe start WinDefend 2>$null | Out-Null
& sc.exe start SecurityHealthService 2>$null | Out-Null
& sc.exe start wscsvc 2>$null | Out-Null
"""
        ok, err = run_powershell_as_trustedinstaller(script, timeout=60)
        if not ok:
            ok, err = run_powershell_as_system(script, timeout=60)

        if ok:
            self.log("[+] Defender ve SmartScreen başarıyla tekrar etkinleştirildi.", "#00FF9D")
            return True, ""
        else:
            self.log(f"[!] Defender başlatma hatası: {err}", "#FF6B6B")
            return False, err
