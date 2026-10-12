# =====================================================================
# Zapret v1 (winws) - Native Windows BlockCheck Engine
# Deep DPI Bypass Tester with Real Browser Simulation
# =====================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Zapret v1 - Windows BlockCheck Engine"

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
$winws = "$ScriptDir\winws.exe"
if (-not (Test-Path $winws)) {
    $winws = "$ScriptDir\zapret-v72.13\binaries\windows-x86_64\winws.exe"
}

if (-not (Test-Path $winws)) {
    Write-Host "[HATA] winws.exe bulunamadi!" -ForegroundColor Red
    Write-Host "Lutfen scripti zapret v1 klasorunde calistirin."
    Read-Host "Cikmak icin Enter'a basin..."
    exit 1
}

# Unblock files
Get-ChildItem -Path $ScriptDir -Include *.dll,*.sys,*.exe -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

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
Log-Output "    ZAPRET v1 - NATIVE WINDOWS BLOCKCHECK ENGINE               " "Cyan"
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
Write-Host " [1] Akilli & Hizli Tarama (En cok calisan Turkiye kurallari - ~15 kural)" -ForegroundColor Green
Write-Host " [2] DERIN & TAM TARAMA (TUM stratejileri tek tek dene - 45+ kural)" -ForegroundColor Magenta
Write-Host " [3] Sadece Temel Kurallar (~6 kural)" -ForegroundColor Gray
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
# ZAPRET V1 (WINWS) STRATEJİLERİ HAVUZU
# =====================================================================

$HTTP_Strategies_All = @(
    @{ Name = "HTTP: Hostcase"; Args = "--wf-tcp=80 --hostcase"; Level = "BASIC" },
    @{ Name = "HTTP: Methodeol"; Args = "--wf-tcp=80 --methodeol"; Level = "BASIC" },
    @{ Name = "HTTP: Domcase"; Args = "--wf-tcp=80 --domcase"; Level = "SMART" },
    @{ Name = "HTTP: Fake ts=-1000"; Args = "--wf-tcp=80 --dpi-desync=fake --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000"; Level = "BASIC" },
    @{ Name = "HTTP: Fake ts=-10000"; Args = "--wf-tcp=80 --dpi-desync=fake --dpi-desync-fooling=ts --dpi-desync-ts-increment=-10000"; Level = "DEEP" },
    @{ Name = "HTTP: Fake autottl=-2,3-20"; Args = "--wf-tcp=80 --dpi-desync=fake --dpi-desync-autottl=-2:3-20"; Level = "BASIC" },
    @{ Name = "HTTP: Fake autottl=-1,2-20"; Args = "--wf-tcp=80 --dpi-desync=fake --dpi-desync-autottl=-1:2-20"; Level = "SMART" },
    @{ Name = "HTTP: Fake badsum"; Args = "--wf-tcp=80 --dpi-desync=fake --dpi-desync-fooling=badsum"; Level = "SMART" },
    @{ Name = "HTTP: Fake md5sig"; Args = "--wf-tcp=80 --dpi-desync=fake --dpi-desync-fooling=md5sig"; Level = "BASIC" },
    @{ Name = "HTTP: Split2 pos=1"; Args = "--wf-tcp=80 --dpi-desync=split2 --dpi-desync-split-pos=1"; Level = "BASIC" },
    @{ Name = "HTTP: Split2 pos=host"; Args = "--wf-tcp=80 --dpi-desync=split2 --dpi-desync-split-pos=host"; Level = "SMART" },
    @{ Name = "HTTP: Disorder2 pos=1"; Args = "--wf-tcp=80 --dpi-desync=disorder2 --dpi-desync-split-pos=1"; Level = "SMART" },
    @{ Name = "HTTP: Fake ts + split2 pos=1"; Args = "--wf-tcp=80 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=1"; Level = "SMART" },
    @{ Name = "HTTP: Fake autottl + split2 pos=1"; Args = "--wf-tcp=80 --dpi-desync=fake,split2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=1"; Level = "DEEP" },
    @{ Name = "HTTP: Multisplit pos=1,host"; Args = "--wf-tcp=80 --dpi-desync=multisplit --dpi-desync-split-pos=1,host"; Level = "DEEP" },
    @{ Name = "HTTP: Multisplit pos=1,midsld"; Args = "--wf-tcp=80 --dpi-desync=multisplit --dpi-desync-split-pos=1,midsld"; Level = "DEEP" },
    @{ Name = "HTTP: Fakedsplit autottl pos=midsld"; Args = "--wf-tcp=80 --dpi-desync=fakedsplit --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=midsld"; Level = "DEEP" },
    @{ Name = "HTTP: IP Frag (ipfrag2 pos=32)"; Args = "--wf-tcp=80 --dpi-desync=ipfrag2 --dpi-desync-ipfrag-pos-tcp=32"; Level = "DEEP" }
)

