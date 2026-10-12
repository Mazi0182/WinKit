# =====================================================================
# Zapret v2 (winws2) - Ultimate Native Windows BlockCheck Engine
# Deep DPI Bypass Tester with Real Browser Simulation
# =====================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Zapret v2 - Ultimate Windows BlockCheck Engine"

# 1. Administrator Yetkisi Kontrolü
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[!] Yonetici yetkisi gerekiyor. Yonetici olarak baslatiliyor..." -ForegroundColor Yellow
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Clear-Host

# 2. TCP Timestamps Aktif Et
netsh interface tcp set global timestamps=enabled | Out-Null

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Binary yollarını belirle
$winws2 = "$ScriptDir\winws2.exe"
if (-not (Test-Path $winws2)) {
    $winws2 = "$ScriptDir\binaries\windows-x86_64\winws2.exe"
}

if (-not (Test-Path $winws2)) {
    Write-Host "[HATA] winws2.exe bulunamadi!" -ForegroundColor Red
    Write-Host "Lutfen scripti zapret klasorunde calistirin."
    Read-Host "Cikmak icin Enter'a basin..."
    exit 1
}

# Unblock files
Get-ChildItem -Path $ScriptDir -Include *.dll,*.sys,*.exe,*.lua -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

# Lua Yolları
$LuaLib = "$ScriptDir\lua\zapret-lib.lua"
$LuaAntidpi = "$ScriptDir\lua\zapret-antidpi.lua"

$LuaInit = ""
if ((Test-Path $LuaLib) -and (Test-Path $LuaAntidpi)) {
    $LuaLibUnix = ($LuaLib -replace '\\', '/')
    $LuaAntidpiUnix = ($LuaAntidpi -replace '\\', '/')
    $LuaInit = "--lua-init=@`"$LuaLibUnix`" --lua-init=@`"$LuaAntidpiUnix`""
} else {
    Write-Host "[UYARI] Lua dosyalari (zapret-lib.lua / zapret-antidpi.lua) bulunamadi. Gomulu Lua calisacak." -ForegroundColor Yellow
}

# Log Dosyası
$LogFile = "$ScriptDir\sonuc.txt"
$OutputBuffer = New-Object System.Text.StringBuilder

function Log-Output ($text, $color = "White", $noNewline = $false) {
    if ($noNewline) {
        Write-Host -NoNewline $text -ForegroundColor $color
        [void]$OutputBuffer.Append($text)
    } else {
        Write-Host $text -ForegroundColor $color
        [void]$OutputBuffer.AppendLine($text)
    }
}

Log-Output "================================================================" "Cyan"
Log-Output "    ZAPRET v2 - ULTIMATE NATIVE WINDOWS BLOCKCHECK ENGINE       " "Cyan"
Log-Output "       Gercek Tarayici Simulasyonu & Derin DPI Analizi          " "Cyan"
Log-Output "================================================================" "Cyan"
Log-Output ""

# Kullanıcı Girişleri
$DefaultDomains = @("discord.com", "roblox.com")
Write-Host "Test edilecek domain(ler)i girin (Virgul veya boslukla ayirin)" -ForegroundColor Yellow
Write-Host "Varsayilan: $($DefaultDomains -join ' ')" -ForegroundColor DarkGray
$DomainsInput = Read-Host "Domainler"
if ([string]::IsNullOrWhiteSpace($DomainsInput)) {
    $Domains = $DefaultDomains
} else {
    $Domains = $DomainsInput -split "[\s,]+" | Where-Object { $_ -match "\S" }
}

Log-Output "Hedef Domainler: $($Domains -join ', ')" "White"
Log-Output ""

# Tarama Derinliği
Write-Host "Tarama Modu Secin:" -ForegroundColor Yellow
Write-Host " [1] Akilli & Hizli Tarama (En cok calisan Turkiye kurallari - ~20 kural)" -ForegroundColor Green
Write-Host " [2] DERIN & TAM TARAMA (TUM stratejileri tek tek dene - 60+ kural)" -ForegroundColor Magenta
Write-Host " [3] Sadece Temel Kurallar (~8 kural)" -ForegroundColor Gray
$ScanModeChoice = Read-Host "Seciminiz (1/2/3, Varsayilan: 2)"
if ($ScanModeChoice -eq "1") {
    $ScanLevel = "SMART"
} elseif ($ScanModeChoice -eq "3") {
    $ScanLevel = "BASIC"
} else {
    $ScanLevel = "DEEP"
}

