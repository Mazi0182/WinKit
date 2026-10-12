"""
WinKit - Context Menu Integration & Ownership Engine
Registers classic and modern shell context menu actions for taking ownership,
restoring ownership to TrustedInstaller, and force deleting locked files.
"""

import os
import sys
import shutil
import winreg
from pathlib import Path


def register_winkit_context_menu():
    """Klasik sağ tık menüsüne WinKit araçları alt menüsünü ve komutlarını winreg ile doğrudan ve hatasız ekler."""
    install_winkit_ownership_tools()
    
    takeown_cmd = r'wscript.exe //B //Nologo "C:\ProgramData\WinKit\ownership_runner.vbs" "takeown" "%1"'
    takeown_bg_cmd = r'wscript.exe //B //Nologo "C:\ProgramData\WinKit\ownership_runner.vbs" "takeown" "%V"'
    restore_cmd = r'wscript.exe //B //Nologo "C:\ProgramData\WinKit\ownership_runner.vbs" "restore" "%1"'
    restore_bg_cmd = r'wscript.exe //B //Nologo "C:\ProgramData\WinKit\ownership_runner.vbs" "restore" "%V"'
    forcedel_cmd = r'wscript.exe //B //Nologo "C:\ProgramData\WinKit\ownership_runner.vbs" "forcedel" "%1"'
    
    target_dir = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "WinKit"
    target_ico = target_dir / "winkit_logo.ico"
    winkit_icon_str = str(target_ico) if target_ico.is_file() else "imageres.dll,81"
    
    configs = [
        # 1. Dosyalar (*)
        (r"*\shell\WinKitTools", "WinKit araçları", winkit_icon_str, [
            ("01TakeOwnership", "Sahipliği al (WinKit)", "imageres.dll,73", takeown_cmd),
            ("02RestoreOwnership", "Sahipliği geri ver (TrustedInstaller)", "imageres.dll,74", restore_cmd),
            ("03ForceDelete", "Kilitli dosyayı zorla sil (WinKit)", "shell32.dll,131", forcedel_cmd),
        ]),
        # 2. Klasörler (Directory)
        (r"Directory\shell\WinKitTools", "WinKit araçları", winkit_icon_str, [
            ("01TakeOwnership", "Sahipliği al (WinKit)", "imageres.dll,73", takeown_cmd),
            ("02RestoreOwnership", "Sahipliği geri ver (TrustedInstaller)", "imageres.dll,74", restore_cmd),
            ("03ForceDelete", "Kilitli klasörü zorla sil (WinKit)", "shell32.dll,131", forcedel_cmd),
        ]),
        # 3. Masaüstü ve Klasör Arka Planı (Directory\Background)
        (r"Directory\Background\shell\WinKitTools", "WinKit araçları", winkit_icon_str, [
            ("01TakeOwnership", "Sahipliği al (WinKit)", "imageres.dll,73", takeown_bg_cmd),
            ("02RestoreOwnership", "Sahipliği geri ver (TrustedInstaller)", "imageres.dll,74", restore_bg_cmd),
        ]),
    ]
    
    # Hem HKCU (Software\Classes) hem de HKLM/HKCR için yaz
    hives = [
        (winreg.HKEY_CURRENT_USER, r"Software\Classes"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes"),
    ]
    
    for hive, prefix in hives:
        try:
            for base_rel, menu_title, icon, items in configs:
                base_key = f"{prefix}\\{base_rel}"
                with winreg.CreateKeyEx(hive, base_key, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                    winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, menu_title)
                    winreg.SetValueEx(k, "SubCommands", 0, winreg.REG_SZ, "")
                    winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
                
                for sub_name, item_title, item_icon, item_cmd in items:
                    item_path = f"{base_key}\\shell\\{sub_name}"
                    with winreg.CreateKeyEx(hive, item_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                        winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, item_title)
                        winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, item_icon)
                    with winreg.CreateKeyEx(hive, f"{item_path}\\command", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, item_cmd)
        except Exception:
            pass


