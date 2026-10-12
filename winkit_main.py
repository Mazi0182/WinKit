"""
WinKit - Next-Gen Windows 11 Optimizer & Debloater
Unified Entry Point for GUI and CLI Operations.
"""

import sys
import os
import ctypes
import subprocess
from pathlib import Path

# Ensure project root directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtCore import Qt, QCoreApplication, QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QFont

from core.system import is_admin, deploy_winkit_silent, repair_stale_start_pin_policy
from core.privileges import enable_process_privileges
from core.cli import WinKitCliDebloatController, ensure_cli_console
from gui.styles import QSS
from gui.app import WinKitApp


def elevate_privileges():
    """UAC yetki yükseltme kontrolü ve yeniden başlatma."""
    if not is_admin():
        try:
            executable = sys.executable
            if not getattr(sys, "frozen", False) and executable.lower().endswith("python.exe"):
                pythonw = executable.replace("python.exe", "pythonw.exe")
                if os.path.exists(pythonw):
                    executable = pythonw
            args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
            parameters = subprocess.list2cmdline(args)
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, parameters, None, 1)
            if int(ret) > 32:
                sys.exit(0)
        except Exception:
            sys.exit(1)


def main():
    elevate_privileges()
    enable_process_privileges()
    deploy_winkit_silent()

    cli_args = [arg.lower() for arg in sys.argv[1:]]
    is_cli_requested = any(
        arg in cli_args
        for arg in (
            "-cli", "--cli", "/cli",
            "-test", "--test", "/test",
            "-test-stop", "--test-stop", "/test-stop",
            "-test-purge", "--test-purge", "/test-purge",
            "-test-purge-full", "--test-purge-full", "/test-purge-full",
            "-test-def-disable", "--test-def-disable", "/test-def-disable",
            "-test-def-purge", "--test-def-purge", "/test-def-purge",
            "-test-def-purge-full", "--test-def-purge-full", "/test-def-purge-full",
            "-test-restore", "--test-restore", "/test-restore",
            "-test-dns-reset", "--test-dns-reset", "/test-dns-reset",
            "--exec-script", "-exec-script",
            "--debloat", "-debloat", "/debloat",
            "--help", "-h", "/?",
        )
    )

    if is_cli_requested:
        ensure_cli_console()
        ctrl = WinKitCliDebloatController()
        if any(arg in cli_args for arg in ("-test-dns-reset", "--test-dns-reset", "/test-dns-reset")):
            from core.anti_dpi import restore_zapret_network_settings
            restore_zapret_network_settings(Path(r"C:\ProgramData\zapret"), restore_dns=True)
            print("DNS and DoH policies successfully reset to DHCP defaults.")
            sys.exit(0)
        if any(arg in cli_args for arg in ("--exec-script", "-exec-script")):
            for i, a in enumerate(sys.argv[1:]):
                if a.lower() in ("--exec-script", "-exec-script") and i + 1 < len(sys.argv) - 1:
                    sc_path = sys.argv[i + 2]
                    from core.privileges import run_powershell_as_system
                    ret, out = run_powershell_as_system(Path(sc_path).read_text(encoding="utf-8"))
                    print(out)
                    sys.exit(ret)
        if any(arg in cli_args for arg in ("-test-def-disable", "--test-def-disable", "/test-def-disable")):
            sys.exit(ctrl.run_test_def_disable_only())
        if any(arg in cli_args for arg in ("-test-def-purge", "--test-def-purge", "/test-def-purge")):
            sys.exit(ctrl.run_test_def_purge_only())
        if any(arg in cli_args for arg in ("-test-def-purge-full", "--test-def-purge-full", "/test-def-purge-full")):
            sys.exit(ctrl.run_test_def_purge_full_only())
        if any(arg in cli_args for arg in ("-test-stop", "--test-stop", "/test-stop")):
            sys.exit(ctrl.run_test_stop_profile())
        if any(arg in cli_args for arg in ("-test-purge-full", "--test-purge-full", "/test-purge-full")):
            sys.exit(ctrl.run_test_purge_full_profile())
        if any(arg in cli_args for arg in ("-test-purge", "--test-purge", "/test-purge")):
            sys.exit(ctrl.run_test_purge_profile())
        if any(arg in cli_args for arg in ("-test-restore", "--test-restore", "/test-restore")):
            sys.exit(ctrl.run_test_restore_profile())
        if any(arg in cli_args for arg in ("-test", "--test", "/test")):
            sys.exit(ctrl.run_test_profile())
        res = ctrl.run_interactive_menu()
        if res != "LAUNCH_GUI":
            sys.exit(0)

    # GUI moduna geçerken konsol penceresini serbest bırak
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WinKit.Optimizer.App")
    except Exception:
        pass

    QCoreApplication.setApplicationName("WinKit")
    QCoreApplication.setOrganizationName("WinKit")

    repair_stale_start_pin_policy()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("WinKit")
    app.setApplicationDisplayName("WinKit")

    base_dirs = []
    if getattr(sys, "frozen", False):
        base_dirs.append(getattr(sys, "_MEIPASS", ""))
        base_dirs.append(os.path.dirname(sys.executable))
    base_dirs.append(str(BASE_DIR))
    base_dirs.append(os.getcwd())

    app_icon = None
    icon_path_found = None
    for name in ("winkit_logo.ico", "winkit_logo.png", "ico.ico"):
        for b_dir in base_dirs:
            if not b_dir:
                continue
            cand = os.path.join(b_dir, name)
            if os.path.isfile(cand):
                test_icon = QIcon(cand)
                if not test_icon.isNull():
                    app_icon = test_icon
                    icon_path_found = cand
                    break
        if app_icon is not None and not app_icon.isNull():
            break

    if app_icon is not None and not app_icon.isNull():
        app.setWindowIcon(app_icon)

    ui_font = QFont("Segoe UI Variable Text", 10)
    ui_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    ui_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(ui_font)
    app.setStyleSheet(QSS)

    window = WinKitApp()
    if app_icon is not None and not app_icon.isNull():
        window.setWindowIcon(app_icon)
    for arg in sys.argv[1:]:
        arg_lower = arg.lower()
        if arg_lower in ("--page-debloat", "-page-debloat", "/page-debloat"):
            window.on_debloat_sidebar_click()
        elif arg_lower in ("--test-apply-click", "-test-apply-click"):
            window.on_debloat_sidebar_click()
            QTimer.singleShot(700, window.apply_btn.click)
        elif arg_lower in ("--test-start-debloat", "-test-start-debloat"):
            window.on_debloat_sidebar_click()
            QTimer.singleShot(700, window.actual_start_debloat)
    window.show()

    # Win32 taskbar ve başlık çubuğu simgesini doğrudan HWND'ye bağla
    if os.name == "nt":
        try:
            hwnd = int(window.winId())
            WM_SETICON = 0x0080
            ICON_SMALL = 0
            ICON_BIG = 1
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010

            h_big = 0
            h_small = 0
            if icon_path_found and icon_path_found.lower().endswith(".ico"):
                h_big = ctypes.windll.user32.LoadImageW(None, icon_path_found, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                h_small = ctypes.windll.user32.LoadImageW(None, icon_path_found, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)

            if not h_big and getattr(sys, "frozen", False):
                h_big = ctypes.windll.shell32.ExtractIconW(0, sys.executable, 0)
                h_small = ctypes.windll.shell32.ExtractIconW(0, sys.executable, 0)

            if h_big:
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_big)
            if h_small:
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_small)
        except Exception:
            pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
