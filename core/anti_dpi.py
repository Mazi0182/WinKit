"""
WinKit - Core Anti-DPI & Zapret Management Module
Comprehensive Zapret service installation, uninstallation, DoH and network configuration engine.
"""

import os
import sys
import time
import shutil
import secrets
import subprocess
from pathlib import Path
from typing import Tuple, Optional, Callable

from core.constants import (
    CREATE_NO_WINDOW,
    ZAPRET_V1_PAYLOAD_FILES,
    ZAPRET_V2_PAYLOAD_FILES,
    ZAPRET_ALL_PAYLOAD_FILES,
)
from core.system import get_documents_directory, get_winkit_data_directory
from core.privileges import run_powershell_checked


def is_zapret_installed() -> bool:
    """Sistemde aktif veya kurulu bir Zapret servis/dosya varlığını doğrular."""
    try:
        res = subprocess.run(
            ["sc.exe", "query", "ZapretService"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
        if res.returncode == 0 and ("STATE" in (res.stdout or "")):
            return True
    except Exception:
        pass

    for p in (get_documents_directory() / "Zapret", get_winkit_data_directory() / "Zapret"):
        if (p / "winws.exe").is_file() or (p / "winws2.exe").is_file():
            return True
    return False


def get_zapret_paths(source_override: Optional[Path] = None) -> Tuple[Path, Path]:
    """Zapret kaynak dizinini ve hedef kurulum dizinini döndürür."""
    if source_override is not None:
        source_dir = Path(source_override).resolve()
    else:
        # Standart paket yolu: WinKit kök dizini / zapret veya ProgramData
        base_dir = Path(__file__).resolve().parent.parent
        source_dir = base_dir / "zapret"
        if not source_dir.is_dir():
            source_dir = get_winkit_data_directory() / "zapret"

    install_dir = get_documents_directory() / "Zapret"
    return source_dir, install_dir


def _powershell_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def apply_zapret_network_settings(install_dir: Path) -> None:
    """
    Cloudflare DoH sunucularını Windows'un desteklenen DoH tablosuna kaydeder,
    bağdaştırıcıya atar, IPv6'yı kapatır ve şifrelenmemiş geri dönüşü makine ilkesiyle engeller.
    """
    script = r"""
$ErrorActionPreference = 'Stop'
$adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object {
    $_.Status -eq 'Up' -and -not (
        $_.InterfaceDescription -like '*Loopback*' -or
        $_.InterfaceDescription -like '*Npcap*' -or
        $_.InterfaceDescription -like '*Bluetooth*' -or
        $_.InterfaceDescription -like '*TAP*' -or
        $_.InterfaceDescription -like '*WFP*'
    )
})
if ($adapters.Count -eq 0) {
    $adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' })
}
if ($adapters.Count -eq 0) { throw 'Aktif ağ bağdaştırıcısı bulunamadı.' }

# 1. Cloudflare DoH sunucularını Windows'un desteklenen sunucu listesine ekle
$dohKey = 'HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters\DohWellKnownServers'
if (-not (Test-Path $dohKey)) { New-Item -Path $dohKey -Force | Out-Null }
$dohServers = [ordered]@{
    '1.1.1.1' = 'https://cloudflare-dns.com/dns-query'
    '1.0.0.1' = 'https://cloudflare-dns.com/dns-query'
}

$dnsPolicy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient'
if (-not (Test-Path $dnsPolicy)) { New-Item -Path $dnsPolicy -Force | Out-Null }
# Windows DnsClient.admx: 3 = DoH zorunlu, 2 = otomatik, 1 = kapalı.
Set-ItemProperty -Path $dnsPolicy -Name 'DoHPolicy' -Value 3 -Type DWord -Force
Set-ItemProperty -Path $dnsPolicy -Name 'DohPolicySetting' -Value 3 -Type DWord -Force

foreach ($entry in $dohServers.GetEnumerator()) {
    $server = [string]$entry.Key
    $tmpl = [string]$entry.Value
    & netsh.exe dns delete encryption server=$server 2>$null | Out-Null
    & netsh.exe dns add encryption server=$server dohtemplate=$tmpl autoupgrade=yes udpfallback=no 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "DoH şablonu netsh ile eklenemedi: $server" }

    if (Get-Command Get-DnsClientDohServerAddress -ErrorAction SilentlyContinue) {
        $existingDoh = Get-DnsClientDohServerAddress -ServerAddress $server -ErrorAction SilentlyContinue
        if ($existingDoh -and (Get-Command Set-DnsClientDohServerAddress -ErrorAction SilentlyContinue)) {
            Set-DnsClientDohServerAddress -ServerAddress $server -DohTemplate $tmpl -AllowFallbackToUdp $false -AutoUpgrade $true -ErrorAction Stop
        } elseif (Get-Command Add-DnsClientDohServerAddress -ErrorAction SilentlyContinue) {
            Add-DnsClientDohServerAddress -ServerAddress $server -DohTemplate $tmpl -AllowFallbackToUdp $false -AutoUpgrade $true -ErrorAction Stop
        }
    }

    $itemKey = Join-Path $dohKey $server
    if (-not (Test-Path $itemKey)) { New-Item -Path $itemKey -Force | Out-Null }
    Set-ItemProperty -Path $itemKey -Name 'Template' -Value $tmpl -Type String -Force
    Set-ItemProperty -Path $itemKey -Name 'Flags' -Value 8 -Type DWord -Force
    Set-ItemProperty -Path $itemKey -Name 'ServerAddress' -Value $server -Type String -Force
    Set-ItemProperty -Path $itemKey -Name 'AutoUpgrade' -Value 1 -Type DWord -Force
    Set-ItemProperty -Path $itemKey -Name 'AllowFallbackToUdp' -Value 0 -Type DWord -Force
}

$dnsCacheParam = 'HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters'
Set-ItemProperty -Path $dnsCacheParam -Name 'EnableAutoDoh' -Value 2 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path $dnsCacheParam -Name 'DnsOverHttps' -Value 2 -Type DWord -Force -ErrorAction SilentlyContinue

# 2. Ağ bağdaştırıcılarına DNS ve DoH atama
foreach ($adapter in $adapters) {
    Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses @('1.1.1.1', '1.0.0.1')
    Disable-NetAdapterBinding -Name $adapter.Name -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue | Out-Null

    # Windows 11 Ayarlar uygulamasının "Şifrelenmiş (DoH)" olarak tanıması için arabirim anahtarlarına yaz
    $guid = $adapter.InterfaceGuid
    if ($guid) {
        $ifCacheKey = "HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters\Interfaces\$guid"
        if (-not (Test-Path $ifCacheKey)) { New-Item -Path $ifCacheKey -Force | Out-Null }
        Set-ItemProperty -Path $ifCacheKey -Name 'DnsOverHttps' -Value 2 -Type DWord -Force -ErrorAction SilentlyContinue
        Set-ItemProperty -Path $ifCacheKey -Name 'DohTemplate' -Value 'https://cloudflare-dns.com/dns-query' -Type String -Force -ErrorAction SilentlyContinue
        Set-ItemProperty -Path $ifCacheKey -Name 'EnableDoh' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
        Set-ItemProperty -Path $ifCacheKey -Name 'ServerAddresses' -Value '1.1.1.1,1.0.0.1' -Type String -Force -ErrorAction SilentlyContinue

        $ispKey = "HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\InterfaceSpecificParameters\$guid"
        if (-not (Test-Path $ispKey)) { New-Item -Path $ispKey -Force | Out-Null }
        Set-ItemProperty -Path $ispKey -Name 'DnsOverHttps' -Value 2 -Type DWord -Force -ErrorAction SilentlyContinue
        Set-ItemProperty -Path $ispKey -Name 'DohFlags' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

        # Windows 11 Ayarlar (SystemSettings) arayüzünün doğrudan "(Şifreli)" / Encrypted Only olarak tanıdığı kesin yapı:
        $dohIfKey = "$ispKey\DohInterfaceSettings"
        if (-not (Test-Path $dohIfKey)) { New-Item -Path $dohIfKey -Force | Out-Null }
        Set-ItemProperty -Path $dohIfKey -Name 'DnsOverHttps' -Value 2 -Type DWord -Force -ErrorAction SilentlyContinue
        Set-ItemProperty -Path $dohIfKey -Name 'DohFlags' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

        foreach ($srv in @('1.1.1.1', '1.0.0.1')) {
            $profileKey = "$ispKey\DohProfileSettings\Doh\$srv"
            if (-not (Test-Path $profileKey)) { New-Item -Path $profileKey -Force | Out-Null }
            Set-ItemProperty -Path $profileKey -Name 'Template' -Value 'https://cloudflare-dns.com/dns-query' -Type String -Force -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $profileKey -Name 'AutoUpgrade' -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $profileKey -Name 'AllowFallbackToUdp' -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

            $dohSrvKey = "$dohIfKey\Doh\$srv"
            if (-not (Test-Path $dohSrvKey)) { New-Item -Path $dohSrvKey -Force | Out-Null }
            Set-ItemProperty -Path $dohSrvKey -Name 'DohTemplate' -Value 'https://cloudflare-dns.com/dns-query' -Type String -Force -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $dohSrvKey -Name 'DohFlags' -Value ([int64]17) -Type QWord -Force -ErrorAction SilentlyContinue
        }

        $ifTcpipKey = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\$guid"
        if (Test-Path $ifTcpipKey) {
            Set-ItemProperty -Path $ifTcpipKey -Name 'NameServer' -Value '1.1.1.1,1.0.0.1' -Type String -Force -ErrorAction SilentlyContinue
        }
    }
}

# Sunucular bağdaştırıcıya atandıktan sonra yükseltme bayraklarını tekrar yaz
foreach ($entry in $dohServers.GetEnumerator()) {
    Set-DnsClientDohServerAddress -ServerAddress ([string]$entry.Key) -DohTemplate ([string]$entry.Value) -AllowFallbackToUdp $false -AutoUpgrade $true -ErrorAction Stop
}

# 3. IPv6 global devre dışı bırakma
$regPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters'
New-Item -Path $regPath -Force | Out-Null
New-ItemProperty -Path $regPath -Name DisabledComponents -PropertyType DWord -Value 255 -Force | Out-Null
Clear-DnsClientCache

# 4. Doğrulama
if (Get-Command Get-DnsClientDohServerAddress -ErrorAction SilentlyContinue) {
    foreach ($entry in $dohServers.GetEnumerator()) {
        $check = Get-DnsClientDohServerAddress -ServerAddress ([string]$entry.Key) -ErrorAction SilentlyContinue
        if (-not $check) { throw "DoH doğrulaması başarısız: $($entry.Key)" }
        $templates = @($check | ForEach-Object { [string]$_.DohTemplate })
        if ($templates -notcontains [string]$entry.Value) {
            throw "DoH şablonu doğrulanamadı: $($entry.Key)"
        }
        if (-not @($check | Where-Object { $_.AutoUpgrade -eq $true })) {
            throw "DoH otomatik şifreleme bayrağı doğrulanamadı: $($entry.Key)"
        }
        if (@($check | Where-Object { $_.AllowFallbackToUdp -eq $true })) {
            throw "DoH için şifrelenmemiş DNS geri dönüşü açık kaldı: $($entry.Key)"
        }
    }
}
"""
    run_powershell_checked(script, timeout=150)


def restore_zapret_network_settings(install_dir: Path, restore_dns: bool = True) -> None:
    """Zapret kaldırılırken IPv6 protokolünü tekrar etkinleştirir ve seçilirse DoH/DNS ayarlarını fabrika varsayılanına döndürür."""
    dns_reset_ps = ""
    if restore_dns:
        dns_reset_ps = r"""
        # 1. Windows NT DNSClient DoH politikalarını tamamen temizle
        $dnsPolicy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient'
        if (Test-Path $dnsPolicy) {
            Remove-ItemProperty -Path $dnsPolicy -Name 'DoHPolicy' -Force -ErrorAction SilentlyContinue
            Remove-ItemProperty -Path $dnsPolicy -Name 'DohPolicySetting' -Force -ErrorAction SilentlyContinue
        }

        # 2. Dnscache global parametrelerinden DoH sunucularını temizle
        $dohKey = 'HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters\DohWellKnownServers'
        if (Test-Path $dohKey) {
            Remove-Item -Path $dohKey -Recurse -Force -ErrorAction SilentlyContinue
        }
        $dnsCacheParam = 'HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters'
        Remove-ItemProperty -Path $dnsCacheParam -Name 'EnableAutoDoh' -Force -ErrorAction SilentlyContinue
        Remove-ItemProperty -Path $dnsCacheParam -Name 'DnsOverHttps' -Force -ErrorAction SilentlyContinue

        # 3. Tüm ağ arabirimlerinden DoH profil ve şablon kayıtlarını temizle
        $dnscacheRoot = 'HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache'
        foreach ($sub in @('Parameters\Interfaces', 'InterfaceSpecificParameters')) {
            $baseK = Join-Path $dnscacheRoot $sub
            if (Test-Path $baseK) {
                Get-ChildItem -Path $baseK -ErrorAction SilentlyContinue | ForEach-Object {
                    $ifPath = $_.PSPath
                    Remove-Item -Path "$ifPath\DohInterfaceSettings" -Recurse -Force -ErrorAction SilentlyContinue
                    Remove-Item -Path "$ifPath\DohProfileSettings" -Recurse -Force -ErrorAction SilentlyContinue
                    Remove-ItemProperty -Path $ifPath -Name 'DnsOverHttps' -Force -ErrorAction SilentlyContinue
                    Remove-ItemProperty -Path $ifPath -Name 'DohTemplate' -Force -ErrorAction SilentlyContinue
                    Remove-ItemProperty -Path $ifPath -Name 'EnableDoh' -Force -ErrorAction SilentlyContinue
                    Remove-ItemProperty -Path $ifPath -Name 'ServerAddresses' -Force -ErrorAction SilentlyContinue
                    Remove-ItemProperty -Path $ifPath -Name 'DohFlags' -Force -ErrorAction SilentlyContinue
                }
            }
        }

        # 4. netsh ile kayıtlı DoH şablonlarını sil
        & netsh.exe dns delete encryption server=1.1.1.1 2>$null | Out-Null
        & netsh.exe dns delete encryption server=1.0.0.1 2>$null | Out-Null

        # 5. Tüm aktif ağ bağdaştırıcılarını DHCP / Otomatik DNS moduna döndür
        $adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue)
        foreach ($adapter in $adapters) {
            Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ResetServerAddresses -ErrorAction SilentlyContinue
            $guid = $adapter.InterfaceGuid
            if ($guid) {
                $ifTcpipKey = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\$guid"
                if (Test-Path $ifTcpipKey) {
                    Set-ItemProperty -Path $ifTcpipKey -Name 'NameServer' -Value '' -Type String -Force -ErrorAction SilentlyContinue
                }
            }
        }
        """

    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$regPath = 'HKLM:\\\\SYSTEM\\\\CurrentControlSet\\\\Services\\\\Tcpip6\\\\Parameters'
Remove-ItemProperty -Path $regPath -Name DisabledComponents -ErrorAction SilentlyContinue

$adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue)
foreach ($adapter in $adapters) {{
    Enable-NetAdapterBinding -Name $adapter.Name -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue | Out-Null
}}

{dns_reset_ps}

Clear-DnsClientCache
& ipconfig.exe /flushdns 2>$null | Out-Null
"""
    run_powershell_checked(script, timeout=60)


def install_zapret(
    source_dir: Path,
    install_dir: Path,
    use_v1: bool = False,
    stage_start: Optional[Callable[[str, str], None]] = None,
    stage_finish: Optional[Callable[[str, str, str], None]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """Zapret anti-DPI servisini ve ağ politikalarını sisteme kurar."""
    if (install_dir / "winws.exe").is_file() or (install_dir / "winws2.exe").is_file():
        raise RuntimeError("Zapret zaten sisteminizde kurulu! Lütfen önce mevcut servisi kaldırın.")

    prep_stage = f"zapret_prep_{secrets.token_hex(5)}"
    if stage_start:
        stage_start(prep_stage, "Zapret kurulum ortamı hazırlanıyor")

    files_to_copy = ZAPRET_V1_PAYLOAD_FILES if use_v1 else ZAPRET_V2_PAYLOAD_FILES
    missing = [name for name in files_to_copy if not (source_dir / name).is_file()]
    if missing:
        if stage_finish:
            stage_finish(prep_stage, "başarısız", "#FF5C6B")
        raise FileNotFoundError("Zapret paketinde eksik dosyalar: " + ", ".join(missing))

    # Kopyalama öncesi çalışan servisleri ve sürücü kilitlerini güvenle kapat
    for proc in ("winws.exe", "winws2.exe"):
        subprocess.run(["taskkill.exe", "/f", "/im", proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False)
    for svc in ("ZapretService", "WinDivert", "WinDivert14"):
        subprocess.run(["net.exe", "stop", svc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False)
    time.sleep(0.2)
    if stage_finish:
        stage_finish(prep_stage, "hazırlandı", "#55D67A")

    copy_stage = f"zapret_copy_{secrets.token_hex(5)}"
    if stage_start:
        stage_start(copy_stage, f"Zapret {'v1' if use_v1 else 'v2'} dosyaları kuruluyor")
    install_dir.mkdir(parents=True, exist_ok=True)
    for name in files_to_copy:
        shutil.copy2(source_dir / name, install_dir / name)

    # Tekil exclude.txt kuralı
    raw_exclude_path = install_dir / "exclude.txt"
    if not raw_exclude_path.is_file() and (source_dir / "exclude.txt").is_file():
        shutil.copy2(source_dir / "exclude.txt", raw_exclude_path)

    exclusions = []
    if raw_exclude_path.is_file():
        for raw_line in raw_exclude_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            candidate = raw_line.strip()
            if not candidate or candidate.startswith(("#", ";", "//", "--")):
                continue
            candidate = candidate.split("#", 1)[0].strip()
            if candidate:
                exclusions.append(candidate)

    exclusions.extend([
        "anydesk.com",
        "net.anydesk.com",
        "riotgames.com",
        "riotcdn.net",
        "playvalorant.com",
        "leagueoflegends.com",
    ])
    raw_exclude_path.write_text(
        "\n".join(dict.fromkeys(exclusions)) + "\n",
        encoding="utf-8",
    )

    # Eski geçici dosyaları temizle
    for legacy_f in (install_dir / "exclude-hosts.txt", install_dir / "exclude-ips.txt"):
        try:
            if legacy_f.is_file():
                legacy_f.unlink()
        except OSError:
            pass

    if not use_v1:
        source_lua = source_dir / "lua"
        if source_lua.is_dir():
            target_lua = install_dir / "lua"
            target_lua.mkdir(parents=True, exist_ok=True)
            for item in source_lua.glob("*"):
                if item.is_file():
                    shutil.copy2(item, target_lua / item.name)
    if stage_finish:
        stage_finish(copy_stage, "✔", "#55D67A")

    service_stage = f"zapret_service_{secrets.token_hex(5)}"
    if stage_start:
        stage_start(service_stage, f"Zapret {'v1' if use_v1 else 'v2'} servisi yapılandırılıyor")

    if use_v1:
        winws_path = install_dir / "winws.exe"
        binary_command = (
            f'"{winws_path}" --wf-tcp=80,443 '
            f'--hostlist-exclude="{raw_exclude_path}" '
            "--hostspell=hoSt --dpi-desync=fake,split2 "
            "--dpi-desync-split-pos=2 --dpi-desync-ttl=6"
        )
    else:
        winws2_path = install_dir / "winws2.exe"
        lua_lib = install_dir / "lua" / "zapret-lib.lua"
        lua_antidpi = install_dir / "lua" / "zapret-antidpi.lua"
        if lua_lib.is_file() and lua_antidpi.is_file():
            binary_command = (
                f'"{winws2_path}" --wf-l3=ipv4 --wf-tcp-out=80,443 '
                f'--hostlist-exclude="{raw_exclude_path}" '
                f'--lua-init=@"{lua_lib}" --lua-init=@"{lua_antidpi}" '
                '--filter-l7=http,tls --payload=http_req --lua-desync=http_hostcase '
                '--payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000:tls_mod=rnd,dupsid '
                '--lua-desync=multisplit:pos=1,midsld'
            )
        else:
            binary_command = (
                f'"{winws2_path}" --wf-l3=ipv4 --wf-tcp-out=80,443 '
                f'--hostlist-exclude="{raw_exclude_path}" '
                '--filter-l7=http,tls --payload=http_req --lua-desync=http_hostcase '
                '--payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 '
                '--lua-desync=multisplit:pos=1,midsld'
            )

    service_script = f"""
$ErrorActionPreference = 'Stop'
$existing = Get-Service -Name 'ZapretService' -ErrorAction SilentlyContinue
if ($existing) {{
    Stop-Service -Name 'ZapretService' -Force -ErrorAction SilentlyContinue
    & sc.exe delete 'ZapretService' | Out-Null
    Start-Sleep -Milliseconds 900
}}
New-Service -Name 'ZapretService' -BinaryPathName {_powershell_quote(binary_command)} -DisplayName 'Zapret DPI Bypass' -StartupType Automatic | Out-Null
& sc.exe description 'ZapretService' 'İnternet servis sağlayıcıları tarafından uygulanan derin paket incelemesi (DPI) kısıtlamalarını aşarak engelsiz ve güvenli internet erişimi sağlar.' 2>$null | Out-Null
Start-Service -Name 'ZapretService'
$service = Get-Service -Name 'ZapretService'
if ($service.Status -ne 'Running') {{ throw 'Zapret servisi başlatılamadı.' }}
"""
    run_powershell_checked(service_script)
    if stage_finish:
        stage_finish(service_stage, "✔", "#55D67A")

    network_stage = f"zapret_network_{secrets.token_hex(5)}"
    if stage_start:
        stage_start(network_stage, "Cloudflare DoH ve IPv4 ağı yapılandırılıyor")
    apply_zapret_network_settings(install_dir)
    if stage_finish:
        stage_finish(network_stage, "✔", "#55D67A")

    return True


def remove_zapret(
    install_dir: Path,
    restore_dns: bool = True,
    stage_start: Optional[Callable[[str, str], None]] = None,
    stage_finish: Optional[Callable[[str, str, str], None]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """Zapret servisini ve bileşenlerini güvenle kaldırır."""
    service_stage = f"zapret_remove_service_{secrets.token_hex(5)}"
    if stage_start:
        stage_start(service_stage, "Zapret ve WinDivert servisleri kaldırılıyor")

    service_script = """
$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'SilentlyContinue'
Stop-Service -Name 'ZapretService' -Force -ErrorAction SilentlyContinue
& sc.exe stop 'ZapretService' 2>$null | Out-Null
& sc.exe delete 'ZapretService' 2>$null | Out-Null
& sc.exe stop 'WinDivert' 2>$null | Out-Null
& sc.exe delete 'WinDivert' 2>$null | Out-Null
& sc.exe stop 'WinDivert14' 2>$null | Out-Null
& sc.exe delete 'WinDivert14' 2>$null | Out-Null
Start-Sleep -Milliseconds 500
"""
    run_powershell_checked(service_script)
    if stage_finish:
        stage_finish(service_stage, "✔", "#55D67A")

    network_stage = f"zapret_restore_network_{secrets.token_hex(5)}"
    if stage_start:
        stage_start(network_stage, "IPv6 ve DNS ayarları geri yükleniyor" if restore_dns else "IPv6 ayarları geri yükleniyor")
    restore_zapret_network_settings(install_dir, restore_dns=restore_dns)
    if stage_finish:
        stage_finish(network_stage, "✔", "#55D67A")

    file_stage = f"zapret_remove_files_{secrets.token_hex(5)}"
    if stage_start:
        stage_start(file_stage, "Zapret dosyaları temizleniyor")
    if install_dir.is_dir():
        for name in (
            *ZAPRET_ALL_PAYLOAD_FILES,
            "exclude-hosts.txt",
            "exclude-ips.txt",
            "winkit_network_backup.json",
        ):
            path = install_dir / name
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass
        lua_dir = install_dir / "lua"
        if lua_dir.is_dir():
            shutil.rmtree(lua_dir, ignore_errors=True)
        try:
            install_dir.rmdir()
        except OSError:
            pass
    if stage_finish:
        stage_finish(file_stage, "✔", "#55D67A")

    return True
