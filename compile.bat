@echo off
chcp 65001 >nul
echo ===================================================
echo   WinKit PyQt6 Derleme Scripti (PyInstaller)
echo ===================================================
echo.

set PYTHON_CMD=pyinstaller
where pyinstaller >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\Scripts\pyinstaller.exe" (
        set PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python312\Scripts\pyinstaller.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m PyInstaller
    )
)

echo Derleyici: %PYTHON_CMD%
echo.

%PYTHON_CMD% --clean --onefile --noconsole --uac-admin ^
    --name="winkit" ^
    --icon="winkit_logo.ico" ^
    --add-data "winkit_logo.ico;." ^
    --add-data "winkit_logo.png;." ^
    --add-data "7z.exe;." ^
    --add-data "7z.dll;." ^
    --add-data "oscdimg.exe;." ^
    --add-data "OOSU10.exe;." ^
    --add-data "ooshutup10.cfg;." ^
    --add-data "zapret;zapret" ^
    --add-data "core;core" ^
    --add-data "gui;gui" ^
    --hidden-import="PyQt6" ^
    --hidden-import="PyQt6.QtCore" ^
    --hidden-import="PyQt6.QtGui" ^
    --hidden-import="PyQt6.QtWidgets" ^
    --hidden-import="core" ^
    --hidden-import="core.constants" ^
    --hidden-import="core.privileges" ^
    --hidden-import="core.registry" ^
    --hidden-import="core.shutup10" ^
    --hidden-import="core.iso" ^
    --hidden-import="core.edgewebview" ^
    --hidden-import="core.scanner" ^
    --hidden-import="core.appx_manager" ^
    --hidden-import="core.defender" ^
    --hidden-import="core.tweaks" ^
    --hidden-import="core.key_remap" ^
    --hidden-import="core.context_menu" ^
    --hidden-import="core.system" ^
    --hidden-import="core.debloater" ^
    --hidden-import="core.anti_dpi" ^
    --hidden-import="core.dpi_tester" ^
    --hidden-import="core.restore" ^
    --hidden-import="core.licensing" ^
    --hidden-import="core.cli" ^
    --hidden-import="core.orchestrator" ^
    --hidden-import="gui" ^
    --hidden-import="gui.styles" ^
    --hidden-import="gui.widgets" ^
    --hidden-import="gui.dialogs" ^
    --hidden-import="gui.app" ^
    winkit_main.py

echo.
if %ERRORLEVEL% EQU 0 (
    echo [OK] Derleme basariyla tamamlandi! dist\winkit.exe olusturuldu.
) else (
    echo [HATA] Derleme sirasinda hata olustu.
)
echo.
pause