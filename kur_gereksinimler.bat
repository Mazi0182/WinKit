@echo off
chcp 65001 >nul
echo ===================================================
echo [WINKIT] Gerekli Kutuphaneler Kuruluyor...
echo ===================================================
echo.

set PYTHON_CMD=python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else (
        echo [HATA] Python bulunamadi! Lutfen Python'un kurulu ve PATH'e ekli oldugundan emin olun.
        pause
        exit /b 1
    )
)

echo [*] pip guncelleniyor...
%PYTHON_CMD% -m pip install --upgrade pip

echo.
echo [*] PyQt6 ve PyInstaller kuruluyor...
%PYTHON_CMD% -m pip install -r requirements.txt

echo.
if %ERRORLEVEL% EQU 0 (
    echo [OK] Tum kutuphaneler basariyla kuruldu!
    echo Artik winkit_main.py dosyasini calistirabilir veya compile.bat ile derleyebilirsiniz.
) else (
    echo [HATA] Kurulum sirasinda bir sorun olustu.
)
echo.
pause
