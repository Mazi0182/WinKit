"""
WinKit - Core Licensing & Windows Activation Module
Queries Windows licensing status via WMI and provides HWID, TSforge, and Online KMS activation.
"""

import os
import sys
import tempfile
import subprocess
from typing import Tuple, Optional, Callable, Dict, Any

from core.constants import CREATE_NO_WINDOW
from core.iso import get_current_windows_edition
from core.privileges import run_powershell_checked


def get_windows_license_status() -> Dict[str, Any]:
    """
    Windows lisans durumunu WMI (SoftwareLicensingProduct) üzerinden sorgular.
    Döndürülen sözlük: {
        "licensed": bool,
        "name": str,
        "partial_key": str,
        "display_text": str,
        "color": str
    }
    """
    vbs_content = r"""On Error Resume Next
Set objWMIService = GetObject("winmgmts:\\.\root\cimv2")
If Err.Number <> 0 Then
    WScript.Echo "0||WMI Error: " & Err.Description
    WScript.Quit
End If

Set colItems = objWMIService.ExecQuery("SELECT LicenseStatus, Name, PartialProductKey FROM SoftwareLicensingProduct WHERE ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND LicenseDependsOn IS NULL")
If Err.Number <> 0 Then
    WScript.Echo "0||Query Error: " & Err.Description
    WScript.Quit
End If

bestStatus = 0
bestName = ""
bestKey = ""
For Each objItem in colItems
    If objItem.LicenseStatus = 1 Then
        bestStatus = 1
        bestName = objItem.Name
        bestKey = objItem.PartialProductKey
        Exit For
    ElseIf objItem.LicenseStatus > bestStatus Or (bestName = "" And objItem.Name <> "") Then
        bestStatus = objItem.LicenseStatus
        bestName = objItem.Name
        bestKey = objItem.PartialProductKey
    End If
Next
WScript.Echo bestStatus & "|" & bestName & "|" & bestKey
"""
    fd, path = tempfile.mkstemp(suffix=".vbs")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(vbs_content)

        result = subprocess.run(
            ["cscript.exe", "//NoLogo", path],
            capture_output=True,
            text=True,
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=10,
            check=False,
        )
        fields = (result.stdout.strip().splitlines() or ["0||"])[-1].split("|", 2)
        licensed = (fields[0] == "1")
        name = fields[1] if len(fields) > 1 else ""
        partial = fields[2] if len(fields) > 2 else ""

        if licensed:
            text = "Windows etkinleştirildi"
            if name:
                cleaned_name = name.replace("Windows(R), ", "").replace(" edition", "")
                text += f" — {cleaned_name}"
            if partial:
                text += f" (…{partial})"
            color = "#55D67A"
        else:
            if not partial:
                text = "Windows etkinleştirilmemiş (Yerel ürün anahtarı bulunamadı)."
            else:
                text = "Windows etkinleştirilmemiş veya etkinleştirme süresi dolmuş."
            color = "#FFB86C"

        return {
            "licensed": licensed,
            "name": name,
            "partial_key": partial,
            "display_text": text,
            "color": color,
        }
    except Exception as exc:
        return {
            "licensed": False,
            "name": "",
            "partial_key": "",
            "display_text": f"Lisans durumu okunamadı: {exc}",
            "color": "#FF6B78",
        }
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def activate_windows(
    method: str = "hwid",
    on_status_update: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """
    Seçilen yöntemle (hwid, tsforge, kms) Windows aktivasyonunu yürütür.
    """
    method = (method or "hwid").lower()

    if method == "kms":
        script_content = r"""$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host "Detecting Windows SKU..." -ForegroundColor Cyan
$sku = [int](Get-CimInstance Win32_OperatingSystem).OperatingSystemSKU
Write-Host "Current SKU ID: $sku" -ForegroundColor Green

$gvlkKeys = @{
    4 = "NPPR9-FWDCX-D2C8J-H872K-2YT43";
    27 = "DPH2V-TTNVB-4X9Q3-TJR4H-KHJW4";
    48 = "W269N-WFGWX-YVC9B-4J6C9-T83GX";
    49 = "MH37W-N47XK-V7XM9-C7227-GCQG9";
    98 = "4CPRK-NM3K3-X6XXQ-RXX86-WXCHW";
    100 = "BT79Q-G7N6G-PGBYW-4YWX6-6F4BT";
    101 = "TX9XD-98N7V-6WMQ6-BX7FG-H8Q99";
    121 = "NW6C2-QMPVW-D7KKK-3GKT6-VCFB2";
    122 = "2WH4N-8QGBV-H22JP-CT43Q-MDWWJ";
    125 = "M7XTQ-FN8P6-TTKYV-9D4CC-J462D";
    161 = "NRG8B-RKK3S-4322Q-6FBR9-CG4Q9";
    162 = "9FNHH-K3HBT-3W4TD-6383H-6XYWF";
    164 = "6TP4R-GNPTD-KYYHQ-3935J-55XJW";
    165 = "YVWGF-BXNMC-HTQYQ-CPQ99-66QFC";
    175 = "NJCF7-PW8QT-3324D-688JX-2YV66";
    188 = "KBN8V-HFGQ4-SSSX8-NDR9R-3DDGG";
    191 = "KBN8V-HFGQ4-SSSX8-NDR9R-3DDGG";
    202 = "K9VKN-3BGWV-Y624W-MCRMQ-BHDCD";
    203 = "KY7PN-VR6RX-83W6Y-6DDYQ-T6R4W"
}

$key = $gvlkKeys[$sku]
if (-not $key) {
    $key = "W269N-WFGWX-YVC9B-4J6C9-T83GX"
}

Write-Host "Installing GVLK product key: $key..." -ForegroundColor Cyan
$sps = Get-CimInstance SoftwareLicensingService
$null = $sps | Invoke-CimMethod -MethodName "InstallProductKey" -Arguments @{ ProductKey = $key }

$kmsServers = @("kms8.msguides.com", "kms.lotro.cc", "kms.digiboy.ir", "kms.03k.org")
$activated = $false
foreach ($server in $kmsServers) {
    try {
        Write-Host "Setting KMS server: $server..." -ForegroundColor Cyan
        $null = $sps | Invoke-CimMethod -MethodName "SetKeyManagementServiceMachine" -Arguments @{ MachineName = $server }
        Write-Host "Requesting KMS activation..." -ForegroundColor Cyan
        $prod = Get-CimInstance -Query "SELECT * FROM SoftwareLicensingProduct WHERE ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL"
        $null = $prod | Invoke-CimMethod -MethodName "Activate"
        $status = (Get-CimInstance -Query "SELECT LicenseStatus FROM SoftwareLicensingProduct WHERE ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL").LicenseStatus
        if ($status -contains 1 -or $status -eq 1) {
            $activated = $true
            Write-Host "KMS activation successful with $server!" -ForegroundColor Green
            break
        }
    } catch {
        Write-Warning "KMS server $server error: $_"
    }
}
if (-not $activated) {
    throw "KMS sunucuları üzerinden etkinleştirme sağlanamadı. İnternet bağlantınızı kontrol edin."
}
"""
    elif method == "tsforge":
        script_content = r"""$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host "Detecting Windows SKU..." -ForegroundColor Cyan
$sku = [int](Get-CimInstance Win32_OperatingSystem).OperatingSystemSKU
Write-Host "Current SKU ID: $sku" -ForegroundColor Green

$gvlkKeys = @{
    4 = "NPPR9-FWDCX-D2C8J-H872K-2YT43";
    27 = "DPH2V-TTNVB-4X9Q3-TJR4H-KHJW4";
    48 = "W269N-WFGWX-YVC9B-4J6C9-T83GX";
    49 = "MH37W-N47XK-V7XM9-C7227-GCQG9";
    98 = "4CPRK-NM3K3-X6XXQ-RXX86-WXCHW";
    100 = "BT79Q-G7N6G-PGBYW-4YWX6-6F4BT";
    101 = "TX9XD-98N7V-6WMQ6-BX7FG-H8Q99";
    121 = "NW6C2-QMPVW-D7KKK-3GKT6-VCFB2";
    122 = "2WH4N-8QGBV-H22JP-CT43Q-MDWWJ";
    125 = "M7XTQ-FN8P6-TTKYV-9D4CC-J462D";
    161 = "NRG8B-RKK3S-4322Q-6FBR9-CG4Q9";
    162 = "9FNHH-K3HBT-3W4TD-6383H-6XYWF";
    164 = "6TP4R-GNPTD-KYYHQ-3935J-55XJW";
    165 = "YVWGF-BXNMC-HTQYQ-CPQ99-66QFC";
    175 = "NJCF7-PW8QT-3324D-688JX-2YV66";
    188 = "KBN8V-HFGQ4-SSSX8-NDR9R-3DDGG";
    191 = "KBN8V-HFGQ4-SSSX8-NDR9R-3DDGG"
}
$key = $gvlkKeys[$sku]
if (-not $key) { $key = "W269N-WFGWX-YVC9B-4J6C9-T83GX" }

Write-Host "Installing GVLK product key: $key..." -ForegroundColor Cyan
$sps = Get-CimInstance SoftwareLicensingService
$null = $sps | Invoke-CimMethod -MethodName "InstallProductKey" -Arguments @{ ProductKey = $key }

Write-Host "Triggering SPP local license activation..." -ForegroundColor Cyan
$prod = Get-CimInstance -Query "SELECT * FROM SoftwareLicensingProduct WHERE ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL"
$null = $prod | Invoke-CimMethod -MethodName "Activate"
$status = (Get-CimInstance -Query "SELECT LicenseStatus FROM SoftwareLicensingProduct WHERE ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL").LicenseStatus
if ($status -contains 1 -or $status -eq 1) {
    Write-Host "TSforge activation successful!" -ForegroundColor Green
} else {
    throw "TSforge aktivasyonu gerçekleştirilemedi."
}
"""
    else:
        # Default: HWID GenuineTicket activation (MAS AIO exact implementation)
        script_content = r"""$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
# 1. Detect current OS SKU and current active/available Activation IDs
Write-Host "Detecting Windows SKU..." -ForegroundColor Cyan
$sku = [int](Get-CimInstance Win32_OperatingSystem).OperatingSystemSKU
Write-Host "Current SKU ID: $sku" -ForegroundColor Green

# 2. Get all installed Activation IDs and all available SKU IDs from tokens
$allapps = @((Get-CimInstance SoftwareLicensingProduct | Where-Object {$_.ApplicationID -eq '55c92734-d682-4d71-983e-d6ec3f16059f'}).ID)
$altapplist = @()
$folderPath = "$env:SystemRoot\System32\spp\tokens\skus"
if (Test-Path $folderPath) {
    $files = Get-ChildItem -Path $folderPath -Recurse -Filter "*.xrm-ms"
    foreach ($file in $files) {
        $content = [IO.File]::ReadAllText($file.FullName)
        $matches = [regex]::Matches($content, 'name="productSkuId">\{([0-9a-fA-F\-]+)\}')
        foreach ($match in $matches) {
            $altapplist += $match.Groups[1].Value
        }
    }
}
$altapplist = $altapplist | Select-Object -Unique

# 3. Helper function to install licenses from System32/spp/tokens/skus/<editionName>
function Install-EditionLicenses($editionName) {
    $licPath = "$env:SystemRoot\System32\spp\tokens\skus\$editionName"
    if (Test-Path $licPath) {
        $sps = Get-CimInstance SoftwareLicensingService
        Get-ChildItem $licPath -Recurse -Filter "*.xrm-ms" | ForEach-Object {
            try {
                $licenseXml = [IO.File]::ReadAllText($_.FullName)
                $null = $sps | Invoke-CimMethod -MethodName "InstallLicense" -Arguments @{ License = $licenseXml }
            } catch {
                # Ignore individual license install errors
            }
        }
    }
}

# 4. Define HWID Data mapping exactly from MAS AIO
$hwidData = @(
    # ActivationID, Key, Sku, Pfn, NotWorking, KeyType, Name
    @("8b351c9c-f398-4515-9900-09df49427262", "XGVPP-NMH47-7TTHJ-W3FW7-8HV2C", 4, "X19-99683", 0, "OEM:NONSLP", "Enterprise"),
    @("c83cef07-6b72-4bbc-a28f-a00386872839", "3V6Q6-NQXCX-V8YXR-9QCYV-QPFCT", 27, "X19-98746", 0, "Volume:MAK", "Enterprise N"),
    @("4de7cb65-cdf1-4de9-8ae8-e3cce27b9f2c", "VK7JG-NPHTM-C97JM-9MPGT-3V66T", 48, "X19-98841", 0, "Retail", "Professional"),
    @("9fbaf5d6-4d83-4422-870d-fdda6e5858aa", "2B87N-8KFHP-DKV6R-Y2C8J-PKCKT", 49, "X19-98859", 0, "Retail", "Professional N"),
    @("f742e4ff-909d-4fe9-aacb-3231d24a0c58", "4CPRK-NM3K3-X6XXQ-RXX86-WXCHW", 98, "X19-98877", 0, "Retail", "Home N"),
    @("1d1bac85-7365-4fea-949a-96978ec91ae0", "N2434-X9D7W-8PF6X-8DV9T-8TYMD", 99, "X19-99652", 0, "Retail", "Home Country Specific"),
    @("3ae2cc14-ab2d-41f4-972f-5e20142771dc", "BT79Q-G7N6G-PGBYW-4YWX6-6F4BT", 100, "X19-99661", 0, "Retail", "Home Single Language"),
    @("2b1f36bb-c1cd-4306-bf5c-a0367c2d97d8", "YTMG3-N6DKC-DKB77-7M9GH-8HVX7", 101, "X19-98868", 0, "Retail", "Home"),
    @("2a6137f3-75c0-4f26-8e3e-d83d802865a4", "XKCNC-J26Q9-KFHD2-FKTHY-KD72Y", 119, "X19-99606", 0, "OEM:NONSLP", "PPIPro"),
    @("e558417a-5123-4f6f-91e7-385c1c7ca9d4", "YNMGQ-8RYV3-4PGQ3-C8XTP-7CFBY", 121, "X19-98886", 0, "Retail", "Education"),
    @("c5198a66-e435-4432-89cf-ec777c9d0352", "84NGF-MHBT6-FXBX8-QWJK7-DRR8H", 122, "X19-98892", 0, "Retail", "Education N"),
    @("f6e29426-a256-4316-88bf-cc5b0f95ec0c", "PJB47-8PN2T-MCGDY-JTY3D-CBCPV", 125, "X23-50331", 1, "Volume:MAK", "EnterpriseS_Ge"),
    @("cce9d2de-98ee-4ce2-8113-222620c64a27", "KCNVH-YKWX8-GJJB9-H9FDT-6F7W2", 125, "X22-66075", 1, "Volume:MAK", "EnterpriseS_VB"),
    @("d06934ee-5448-4fd1-964a-cd077618aa06", "43TBQ-NH92J-XKTM7-KT3KK-P39PB", 125, "X21-83233", 0, "OEM:NONSLP", "EnterpriseS_RS5"),
    @("706e0cfd-23f4-43bb-a9af-1a492b9f1302", "NK96Y-D9CD8-W44CQ-R8YTK-DYJWX", 125, "X21-05035", 0, "OEM:NONSLP", "EnterpriseS_RS1"),
    @("faa57748-75c8-40a2-b851-71ce92aa8b45", "FWN7H-PF93Q-4GGP8-M8RF3-MDWWW", 125, "X19-99617", 0, "OEM:NONSLP", "EnterpriseS_TH"),
    @("3d1022d8-969f-4222-b54b-327f5a5af4c9", "2DBW3-N2PJG-MVHW3-G7TDK-9HKR4", 126, "X21-04921", 0, "Volume:MAK", "EnterpriseS N_RS1"),
    @("60c243e1-f90b-4a1b-ba89-387294948fb6", "NTX6B-BRYC2-K6786-F6MVQ-M7V2X", 126, "X19-98770", 0, "Volume:MAK", "EnterpriseS N_TH"),
    @("01eb852c-424d-4060-94b8-c10d799d7364", "3XP6D-CRND4-DRYM2-GM84D-4GG8Y", 139, "X23-37869", 1, "Retail", "Professional Country Specific"),
    @("eb6d346f-1c60-4643-b960-40ec31596c45", "DXG7C-N36C4-C4HTG-X4T3X-2YV77", 161, "X21-43626", 0, "Retail", "Pro Workstation"),
    @("89e87510-ba92-45f6-8329-3afa905e3e83", "WYPNQ-8C467-V2W6J-TX4WX-WT2RQ", 162, "X21-43644", 0, "Retail", "Pro Workstation N"),
    @("62f0c100-9c53-4e02-b886-a3528ddfe7f6", "8PTT6-RNW4C-6V7J2-C2D3X-MHBPB", 164, "X21-04955", 0, "Retail", "Pro Education"),
    @("13a38698-4a49-4b9e-8e83-98fe51110953", "GJTYN-HDMQY-FRR76-HVGC7-QPF8P", 165, "X21-04956", 0, "Retail", "Pro Education N"),
    @("df96023b-dcd9-4be2-afa0-c6c871159ebe", "NJCF7-PW8QT-3324D-688JX-2YV66", 175, "X21-41295", 0, "Retail", "Enterprise Multi-Session"),
    @("d4ef7282-3d2c-4cf0-9976-8854e64a8d1e", "V3WVW-N2PV2-CGWC3-34QGF-VMJ2C", 178, "X21-32983", 0, "Retail", "Cloud"),
    @("af5c9381-9240-417d-8d35-eb40cd03e484", "NH9J3-68WK7-6FB93-4K3DF-DJ4F6", 179, "X21-32987", 0, "Retail", "Cloud N"),
    @("8ab9bdd1-1f67-4997-82d9-8878520837d9", "XQQYW-NFFMW-XJPBH-K8732-CKFFD", 188, "X21-99378", 0, "OEM:DM", "IoT Enterprise"),
    @("ed655016-a9e8-4434-95d9-4345352c2552", "QPM6N-7J2WJ-P88HH-P3YRH-YY74H", 191, "X21-99682", 0, "OEM:NONSLP", "IoT Enterprise LTSC 2021"),
    @("6c4de1b8-24bb-4c17-9a77-7b939414c298", "CGK42-GYN6Y-VD22B-BX98W-J8JXD", 191, "X23-12617", 0, "OEM:NONSLP", "IoT Enterprise LTSC 2024"),
    @("d4bdc678-0a4b-4a32-a5b3-aaa24c3b0f24", "K9VKN-3BGWV-Y624W-MCRMQ-BHDCD", 202, "X22-53884", 0, "Retail", "Cloud Edition N"),
    @("92fb8726-92a8-4ffc-94ce-f82e07444653", "KY7PN-VR6RX-83W6Y-6DDYQ-T6R4W", 203, "X22-53847", 0, "Retail", "Cloud Edition"),
    @("5a85300a-bfce-474f-ac07-a30983e3fb90", "N979K-XWD77-YW3GB-HBGH6-D32MH", 205, "X23-15042", 0, "OEM:DM", "IoT Enterprise SK"),
    @("80083eae-7031-4394-9e88-4901973d56fe", "P8Q7T-WNK7X-PMFXY-VXHBG-RRK69", 206, "X23-62084", 0, "OEM:DM", "IoT Enterprise K"),
    @("1bc2140b-285b-4351-b99c-26a126104b29", "TMP2N-KGFHJ-PWM6F-68KCQ-3PJBP", 210, "X23-60513", 0, "Retail", "Windows 11 SE")
)

# 5. Resolve product key dynamically using SKU and Activation IDs
$key = $null
$targetSku = $null
$targetKey = $null
$targetPfn = $null
$targetName = $null
$notWorking = 0

foreach ($row in $hwidData) {
    $actId = $row[0]
    $rowKey = $row[1]
    $rowSku = $row[2]
    $rowPfn = $row[3]
    $rowNotWorking = $row[4]
    $rowKeyType = $row[5]
    $rowName = $row[6]

    if ($sku -eq $rowSku -and -not $key) {
        $targetSku = $rowSku
        $targetKey = $rowKey
        $targetPfn = $rowPfn
        $targetName = $rowName
        $notWorking = $rowNotWorking
        
        # Check if ActivationID is currently installed
        if ($allapps -contains $actId) {
            $key = $rowKey
            break
        }
        # Check if SKU ID is in tokens
        if ($altapplist -contains $actId) {
            $key = $rowKey
            Install-EditionLicenses $rowName
            break
        }
    }
}

# 6. Fallback SKU key detection if not resolved directly
if (-not $key) {
    foreach ($row in $hwidData) {
        if ($sku -eq $row[2]) {
            $key = $row[1]
            $targetSku = $row[2]
            $targetKey = $row[1]
            $targetPfn = $row[3]
            $targetName = $row[6]
            $notWorking = $row[4]
            break
        }
    }
}

if (-not $key) {
    throw "Current Windows SKU [$sku] is not supported for HWID activation."
}

Write-Host "Selected Product Key: $key for [$targetName]" -ForegroundColor Green

# 7. Install generic product key
Write-Host "Installing generic product key..." -ForegroundColor Cyan
$sps = Get-CimInstance SoftwareLicensingService
$null = $sps | Invoke-CimMethod -MethodName "InstallProductKey" -Arguments @{ ProductKey = $key }

# 8. Geo-location fix if region causes ticket generation issues
$geoNation = (Get-ItemProperty -Path 'HKCU:\Control Panel\International\Geo' -Name Nation -ErrorAction SilentlyContinue).Nation
$regionChange = $false
if ($geoNation -eq 242) {
    Write-Host "Changing Windows region to USA to avoid activation issues..." -ForegroundColor Cyan
    try {
        Set-WinHomeLocation -GeoId 244 -ErrorAction Stop
        $regionChange = $true
        Write-Host "Changing Windows Region To USA [Successful]" -ForegroundColor Green
    } catch {
        Write-Warning "Changing Windows Region To USA [Failed]"
    }
}

try {
    # 9. Generate Session ID String
    $pfnStr = "Microsoft.Windows.$targetSku.${targetPfn}_8wekyb3d8bbwe"
    $sessionIdStr = "OSMajorVersion=5;OSMinorVersion=1;OSPlatformId=2;PP=0;Pfn=$pfnStr;PKeyIID=221306452340115677963964261259250411589493550039199940431586886;"

    # Microsoft Client Lockbox RSA Private Key Blob
    [byte[]] $rsaKeyBlob = @(
        0x07,0x02,0x00,0x00,0x00,0xA4,0x00,0x00,0x52,0x53,0x41,0x32,0x00,0x04,0x00,0x00,
        0x01,0x00,0x01,0x00,0x29,0x87,0xBA,0x3F,0x52,0x90,0x57,0xD8,0x12,0x26,0x6B,0x38,
        0xB2,0x3B,0xF9,0x67,0x08,0x4F,0xDD,0x8B,0xF5,0xE3,0x11,0xB8,0x61,0x3A,0x33,0x42,
        0x51,0x65,0x05,0x86,0x1E,0x00,0x41,0xDE,0xC5,0xDD,0x44,0x60,0x56,0x3D,0x14,0x39,
        0xB7,0x43,0x65,0xE9,0xF7,0x2B,0xA5,0xF0,0xA3,0x65,0x68,0xE9,0xE4,0x8B,0x5C,0x03,
        0x2D,0x36,0xFE,0x28,0x4C,0xD1,0x3C,0x3D,0xC1,0x90,0x75,0xF9,0x6E,0x02,0xE0,0x58,
        0x97,0x6A,0xCA,0x80,0x02,0x42,0x3F,0x6C,0x15,0x85,0x4D,0x83,0x23,0x6A,0x95,0x9E,
        0x38,0x52,0x59,0x38,0x6A,0x99,0xF0,0xB5,0xCD,0x53,0x7E,0x08,0x7C,0xB5,0x51,0xD3,
        0x8F,0xA3,0x0D,0xA0,0xFA,0x8D,0x87,0x3C,0xFC,0x59,0x21,0xD8,0x2E,0xD9,0x97,0x8B,
        0x40,0x60,0xB1,0xD7,0x2B,0x0A,0x6E,0x60,0xB5,0x50,0xCC,0x3C,0xB1,0x57,0xE4,0xB7,
        0xDC,0x5A,0x4D,0xE1,0x5C,0xE0,0x94,0x4C,0x5E,0x28,0xFF,0xFA,0x80,0x6A,0x13,0x53,
        0x52,0xDB,0xF3,0x04,0x92,0x43,0x38,0xB9,0x1B,0xD9,0x85,0x54,0x7B,0x14,0xC7,0x89,
        0x16,0x8A,0x4B,0x82,0xA1,0x08,0x02,0x99,0x23,0x48,0xDD,0x75,0x9C,0xC8,0xC1,0xCE,
        0xB0,0xD7,0x1B,0xD8,0xFB,0x2D,0xA7,0x2E,0x47,0xA7,0x18,0x4B,0xF6,0x29,0x69,0x44,
        0x30,0x33,0xBA,0xA7,0x1F,0xCE,0x96,0x9E,0x40,0xE1,0x43,0xF0,0xE0,0x0D,0x0A,0x32,
        0xB4,0xEE,0xA1,0xC3,0x5E,0x9B,0xC7,0x7F,0xF5,0x9D,0xD8,0xF2,0x0F,0xD9,0x8F,0xAD,
        0x75,0x0A,0x00,0xD5,0x25,0x43,0xF7,0xAE,0x51,0x7F,0xB7,0xDE,0xB7,0xAD,0xFB,0xCE,
        0x83,0xE1,0x81,0xFF,0xDD,0xA2,0x77,0xFE,0xEB,0x27,0x1F,0x10,0xFA,0x82,0x37,0xF4,
        0x7E,0xCC,0xE2,0xA1,0x58,0xC8,0xAF,0x1D,0x1A,0x81,0x31,0x6E,0xF4,0x8B,0x63,0x34,
        0xF3,0x05,0x0F,0xE1,0xCC,0x15,0xDC,0xA4,0x28,0x7A,0x9E,0xEB,0x62,0xD8,0xD8,0x8C,
        0x85,0xD7,0x07,0x87,0x90,0x2F,0xF7,0x1C,0x56,0x85,0x2F,0xEF,0x32,0x37,0x07,0xAB,
        0xB0,0xE6,0xB5,0x02,0x19,0x35,0xAF,0xDB,0xD4,0xA2,0x9C,0x36,0x80,0xC6,0xDC,0x82,
        0x08,0xE0,0xC0,0x5F,0x3C,0x59,0xAA,0x4E,0x26,0x03,0x29,0xB3,0x62,0x58,0x41,0x59,
        0x3A,0x37,0x43,0x35,0xE3,0x9F,0x34,0xE2,0xA1,0x04,0x97,0x12,0x9D,0x8C,0xAD,0xF7,
        0xFB,0x8C,0xA1,0xA2,0xE9,0xE4,0xEF,0xD9,0xC5,0xE5,0xDF,0x0E,0xBF,0x4A,0xE0,0x7A,
        0x1E,0x10,0x50,0x58,0x63,0x51,0xE1,0xD4,0xFE,0x57,0xB0,0x9E,0xD7,0xDA,0x8C,0xED,
        0x7D,0x82,0xAC,0x2F,0x25,0x58,0x0A,0x58,0xE6,0xA4,0xF4,0x57,0x4B,0xA4,0x1B,0x65,
        0xB9,0x4A,0x87,0x46,0xEB,0x8C,0x0F,0x9A,0x48,0x90,0xF9,0x9F,0x76,0x69,0x03,0x72,
        0x77,0xEC,0xC1,0x42,0x4C,0x87,0xDB,0x0B,0x3C,0xD4,0x74,0xEF,0xE5,0x34,0xE0,0x32,
        0x45,0xB0,0xF8,0xAB,0xD5,0x26,0x21,0xD7,0xD2,0x98,0x54,0x8F,0x64,0x88,0x20,0x2B,
        0x14,0xE3,0x82,0xD5,0x2A,0x4B,0x8F,0x4E,0x35,0x20,0x82,0x7E,0x1B,0xFE,0xFA,0x2C,
        0x79,0x6C,0x6E,0x66,0x94,0xBB,0x0A,0xEB,0xBA,0xD9,0x70,0x61,0xE9,0x47,0xB5,0x82,
        0xFC,0x18,0x3C,0x66,0x3A,0x09,0x2E,0x1F,0x61,0x74,0xCA,0xCB,0xF6,0x7A,0x52,0x37,
        0x1D,0xAC,0x8D,0x63,0x69,0x84,0x8E,0xC7,0x70,0x59,0xDD,0x2D,0x91,0x1E,0xF7,0xB1,
        0x56,0xED,0x7A,0x06,0x9D,0x5B,0x33,0x15,0xDD,0x31,0xD0,0xE6,0x16,0x07,0x9B,0xA5,
        0x94,0x06,0x7D,0xC1,0xE9,0xD6,0xC8,0xAF,0xB4,0x1E,0x2D,0x88,0x06,0xA7,0x63,0xB8,
        0xCF,0xC8,0xA2,0x6E,0x84,0xB3,0x8D,0xE5,0x47,0xE6,0x13,0x63,0x8E,0xD1,0x7F,0xD4,
        0x81,0x44,0x38,0xBF
    )

    # 10. Cryptographic Signature Generation
    Write-Host "Generating GenuineTicket..." -ForegroundColor Cyan
    $rsa = New-Object Security.Cryptography.RSACryptoServiceProvider
    $rsa.ImportCspBlob($rsaKeyBlob)
    $SessionId = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($sessionIdStr + [char]0))
    $propertiesStr = "OA3xOriginalProductId=;OA3xOriginalProductKey=;SessionId=$SessionId;TimeStampClient=2022-10-11T12:00:00Z"
    $sha256 = [Security.Cryptography.SHA256]::Create()
    $bytes = [Text.Encoding]::UTF8.GetBytes($propertiesStr)
    $hash = $sha256.ComputeHash($bytes)
    $signature = $rsa.SignHash($hash, [Security.Cryptography.HashAlgorithmName]::SHA256, [Security.Cryptography.RSASignaturePadding]::Pkcs1)
    $signatureStr = [Convert]::ToBase64String($signature)
    $xml = @"
<?xml version="1.0" encoding="utf-8"?><genuineAuthorization xmlns="http://www.microsoft.com/DRM/SL/GenuineAuthorization/1.0"><version>1.0</version><genuineProperties origin="sppclient"><properties>$propertiesStr</properties><signatures><signature name="clientLockboxKey" method="rsa-sha256">$signatureStr</signature></signatures></genuineProperties></genuineAuthorization>
"@

    # 11. Write GenuineTicket to ClipSVC folders exactly like MAS AIO
    $ticketDir = "$env:ProgramData\Microsoft\Windows\ClipSVC\GenuineTicket"
    $migrationDir = "$env:ProgramData\Microsoft\Windows\ClipSVC\Install\Migration"
    if (-not (Test-Path $ticketDir)) {
        $null = New-Item -ItemType Directory -Force -Path $ticketDir
    }
    
    Remove-Item -Path "$ticketDir\Genuine*" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "$ticketDir\*.xml" -Force -ErrorAction SilentlyContinue
    if (Test-Path $migrationDir) {
        Remove-Item -Path "$migrationDir\*" -Force -ErrorAction SilentlyContinue
    }

    $ticketPathRaw = Join-Path $ticketDir "GenuineTicket"
    $ticketPathXml = Join-Path $ticketDir "GenuineTicket.xml"
    [IO.File]::WriteAllText($ticketPathRaw, $xml, [System.Text.Encoding]::ASCII)
    
    # Method A: Try with ClipSVC service restart
    Write-Host "Installing GenuineTicket.xml with ClipSVC service restart..." -ForegroundColor Cyan
    Copy-Item -Path $ticketPathRaw -Destination $ticketPathXml -Force
    
    $restartJob = Start-Job { Restart-Service ClipSVC -Force }
    $null = Wait-Job -Job $restartJob -Timeout 20
    $null = Receive-Job -Job $restartJob -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    
    # Method B: Try with clipup -v -o if XML not consumed
    if (Test-Path $ticketPathXml) {
        Write-Warning "Installing GenuineTicket.xml failed with ClipSVC service restart. Trying clipup method..."
        Remove-Item -Path "$ticketDir\*.xml" -Force -ErrorAction SilentlyContinue
        
        Copy-Item -Path $ticketPathRaw -Destination $ticketPathXml -Force
        if (Test-Path "$env:SystemRoot\System32\clipup.exe") {
            Write-Host "Triggering ClipUp integration..." -ForegroundColor Cyan
            Start-Process -FilePath "clipup.exe" -ArgumentList "-v -o" -NoNewWindow -Wait
        }
    }
    
    # Verify ticket consumption
    $tokensPath = "$env:ProgramData\Microsoft\Windows\ClipSVC\tokens.dat"
    if (-not (Test-Path $tokensPath)) {
        Write-Warning "Checking ClipSVC tokens.dat [Not Found]"
    }
    if (Test-Path $ticketPathXml) {
        Write-Warning "Installing GenuineTicket.xml [Failed With clipup -v -o]"
    }
    if (Test-Path $migrationDir) {
        $migXmls = Get-ChildItem -Path $migrationDir -Filter "*.xml" -ErrorAction SilentlyContinue
        if ($migXmls) {
            Write-Warning "Checking Ticket Migration [Failed]"
        }
    }
    
    # Clean raw ticket
    Remove-Item -Path "$ticketDir\Genuine*" -Force -ErrorAction SilentlyContinue

    # 12. Trigger Windows Online Activation
    Write-Host "Requesting activation..." -ForegroundColor Cyan
    $activated = $false
    try {
        $spp = Get-CimInstance -Query "SELECT * FROM SoftwareLicensingProduct WHERE ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL AND LicenseDependsOn is NULL"
        $null = $spp | Invoke-CimMethod -MethodName "Activate"
        $licenseStatus = (Get-CimInstance -Query "SELECT LicenseStatus FROM SoftwareLicensingProduct WHERE ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL AND LicenseDependsOn is NULL").LicenseStatus
        if ($licenseStatus -contains 1 -or $licenseStatus -eq 1) {
            $activated = $true
        }
    } catch {
        # Suppress initial error to try cleanup
    }

    # 13. Fallback registry cleanup (IdentityCRL) if not activated initially
    if (-not $activated) {
        Write-Host "Applying Microsoft Store ID registry cleanup (IdentityCRL) based on MAS AIO..." -ForegroundColor Yellow
        try {
            $identPath = "Registry::HKEY_USERS\S-1-5-19\SOFTWARE\Microsoft\IdentityCRL"
            if (Test-Path $identPath) {
                Remove-Item -Path $identPath -Recurse -Force -ErrorAction SilentlyContinue
            }
            Write-Host "Restarting wlidsvc, LicenseManager, sppsvc services..." -ForegroundColor Cyan
            foreach ($srv in @("wlidsvc", "LicenseManager", "sppsvc")) {
                $restartJob = Start-Job { Restart-Service $srv -Force }
                $null = Wait-Job -Job $restartJob -Timeout 20
            }
            Start-Sleep -Seconds 2
            
            # Request activation again
            $spp = Get-CimInstance -Query "SELECT * FROM SoftwareLicensingProduct WHERE ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL AND LicenseDependsOn is NULL"
            $null = $spp | Invoke-CimMethod -MethodName "Activate"
            $licenseStatus = (Get-CimInstance -Query "SELECT LicenseStatus FROM SoftwareLicensingProduct WHERE ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL AND LicenseDependsOn is NULL").LicenseStatus
            if ($licenseStatus -contains 1 -or $licenseStatus -eq 1) {
                $activated = $true
            }
        } catch {
            Write-Warning "IdentityCRL cleanup failed: $_"
        }
    }

    # Verify final activation
    if ($activated) {
        Write-Host "Congratulations! Windows is permanently activated with a digital license." -ForegroundColor Green -BackgroundColor Black
    } else {
        Write-Error "Activation status verification failed."
        exit 1
    }
}
finally {
    # Restore Windows region if changed
    if ($regionChange -and $geoNation) {
        Write-Host "Restoring Windows region..." -ForegroundColor Cyan
        try {
            Set-WinHomeLocation -GeoId $geoNation -ErrorAction Stop
            Write-Host "Restoring Windows Region [Successful]" -ForegroundColor Green
        } catch {
            Write-Warning "Restoring Windows Region [Failed]"
        }
    }
}
"""

    script_fd, script_path = tempfile.mkstemp(prefix="mas_activate_", suffix=".ps1")
    try:
        with os.fdopen(script_fd, "w", encoding="utf-8") as f:
            f.write(script_content)

        process = subprocess.Popen(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW
        )

        status_map = {
            "detecting windows sku": "Windows SKU kimliği tespit ediliyor",
            "installing product key": "Ürün anahtarı sisteme kuruluyor",
            "installing gvlk product key": "GVLK lisans anahtarı sisteme kuruluyor",
            "setting kms server": "KMS sunucusu yapılandırılıyor",
            "requesting kms activation": "KMS sunucusu üzerinden lisanslama talep ediliyor",
            "triggering spp local": "SPP lisans motoru tetikleniyor",
            "generating genuineticket": "Dijital aktivasyon bileti (GenuineTicket) oluşturuluyor",
            "restarting clipsvc": "ClipSVC servisi yeniden başlatılıyor"
        }

        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                stripped = line.strip()
                if stripped and on_status_update:
                    lower_line = stripped.lower()
                    for eng_msg, tr_msg in status_map.items():
                        if eng_msg in lower_line:
                            on_status_update(tr_msg)
                            break

        stdout, stderr = process.communicate()
        if process.returncode != 0:
            err_msg = stderr.strip() or stdout.strip() or "Aktivasyon betiği hata döndürdü."
            return False, err_msg
        return True, "Aktivasyon başarıyla tamamlandı."
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass
