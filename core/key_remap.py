"""
WinKit - Keyboard Remap Engine and Accessibility Tweaks
Scancode mappings, registry Scancode Map manipulation, hotkey suppression,
and live session accessibility flag updates via SystemParametersInfoW.
"""

import os
import sys
import ctypes
import winreg
from PyQt6.QtCore import Qt

# =============================================================================
# KLAVYE TUS DONUSTURUCU VE SCANCODE HARITALAYICI VERITABANI
# =============================================================================
SCANCODE_DATABASE = [
    # (Ad, Scancode, Kategori)
    ("Tuşu Devre Dışı Bırak / Sustur", 0x0000, "Özel"),
    ("Windows + Space (Dil Kısayolu)", 0xF001, "Özel"),
    # Standart Fonksiyon Tuşları (F1 - F12)
    ("F1", 0x003B, "Fonksiyon"),
    ("F2", 0x003C, "Fonksiyon"),
    ("F3", 0x003D, "Fonksiyon"),
    ("F4", 0x003E, "Fonksiyon"),
    ("F5", 0x003F, "Fonksiyon"),
    ("F6", 0x0040, "Fonksiyon"),
    ("F7", 0x0041, "Fonksiyon"),
    ("F8", 0x0042, "Fonksiyon"),
    ("F9", 0x0043, "Fonksiyon"),
    ("F10", 0x0044, "Fonksiyon"),
    ("F11", 0x0057, "Fonksiyon"),
    ("F12", 0x0058, "Fonksiyon"),
    # Genişletilmiş Fonksiyon Tuşları (F13 - F24)
    ("F13", 0x0064, "Genişletilmiş F13-F24"),
    ("F14", 0x0065, "Genişletilmiş F13-F24"),
    ("F15", 0x0066, "Genişletilmiş F13-F24"),
    ("F16", 0x0067, "Genişletilmiş F13-F24"),
    ("F17", 0x0068, "Genişletilmiş F13-F24"),
    ("F18", 0x0069, "Genişletilmiş F13-F24"),
    ("F19", 0x006A, "Genişletilmiş F13-F24"),
    ("F20", 0x006B, "Genişletilmiş F13-F24"),
    ("F21", 0x006C, "Genişletilmiş F13-F24"),
    ("F22", 0x006D, "Genişletilmiş F13-F24"),
    ("F23", 0x006E, "Genişletilmiş F13-F24"),
    ("F24", 0x006F, "Genişletilmiş F13-F24"),
    # Değiştirici Tuşlar (Modifiers)
    ("Sağ Ctrl", 0xE01D, "Değiştirici"),
    ("Sol Ctrl", 0x001D, "Değiştirici"),
    ("Sağ Alt (AltGr)", 0xE038, "Değiştirici"),
    ("Sol Alt", 0x0038, "Değiştirici"),
    ("Sağ Shift", 0x0036, "Değiştirici"),
    ("Sol Shift", 0x002A, "Değiştirici"),
    ("Sol Windows Tuşu", 0xE05B, "Değiştirici"),
    ("Sağ Windows Tuşu", 0xE05C, "Değiştirici"),
    ("Caps Lock", 0x003A, "Değiştirici"),
    # Standart Kontrol Tuşları
    ("Enter", 0x001C, "Kontrol"),
    ("Numpad Enter", 0xE01C, "Kontrol"),
    ("Tab", 0x000F, "Kontrol"),
    ("Boşluk", 0x0039, "Kontrol"),
    ("Backspace", 0x000E, "Kontrol"),
    ("Esc", 0x0001, "Kontrol"),
    # Gezinme (Navigation)
    ("Insert", 0xE052, "Gezinme"),
    ("Delete", 0xE053, "Gezinme"),
    ("Home", 0xE047, "Gezinme"),
    ("End", 0xE04F, "Gezinme"),
    ("Page Up", 0xE049, "Gezinme"),
    ("Page Down", 0xE051, "Gezinme"),
    ("Yukarı Ok", 0xE048, "Gezinme"),
    ("Aşağı Ok", 0xE050, "Gezinme"),
    ("Sol Ok", 0xE04B, "Gezinme"),
    ("Sağ Ok", 0xE04D, "Gezinme"),
    ("Print Screen", 0xE037, "Sistem"),
    ("Scroll Lock", 0x0046, "Sistem"),
    ("Pause", 0x0045, "Sistem"),
    # Harfler A-Z
    ("A", 0x001E, "Harf"), ("B", 0x0030, "Harf"), ("C", 0x002E, "Harf"),
    ("D", 0x0020, "Harf"), ("E", 0x0012, "Harf"), ("F", 0x0021, "Harf"),
    ("G", 0x0022, "Harf"), ("H", 0x0023, "Harf"), ("I", 0x0017, "Harf"),
    ("J", 0x0024, "Harf"), ("K", 0x0025, "Harf"), ("L", 0x0026, "Harf"),
    ("M", 0x0032, "Harf"), ("N", 0x0031, "Harf"), ("O", 0x0018, "Harf"),
    ("P", 0x0019, "Harf"), ("Q", 0x0010, "Harf"), ("R", 0x0013, "Harf"),
    ("S", 0x001F, "Harf"), ("T", 0x0014, "Harf"), ("U", 0x0016, "Harf"),
    ("V", 0x002F, "Harf"), ("W", 0x0011, "Harf"), ("X", 0x002D, "Harf"),
    ("Y", 0x0015, "Harf"), ("Z", 0x002C, "Harf"),
    # Türkçe Harfler / Karakterler
    ("Ç", 0x0034, "Harf"), ("Ğ", 0x001A, "Harf"), ("İ", 0x0028, "Harf"),
    ("Ö", 0x0033, "Harf"), ("Ş", 0x0027, "Harf"), ("Ü", 0x001B, "Harf"),
    # Rakamlar (Üst Sıra)
    ("0", 0x000B, "Rakam"), ("1", 0x0002, "Rakam"), ("2", 0x0003, "Rakam"),
    ("3", 0x0004, "Rakam"), ("4", 0x0005, "Rakam"), ("5", 0x0006, "Rakam"),
    ("6", 0x0007, "Rakam"), ("7", 0x0008, "Rakam"), ("8", 0x0009, "Rakam"),
    ("9", 0x000A, "Rakam"),
    # Numpad
    ("Num Lock", 0x0045, "Numpad"),
    ("Numpad 0", 0x0052, "Numpad"), ("Numpad 1", 0x004F, "Numpad"),
    ("Numpad 2", 0x0050, "Numpad"), ("Numpad 3", 0x0051, "Numpad"),
    ("Numpad 4", 0x004B, "Numpad"), ("Numpad 5", 0x004C, "Numpad"),
    ("Numpad 6", 0x004D, "Numpad"), ("Numpad 7", 0x0047, "Numpad"),
    ("Numpad 8", 0x0048, "Numpad"), ("Numpad 9", 0x0049, "Numpad"),
    ("Numpad /", 0xE035, "Numpad"), ("Numpad *", 0x0037, "Numpad"),
    ("Numpad -", 0x004A, "Numpad"), ("Numpad +", 0x004E, "Numpad"),
    ("Numpad .", 0x0053, "Numpad"),
    # Multimedya Tuşları
    ("Ses Kısma", 0xE02E, "Medya"),
    ("Ses Açma", 0xE030, "Medya"),
    ("Sessiz", 0xE020, "Medya"),
    ("Oynat / Duraklat", 0xE022, "Medya"),
    ("Durdur", 0xE024, "Medya"),
    ("Önceki Parça", 0xE010, "Medya"),
    ("Sonraki Parça", 0xE019, "Medya"),
]