def install_winkit_ownership_tools():
    """Özel sağ tık menüsü için arka planda çalışan sahiplik veritabanı, bildirim motoru ve kayıt defteri anahtarlarını kurar."""
    try:
        target_dir = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "WinKit"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_ico = target_dir / "winkit_logo.ico"
        try:
            base_candidates = [
                getattr(sys, "_MEIPASS", None),
                os.path.dirname(os.path.abspath(__file__)),
                os.getcwd(),
                r"C:\ProgramData\WinKit",
            ]
            for cand in base_candidates:
                if cand:
                    src_ico = Path(cand) / "winkit_logo.ico"
                    if src_ico.is_file():
                        shutil.copy2(src_ico, target_ico)
                        break
        except Exception:
            pass
        winkit_icon_str = str(target_ico) if target_ico.is_file() else "imageres.dll,81"
        
        ps1_lines = [
            "param(",
            "    [string]$Action,",
            "    [string]$TargetPath",
            ")",
            "$ErrorActionPreference = 'SilentlyContinue'",
            "if ([string]::IsNullOrWhiteSpace($TargetPath) -or -not (Test-Path -LiteralPath $TargetPath)) { exit 0 }",
            '$dbPath = "$env:ProgramData\\WinKit\\ownership_db.json"',
            "$item = Get-Item -LiteralPath $TargetPath -Force",
            "function Show-Notification($title, $msg) {",
            "    try {",
            "        Add-Type -AssemblyName System.Windows.Forms",
            "        [System.Windows.Forms.MessageBox]::Show($msg, $title, [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null",
            "    } catch {",
            "        try {",
            "            $ws = New-Object -ComObject WScript.Shell",
            "            $ws.Popup($msg, 5, $title, 64) | Out-Null",
            "        } catch {}",
            "    }",
            "}",
            "function Enable-SecurityPrivileges {",
            "    if (-not ('WinKitSecPriv' -as [type])) {",
            "        Add-Type -TypeDefinition @'",
            "using System;",
            "using System.Runtime.InteropServices;",
            "public static class WinKitSecPriv {",
            "    [DllImport(\"advapi32.dll\", SetLastError=true)] public static extern bool OpenProcessToken(IntPtr h, int a, out IntPtr t);",
            "    [DllImport(\"advapi32.dll\", SetLastError=true, CharSet=CharSet.Auto)] public static extern bool LookupPrivilegeValue(string s, string n, out long l);",
            "    [DllImport(\"advapi32.dll\", SetLastError=true)] public static extern bool AdjustTokenPrivileges(IntPtr t, bool d, ref TP n, int b, IntPtr p, IntPtr r);",
            "    [DllImport(\"kernel32.dll\")] public static extern IntPtr GetCurrentProcess();",
            "    [DllImport(\"kernel32.dll\")] public static extern bool CloseHandle(IntPtr h);",
            "    [StructLayout(LayoutKind.Sequential, Pack=1)] public struct TP { public int c; public long l; public int a; }",
            "    public static void Enable() {",
            "        IntPtr t;",
            "        if (OpenProcessToken(GetCurrentProcess(), 0x0028, out t)) {",
            "            foreach (string p in new[] { \"SeRestorePrivilege\", \"SeTakeOwnershipPrivilege\", \"SeBackupPrivilege\", \"SeSecurityPrivilege\", \"SeDebugPrivilege\", \"SeLoadDriverPrivilege\" }) {",
            "                long l;",
            "                if (LookupPrivilegeValue(null, p, out l)) {",
            "                    TP tp = new TP { c=1, l=l, a=2 };",
            "                    AdjustTokenPrivileges(t, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero);",
            "                }",
            "            }",
            "            CloseHandle(t);",
            "        }",
            "    }",
            "}",
            "'@",
            "    }",
            "    [WinKitSecPriv]::Enable()",
            "}",
            "function Get-OwnershipDb {",
            "    if (Test-Path -LiteralPath $dbPath) {",
            "        try {",
            "            $raw = Get-Content -LiteralPath $dbPath -Raw -Encoding UTF8",
            "            return ($raw | ConvertFrom-Json)",
            "        } catch { return @{} }",
            "    }",
            "    return @{}",
            "}",
            "function Save-OwnershipDb($dbObj) {",
            "    try {",
            "        $dbObj | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $dbPath -Encoding UTF8 -Force",
            "    } catch {}",
            "}",
            "function Grant-FullControl($path, $isDirectory) {",
            "    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name",
            "    if ($isDirectory) {",
            "        & icacls.exe $path /inheritance:e /grant:r \"*S-1-5-32-544:(OI)(CI)F\" \"*S-1-5-18:(OI)(CI)F\" \"*S-1-1-0:(OI)(CI)F\" \"${currentIdentity}:(OI)(CI)F\" /t /c /q 2>$null | Out-Null",
            "    } else {",
            "        & icacls.exe $path /inheritance:e /grant:r \"*S-1-5-32-544:F\" \"*S-1-5-18:F\" \"*S-1-1-0:F\" \"${currentIdentity}:F\" /c /q 2>$null | Out-Null",
            "    }",
            "    return ($LASTEXITCODE -eq 0)",
            "}",
            "function Stop-LockingServicesAndDrivers($targetPath) {",
            "    try {",
            "        $cleanPath = [System.IO.Path]::GetFullPath($targetPath)",
            "        $fileName = [System.IO.Path]::GetFileNameWithoutExtension($targetPath)",
            "        $ext = [System.IO.Path]::GetExtension($targetPath).ToLowerInvariant()",
            "        if ($ext -eq '.sys') {",
            "            & sc.exe stop $fileName 2>$null | Out-Null",
            "            & net.exe stop $fileName 2>$null | Out-Null",
            "            & sc.exe delete $fileName 2>$null | Out-Null",
            "        }",
            "        Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Where-Object { $_.PathName -and $_.PathName -like \"*$cleanPath*\" } | ForEach-Object {",
            "            & sc.exe stop $_.Name 2>$null | Out-Null",
            "            & net.exe stop $_.Name 2>$null | Out-Null",
            "        }",
            "        Get-CimInstance Win32_SystemDriver -ErrorAction SilentlyContinue | Where-Object { $_.PathName -and $_.PathName -like \"*$cleanPath*\" } | ForEach-Object {",
            "            & sc.exe stop $_.Name 2>$null | Out-Null",
            "        }",
            "    } catch {}",
            "}",
            "function Schedule-DeleteOnReboot($path, $isDirectory) {",
            "    if (-not ('WinKitPendingDelete' -as [type])) {",
            "        Add-Type -TypeDefinition @'",
            "using System;",
            "using System.Runtime.InteropServices;",
            "using Microsoft.Win32;",
            "public static class WinKitPendingDelete {",
            "    [DllImport(\"kernel32.dll\", CharSet=CharSet.Unicode, SetLastError=true)]",
            "    public static extern bool MoveFileEx(string existingFile, string newFile, int flags);",
            "    public static bool AddPendingRename(string path) {",
            "        try {",
            "            using (RegistryKey k = Registry.LocalMachine.OpenSubKey(@\"SYSTEM\\CurrentControlSet\\Control\\Session Manager\", true)) {",
            "                if (k == null) return false;",
            "                string[] current = k.GetValue(\"PendingFileRenameOperations\") as string[] ?? new string[0];",
            "                string formatted = @\"\\??\\\" + path;",
            "                System.Collections.Generic.List<string> list = new System.Collections.Generic.List<string>(current);",
            "                list.Add(formatted);",
            "                list.Add(\"\");",
            "                k.SetValue(\"PendingFileRenameOperations\", list.ToArray(), RegistryValueKind.MultiString);",
            "                return true;",
            "            }",
            "        } catch { return false; }",
            "    }",
            "}",
            "'@",
            "    }",
            "    $scheduled = $false",
            "    if ($isDirectory) {",
            "        Get-ChildItem -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue | Sort-Object { $_.FullName.Length } -Descending | ForEach-Object {",
            "            [WinKitPendingDelete]::MoveFileEx($_.FullName, $null, 4) | Out-Null",
            "            [WinKitPendingDelete]::AddPendingRename($_.FullName) | Out-Null",
            "            $scheduled = $true",
            "        }",
            "    }",
            "    if ([WinKitPendingDelete]::MoveFileEx([string]$path, $null, 4)) { $scheduled = $true }",
            "    if ([WinKitPendingDelete]::AddPendingRename([string]$path)) { $scheduled = $true }",
            "    return $scheduled",
            "}",
            "if ($Action -eq 'takeown') {",
            "    Enable-SecurityPrivileges",
            "    $currentOwner = ''",
            "    $sddl = ''",
            "    try {",
            "        $acl = Get-Acl -LiteralPath $item.FullName",
            "        $currentOwner = [string]$acl.Owner",
            "        $sddl = $acl.GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::All)",
            "    } catch {}",
            "    if ([string]::IsNullOrWhiteSpace($currentOwner)) { $currentOwner = 'NT SERVICE\\TrustedInstaller' }",
            "    $sha256 = ''",
            "    if (-not $item.PSIsContainer) {",
            "        try { $sha256 = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash } catch {}",
            "    }",
            "    $db = Get-OwnershipDb",
            "    $normPath = $item.FullName.ToLowerInvariant()",
            "    $record = [ordered]@{",
            "        'Path' = $item.FullName",
            "        'Owner' = $currentOwner",
            "        'SDDL' = $sddl",
            "        'SHA256' = $sha256",
            "        'IsDirectory' = [bool]$item.PSIsContainer",
            "        'Date' = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')",
            "    }",
            "    $db | Add-Member -NotePropertyName $normPath -NotePropertyValue $record -Force",
            "    Save-OwnershipDb $db",
            "    & attrib.exe -r -s -h \"$($item.FullName)\" 2>$null | Out-Null",
            "    & takeown.exe /f \"$($item.FullName)\" /a 2>$null | Out-Null",
            "    $ownershipTaken = ($LASTEXITCODE -eq 0)",
            "    $aclGranted = Grant-FullControl $item.FullName [bool]$item.PSIsContainer",
            "    if (-not $aclGranted -and $item.PSIsContainer) {",
            "        & takeown.exe /f \"$($item.FullName)\" /a /r /d y 2>$null | Out-Null",
            "        $aclGranted = Grant-FullControl $item.FullName $true",
            "    }",
            "    $ownerSid = ''",
            "    try { $ownerSid = (Get-Acl -LiteralPath $item.FullName).GetOwner([Security.Principal.SecurityIdentifier]).Value } catch {}",
            "    if ($ownershipTaken -and $aclGranted -and $ownerSid -eq 'S-1-5-32-544') {",
            "        Show-Notification \"WinKit Sahiplik Yöneticisi\" \"Sahiplik ve tam denetim başarıyla alındı:`n$($item.FullName)\"",
            "    } else {",
            "        Show-Notification \"WinKit Sahiplik Yöneticisi\" \"Sahiplik doğrulanamadı. İşlemi yönetici olarak yeniden deneyin:`n$($item.FullName)\"",
            "    }",
            "}",
            "elseif ($Action -eq 'restore') {",
            "    Enable-SecurityPrivileges",
            "    $db = Get-OwnershipDb",
            "    $normPath = $item.FullName.ToLowerInvariant()",
            "    $targetOwner = 'NT SERVICE\\TrustedInstaller'",
            "    $savedSddl = ''",
            "    $savedHash = ''",
            "    if ($db -and $db.PSObject.Properties[$normPath]) {",
            "        $rec = $db.PSObject.Properties[$normPath].Value",
            "        if ($rec) {",
            "            if ($rec.Owner) { $targetOwner = [string]$rec.Owner }",
            "            if ($rec.SDDL) { $savedSddl = [string]$rec.SDDL }",
            "            if ($rec.SHA256) { $savedHash = [string]$rec.SHA256 }",
            "        }",
            "    }",
            "    if (-not $item.PSIsContainer -and -not [string]::IsNullOrWhiteSpace($savedHash)) {",
            "        $currHash = ''",
            "        try { $currHash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash } catch {}",
            "        if ($currHash -ne $savedHash) {",
            "            Show-Notification \"WinKit Sahiplik Yöneticisi\" \"Uyarı: Dosya içeriğinde değişiklik tespit edildi (SHA-256 farklı). Sahiplik yine de devrediliyor.`n$($item.FullName)\"",
            "        }",
            "    }",
            "    $restoredWithSddl = $false",
            "    if (-not [string]::IsNullOrWhiteSpace($savedSddl)) {",
            "        try {",
            "            $aclObj = Get-Acl -LiteralPath $item.FullName",
            "            $aclObj.SetSecurityDescriptorSddlForm($savedSddl)",
            "            Set-Acl -LiteralPath $item.FullName -AclObject $aclObj -ErrorAction Stop",
            "            $restoredWithSddl = $true",
            "        } catch {}",
            "    }",
            "    if (-not $restoredWithSddl) {",
            "        if ($targetOwner -match 'TrustedInstaller') { $targetOwner = 'NT SERVICE\\TrustedInstaller' }",
            "        $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name",
            "        if ($item.PSIsContainer) {",
            "            & icacls.exe \"$($item.FullName)\" /setowner \"$targetOwner\" /t /c /q 2>$null | Out-Null",
            "            & icacls.exe \"$($item.FullName)\" /remove:g \"*S-1-5-32-544\" \"*S-1-1-0\" \"${currentIdentity}\" /t /c /q 2>$null | Out-Null",
            "            & icacls.exe \"$($item.FullName)\" /reset /t /c /q 2>$null | Out-Null",
            "        } else {",
            "            & icacls.exe \"$($item.FullName)\" /setowner \"$targetOwner\" /c /q 2>$null | Out-Null",
            "            & icacls.exe \"$($item.FullName)\" /remove:g \"*S-1-5-32-544\" \"*S-1-1-0\" \"${currentIdentity}\" /c /q 2>$null | Out-Null",
            "            & icacls.exe \"$($item.FullName)\" /reset /c /q 2>$null | Out-Null",
            "        }",
            "    }",
            "    Show-Notification \"WinKit Sahiplik Yöneticisi\" \"Sahiplik ve orijinal ACL izinleri başarıyla geri yüklendi ($targetOwner):`n$($item.FullName)\"",
            "}",
            "elseif ($Action -eq 'forcedel') {",
            "    Enable-SecurityPrivileges",
            "    $p = $item.FullName",
            "    Stop-LockingServicesAndDrivers $p",
            "    if (-not $item.PSIsContainer) {",
            "        $procName = [System.IO.Path]::GetFileNameWithoutExtension($p)",
            "        Stop-Process -Name $procName -Force -ErrorAction SilentlyContinue",
            "    }",
            "    Get-Process -ErrorAction SilentlyContinue | Where-Object {",
            "        $_.Path -eq $p -or ($_.Modules -and ($_.Modules | Where-Object { $_.FileName -eq $p }))",
            "    } | Stop-Process -Force -ErrorAction SilentlyContinue",
            "    & taskkill.exe /f /fi \"MODULES eq $p\" 2>$null | Out-Null",
            "    & attrib.exe -r -s -h \"$p\" 2>$null | Out-Null",
            "    if ($item.PSIsContainer) {",
            "        & takeown.exe /f \"$p\" /a /r /d y 2>$null | Out-Null",
            "        Grant-FullControl $p $true | Out-Null",
            "        Remove-Item -LiteralPath \"$p\" -Recurse -Force -ErrorAction SilentlyContinue",
            "        if (Test-Path -LiteralPath \"$p\") { & cmd.exe /c \"rd /s /q \"\"$p\"\"\" 2>$null | Out-Null }",
            "    } else {",
            "        & takeown.exe /f \"$p\" /a 2>$null | Out-Null",
            "        Grant-FullControl $p $false | Out-Null",
            "        Remove-Item -LiteralPath \"$p\" -Force -ErrorAction SilentlyContinue",
            "        if (Test-Path -LiteralPath \"$p\") { & cmd.exe /c \"del /f /q /a \"\"$p\"\"\" 2>$null | Out-Null }",
            "    }",
            "    if (Test-Path -LiteralPath \"$p\") {",
            "        $scheduled = Schedule-DeleteOnReboot $p ([bool]$item.PSIsContainer)",
            "        if ($scheduled) {",
            "            Show-Notification \"WinKit Sahiplik Yöneticisi\" \"Öğe kullanımda olduğu için yeniden başlatmada silinecek:`n$p\"",
            "        } else {",
            "            Show-Notification \"WinKit Sahiplik Yöneticisi\" \"Kilitli öğe silinemedi ve yeniden başlatmaya planlanamadı:`n$p\"",
            "        }",
            "    } else {",
            "        Show-Notification \"WinKit Sahiplik Yöneticisi\" \"Kilitli öğe başarıyla silindi:`n$p\"",
            "    }",
            "}"
        ]
        (target_dir / "ownership_engine.ps1").write_text("\n".join(ps1_lines), encoding="utf-8-sig")
        
        vbs_lines = [
            'Set objArgs = WScript.Arguments',
            'If objArgs.Count < 2 Then WScript.Quit',
            'action = objArgs(0)',
            'target = ""',
            'For i = 1 To objArgs.Count - 1',
            '    If target <> "" Then target = target & " "',
            '    target = target & objArgs(i)',
            'Next',
            'Set objShell = CreateObject("Shell.Application")',
            'psCmd = "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\\ProgramData\\WinKit\\ownership_engine.ps1"" -Action """ & action & """ -TargetPath """ & target & """"',
            'objShell.ShellExecute "powershell.exe", psCmd, "", "runas", 0'
        ]
        (target_dir / "ownership_runner.vbs").write_text("\n".join(vbs_lines), encoding="utf-8")

        # Direct registry writing for context menus
        takeown_cmd = r'wscript.exe //B //Nologo "C:\ProgramData\WinKit\ownership_runner.vbs" "takeown" "%1"'
        takeown_bg_cmd = r'wscript.exe //B //Nologo "C:\ProgramData\WinKit\ownership_runner.vbs" "takeown" "%V"'
        restore_cmd = r'wscript.exe //B //Nologo "C:\ProgramData\WinKit\ownership_runner.vbs" "restore" "%1"'
        restore_bg_cmd = r'wscript.exe //B //Nologo "C:\ProgramData\WinKit\ownership_runner.vbs" "restore" "%V"'
        forcedel_cmd = r'wscript.exe //B //Nologo "C:\ProgramData\WinKit\ownership_runner.vbs" "forcedel" "%1"'

        def set_reg_str(key_path, val_name, val_str):
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CLASSES_ROOT, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                    winreg.SetValueEx(k, val_name, 0, winreg.REG_SZ, str(val_str))
            except Exception:
                pass

        # 1. Dosyalar (*)
        set_reg_str(r"*\shell\WinKitTools", "MUIVerb", "WinKit araçları")
        set_reg_str(r"*\shell\WinKitTools", "SubCommands", "")
        set_reg_str(r"*\shell\WinKitTools", "Icon", winkit_icon_str)
        set_reg_str(r"*\shell\WinKitTools\shell\01TakeOwnership", "MUIVerb", "Sahipliği al")
        set_reg_str(r"*\shell\WinKitTools\shell\01TakeOwnership", "Icon", "imageres.dll,73")
        set_reg_str(r"*\shell\WinKitTools\shell\01TakeOwnership\command", "", takeown_cmd)
        set_reg_str(r"*\shell\WinKitTools\shell\02RestoreOwnership", "MUIVerb", "Sahipliği geri ver")
        set_reg_str(r"*\shell\WinKitTools\shell\02RestoreOwnership", "Icon", "imageres.dll,74")
        set_reg_str(r"*\shell\WinKitTools\shell\02RestoreOwnership\command", "", restore_cmd)
        set_reg_str(r"*\shell\WinKitTools\shell\03ForceDelete", "MUIVerb", "Kilitli dosyayı zorla sil")
        set_reg_str(r"*\shell\WinKitTools\shell\03ForceDelete", "Icon", "shell32.dll,131")
        set_reg_str(r"*\shell\WinKitTools\shell\03ForceDelete\command", "", forcedel_cmd)

        # 2. Klasörler (Directory)
        set_reg_str(r"Directory\shell\WinKitTools", "MUIVerb", "WinKit araçları")
        set_reg_str(r"Directory\shell\WinKitTools", "SubCommands", "")
        set_reg_str(r"Directory\shell\WinKitTools", "Icon", winkit_icon_str)
        set_reg_str(r"Directory\shell\WinKitTools\shell\01TakeOwnership", "MUIVerb", "Sahipliği al")
        set_reg_str(r"Directory\shell\WinKitTools\shell\01TakeOwnership", "Icon", "imageres.dll,73")
        set_reg_str(r"Directory\shell\WinKitTools\shell\01TakeOwnership\command", "", takeown_cmd)
        set_reg_str(r"Directory\shell\WinKitTools\shell\02RestoreOwnership", "MUIVerb", "Sahipliği geri ver")
        set_reg_str(r"Directory\shell\WinKitTools\shell\02RestoreOwnership", "Icon", "imageres.dll,74")
        set_reg_str(r"Directory\shell\WinKitTools\shell\02RestoreOwnership\command", "", restore_cmd)
        set_reg_str(r"Directory\shell\WinKitTools\shell\03ForceDelete", "MUIVerb", "Kilitli klasörü zorla sil")
        set_reg_str(r"Directory\shell\WinKitTools\shell\03ForceDelete", "Icon", "shell32.dll,131")
        set_reg_str(r"Directory\shell\WinKitTools\shell\03ForceDelete\command", "", forcedel_cmd)

        # 3. Masaüstü & Klasör Arka Planı (Directory\Background)
        set_reg_str(r"Directory\Background\shell\WinKitTools", "MUIVerb", "WinKit araçları")
        set_reg_str(r"Directory\Background\shell\WinKitTools", "SubCommands", "")
        set_reg_str(r"Directory\Background\shell\WinKitTools", "Icon", winkit_icon_str)
        set_reg_str(r"Directory\Background\shell\WinKitTools\shell\01TakeOwnership", "MUIVerb", "Sahipliği al")
        set_reg_str(r"Directory\Background\shell\WinKitTools\shell\01TakeOwnership", "Icon", "imageres.dll,73")
        set_reg_str(r"Directory\Background\shell\WinKitTools\shell\01TakeOwnership\command", "", takeown_bg_cmd)
        set_reg_str(r"Directory\Background\shell\WinKitTools\shell\02RestoreOwnership", "MUIVerb", "Sahipliği geri ver")
        set_reg_str(r"Directory\Background\shell\WinKitTools\shell\02RestoreOwnership", "Icon", "imageres.dll,74")
        set_reg_str(r"Directory\Background\shell\WinKitTools\shell\02RestoreOwnership\command", "", restore_bg_cmd)
    except Exception:
        pass
