@echo off
chcp 65001 >nul
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Yonetici olarak calistirilsin!
    pause
    exit /b
)
cd /d "%~dp0"
echo Zapret v1 servisi kuruluyor...
sc stop "ZapretService" >nul 2>&1
sc delete "ZapretService" >nul 2>&1
sc create "ZapretService" binPath= "\"%~dp0winws.exe\" --wf-tcp=80,443 --wf-udp=443 --hostlist-exclude=\"%~dp0exclude.txt\" --hostspell=hoSt --dpi-desync=fake,split2 --dpi-desync-split-pos=2 --dpi-desync-ttl=6" start= auto displayname= "Zapret DPI Bypass"
if %errorLevel% equ 0 (
    echo Servis kuruldu, baslatiliyor...
    sc start "ZapretService"
) else (
    echo Kurulum basarisiz.
)
pause