SCANCODE_TO_LABEL = {code: name for name, code, _ in SCANCODE_DATABASE}

QT_KEY_TO_SCANCODE = {
    Qt.Key.Key_F1: 0x003B, Qt.Key.Key_F2: 0x003C, Qt.Key.Key_F3: 0x003D,
    Qt.Key.Key_F4: 0x003E, Qt.Key.Key_F5: 0x003F, Qt.Key.Key_F6: 0x0040,
    Qt.Key.Key_F7: 0x0041, Qt.Key.Key_F8: 0x0042, Qt.Key.Key_F9: 0x0043,
    Qt.Key.Key_F10: 0x0044, Qt.Key.Key_F11: 0x0057, Qt.Key.Key_F12: 0x0058,
    Qt.Key.Key_F13: 0x0064, Qt.Key.Key_F14: 0x0065, Qt.Key.Key_F15: 0x0066,
    Qt.Key.Key_F16: 0x0067, Qt.Key.Key_F17: 0x0068, Qt.Key.Key_F18: 0x0069,
    Qt.Key.Key_F19: 0x006A, Qt.Key.Key_F20: 0x006B, Qt.Key.Key_F21: 0x006C,
    Qt.Key.Key_F22: 0x006D, Qt.Key.Key_F23: 0x006E, Qt.Key.Key_F24: 0x006F,
    Qt.Key.Key_Escape: 0x0001, Qt.Key.Key_Return: 0x001C, Qt.Key.Key_Enter: 0xE01C,
    Qt.Key.Key_Tab: 0x000F, Qt.Key.Key_Backspace: 0x000E, Qt.Key.Key_Space: 0x0039,
    Qt.Key.Key_CapsLock: 0x003A,
    Qt.Key.Key_Insert: 0xE052, Qt.Key.Key_Delete: 0xE053,
    Qt.Key.Key_Home: 0xE047, Qt.Key.Key_End: 0xE04F,
    Qt.Key.Key_PageUp: 0xE049, Qt.Key.Key_PageDown: 0xE051,
    Qt.Key.Key_Up: 0xE048, Qt.Key.Key_Down: 0xE050,
    Qt.Key.Key_Left: 0xE04B, Qt.Key.Key_Right: 0xE04D,
    Qt.Key.Key_Print: 0xE037, Qt.Key.Key_ScrollLock: 0x0046, Qt.Key.Key_Pause: 0x0045,
    Qt.Key.Key_VolumeDown: 0xE02E, Qt.Key.Key_VolumeUp: 0xE030, Qt.Key.Key_VolumeMute: 0xE020,
    Qt.Key.Key_MediaPlay: 0xE022, Qt.Key.Key_MediaStop: 0xE024,
    Qt.Key.Key_MediaPrevious: 0xE010, Qt.Key.Key_MediaNext: 0xE019,
}
for _i, _ch in enumerate("1234567890"):
    QT_KEY_TO_SCANCODE[getattr(Qt.Key, f"Key_{_ch}")] = 0x0002 + _i if _ch != '0' else 0x000B
