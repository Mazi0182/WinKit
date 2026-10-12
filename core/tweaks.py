"""
WinKit Core System Tweaks Module
Handles hardware-safe MSI interrupt tuning, Windows Update 2099 pausing/unpausing,
and isolated system registry optimizations.
"""

import winreg
from typing import Callable, Optional, List, Dict, Any

class SystemTweaks:
    """
    Manages safe system-level tweaks and hardware optimizations.
    """
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback

    def log(self, text: str, color: str = "#00FF9D"):
        if self.log_callback:
            self.log_callback(text, color)

    def apply_msi_tuning_safe(self) -> Dict[str, Any]:
        """
        Safely tunes MSI (Message Signaled Interrupts) for GPUs and NICs.
        Strictly tests hardware capability before enabling MSI to avoid BSODs.
        Returns report of tuned and skipped devices.
        """
        self.log("[*] Donanım uyumluluk kontrollü MSI Interrupt Tuning başlatılıyor...", "#00E5FF")

        gpu_class_guid = "{4d36e968-e325-11ce-bfc1-08002be10318}"
        nic_class_guid = "{4d36e972-e325-11ce-bfc1-08002be10318}"
        pci_path = r"SYSTEM\CurrentControlSet\Enum\PCI"

        tuned_devices = []
        skipped_devices = []

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pci_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as pci_k:
                num_devs = winreg.QueryInfoKey(pci_k)[0]
                for i in range(num_devs):
                    dev_name = winreg.EnumKey(pci_k, i)
                    dev_sub = f"{pci_path}\\{dev_name}"
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, dev_sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as dev_k:
                            num_inst = winreg.QueryInfoKey(dev_k)[0]
                            for j in range(num_inst):
                                inst_name = winreg.EnumKey(dev_k, j)
                                inst_sub = f"{dev_sub}\\{inst_name}"
                                try:
                                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, inst_sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as inst_k:
                                        try:
                                            guid, _ = winreg.QueryValueEx(inst_k, "ClassGUID")
                                        except OSError:
                                            continue

                                        desc = ""
                                        for p in ("DeviceDesc", "FriendlyName"):
                                            try:
                                                val, _ = winreg.QueryValueEx(inst_k, p)
                                                desc += " " + str(val)
                                            except OSError:
                                                pass
                                        desc = desc.strip() or inst_name

                                        is_gpu = guid.lower() == gpu_class_guid.lower()
                                        is_nic = guid.lower() == nic_class_guid.lower()

                                        if not (is_gpu or is_nic):
                                            continue

                                        # Skip virtual or emulated devices that crash under MSI
                                        low_desc = desc.lower()
                                        if any(bad in low_desc for bad in ("virtual", "vmware", "hyper-v", "loopback", "tap", "npcap", "82540", "pro/1000 mt")):
                                            skipped_devices.append((desc, "Sanal / Emüle cihaz (MSI desteklemez)"))
                                            self.log(f"[!] Sanal aygıt atlandı: {desc}", "#FFB86C")
                                            continue

                                        msi_prop_path = f"{inst_sub}\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties"
                                        
                                        # Test if hardware/driver supports MSI:
                                        # If the registry branch does not exist at all, driver has not enabled MSI capabilities
                                        try:
                                            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, msi_prop_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
                                                pass
                                        except OSError:
                                            skipped_devices.append((desc, "Sürücü MSI yapılandırmasını desteklemiyor"))
                                            self.log(f"[!] Donanım MSI desteklemiyor, güvenle atlandı: {desc}", "#FFB86C")
                                            continue

                                        # Hardware natively supports MSI, apply safely
                                        with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, msi_prop_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as msi_k:
                                            winreg.SetValueEx(msi_k, "MSISupported", 0, winreg.REG_DWORD, 1)

                                        affinity_path = f"{inst_sub}\\Device Parameters\\Interrupt Management\\Affinity Policy"
                                        if is_nic:
                                            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, affinity_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as aff_k:
                                                winreg.SetValueEx(aff_k, "DevicePriority", 0, winreg.REG_DWORD, 2)

                                        tuned_devices.append(desc)
                                        self.log(f"[+] MSI Başarıyla Açıldı: {desc}", "#00FF9D")
                                except OSError:
                                    continue
                    except OSError:
                        continue
        except Exception as e:
            self.log(f"[!] MSI tarama hatası: {e}", "#FF6B6B")

        self.log(f"[OK] MSI Tuning bitti: {len(tuned_devices)} cihaz optimize edildi, {len(skipped_devices)} uyumsuz cihaz korundu.", "#00FF9D")
        return {"tuned": tuned_devices, "skipped": skipped_devices}

    def pause_windows_updates_2099(self) -> bool:
        """
        Pauses Windows updates until year 2099 via official UX policies.
        """
        self.log("[*] Windows güncellemeleri 2099 yılına erteleniyor...", "#00E5FF")
        p = r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
        try:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, p, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                winreg.SetValueEx(k, "FlightSettingsMaxPauseDays", 0, winreg.REG_DWORD, 36500)
                winreg.SetValueEx(k, "PauseUpdatesStartTime", 0, winreg.REG_SZ, "2026-01-01T00:00:00Z")
                winreg.SetValueEx(k, "PauseUpdatesExpiryTime", 0, winreg.REG_SZ, "2099-12-31T23:59:59Z")
                winreg.SetValueEx(k, "PauseFeatureUpdatesStartTime", 0, winreg.REG_SZ, "2026-01-01T00:00:00Z")
                winreg.SetValueEx(k, "PauseFeatureUpdatesEndTime", 0, winreg.REG_SZ, "2099-12-31T23:59:59Z")
                winreg.SetValueEx(k, "PauseQualityUpdatesStartTime", 0, winreg.REG_SZ, "2026-01-01T00:00:00Z")
                winreg.SetValueEx(k, "PauseQualityUpdatesEndTime", 0, winreg.REG_SZ, "2099-12-31T23:59:59Z")
            self.log("[+] Güncellemeler 2099'a kadar ertelendi.", "#00FF9D")
            return True
        except Exception as e:
            self.log(f"[!] Güncelleme erteleme hatası: {e}", "#FF6B6B")
            return False

    def resume_windows_updates(self) -> bool:
        """
        Resumes Windows updates (useful when installing optional features like .NET 3.5).
        """
        self.log("[*] Windows güncellemeleri normale döndürülüyor (.NET 3.5 vb. için)...", "#00E5FF")
        p = r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
        values = [
            "PauseUpdatesStartTime", "PauseUpdatesExpiryTime",
            "PauseFeatureUpdatesStartTime", "PauseFeatureUpdatesEndTime",
            "PauseQualityUpdatesStartTime", "PauseQualityUpdatesEndTime"
        ]
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, p, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                for v in values:
                    try:
                        winreg.DeleteValue(k, v)
                    except OSError:
                        pass
            self.log("[+] Güncelleme ertelemesi kaldırıldı.", "#00FF9D")
            return True
        except Exception as e:
            self.log(f"[!] Hata: {e}", "#FF6B6B")
            return False

    def configure_windows_update_mode(self, mode: str = "disable_auto_allow_features") -> bool:
        r"""
        Configures Windows Update according to requested mode:
        - 'pause_2100': Sets UX pause keys up to year 2100.
        - 'disable_auto_allow_features': Clears UX pause keys so CBS / .NET features can be downloaded,
          sets NoAutoUpdate=1 and AUOptions=2 in WindowsUpdate\AU policies, ensures DoSvc is Demand (not disabled).
        """
        if mode == "pause_2100":
            self.log("[*] Windows güncellemeleri 2100 yılına kadar duraklatılıyor...", "#00E5FF")
            try:
                au_path = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, au_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                    for v in ("NoAutoUpdate", "AUOptions", "ScheduledInstallDay", "ScheduledInstallTime"):
                        try:
                            winreg.DeleteValue(k, v)
                        except OSError:
                            pass
            except OSError:
                pass

            p = r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
            try:
                with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, p, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                    winreg.SetValueEx(k, "FlightSettingsMaxPauseDays", 0, winreg.REG_DWORD, 36500)
                    winreg.SetValueEx(k, "PauseUpdatesStartTime", 0, winreg.REG_SZ, "2026-01-01T00:00:00Z")
                    winreg.SetValueEx(k, "PauseUpdatesExpiryTime", 0, winreg.REG_SZ, "2100-12-31T23:59:59Z")
                    winreg.SetValueEx(k, "PauseFeatureUpdatesStartTime", 0, winreg.REG_SZ, "2026-01-01T00:00:00Z")
                    winreg.SetValueEx(k, "PauseFeatureUpdatesEndTime", 0, winreg.REG_SZ, "2100-12-31T23:59:59Z")
                    winreg.SetValueEx(k, "PauseQualityUpdatesStartTime", 0, winreg.REG_SZ, "2026-01-01T00:00:00Z")
                    winreg.SetValueEx(k, "PauseQualityUpdatesEndTime", 0, winreg.REG_SZ, "2100-12-31T23:59:59Z")
                self.log("[+] Güncellemeler 2100'e kadar başarıyla duraklatıldı.", "#00FF9D")
                return True
            except Exception as e:
                self.log(f"[!] Güncelleme duraklatma hatası: {e}", "#FF6B6B")
                return False
        else:
            self.log("[*] Windows otomatik güncellemeleri kapatılıyor (.NET ve özellik indirmeleri açık tutuluyor)...", "#00E5FF")
            p_ux = r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
            ux_values = [
                "PauseUpdatesStartTime", "PauseUpdatesExpiryTime",
                "PauseFeatureUpdatesStartTime", "PauseFeatureUpdatesEndTime",
                "PauseQualityUpdatesStartTime", "PauseQualityUpdatesEndTime"
            ]
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, p_ux, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                    for v in ux_values:
                        try:
                            winreg.DeleteValue(k, v)
                        except OSError:
                            pass
            except OSError:
                pass

            try:
                wu_pol = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"
                with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, wu_pol, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                    winreg.SetValueEx(k, "DoNotConnectToWindowsUpdateInternetLocations", 0, winreg.REG_DWORD, 0)
                    winreg.SetValueEx(k, "DisableWindowsUpdateAccess", 0, winreg.REG_DWORD, 0)

                au_pol = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
                with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, au_pol, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                    winreg.SetValueEx(k, "NoAutoUpdate", 0, winreg.REG_DWORD, 1)
                    winreg.SetValueEx(k, "AUOptions", 0, winreg.REG_DWORD, 2)
                    winreg.SetValueEx(k, "ScheduledInstallDay", 0, winreg.REG_DWORD, 0)
                    winreg.SetValueEx(k, "ScheduledInstallTime", 0, winreg.REG_DWORD, 3)

                servicing_pol = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Servicing"
                with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, servicing_pol, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                    winreg.SetValueEx(k, "UseWindowsUpdate", 0, winreg.REG_DWORD, 2)
                    winreg.SetValueEx(k, "RepairContentServerSource", 0, winreg.REG_DWORD, 2)

                dosvc_path = r"SYSTEM\CurrentControlSet\Services\DoSvc"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, dosvc_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
                        winreg.SetValueEx(k, "Start", 0, winreg.REG_DWORD, 3)
                except OSError:
                    pass

                self.log("[+] Otomatik güncellemeler kapatıldı; .NET ve isteğe bağlı Windows özellikleri için indirme açık bırakıldı.", "#00FF9D")
                return True
            except Exception as e:
                self.log(f"[!] Güncelleme yapılandırma hatası: {e}", "#FF6B6B")
                return False

def apply_msi_interrupt_tuning() -> int:
    t = SystemTweaks()
    res = t.apply_msi_tuning_safe()
    return len(res.get("tuned", []))

def pause_windows_updates_2099() -> bool:
    return SystemTweaks().pause_windows_updates_2099()

def resume_windows_updates() -> bool:
    return SystemTweaks().resume_windows_updates()

def configure_windows_update_mode(mode: str = "disable_auto_allow_features") -> bool:
    return SystemTweaks().configure_windows_update_mode(mode)

