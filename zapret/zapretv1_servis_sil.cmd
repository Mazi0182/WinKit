@echo off
chcp 65001 >nul
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Yönetici olarak çalýþtýrmalýsýn!
    pause
    exit /b
)
echo Zapret v1 servisi durduruluyor ve siliniyor...
sc stop "ZapretService"
sc delete "ZapretService"
sc stop "WinDivert"
sc delete "WinDivert"
sc stop "WinDivert14"
sc delete "WinDivert14"
echo Servis tamamen kaldýrýldý.
pause