for _ch, _code in [
    ('A', 0x001E), ('B', 0x0030), ('C', 0x002E), ('D', 0x0020), ('E', 0x0012),
    ('F', 0x0021), ('G', 0x0022), ('H', 0x0023), ('I', 0x0017), ('J', 0x0024),
    ('K', 0x0025), ('L', 0x0026), ('M', 0x0032), ('N', 0x0031), ('O', 0x0018),
    ('P', 0x0019), ('Q', 0x0010), ('R', 0x0013), ('S', 0x001F), ('T', 0x0014),
    ('U', 0x0016), ('V', 0x002F), ('W', 0x0011), ('X', 0x002D), ('Y', 0x0015),
    ('Z', 0x002C)
]:
    QT_KEY_TO_SCANCODE[getattr(Qt.Key, f"Key_{_ch}")] = _code


class KeyboardRemapEngine:
    REG_KEY = r"SYSTEM\CurrentControlSet\Control\Keyboard Layout"
    VAL_NAME = "Scancode Map"

    @classmethod
    def load_mappings(cls):
        mappings = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls.REG_KEY, 0, winreg.KEY_READ) as key:
                data, val_type = winreg.QueryValueEx(key, cls.VAL_NAME)
                if val_type == winreg.REG_BINARY and len(data) >= 16:
                    count = int.from_bytes(data[8:12], byteorder="little")
                    offset = 12
                    for _ in range(count - 1):
                        if offset + 4 <= len(data):
                            target = int.from_bytes(data[offset:offset+2], byteorder="little")
                            source = int.from_bytes(data[offset+2:offset+4], byteorder="little")
                            mappings.append((source, target))
                            offset += 4
        except OSError:
            pass
        return mappings

    @classmethod
    def save_mappings(cls, mappings):
        try:
            if not mappings:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls.REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    try:
                        winreg.DeleteValue(key, cls.VAL_NAME)
                    except OSError:
                        pass
                return True
            count = len(mappings) + 1
            buffer = bytearray(8)
            buffer.extend(count.to_bytes(4, byteorder="little"))
            for src, tgt in mappings:
                buffer.extend(tgt.to_bytes(2, byteorder="little"))
                buffer.extend(src.to_bytes(2, byteorder="little"))
            buffer.extend(b"\x00\x00\x00\x00")
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls.REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, cls.VAL_NAME, 0, winreg.REG_BINARY, bytes(buffer))
            return True
        except Exception as exc:
            try:
                from core.system import append_runtime_diagnostic
                append_runtime_diagnostic(f"Scancode Map save error: {exc}")
            except Exception:
                pass
            return False

    @classmethod
    def delete_mapping(cls, orig_sc: int) -> bool:
        mappings = cls.load_mappings()
        new_mappings = [(o, t) for o, t in mappings if o != orig_sc]
        return cls.save_mappings(new_mappings)

    @classmethod
    def add_or_update_mapping(cls, orig_sc: int, target_sc: int) -> bool:
        mappings = cls.load_mappings()
        new_mappings = [(o, t) for o, t in mappings if o != orig_sc]
        new_mappings.append((orig_sc, target_sc))
        return cls.save_mappings(new_mappings)

    @classmethod
    def edit_mapping(cls, old_orig_sc: int, new_orig_sc: int, target_sc: int) -> bool:
        mappings = cls.load_mappings()
        new_mappings = [(o, t) for o, t in mappings if o != old_orig_sc and o != new_orig_sc]
        new_mappings.append((new_orig_sc, target_sc))
        return cls.save_mappings(new_mappings)

    @classmethod
    def get_label(cls, scancode):
        if scancode == 0x0000:
            return "Devre Dışı / Sustur"
        return SCANCODE_TO_LABEL.get(scancode, f"0x{scancode:04X}")

    @classmethod
    def is_win_space_disabled(cls):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, "DisabledHotkeys")
                return " " in str(val)
        except OSError:
            return False

    @classmethod
    def set_win_space_disabled(cls, disabled):
        p = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, p) as key:
                val = ""
                try:
                    val, _ = winreg.QueryValueEx(key, "DisabledHotkeys")
                    val = str(val)
                except OSError:
                    val = ""
                if disabled:
                    if " " not in val:
                        val += " "
                else:
                    val = val.replace(" ", "")
                if val:
                    winreg.SetValueEx(key, "DisabledHotkeys", 0, winreg.REG_SZ, val)
                else:
                    try:
                        winreg.DeleteValue(key, "DisabledHotkeys")
                    except OSError:
                        pass
            try:
                with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\Explorer") as lm_key:
                    if disabled:
                        winreg.SetValueEx(lm_key, "DisabledHotkeys", 0, winreg.REG_SZ, " ")
                    else:
                        try:
                            winreg.DeleteValue(lm_key, "DisabledHotkeys")
                        except OSError:
                            pass
            except OSError:
                pass
            return True
        except Exception as exc:
            try:
                from core.system import append_runtime_diagnostic
                append_runtime_diagnostic(f"DisabledHotkeys error: {exc}")
            except Exception:
                pass
            return False


