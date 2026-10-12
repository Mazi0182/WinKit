"""
WinKit Core Registry Engine Module
Low-level 64-bit Registry operations and ultra-fast non-intrusive Defender status querying.
"""

import winreg

class RegistryEngine:
    """64-bit registry görünümünde temel okuma/yazma işlemleri."""
    
    @staticmethod
    def apply_tweak(hkey, sub_key, value_name, value, value_type=winreg.REG_DWORD):
        access_flags = winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
        try:
            with winreg.CreateKeyEx(hkey, sub_key, 0, access_flags) as key:
                if value == "<RemoveEntry>":
                    try:
                        winreg.DeleteValue(key, value_name)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(key, value_name, 0, value_type, value)
            return True
        except PermissionError:
            return False
        except Exception:
            return False

    @staticmethod
    def check_tweak_state(hkey, sub_key, value_name, expected_value):
        access_flags = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        try:
            with winreg.OpenKey(hkey, sub_key, 0, access_flags) as key:
                val, _ = winreg.QueryValueEx(key, value_name)
                if isinstance(val, bytes) and isinstance(expected_value, bytes):
                    return val == expected_value
                return val == expected_value
        except (FileNotFoundError, OSError):
            return False
        except Exception:
            return False

    @staticmethod
    def delete_key_recursive(hkey, sub_key, view_flag=winreg.KEY_WOW64_64KEY):
        """Bir registry anahtarını seçilen 32/64-bit görünümde altlarıyla siler."""
        access = winreg.KEY_READ | winreg.KEY_WRITE | view_flag
        with winreg.OpenKey(hkey, sub_key, 0, access) as key:
            children = []
            index = 0
            while True:
                try:
                    children.append(winreg.EnumKey(key, index))
                    index += 1
                except OSError:
                    break
        for child in children:
            RegistryEngine.delete_key_recursive(
                hkey,
                f"{sub_key}\\{child}",
                view_flag,
            )
        winreg.DeleteKeyEx(hkey, sub_key, view_flag, 0)


def is_defender_active() -> bool:
    """Windows Defender, Kurcalamaya Karşı Koruma veya Gerçek Zamanlı Koruma aktif mi sorgular."""
    # 1. WinDefend servis durumu kontrolü
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\WinDefend", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as s_key:
            start_mode, _ = winreg.QueryValueEx(s_key, "Start")
            if start_mode == 4:
                return False
    except FileNotFoundError:
        return False
    except OSError:
        pass

    # 2. İlke (Policy) kontrolleri
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows Defender", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as def_key:
            try:
                av_disabled, _ = winreg.QueryValueEx(def_key, "DisableAntiVirus")
                if av_disabled == 1:
                    return False
            except OSError:
                pass
            try:
                spy_disabled, _ = winreg.QueryValueEx(def_key, "DisableAntiSpyware")
                if spy_disabled == 1:
                    return False
            except OSError:
                pass
    except OSError:
        pass

    # 3. Gerçek Zamanlı Koruma (Real-Time Protection) durumu
    rt_disabled = False
    for reg_path in (
        r"SOFTWARE\Microsoft\Windows Defender\Real-Time Protection",
        r"SOFTWARE\Policies\Microsoft\Windows Defender\Real-Time Protection",
    ):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as rt_key:
                val, _ = winreg.QueryValueEx(rt_key, "DisableRealtimeMonitoring")
                if val == 1:
                    rt_disabled = True
                    break
        except OSError:
            pass

    # 4. Kurcalamaya Karşı Koruma (Tamper Protection) durumu
    tp_disabled = False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows Defender\Features", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as f_key:
            tp, _ = winreg.QueryValueEx(f_key, "TamperProtection")
            if tp in (0, 4):
                tp_disabled = True
            elif tp == 5:
                tp_disabled = False
    except OSError:
        tp_disabled = False

    if tp_disabled and rt_disabled:
        return False

    return True


def check_appx_installed_via_registry(package_family_name: str) -> bool:
    paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\Applications",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore\InboxApplications"
    ]
    package_family_name = str(package_family_name).lower()
    for path in paths:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                info = winreg.QueryInfoKey(key)
                num_subkeys = info[0]
                for i in range(num_subkeys):
                    subkey_name = winreg.EnumKey(key, i)
                    if package_family_name in subkey_name.lower():
                        return True
        except Exception:
            pass
    return False