$TLS_Strategies_All = @(
    # 1. Fake Timestamp (Turkiye Standarti)
    @{ Name = "TLS: Fake ts=-1000"; Args = "--wf-tcp=443 --dpi-desync=fake --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000"; Level = "BASIC" },
    @{ Name = "TLS: Fake ts=-10000"; Args = "--wf-tcp=443 --dpi-desync=fake --dpi-desync-fooling=ts --dpi-desync-ts-increment=-10000"; Level = "DEEP" },
    @{ Name = "TLS: Fake ts=-1000 + split2 pos=1"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=1"; Level = "BASIC" },
    @{ Name = "TLS: Fake ts=-1000 + split2 pos=2"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=2"; Level = "BASIC" },
    @{ Name = "TLS: Fake ts=-1000 + split2 pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=1,midsld"; Level = "BASIC" },
    @{ Name = "TLS: Fake ts=-1000 + split2 pos=2,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=2,midsld"; Level = "SMART" },
    @{ Name = "TLS: Fake ts=-1000 + disorder2 pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,disorder2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=1,midsld"; Level = "SMART" },
    @{ Name = "TLS: Fake ts=-1000 + multisplit pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,multisplit --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=1,midsld"; Level = "SMART" },
    @{ Name = "TLS: Fake ts=-1000 + repeats=2 + split2 pos=1"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-repeats=2 --dpi-desync-split-pos=1"; Level = "DEEP" },

    # 2. AutoTTL
    @{ Name = "TLS: Fake autottl=-2,3-20"; Args = "--wf-tcp=443 --dpi-desync=fake --dpi-desync-autottl=-2:3-20"; Level = "BASIC" },
    @{ Name = "TLS: Fake autottl=-1,2-20"; Args = "--wf-tcp=443 --dpi-desync=fake --dpi-desync-autottl=-1:2-20"; Level = "SMART" },
    @{ Name = "TLS: Fake autottl=-3,3-20"; Args = "--wf-tcp=443 --dpi-desync=fake --dpi-desync-autottl=-3:3-20"; Level = "DEEP" },
    @{ Name = "TLS: Fake autottl=-2,3-20 + split2 pos=1"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=1"; Level = "BASIC" },
    @{ Name = "TLS: Fake autottl=-2,3-20 + split2 pos=2"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=2"; Level = "BASIC" },
    @{ Name = "TLS: Fake autottl=-2,3-20 + split2 pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=1,midsld"; Level = "BASIC" },
    @{ Name = "TLS: Fake autottl=-2,3-20 + split2 pos=2,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=2,midsld"; Level = "SMART" },
    @{ Name = "TLS: Fake autottl=-1,2-20 + split2 pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-autottl=-1:2-20 --dpi-desync-split-pos=1,midsld"; Level = "DEEP" },
    @{ Name = "TLS: Fake autottl=-3,3-20 + split2 pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-autottl=-3:3-20 --dpi-desync-split-pos=1,midsld"; Level = "DEEP" },
    @{ Name = "TLS: Fake autottl=-2,3-20 + disorder2 pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,disorder2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=1,midsld"; Level = "SMART" },
    @{ Name = "TLS: Fake autottl=-2,3-20 + multisplit pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,multisplit --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=1,midsld"; Level = "SMART" },
    @{ Name = "TLS: Fakedsplit autottl=-2,3-20 pos=midsld"; Args = "--wf-tcp=443 --dpi-desync=fakedsplit --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=midsld"; Level = "SMART" },
    @{ Name = "TLS: Fakedsplit autottl=-2,3-20 pos=2"; Args = "--wf-tcp=443 --dpi-desync=fakedsplit --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=2"; Level = "DEEP" },

    # 3. MD5Sig & BadSum
    @{ Name = "TLS: Fake md5sig"; Args = "--wf-tcp=443 --dpi-desync=fake --dpi-desync-fooling=md5sig"; Level = "BASIC" },
    @{ Name = "TLS: Fake md5sig + split2 pos=2"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=md5sig --dpi-desync-split-pos=2"; Level = "BASIC" },
    @{ Name = "TLS: Fake md5sig + split2 pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=md5sig --dpi-desync-split-pos=1,midsld"; Level = "SMART" },
    @{ Name = "TLS: Fake badsum"; Args = "--wf-tcp=443 --dpi-desync=fake --dpi-desync-fooling=badsum"; Level = "SMART" },
    @{ Name = "TLS: Fake badsum + split2 pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=badsum --dpi-desync-split-pos=1,midsld"; Level = "DEEP" },

    # 4. Pure Split & Disorder
    @{ Name = "TLS: Split2 pos=1"; Args = "--wf-tcp=443 --dpi-desync=split2 --dpi-desync-split-pos=1"; Level = "BASIC" },
    @{ Name = "TLS: Split2 pos=2"; Args = "--wf-tcp=443 --dpi-desync=split2 --dpi-desync-split-pos=2"; Level = "BASIC" },
    @{ Name = "TLS: Split2 pos=midsld"; Args = "--wf-tcp=443 --dpi-desync=split2 --dpi-desync-split-pos=midsld"; Level = "SMART" },
    @{ Name = "TLS: Disorder2 pos=1"; Args = "--wf-tcp=443 --dpi-desync=disorder2 --dpi-desync-split-pos=1"; Level = "BASIC" },
    @{ Name = "TLS: Disorder2 pos=2"; Args = "--wf-tcp=443 --dpi-desync=disorder2 --dpi-desync-split-pos=2"; Level = "SMART" },
    @{ Name = "TLS: Disorder2 pos=midsld"; Args = "--wf-tcp=443 --dpi-desync=disorder2 --dpi-desync-split-pos=midsld"; Level = "SMART" },
    @{ Name = "TLS: Multisplit pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=multisplit --dpi-desync-split-pos=1,midsld"; Level = "SMART" },
    @{ Name = "TLS: Multisplit pos=2,midsld"; Args = "--wf-tcp=443 --dpi-desync=multisplit --dpi-desync-split-pos=2,midsld"; Level = "DEEP" },
    @{ Name = "TLS: Multidisorder pos=1,midsld"; Args = "--wf-tcp=443 --dpi-desync=multidisorder --dpi-desync-split-pos=1,midsld"; Level = "DEEP" },
    @{ Name = "TLS: IP Frag (ipfrag2 pos=32)"; Args = "--wf-tcp=443 --dpi-desync=ipfrag2 --dpi-desync-ipfrag-pos-tcp=32"; Level = "DEEP" }
)

# Filtreleme
function Filter-Strategies ($list, $level) {
    if ($level -eq "BASIC") {
        return @($list | Where-Object { $_.Level -eq "BASIC" })
    } elseif ($level -eq "SMART") {
        return @($list | Where-Object { $_.Level -in @("BASIC", "SMART") })
    } else {
        return @($list)
    }
}

$HTTP_Strategies = Filter-Strategies $HTTP_Strategies_All $ScanLevel
$TLS_Strategies  = Filter-Strategies $TLS_Strategies_All $ScanLevel

function Stop-Winws {
    Get-Process -Name "winws" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 150
}

function Invoke-BrowserCurl ($domain, $protocol) {
    $ciphers = "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384"
    $ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

    $targetArgs = @(
        "-s", "-o", "NUL",
        "-w", "%{http_code}",
        "--connect-timeout", "2",
        "--max-time", "3",
        "-A", $ua
    )

    if ($protocol -eq "HTTP") {
        $targetArgs += "http://$domain"
    } elseif ($protocol -eq "HTTPS TLS 1.2") {
        $targetArgs += @("--tlsv1.2", "--tls-max", "1.2", "--ciphers", $ciphers, "https://$domain")
    } elseif ($protocol -eq "HTTPS TLS 1.3") {
        $targetArgs += @("--tlsv1.3", "--tls-max", "1.3", "https://$domain")
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

function Run-TestEngine-Exhaustive ($domain, $proto, $stratList) {
    Log-Output "`n----------------------------------------------------------------" "DarkGray"
    Log-Output " Hedef: $domain [$proto] (Toplam $($stratList.Count) Strateji Denenecek)" "Cyan"
    Log-Output "----------------------------------------------------------------" "DarkGray"

    # 1. Bypass Olmadan Kontrol
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

        $fullArgs = "--wf-l3=ipv4 $stratArgs"
        
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = $winws
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

        Start-Sleep -Milliseconds 450

        # Gerçek Tarayıcı Curl ile Test
        $res1 = Invoke-BrowserCurl $domain $proto
        $res2 = "000"

        if (Is-SuccessCode $res1) {
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
# RAPOR VE EN İYİ ORTAK KURAL ANALİZİ
# =====================================================================
Log-Output "`n`n================================================================" "Cyan"
Log-Output "                  TUM TEST SONUCLARI OZETI                      " "Cyan"
Log-Output "================================================================" "Cyan"

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

# HTTPS Ortak Kural Analizi
$HttpsWorking = $WorkingResults | Where-Object { $_.Proto -like "HTTPS*" }
if ($HttpsWorking.Count -gt 0) {
    $TargetCount = ($Domains.Count * ((if ($TestTLS12){1}else{0}) + (if ($TestTLS13){1}else{0})))
    $Grouped = $HttpsWorking | Group-Object Name
    $Universal = $Grouped | Where-Object { $_.Count -eq $TargetCount }

    if ($Universal.Count -gt 0) {
        Log-Output "`n[***] TUM HEDEFLERDE VE PROTOKOLLERDE CALISAN EVRENSEL HTTPS STRATEJILERI:" "Green"
        foreach ($u in $Universal) {
            $stratObj = $u.Group[0]
            Log-Output "  -> $($stratObj.Name)" "Green"
            Log-Output "     Parametre: winws.exe $($stratObj.Args)" "Yellow"
        }
    } else {
        Log-Output "`n[!] Tum hedeflerde ortak calisan tek bir kural bulunamadi." "DarkYellow"
        Log-Output "    En cok calisan kurallar:" "White"
        $Grouped | Sort-Object Count -Descending | Select-Object -First 3 | ForEach-Object {
            Log-Output "  - $($_.Name) ($($_.Count)/$TargetCount basarili)" "Yellow"
        }
    }
}

# Raporu Dosyaya Kaydet
try {
    [System.IO.File]::WriteAllText($LogFile, $OutputBuffer.ToString(), [System.Text.Encoding]::UTF8)
    Log-Output "`n[+] Ayrintili test raporu kaydedildi: $LogFile" "Cyan"
} catch {
    Log-Output "`n[!] Rapor kaydedilemedi: $_" "Red"
}

Log-Output "`nTest tamamlandi. Cikmak icin bir tusa basin..." "Gray"
Read-Host