def apply_sticky_keys_fix(enable_sticky=False):
    class STICKYKEYS(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.c_uint), ('dwFlags', ctypes.c_uint)]
    class TOGGLEKEYS(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.c_uint), ('dwFlags', ctypes.c_uint)]
    class FILTERKEYS(ctypes.Structure):
        _fields_ = [
            ('cbSize', ctypes.c_uint), ('dwFlags', ctypes.c_uint),
            ('iWaitMSec', ctypes.c_uint), ('iDelayMSec', ctypes.c_uint),
            ('iRepeatMSec', ctypes.c_uint), ('iBounceMSec', ctypes.c_uint)
        ]

    SPI_SETSTICKYKEYS = 0x003B
    SPI_SETTOGGLEKEYS = 0x0035
    SPI_SETFILTERKEYS = 0x0033
    SPIF_UPDATEINIFILE = 0x0001
    SPIF_SENDCHANGE = 0x0002
    flags = SPIF_UPDATEINIFILE | SPIF_SENDCHANGE

    if enable_sticky:
        sk_flags, tk_flags, fk_flags = 510, 58, 126
        hotkey_val = "1"
    else:
        sk_flags, tk_flags, fk_flags = 506, 58, 122
        hotkey_val = "0"

    hives = [
        (winreg.HKEY_CURRENT_USER, r"Control Panel\Accessibility"),
        (winreg.HKEY_USERS, r".DEFAULT\Control Panel\Accessibility"),
    ]
    for h, base_path in hives:
        try:
            with winreg.CreateKeyEx(h, f"{base_path}\\StickyKeys", 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "Flags", 0, winreg.REG_SZ, str(sk_flags))
                winreg.SetValueEx(k, "HotKeyActive", 0, winreg.REG_SZ, hotkey_val)
                winreg.SetValueEx(k, "ConfirmHotKey", 0, winreg.REG_SZ, "0")
                winreg.SetValueEx(k, "HotKeySound", 0, winreg.REG_SZ, "0")
            with winreg.CreateKeyEx(h, f"{base_path}\\Keyboard Response", 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "Flags", 0, winreg.REG_SZ, str(fk_flags))
                winreg.SetValueEx(k, "HotKeyActive", 0, winreg.REG_SZ, hotkey_val)
                winreg.SetValueEx(k, "ConfirmHotKey", 0, winreg.REG_SZ, "0")
                winreg.SetValueEx(k, "HotKeySound", 0, winreg.REG_SZ, "0")
            with winreg.CreateKeyEx(h, f"{base_path}\\ToggleKeys", 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "Flags", 0, winreg.REG_SZ, str(tk_flags))
                winreg.SetValueEx(k, "HotKeyActive", 0, winreg.REG_SZ, hotkey_val)
                winreg.SetValueEx(k, "ConfirmHotKey", 0, winreg.REG_SZ, "0")
                winreg.SetValueEx(k, "HotKeySound", 0, winreg.REG_SZ, "0")
        except Exception:
            pass

    try:
        sk = STICKYKEYS(cbSize=ctypes.sizeof(STICKYKEYS), dwFlags=sk_flags)
        ctypes.windll.user32.SystemParametersInfoW(SPI_SETSTICKYKEYS, ctypes.sizeof(STICKYKEYS), ctypes.byref(sk), flags)
        tk = TOGGLEKEYS(cbSize=ctypes.sizeof(TOGGLEKEYS), dwFlags=tk_flags)
        ctypes.windll.user32.SystemParametersInfoW(SPI_SETTOGGLEKEYS, ctypes.sizeof(TOGGLEKEYS), ctypes.byref(tk), flags)
        fk = FILTERKEYS(cbSize=ctypes.sizeof(FILTERKEYS), dwFlags=fk_flags, iWaitMSec=0, iDelayMSec=0, iRepeatMSec=0, iBounceMSec=0)
        ctypes.windll.user32.SystemParametersInfoW(SPI_SETFILTERKEYS, ctypes.sizeof(FILTERKEYS), ctypes.byref(fk), flags)
    except Exception:
        pass