Log-Output "Secilen Tarama Seviyesi: $ScanLevel" "Yellow"

$TestHTTP  = (Read-Host "HTTP (Port 80) Test edilsin mi? (E/H, Varsayilan: E)") -notmatch "^[hHnN]"
$TestTLS12 = (Read-Host "HTTPS TLS 1.2 (Port 443) Test edilsin mi? (E/H, Varsayilan: E)") -notmatch "^[hHnN]"
$TestTLS13 = (Read-Host "HTTPS TLS 1.3 (Port 443) Test edilsin mi? (E/H, Varsayilan: E)") -notmatch "^[hHnN]"

Log-Output "`nTest baslatiliyor... Lutfen bekleyin.`n" "Yellow"

# =====================================================================
# TÜM STRATEJİLER HAVUZU (ARŞA ÇIKARILAN KAPSAMLI MATRİS)
# =====================================================================

$HTTP_Strategies_All = @(
    # 1. Fake Timestamp (Turkiye Standarti)
    @{ Name = "HTTP: Fake tcp_ts=-1000"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:tcp_ts=-1000"; Level = "BASIC" },
    @{ Name = "HTTP: Fake tcp_ts=-10000"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:tcp_ts=-10000"; Level = "DEEP" },
    @{ Name = "HTTP: Fake autottl=-2,3-20"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:ip_autottl=-2,3-20"; Level = "BASIC" },
    @{ Name = "HTTP: Fake autottl=-1,2-20"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:ip_autottl=-1,2-20"; Level = "SMART" },
    @{ Name = "HTTP: Fake autottl=-3,3-20"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:ip_autottl=-3,3-20"; Level = "DEEP" },
    @{ Name = "HTTP: Fake tcp_md5"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:tcp_md5"; Level = "BASIC" },
    @{ Name = "HTTP: Fake badsum"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:badsum"; Level = "SMART" },
    @{ Name = "HTTP: Fake autottl + tcp_md5"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:ip_autottl=-2,3-20:tcp_md5"; Level = "SMART" },
    @{ Name = "HTTP: Fake tcp_ts + multisplit pos=1"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:tcp_ts=-1000 --lua-desync=multisplit:pos=1"; Level = "SMART" },
    @{ Name = "HTTP: Fake autottl + multisplit pos=1"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:ip_autottl=-2,3-20 --lua-desync=multisplit:pos=1"; Level = "DEEP" },

    # 2. HTTP Header Manipulations
    @{ Name = "HTTP: Hostcase (host)"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=http_hostcase"; Level = "BASIC" },
    @{ Name = "HTTP: Hostcase (hOSt)"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=http_hostcase:spell=hOSt"; Level = "DEEP" },
    @{ Name = "HTTP: Methodeol"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=http_methodeol"; Level = "BASIC" },
    @{ Name = "HTTP: Unixeol"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=http_unixeol"; Level = "SMART" },
    @{ Name = "HTTP: Domcase"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=http_domcase"; Level = "SMART" },

    # 3. Pure Split
    @{ Name = "HTTP: Multisplit pos=1"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=multisplit:pos=1"; Level = "BASIC" },
    @{ Name = "HTTP: Multisplit pos=host"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=multisplit:pos=host"; Level = "SMART" },
    @{ Name = "HTTP: Multisplit pos=1,host"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=multisplit:pos=1,host"; Level = "DEEP" },
    @{ Name = "HTTP: Multisplit pos=1,midsld"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=multisplit:pos=1,midsld"; Level = "DEEP" },
    @{ Name = "HTTP: Multidisorder pos=1,midsld"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=multidisorder:pos=1,midsld"; Level = "DEEP" },
    @{ Name = "HTTP: Fakedsplit autottl pos=midsld"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=fakedsplit:ip_autottl=-2,3-20:pos=midsld"; Level = "DEEP" },
    @{ Name = "HTTP: Send IP Frag (send:ipfrag)"; Args = "--wf-tcp-out=80 --payload=http_req --lua-desync=send:ipfrag"; Level = "DEEP" }
)

$TLS_Strategies_All = @(
    # --- GRUP 1: TURKIYE ISS EN ETKILI TEMEL KURALLAR (TCP TIMESTAMP & AUTOTTL) ---
    @{ Name = "TLS: Fake tcp_ts=-1000";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000";
       Level = "BASIC" },

    @{ Name = "TLS: Fake tcp_ts=-10000";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-10000";
       Level = "DEEP" },

    @{ Name = "TLS: Fake tcp_ts=-1000 + multisplit pos=2";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=multisplit:pos=2";
       Level = "BASIC" },

    @{ Name = "TLS: Fake tcp_ts=-1000 + multisplit pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=multisplit:pos=1,midsld";
       Level = "BASIC" },

    @{ Name = "TLS: Fake tcp_ts=-1000 + multisplit pos=2,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=multisplit:pos=2,midsld";
       Level = "SMART" },

    @{ Name = "TLS: Fake tcp_ts=-1000 + split pos=1";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=split:pos=1";
       Level = "SMART" },

    @{ Name = "TLS: Fake tcp_ts=-1000 + multidisorder pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=multidisorder:pos=1,midsld";
       Level = "SMART" },

    @{ Name = "TLS: Fake tcp_ts=-1000 + tls_mod=rnd,dupsid";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000:tls_mod=rnd,dupsid";
       Level = "SMART" },

    @{ Name = "TLS: Fake tcp_ts=-1000 + tls_mod=rnd,dupsid,padencap:repeats=2";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000:tls_mod=rnd,dupsid,padencap:repeats=2";
       Level = "SMART" },

    @{ Name = "TLS: Fake tcp_ts=-1000 + tls_mod=rnd,rndsni,dupsid,padencap:repeats=2";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000:tls_mod=rnd,rndsni,dupsid,padencap:repeats=2";
       Level = "DEEP" },

    # --- GRUP 2: AUTOTTL & TTL MANIPULATION ---
    @{ Name = "TLS: Fake autottl=-2,3-20";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-2,3-20";
       Level = "BASIC" },

    @{ Name = "TLS: Fake autottl=-1,2-20";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-1,2-20";
       Level = "SMART" },

    @{ Name = "TLS: Fake autottl=-3,3-20";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-3,3-20";
       Level = "DEEP" },

    @{ Name = "TLS: Fake autottl=-2,3-20 + dupsid/padencap + multisplit midsld (repeats=2)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-2,3-20:tls_mod=rnd,dupsid,padencap:repeats=2 --lua-desync=multisplit:pos=1,midsld";
       Level = "BASIC" },

    @{ Name = "TLS: Fake autottl=-2,3-20 + dupsid + multisplit pos=2";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-2,3-20:tls_mod=rnd,dupsid --lua-desync=multisplit:pos=2";
       Level = "BASIC" },

    @{ Name = "TLS: Fake autottl=-2,3-20 + split pos=1";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-2,3-20:tls_mod=rnd,dupsid --lua-desync=split:pos=1";
       Level = "SMART" },

    @{ Name = "TLS: Fake autottl=-1,2-20 + multisplit pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-1,2-20:tls_mod=rnd,dupsid,padencap:repeats=2 --lua-desync=multisplit:pos=1,midsld";
       Level = "DEEP" },

    @{ Name = "TLS: Fake autottl=-3,3-20 + multisplit pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-3,3-20:tls_mod=rnd,dupsid,padencap:repeats=2 --lua-desync=multisplit:pos=1,midsld";
       Level = "DEEP" },

    @{ Name = "TLS: Fake autottl=-2,3-20 + multidisorder pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-2,3-20:tls_mod=rnd,dupsid --lua-desync=multidisorder:pos=1,midsld";
       Level = "SMART" },

    @{ Name = "TLS: Fake autottl=-2,3-20 + multidisorder pos=2,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-2,3-20:tls_mod=rnd,dupsid --lua-desync=multidisorder:pos=2,midsld";
       Level = "DEEP" },

    @{ Name = "TLS: Fakedsplit autottl=-2,3-20 pos=midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fakedsplit:ip_autottl=-2,3-20:pos=midsld";
       Level = "SMART" },

    @{ Name = "TLS: Fakedsplit autottl=-2,3-20 pos=2";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fakedsplit:ip_autottl=-2,3-20:pos=2";
       Level = "DEEP" },

    @{ Name = "TLS: Fakedsplit autottl=-2,3-20 pos=host";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fakedsplit:ip_autottl=-2,3-20:pos=host";
       Level = "DEEP" },

    @{ Name = "TLS: Hostfakesplit autottl=-2,3-20 midhost=midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=hostfakesplit:ip_autottl=-2,3-20:midhost=midsld";
       Level = "DEEP" },

    # --- GRUP 3: TCP MD5 & BAD CHECKSUM FOOLING ---
    @{ Name = "TLS: Fake tcp_md5";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_md5";
       Level = "BASIC" },

    @{ Name = "TLS: Fake tcp_md5 + multisplit pos=2";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_md5:tls_mod=rnd,dupsid:repeats=1 --lua-desync=multisplit:pos=2";
       Level = "BASIC" },

    @{ Name = "TLS: Fake tcp_md5 + multisplit pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_md5:tls_mod=rnd,dupsid:repeats=2 --lua-desync=multisplit:pos=1,midsld";
       Level = "SMART" },

    @{ Name = "TLS: Fake tcp_md5 + multidisorder pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_md5:tls_mod=rnd,dupsid --lua-desync=multidisorder:pos=1,midsld";
       Level = "DEEP" },

    @{ Name = "TLS: Fake 0x00:tcp_md5 + Fake tls:tcp_md5 + multisplit pos=2 (Zapret2 Dual Fake)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=0x00000000:tcp_md5:repeats=1 --lua-desync=fake:blob=fake_default_tls:tcp_md5:tls_mod=rnd,dupsid:repeats=1 --lua-desync=multisplit:pos=2";
       Level = "SMART" },

    @{ Name = "TLS: Fake 0x00:tcp_md5 + Fake tls:tcp_md5 + multisplit pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=0x00000000:tcp_md5:repeats=1 --lua-desync=fake:blob=fake_default_tls:tcp_md5:tls_mod=rnd,dupsid:repeats=1 --lua-desync=multisplit:pos=1,midsld";
       Level = "DEEP" },

    @{ Name = "TLS: Fake badsum";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:badsum";
       Level = "SMART" },

    @{ Name = "TLS: Fake badsum + multisplit pos=2";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:badsum:tls_mod=rnd,dupsid --lua-desync=multisplit:pos=2";
       Level = "SMART" },

    @{ Name = "TLS: Fake badsum + multisplit pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:badsum:tls_mod=rnd,dupsid,padencap:repeats=2 --lua-desync=multisplit:pos=1,midsld";
       Level = "SMART" },

    @{ Name = "TLS: Fake badsum + multidisorder pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:badsum:tls_mod=rnd,dupsid --lua-desync=multidisorder:pos=1,midsld";
       Level = "DEEP" },

    @{ Name = "TLS: Fakedsplit badsum pos=midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fakedsplit:badsum:pos=midsld";
       Level = "DEEP" },

    @{ Name = "TLS: Hostfakesplit badsum midhost=midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=hostfakesplit:badsum:midhost=midsld";
       Level = "DEEP" },

    # --- GRUP 4: FAKE SNI CLOAKING ---
    @{ Name = "TLS: Fake sni=google.com + tcp_ts=-1000";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tls_mod=sni=google.com:tcp_ts=-1000";
       Level = "SMART" },

    @{ Name = "TLS: Fake sni=iana.org + tcp_ts=-1000";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tls_mod=sni=iana.org:tcp_ts=-1000";
       Level = "DEEP" },

    @{ Name = "TLS: Fake sni=cloudflare.com + tcp_ts=-1000";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tls_mod=sni=cloudflare.com:tcp_ts=-1000";
       Level = "DEEP" },

    @{ Name = "TLS: Fake sni=google.com + autottl=-2,3-20 + multisplit pos=1,midsld";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tls_mod=sni=google.com,dupsid:ip_autottl=-2,3-20 --lua-desync=multisplit:pos=1,midsld";
       Level = "DEEP" },

    @{ Name = "TLS: Fake sni=google.com + badsum + multisplit pos=2";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tls_mod=sni=google.com,dupsid:badsum --lua-desync=multisplit:pos=2";
       Level = "DEEP" },

    # --- GRUP 5: PURE SEGMENTATION & REORDERING (SAHTE PAKETSIZ SAF BOLME) ---
    @{ Name = "TLS: Multisplit only (pos=1)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multisplit:pos=1";
       Level = "BASIC" },

    @{ Name = "TLS: Multisplit only (pos=2)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multisplit:pos=2";
       Level = "BASIC" },

    @{ Name = "TLS: Multisplit only (pos=1,midsld)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multisplit:pos=1,midsld";
       Level = "BASIC" },

    @{ Name = "TLS: Multisplit only (pos=2,midsld)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multisplit:pos=2,midsld";
       Level = "SMART" },

    @{ Name = "TLS: Multisplit only (pos=midsld)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multisplit:pos=midsld";
       Level = "SMART" },

    @{ Name = "TLS: Multisplit only (pos=1,host,midsld+1,-10)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multisplit:pos=1,host,midsld+1,-10";
       Level = "DEEP" },

    @{ Name = "TLS: Multidisorder only (pos=1,midsld)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multidisorder:pos=1,midsld";
       Level = "SMART" },

    @{ Name = "TLS: Multidisorder only (pos=2,midsld)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multidisorder:pos=2,midsld";
       Level = "DEEP" },

    @{ Name = "TLS: Multidisorder only (pos=midsld)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multidisorder:pos=midsld";
       Level = "DEEP" },

    @{ Name = "TLS: Multisplit pos=1,midsld:seqovl=1";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multisplit:pos=1,midsld:seqovl=1";
       Level = "DEEP" },

    @{ Name = "TLS: Multisplit pos=2,midsld:seqovl=1";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multisplit:pos=2,midsld:seqovl=1";
       Level = "DEEP" },

    @{ Name = "TLS: Multidisorder pos=1,midsld:seqovl=1";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multidisorder:pos=1,midsld:seqovl=1";
       Level = "DEEP" },

    @{ Name = "TLS: TCP Segmentation (tcpseg pos=0,-1:seqovl=1 + drop)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=tcpseg:pos=0,-1:seqovl=1 --lua-desync=drop";
       Level = "DEEP" },

    @{ Name = "TLS: TCP Segmentation (tcpseg pos=1,midsld:seqovl=1 + drop)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=tcpseg:pos=1,midsld:seqovl=1 --lua-desync=drop";
       Level = "DEEP" },

    @{ Name = "TLS: Advanced Lua Pattern Desync (seqovl=#pat + drop)";
       Args = '--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=luaexec:code=\"desync.pat=tls_mod(fake_default_tls,\''rnd,rndsni,dupsid,padencap\'',desync.reasm_data)\" --lua-desync=tcpseg:pos=0,-1:seqovl=#pat:seqovl_pattern=pat --lua-desync=drop';
       Level = "DEEP" },

    @{ Name = "TLS: IP Fragmentation (send:ipfrag)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=send:ipfrag";
       Level = "DEEP" },

    @{ Name = "TLS: IP Fragmentation (send:ipfrag:ipfrag_pos_tcp=32)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=send:ipfrag:ipfrag_pos_tcp=32";
       Level = "DEEP" },

    # --- GRUP 6: SYN / SYNDATA / SYNACK TAMPERING ---
    @{ Name = "TLS: Syndata tcp_ts=-1000";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=syndata:blob=fake_default_tls:tcp_ts=-1000";
       Level = "SMART" },

    @{ Name = "TLS: Syndata tcp_ts=-1000 + multisplit pos=2";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=syndata:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=multisplit:pos=2";
       Level = "DEEP" },

    @{ Name = "TLS: Synack";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=synack";
       Level = "DEEP" },

    @{ Name = "TLS: Synack Split (mode=synack)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=synack_split:mode=synack";
       Level = "DEEP" },

    @{ Name = "TLS: Synack Split (mode=acksyn)";
       Args = "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=synack_split:mode=acksyn";
       Level = "DEEP" }
)

# Filtreleme
if ($ScanLevel -eq "BASIC") {
    $HTTP_Strategies = $HTTP_Strategies_All | Where-Object { $_.Level -eq "BASIC" }
    $TLS_Strategies  = $TLS_Strategies_All  | Where-Object { $_.Level -eq "BASIC" }
} elseif ($ScanLevel -eq "SMART") {
    $HTTP_Strategies = $HTTP_Strategies_All | Where-Object { $_.Level -in "BASIC", "SMART" }
    $TLS_Strategies  = $TLS_Strategies_All  | Where-Object { $_.Level -in "BASIC", "SMART" }
} else {
    $HTTP_Strategies = $HTTP_Strategies_All
    $TLS_Strategies  = $TLS_Strategies_All
}

function Stop-Winws {
    Get-Process winws2 -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Milliseconds 150
}

# Gerçek Tarayıcı Curl İstek Fonksiyonu
function Invoke-BrowserCurl ($domain, $proto) {
    $baseArgs = @(
        "-s",
        "-o", "NUL",
        "-w", "%{http_code}",
        "-k",
        "--connect-timeout", "3",
        "-m", "5",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "-H", "Accept-Language: tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "-H", "Sec-Fetch-Dest: document",
        "-H", "Sec-Fetch-Mode: navigate",
        "-H", "Sec-Fetch-Site: none",
        "-H", "Sec-Fetch-User: ?1",
        "-H", "Upgrade-Insecure-Requests: 1"
    )

    if ($proto -eq "HTTP") {
        $targetArgs = $baseArgs + @("http://$domain")
    } elseif ($proto -eq "HTTPS TLS 1.2") {
        $targetArgs = $baseArgs + @("--tlsv1.2", "--tls-max", "1.2", "https://$domain")
    } elseif ($proto -eq "HTTPS TLS 1.3") {
        $targetArgs = $baseArgs + @("--tlsv1.3", "--tls-max", "1.3", "https://$domain")
    } else {
        $targetArgs = $baseArgs + @("https://$domain")
    }

    try {
        $res = & curl.exe $targetArgs
        if ([string]::IsNullOrWhiteSpace($res)) { return "000" }
        return $res.Trim()
    } catch {
        return "000"
    }
}

function Is-SuccessCode ($code) {
    return ($code -match "^(200|204|301|302|303|304|307|308|400|401|403|404|405|500|502|503|530)$")
}

# TAM VE KAPSAMLI TEST DÖNGÜSÜ (HEPSİNİ TEK TEK DENER)
function Run-TestEngine-Exhaustive ($domain, $proto, $stratList) {
    Log-Output "`n----------------------------------------------------------------" "DarkGray"
    Log-Output " Hedef: $domain [$proto] (Toplam $($stratList.Count) Strateji Denenecek)" "Cyan"
    Log-Output "----------------------------------------------------------------" "DarkGray"

    # 1. Bypass Olmadan Önce Kontrol Et
    Stop-Winws
    $noBypass = Invoke-BrowserCurl $domain $proto

    if (Is-SuccessCode $noBypass) {
        Log-Output "[+] Bypass OLMADAN zaten aciliyor (HTTP Kodu: $noBypass)" "Green"
    } else {
        Log-Output "[-] Engel Algilandi (Bypass kapali HTTP Kodu: $noBypass)" "DarkYellow"
    }

    $resultsForTarget = @()
    $stratIndex = 0
    $totalStrats = $stratList.Count
    $workingCount = 0

    foreach ($strat in $stratList) {
        $stratIndex++
        $stratName = $strat.Name
        $stratArgs = $strat.Args

        Log-Output -text "  [$stratIndex/$totalStrats] $stratName ... " -color "DarkGray" -noNewline $true
        Stop-Winws

        $fullArgs = "--wf-l3=ipv4 $LuaInit $stratArgs"
        
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = $winws2
        $pinfo.Arguments = $fullArgs
        $pinfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
        $pinfo.CreateNoWindow = $true
        
        try {
            $proc = [System.Diagnostics.Process]::Start($pinfo)
        } catch {
            Log-Output "Calistirilamadi! ($($_.Exception.Message))" "Red"
            $resultsForTarget += [PSCustomObject]@{
                Domain = $domain
                Proto  = $proto
                Name   = $stratName
                Args   = $stratArgs
                Status = "ERROR"
                Code   = "ERR"
                Level  = $strat.Level
            }
            continue
        }

        # Sürücü ve motorun oturması için bekleme
        Start-Sleep -Milliseconds 450

        # Gerçek Tarayıcı Curl ile Test Et
        $res1 = Invoke-BrowserCurl $domain $proto
        $res2 = "000"

        if (Is-SuccessCode $res1) {
            # 1. istek başarılıysa 2. doğrulama isteği gönder (kararlılık kontrolü)
            Start-Sleep -Milliseconds 200
            $res2 = Invoke-BrowserCurl $domain $proto
        }

        Stop-Winws

        if ((Is-SuccessCode $res1) -and (Is-SuccessCode $res2)) {
            $workingCount++
            Log-Output "CALISTI! (HTTP: $res1, $res2)" "Green"
            $resultsForTarget += [PSCustomObject]@{
                Domain = $domain
                Proto  = $proto
                Name   = $stratName
                Args   = $stratArgs
                Status = "OK"
                Code   = "$res1, $res2"
                Level  = $strat.Level
            }
        } else {
            Log-Output "Basarisiz ($res1, $res2)" "DarkGray"
            $resultsForTarget += [PSCustomObject]@{
                Domain = $domain
                Proto  = $proto
                Name   = $stratName
                Args   = $stratArgs
                Status = "FAIL"
                Code   = "$res1, $res2"
                Level  = $strat.Level
            }
        }
    }

    $summaryColor = if ($workingCount -gt 0) { "Green" } else { "Red" }
    Log-Output "`n>>> $domain [$proto] Sonuclari: $workingCount / $totalStrats strateji CALISTI." $summaryColor
    return $resultsForTarget
}

$GlobalResults = @()

foreach ($dom in $Domains) {
    if ($TestHTTP) {
        $GlobalResults += Run-TestEngine-Exhaustive $dom "HTTP" $HTTP_Strategies
    }
    if ($TestTLS12) {
        $GlobalResults += Run-TestEngine-Exhaustive $dom "HTTPS TLS 1.2" $TLS_Strategies
    }
    if ($TestTLS13) {
        $GlobalResults += Run-TestEngine-Exhaustive $dom "HTTPS TLS 1.3" $TLS_Strategies
    }
}

Stop-Winws

# =====================================================================
# RAPOR VE EN İYİ ORTAK KURAL ANALİZİ (INTERSECTION)
# =====================================================================
Log-Output "`n`n================================================================" "Cyan"
Log-Output "                  TUM TEST SONUCLARI OZETI                      " "Cyan"
Log-Output "================================================================" "Cyan"

# Sadece çalışanları özetle
$WorkingResults = $GlobalResults | Where-Object { $_.Status -eq "OK" }

if ($WorkingResults.Count -gt 0) {
    Log-Output "`n[+] CALISAN STRATEJILER TABLOSU:" "Green"
    $SummaryTable = $WorkingResults | Select-Object Domain, Proto, Code, Name | Format-Table -AutoSize | Out-String
    Log-Output $SummaryTable "White"
} else {
    Log-Output "`n[!] Hicbir strateji basarili olamadi." "Red"
}

Log-Output "================================================================" "Cyan"
Log-Output "         ORTAK KURAL KESISIMI (COMMON WORKING STRATEGIES)       " "Cyan"
Log-Output "================================================================" "Cyan"

# 1. HTTPS Ortak Kural Analizi
# Her HTTPS hedefinde (tüm domainler ve TLS 1.2/1.3) çalışan stratejileri bul
$DistinctHttpsTargets = $GlobalResults | Where-Object { $_.Proto -like "HTTPS*" } | Select-Object -Property Domain, Proto -Unique
$TotalHttpsTargetsCount = $DistinctHttpsTargets.Count

$TLS_OK = $GlobalResults | Where-Object { $_.Proto -like "HTTPS*" -and $_.Status -eq "OK" }
$CommonTLS = @()

if ($TLS_OK -and $TotalHttpsTargetsCount -gt 0) {
    $TLS_Grouped = $TLS_OK | Group-Object -Property Args | Where-Object { $_.Count -eq $TotalHttpsTargetsCount } | Sort-Object Count -Descending
    if ($TLS_Grouped.Count -gt 0) {
        $CommonTLS = $TLS_Grouped
    } else {
        # Eğer tümünde çalışan yoksa en çok domainde çalışanı bul
        $CommonTLS = $TLS_OK | Group-Object -Property Args | Sort-Object Count -Descending
    }
}

# 2. HTTP Ortak Kural Analizi
$DistinctHttpTargets = $GlobalResults | Where-Object { $_.Proto -eq "HTTP" } | Select-Object -Property Domain -Unique
$TotalHttpTargetsCount = $DistinctHttpTargets.Count

$HTTP_OK = $GlobalResults | Where-Object { $_.Proto -eq "HTTP" -and $_.Status -eq "OK" }
$CommonHTTP = @()

if ($HTTP_OK -and $TotalHttpTargetsCount -gt 0) {
    $HTTP_Grouped = $HTTP_OK | Group-Object -Property Args | Where-Object { $_.Count -eq $TotalHttpTargetsCount } | Sort-Object Count -Descending
    if ($HTTP_Grouped.Count -gt 0) {
        $CommonHTTP = $HTTP_Grouped
    } else {
        $CommonHTTP = $HTTP_OK | Group-Object -Property Args | Sort-Object Count -Descending
    }
}

$BestTLSArg = $null
$BestTLSDesc = $null

if ($CommonTLS.Count -gt 0) {
    $BestTLSItem = $CommonTLS[0]
    $BestTLSArg = $BestTLSItem.Name
    $BestTLSDesc = $BestTLSItem.Group[0].Name
    $BestTLSCount = $BestTLSItem.Count

    Log-Output "`n[+] EN IYI HTTPS ORTAK KURALI ($BestTLSCount / $TotalHttpsTargetsCount hedefte calisti):" "Green"
    Log-Output "    Strateji : $BestTLSDesc" "White"
    Log-Output "    Parametre: $BestTLSArg" "DarkCyan"

    if ($CommonTLS.Count -gt 1) {
        Log-Output "`n[i] Diger Guclu Calisan HTTPS Alternatifleri:" "Yellow"
        for ($i = 1; $i -lt [Math]::Min($CommonTLS.Count, 5); $i++) {
            $alt = $CommonTLS[$i]
            Log-Output "    ($i) $($alt.Group[0].Name) [$($alt.Count) hedef]" "DarkGray"
        }
    }
} else {
    Log-Output "`n[!] Hicbir calisan HTTPS kurali bulunamadi." "Red"
}

$BestHTTPArg = $null
$BestHTTPDesc = $null

if ($CommonHTTP.Count -gt 0) {
    $BestHTTPItem = $CommonHTTP[0]
    $BestHTTPArg = $BestHTTPItem.Name
    $BestHTTPDesc = $BestHTTPItem.Group[0].Name
    $BestHTTPCount = $BestHTTPItem.Count

    Log-Output "`n[+] EN IYI HTTP ORTAK KURALI ($BestHTTPCount / $TotalHttpTargetsCount hedefte calisti):" "Green"
    Log-Output "    Strateji : $BestHTTPDesc" "White"
    Log-Output "    Parametre: $BestHTTPArg" "DarkCyan"
}

# HAZIR KOMUTLAR ÜRET
if ($BestTLSArg) {
    $WinHttpArg = if ($BestHTTPArg) { $BestHTTPArg } else { "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:tcp_ts=-1000" }
    $WinTlsArg  = $BestTLSArg

    Log-Output "`n----------------------------------------------------------------" "DarkGray"
    Log-Output "1. WINDOWS (winws2.exe) ICIN KULLANIMA HAZIR KOMUT:" "Green"
    Log-Output "----------------------------------------------------------------" "DarkGray"

    $WindowsCommand = "winws2.exe --wf-l3=ipv4 $LuaInit $WinHttpArg --new $WinTlsArg"
    Log-Output $WindowsCommand "Cyan"

    Log-Output "`n----------------------------------------------------------------" "DarkGray"
    Log-Output "2. OPENWRT (/opt/zapret2/config) ICIN KULLANIMA HAZIR NFQWS2_OPT:" "Green"
    Log-Output "----------------------------------------------------------------" "DarkGray"

    # OpenWrt nfqws2 formatına dönüştür (wf parametrelerini temizle, filter-tcp ve HOSTLIST ekle)
    $NfqHttp = $WinHttpArg -replace "--wf-tcp-out=\d+\s*", ""
    $NfqTls  = $WinTlsArg  -replace "--wf-tcp-out=\d+\s*", ""

    $OpenWrtConfig = @"
MODE=nfqws2
MODE_HTTP=1
MODE_HTTPS=1
MODE_QUIC=0
MODE_FILTER=autohostlist
DISABLE_IPV6=1

NFQWS2_OPT="
--filter-tcp=80 --filter-l7=http <HOSTLIST> --out-range=-d5 $NfqHttp --new
--filter-tcp=443 --filter-l7=tls <HOSTLIST> --out-range=-d8 $NfqTls
"
"@
    Log-Output $OpenWrtConfig "Yellow"
}

# Dosyaya Kaydet
$OutputBuffer.ToString() | Out-File -FilePath $LogFile -Encoding UTF8 -Force
Log-Output "`n================================================================" "Cyan"
Log-Output "Tum detayli sonuclar ve rapor '$LogFile' dosyasina kaydedildi." "Green"
Log-Output "Test tamamlandi." "Cyan"
Read-Host "Cikmak icin Enter'a basin..."
