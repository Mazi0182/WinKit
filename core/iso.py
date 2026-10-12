"""
WinKit Core ISO Engine Module
Handles Windows 11 ISO image inspection, WIM/ESD architecture verification,
tree validation, and oscdimg compilation helpers.
"""

import os
import re
import time
import shutil
import tempfile
import subprocess
import winreg
from pathlib import Path
from typing import Tuple, Optional, Any, Callable

from core.constants import (
    SUPPORTED_WINDOWS_VERSION, SUPPORTED_WINDOWS_BUILD, CREATE_NO_WINDOW
)

def normalize_windows_product_name(product_name: str, build: Any) -> str:
    """
    Windows 11'in bazı kurulumlarında ProductName geriye dönük uyumluluk
    nedeniyle 'Windows 10 ...' olarak kalabilir. 22000+ client build'lerini
    kullanıcıya doğru ürün adıyla göster.
    """
    name = str(product_name or "").strip()
    try:
        build_number = int(str(build).strip())
    except (TypeError, ValueError):
        build_number = 0
    if build_number >= 22000 and name.casefold().startswith("windows 10"):
        return "Windows 11" + name[len("Windows 10"):]
    return name


def get_current_windows_release() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Kurulu Windows sürümünü salt-okunur olarak döndürür."""
    try:
        access = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, access) as key:
            display_version = str(winreg.QueryValueEx(key, "DisplayVersion")[0]).strip()
            build = str(winreg.QueryValueEx(key, "CurrentBuildNumber")[0]).strip()
            product_name = str(winreg.QueryValueEx(key, "ProductName")[0]).strip()
        return display_version, build, normalize_windows_product_name(product_name, build)
    except (FileNotFoundError, OSError):
        return None, None, None


def get_current_windows_edition() -> str:
    """Kurulu Windows edisyonunu kullanıcıya gösterilecek kısa adla döndürür."""
    edition_names = {
        "core": "Home",
        "coresinglelanguage": "Home Single Language",
        "professional": "Pro",
        "professionalworkstation": "Pro for Workstations",
        "education": "Education",
        "enterprise": "Enterprise",
        "iotenterprise": "IoT Enterprise",
        "iotenterpriseltsc": "IoT Enterprise LTSC",
    }
    try:
        access = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, access) as key:
            edition_id = str(winreg.QueryValueEx(key, "EditionID")[0]).strip()
        return edition_names.get(edition_id.casefold(), edition_id or "Bilinmiyor")
    except (FileNotFoundError, OSError):
        return "Bilinmiyor"


def is_supported_windows_release() -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    display_version, build, product_name = get_current_windows_release()
    supported = (
        (display_version or "").casefold() == SUPPORTED_WINDOWS_VERSION.casefold()
        and build == SUPPORTED_WINDOWS_BUILD
        and "windows 11" in (product_name or "").casefold()
    )
    return supported, display_version, build, product_name


def validate_iso_paths(source_path: str, output_path: str, allow_same: bool = True) -> Tuple[bool, str]:
    if not source_path or not output_path:
        return False, "Kaynak veya hedef yol boş bırakılamaz."
    src = Path(source_path).resolve()
    out = Path(output_path).resolve()
    if not src.is_file() or src.suffix.casefold() != ".iso":
        return False, "Geçerli bir kaynak Windows ISO dosyası seçilmedi."
    if out.suffix.casefold() != ".iso":
        return False, "Hedef dosya uzantısı '.iso' olmalıdır."
    if not allow_same and src == out:
        return False, "Kaynak ve hedef ISO dosyası aynı olamaz."
    return True, ""


def windows_release_for_build(build: str) -> str:
    build_str = str(build).strip()
    if build_str == "26200":
        return "25H2"
    if build_str == "26100":
        return "24H2"
    return ""


def summarize_oscdimg_failure(lines: list, return_code: int) -> str:
    """oscdimg çıktısını teknik döküm yerine kısa ve anlaşılır bir nedene indirger."""
    cleaned = [line.strip() for line in lines if line and line.strip()]
    joined = " ".join(cleaned).casefold()
    if any(marker in joined for marker in ("access is denied", "error 5", "erişim engellendi")):
        return "ISO dosyasına veya geçici klasöre erişim engellendi."
    if any(marker in joined for marker in ("disk full", "not enough space", "insufficient disk", "112")):
        return "Diskte ISO'yu oluşturacak kadar boş alan kalmadı."
    if "boot" in joined and any(marker in joined for marker in ("error", "invalid", "cannot", "failed")):
        return "ISO önyükleme dosyaları oscdimg tarafından kabul edilmedi."
    if any(marker in joined for marker in ("cannot create", "unable to create", "could not create")):
        return "Geçici ISO dosyası oluşturulamadı."
    for line in reversed(cleaned):
        if any(marker in line.casefold() for marker in ("error", "failed", "cannot", "unable")):
            return line[:220]
    return f"oscdimg beklenmeyen bir hatayla kapandı (kod {return_code})."


def write_iso_build_log(command: list, lines: list, return_code: int):
    """ISO üretimi için dosya çıktısı oluşturulmaz."""
    return None


def validate_extracted_iso_tree(extracted_iso_dir: str) -> Tuple[bool, str]:
    """Ayıklanan medyada kök dışına çıkan yol veya reparse point olmadığını doğrular."""
    root = Path(extracted_iso_dir).resolve()
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            return False, f"ISO içeriği okunamadı: {exc}"
        for entry in entries:
            try:
                item_stat = entry.stat(follow_symlinks=False)
                is_reparse = bool(
                    getattr(item_stat, "st_file_attributes", 0) & 0x400
                )
                if entry.is_symlink() or is_reparse:
                    return False, f"ISO içinde izin verilmeyen bağlantı bulundu: {entry.name}"
                item_path = Path(entry.path).resolve()
                item_path.relative_to(root)
                if entry.is_dir(follow_symlinks=False):
                    stack.append(item_path)
            except ValueError:
                return False, f"ISO içeriği geçici klasörün dışına çıkıyor: {entry.name}"
            except OSError as exc:
                return False, f"ISO üyesi doğrulanamadı ({entry.name}): {exc}"
    return True, ""


def _read_offline_windows_release(image_path: Path, sevenzip_path: Path) -> Tuple[str, str, bool]:
    """İlk WIM/ESD imajındaki SOFTWARE hive'ından etkin Windows sürümünü okur."""
    extract_dir = Path(tempfile.mkdtemp(prefix="winkit_hive_"))
    try:
        result = subprocess.run(
            [
                str(sevenzip_path), "x", str(image_path),
                r"1\Windows\System32\config\SOFTWARE",
                f"-o{extract_dir}", "-y", "-bso0", "-bsp0",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=300,
            check=False,
        )
        software_hive = extract_dir / "1" / "Windows" / "System32" / "config" / "SOFTWARE"
        if result.returncode not in (0, 1) or not software_hive.is_file():
            return "", "", False

        hive_bytes = software_hive.read_bytes()
        hive_text = hive_bytes.decode("utf-16le", errors="ignore")
        has_display_version = "DisplayVersion" in hive_text
        has_current_build = "CurrentBuildNumber" in hive_text
        display_version = "25H2" if has_display_version and "25H2" in hive_text else ""
        current_build = "26200" if has_current_build and "26200" in hive_text else ""
        return display_version, current_build, bool(display_version or current_build)
    except (OSError, subprocess.TimeoutExpired, PermissionError):
        return "", "", False
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


def get_windows_image_info(extracted_iso_dir: str, sevenzip_path: Path) -> Tuple[Optional[str], Optional[str], str]:
    """ISO imajının etkin sürümünü, taban build'ini ve mimarisini doğrular."""
    sources_dir = Path(extracted_iso_dir) / "sources"
    image_path = next(
        (path for path in (sources_dir / "install.wim", sources_dir / "install.esd") if path.is_file()),
        None,
    )
    if image_path is None:
        return None, None, "ISO içinde sources/install.wim veya install.esd bulunamadı."
    try:
        result = subprocess.run(
            [
                "dism.exe",
                "/English",
                "/Get-WimInfo",
                f"/WimFile:{image_path}",
                "/Index:1",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, None, f"Windows imaj sürümü okunamadı: {exc}"
    if result.returncode != 0:
        return None, None, "DISM, Windows imaj bilgisini okuyamadı."
    version_match = re.search(
        r"^\s*Version\s*:\s*10\.0\.(\d+)(?:\.\d+)?\s*$",
        result.stdout,
        re.MULTILINE,
    )
    architecture_match = re.search(
        r"^\s*Architecture\s*:\s*(\S+)\s*$",
        result.stdout,
        re.MULTILINE | re.IGNORECASE,
    )
    if not version_match or not architecture_match:
        return None, None, "Windows imajının build veya mimari bilgisi çözümlenemedi."
    base_build = version_match.group(1)
    architecture = architecture_match.group(1).casefold()
    if base_build == "26100":
        display_version, offline_build, has_25h2_metadata = _read_offline_windows_release(
            image_path,
            sevenzip_path,
        )
        if display_version.casefold() == "25h2" or offline_build == "26200" or has_25h2_metadata:
            return SUPPORTED_WINDOWS_BUILD, architecture, ""
    return base_build, architecture, ""


def generate_unattend_xml(
    bypass_requirements: bool = False,
    bypass_online_account: bool = False,
    bypass_bitlocker: bool = False,
) -> str:
    """Windows Setup için otomatik autounattend.xml içeriği üretir."""
    xml = '<?xml version="1.0" encoding="utf-8"?>\n<unattend xmlns="urn:schemas-microsoft-com:unattend">\n'

    if bypass_requirements:
        xml += """    <settings pass="windowsPE">
        <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <RunSynchronous>
                <RunSynchronousCommand wcm:action="add">
                    <Order>1</Order>
                    <Path>reg.exe add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassTPMCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>2</Order>
                    <Path>reg.exe add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassSecureBootCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>3</Order>
                    <Path>reg.exe add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassRAMCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>4</Order>
                    <Path>reg.exe add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassStorageCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>5</Order>
                    <Path>reg.exe add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassCPUCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>6</Order>
                    <Path>reg.exe add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassDiskCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
            </RunSynchronous>
            <UserData>
                <AcceptEula>true</AcceptEula>
            </UserData>
        </component>
    </settings>\n"""
    else:
        xml += """    <settings pass="windowsPE">
        <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <UserData>
                <AcceptEula>true</AcceptEula>
            </UserData>
        </component>
    </settings>\n"""

    specialize_cmds = []
    specialize_order = 1
    if bypass_online_account:
        specialize_cmds.extend([
            # Fiziksel sistemlerde PCIe NIC donanım gecikmesi ve internet kablosu takılı olsa bile
            # OOBE'nin kesinlikle internete çıkamaması ve yerel hesap dayatması için outbound güvenlik duvarı mühürlenir.
            (specialize_order, r'cmd.exe /c netsh advfirewall set allprofiles firewallpolicy blockinbound,blockoutbound'),
            (specialize_order + 1, r'cmd.exe /c reg add HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE /v BypassNRO /t REG_DWORD /d 1 /f'),
            (specialize_order + 2, r'cmd.exe /c reg add HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE /v HideOnlineAccountScreens /t REG_DWORD /d 1 /f'),
            (specialize_order + 3, r'cmd.exe /c reg add HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE /v DisableNetworkCheck /t REG_DWORD /d 1 /f'),
            (specialize_order + 4, r'cmd.exe /c reg add HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE /v HideWirelessSetupInOOBE /t REG_DWORD /d 1 /f'),
            (specialize_order + 5, r'cmd.exe /c C:\Windows\Setup\Scripts\disable_net.cmd'),
            (specialize_order + 6, r'cmd.exe /c schtasks /Create /TN "DisableNet" /TR "cmd.exe /c C:\Windows\Setup\Scripts\disable_net.cmd" /SC ONSTART /RU "SYSTEM" /RL HIGHEST /F'),
        ])
        specialize_order += 7
    if bypass_bitlocker:
        specialize_cmds.extend([
            (specialize_order, r'cmd.exe /c reg add HKLM\SYSTEM\CurrentControlSet\Control\BitLocker /v PreventDeviceEncryption /t REG_DWORD /d 1 /f'),
            (specialize_order + 1, r'cmd.exe /c reg add HKLM\SYSTEM\CurrentControlSet\Services\BDESVC /v Start /t REG_DWORD /d 4 /f'),
            (specialize_order + 2, r'cmd.exe /c sc.exe config BDESVC start= disabled'),
        ])
        specialize_order += 3

    if specialize_cmds:
        specialize_xml = "\n".join(
            f"""                <RunSynchronousCommand wcm:action="add">
                    <Order>{cmd_order}</Order>
                    <Path>{cmd}</Path>
                </RunSynchronousCommand>"""
            for cmd_order, cmd in specialize_cmds
        )
        xml += f"""    <settings pass="specialize">
        <component name="Microsoft-Windows-Deployment" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <RunSynchronous>
{specialize_xml}
            </RunSynchronous>
        </component>
    </settings>\n"""

    hide_online_accounts = "true" if bypass_online_account else "false"
    hide_wireless = "true" if bypass_online_account else "false"
    first_logon_items = []
    first_logon_order = 1
    if bypass_online_account:
        first_logon_items.append(
            f"""                <SynchronousCommand wcm:action="add">
                    <Order>{first_logon_order}</Order>
                    <CommandLine>cmd.exe /c C:\\Windows\\Setup\\Scripts\\SetupComplete.cmd</CommandLine>
                    <Description>Enable network adapters and cleanup</Description>
                </SynchronousCommand>"""
        )
        first_logon_order += 1

    first_logon_commands = ""
    if first_logon_items:
        first_logon_commands = (
            "\n            <FirstLogonCommands>\n"
            + "\n".join(first_logon_items)
            + "\n            </FirstLogonCommands>"
        )

    xml += f"""    <settings pass="oobeSystem">
        <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <OOBE>
                <HideEULAPage>true</HideEULAPage>
                <HideLocalAccountScreen>false</HideLocalAccountScreen>
                <HideOEMRegistrationScreen>true</HideOEMRegistrationScreen>
                <HideOnlineAccountScreens>{hide_online_accounts}</HideOnlineAccountScreens>
                <HideWirelessSetupInOOBE>{hide_wireless}</HideWirelessSetupInOOBE>
                <ProtectYourPC>3</ProtectYourPC>
            </OOBE>{first_logon_commands}
        </component>
    </settings>
</unattend>"""
    return xml


def build_custom_iso(
    source: Path,
    output: Path,
    sevenzip_exe: str,
    oscdimg_exe: str,
    bypass_requirements: bool = False,
    bypass_online_account: bool = False,
    bypass_bitlocker: bool = False,
    progress_callback: Optional[Callable[[str, int], None]] = None,
    stage_start: Optional[Callable[[str, str], None]] = None,
    stage_finish: Optional[Callable[[str, str, str], None]] = None,
    log_callback: Optional[Callable[[str, str], None]] = None,
) -> Tuple[bool, str]:
    """
    Orijinal Windows 11 ISO dosyasını açar, otomasyon XML ve scriptlerini enjekte eder,
    oscdimg ile önyüklenebilir (UEFI + BIOS) yeni ISO imajını derler.
    """
    import secrets
    temp_iso_dir = None
    staging_output = None

    def emit_log(text, color="#E7ECF2"):
        if log_callback:
            log_callback(text, color)

    try:
        valid, error = validate_iso_paths(source, output)
        if not valid:
            return False, error

        source = Path(source).resolve()
        output = Path(output).resolve()

        source_size = source.stat().st_size
        required_temp_space = max(10 * 1024**3, source_size * 2)
        temp_free = shutil.disk_usage(tempfile.gettempdir()).free
        if temp_free < required_temp_space:
            return False, f"Geçici diskte yeterli alan yok. En az {required_temp_space / 1024**3:.1f} GB boş alan gerekiyor."

        output_free = shutil.disk_usage(output.parent).free
        if output_free < source_size + 1024**3:
            return False, "Çıktı diskinde yeni ISO için yeterli boş alan yok."

        temp_iso_dir = tempfile.mkdtemp(prefix="winkit_iso_")

        if progress_callback:
            progress_callback("Ayıklanıyor", 0)

        threads = min(4, max(1, (os.cpu_count() or 4) // 2))
        proc_7z = subprocess.Popen(
            [sevenzip_exe, "x", str(source), f"-o{temp_iso_dir}", "-y", "-bsp1", f"-mmt={threads}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
            text=True,
            bufsize=1,
        )
        last_sent_pct = -1
        last_time = time.time()
        buffer_7z = ""
        while True:
            chunk = proc_7z.stdout.read(64)
            if not chunk and proc_7z.poll() is not None:
                break
            if chunk:
                buffer_7z += chunk
                matches = re.findall(r'(\d+)\s*%', buffer_7z)
                if matches:
                    pct = int(matches[-1])
                    curr_time = time.time()
                    if pct != last_sent_pct and (curr_time - last_time > 0.12 or pct == 100):
                        if progress_callback:
                            progress_callback("Ayıklanıyor", pct)
                        last_sent_pct = pct
                        last_time = curr_time
                if len(buffer_7z) > 1024:
                    buffer_7z = buffer_7z[-256:]
            else:
                time.sleep(0.01)
        proc_7z.wait()
        if proc_7z.returncode != 0:
            return False, "7z ayıklama başarısız!"

        tree_valid, tree_error = validate_extracted_iso_tree(temp_iso_dir)
        if not tree_valid:
            return False, tree_error

        validation_stage_id = f"iso_validation_{secrets.token_hex(5)}"
        if stage_start:
            stage_start(validation_stage_id, "Windows sürümü doğrulanıyor")

        image_build, image_architecture, build_error = get_windows_image_info(temp_iso_dir, Path(sevenzip_exe))
        if image_build is None:
            if stage_finish:
                stage_finish(validation_stage_id, "✖", "#FF5C6B")
            return False, build_error

        supported_builds = {"26100", "26200"}
        is_win11 = (image_build in supported_builds) or (image_build.isdigit() and int(image_build) >= 22000)
        if not is_win11:
            detected_release = windows_release_for_build(image_build)
            if stage_finish:
                stage_finish(validation_stage_id, "✖", "#FF5C6B")
            return False, f"Bu ISO akışı yalnızca Windows 11 medyalarını destekler. Algılanan: {detected_release} (build {image_build})."

        if image_architecture not in {"x64", "amd64"}:
            if stage_finish:
                stage_finish(validation_stage_id, "✖", "#FF5C6B")
            return False, f"Bu ISO akışı yalnızca x64/amd64 medyayı destekler; algılanan: {image_architecture}."

        if stage_finish:
            stage_finish(validation_stage_id, "✔", "#55D67A")

        etfs_path = os.path.join(temp_iso_dir, "boot", "etfsboot.com")
        efisys_path = os.path.join(temp_iso_dir, "efi", "microsoft", "boot", "efisys_noprompt.bin")
        if not os.path.exists(efisys_path):
            efisys_path = os.path.join(temp_iso_dir, "efi", "microsoft", "boot", "efisys.bin")

        if not os.path.exists(etfs_path) or not os.path.exists(efisys_path):
            return False, "Bootloader dosyaları bulunamadı!"

        change_stage_id = f"iso_changes_{secrets.token_hex(5)}"
        if stage_start:
            stage_start(change_stage_id, "Değişiklikler ekleniyor")

        if bypass_online_account:
            oem_dir = os.path.join(temp_iso_dir, "sources", "$OEM$", "$$", "Setup", "Scripts")
            os.makedirs(oem_dir, exist_ok=True)
            with open(os.path.join(oem_dir, "disable_net.cmd"), "w", encoding="utf-8", newline="\r\n") as f:
                f.write(
                    "@echo off\r\n"
                    "netsh advfirewall set allprofiles firewallpolicy blockinbound,blockoutbound >nul 2>&1\r\n"
                    "for /f \"skip=2 tokens=3,*\" %%A in ('netsh interface show interface') do (\r\n"
                    "    netsh interface set interface name=\"%%B\" admin=disable >nul 2>&1\r\n"
                    ")\r\n"
                    "netsh interface set interface \"Ethernet\" admin=disable >nul 2>&1\r\n"
                    "netsh interface set interface \"Ethernet 2\" admin=disable >nul 2>&1\r\n"
                    "netsh interface set interface \"Ethernet 3\" admin=disable >nul 2>&1\r\n"
                    "netsh interface set interface \"Wi-Fi\" admin=disable >nul 2>&1\r\n"
                    "netsh interface set interface \"Wi-Fi 2\" admin=disable >nul 2>&1\r\n"
                    "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"Get-NetAdapter -ErrorAction SilentlyContinue | Disable-NetAdapter -Confirm:$false\" >nul 2>&1\r\n"
                )
            with open(os.path.join(oem_dir, "SetupComplete.cmd"), "w", encoding="utf-8", newline="\r\n") as f:
                f.write(
                    "@echo off\r\n"
                    "netsh advfirewall set allprofiles firewallpolicy blockinbound,allowoutbound >nul 2>&1\r\n"
                    "schtasks /Delete /TN \"DisableNet\" /F >nul 2>&1\r\n"
                    "reg delete \"HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce\" /v DisableNet /f >nul 2>&1\r\n"
                    "for /f \"skip=2 tokens=3,*\" %%A in ('netsh interface show interface') do (\r\n"
                    "    netsh interface set interface name=\"%%B\" admin=enable >nul 2>&1\r\n"
                    ")\r\n"
                    "netsh interface set interface \"Ethernet\" admin=enable >nul 2>&1\r\n"
                    "netsh interface set interface \"Ethernet 2\" admin=enable >nul 2>&1\r\n"
                    "netsh interface set interface \"Ethernet 3\" admin=enable >nul 2>&1\r\n"
                    "netsh interface set interface \"Wi-Fi\" admin=enable >nul 2>&1\r\n"
                    "netsh interface set interface \"Wi-Fi 2\" admin=enable >nul 2>&1\r\n"
                    "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"Get-NetAdapter -ErrorAction SilentlyContinue | Enable-NetAdapter -Confirm:$false\" >nul 2>&1\r\n"
                )

        xml = generate_unattend_xml(bypass_requirements, bypass_online_account, bypass_bitlocker)
        root_xml = os.path.join(temp_iso_dir, "autounattend.xml")
        with open(root_xml, "w", encoding="utf-8") as f:
            f.write(xml)
        sources_xml = os.path.join(temp_iso_dir, "sources", "unattend.xml")
        if os.path.exists(os.path.dirname(sources_xml)):
            with open(sources_xml, "w", encoding="utf-8") as f:
                f.write(xml)

        if stage_finish:
            stage_finish(change_stage_id, "✔", "#55D67A")

        staging_output = output.with_name(f".{output.stem}.{secrets.token_hex(8)}.tmp.iso")
        boot_arg = f"-bootdata:2#p0,e,b{etfs_path}#pEF,e,b{efisys_path}"
        cmd = [
            oscdimg_exe,
            "-m",
            "-o",
            "-u2",
            "-udfver102",
            "-lWIN11_CUSTOM",
            boot_arg,
            temp_iso_dir,
            str(staging_output),
        ]

        if progress_callback:
            progress_callback("ISO yeniden oluşturuluyor", 0)

        proc_osc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
            text=True,
            bufsize=1,
        )
        last_osc_pct = -1
        last_osc_time = time.time()
        oscdimg_lines = []
        buffer_osc = ""
        while True:
            chunk = proc_osc.stdout.read(64)
            if not chunk and proc_osc.poll() is not None:
                break
            if chunk:
                buffer_osc += chunk
                oscdimg_lines.append(chunk)
                matches = re.findall(r'(\d+)\s*%', buffer_osc)
                if matches:
                    pct = int(matches[-1])
                    curr_time = time.time()
                    if pct != last_osc_pct and (curr_time - last_osc_time > 0.12 or pct == 100):
                        if progress_callback:
                            progress_callback("ISO yeniden oluşturuluyor", pct)
                        last_osc_pct = pct
                        last_osc_time = curr_time
                if len(buffer_osc) > 1024:
                    buffer_osc = buffer_osc[-256:]
            else:
                time.sleep(0.01)
        proc_osc.wait()
        if proc_osc.returncode != 0:
            summary = summarize_oscdimg_failure(oscdimg_lines, proc_osc.returncode)
            log_path = write_iso_build_log(cmd, oscdimg_lines, proc_osc.returncode)
            extra = f" (Ayrıntı: {log_path.name})" if log_path else ""
            return False, f"HATA: {summary}{extra}"

        if staging_output.is_file():
            staging_output.replace(output)

        return True, str(output)

    except Exception as exc:
        return False, str(exc)
    finally:
        if staging_output is not None and staging_output.is_file():
            try:
                staging_output.unlink()
            except OSError:
                pass
        if temp_iso_dir and os.path.exists(temp_iso_dir):
            shutil.rmtree(temp_iso_dir, ignore_errors=True)
