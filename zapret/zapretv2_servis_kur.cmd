@echo off
chcp 65001 >nul
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Yönetici olarak çalýþtýrman lazým!
    pause
    exit /b
)
cd /d "%~dp0"
echo Zapret v2 servisi kuruluyor...
sc stop "ZapretService" >nul 2>&1
sc delete "ZapretService" >nul 2>&1
if exist "%~dp0lua\zapret-lib.lua" (
    sc create "ZapretService" binPath= "\"%~dp0winws2.exe\" --wf-l3=ipv4 --wf-tcp-out=80,443 --wf-udp-out=443 --lua-init=\"@%~dp0lua\zapret-lib.lua\" --lua-init=\"@%~dp0lua\zapret-antidpi.lua\" --hostlist-exclude=\"%~dp0exclude.txt\" --payload=http_req --lua-desync=http_hostcase --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000:tls_mod=rnd,dupsid --lua-desync=multisplit:pos=1,midsld" start= auto displayname= "Zapret DPI Bypass"
) else (
    sc create "ZapretService" binPath= "\"%~dp0winws2.exe\" --wf-l3=ipv4 --wf-tcp-out=80,443 --wf-udp-out=443 --hostlist-exclude=\"%~dp0exclude.txt\" --payload=http_req --lua-desync=http_hostcase --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=multisplit:pos=1,midsld" start= auto displayname= "Zapret DPI Bypass"
)
if %errorLevel% equ 0 (
    echo Servis kuruldu, baþlatýlýyor...
    sc start "ZapretService"
) else (
    echo Kurulum baþarýsýz.
)
pause