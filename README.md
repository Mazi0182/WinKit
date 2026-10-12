# WinKit 🚀

<div align="center">

<img src="winkit_logo.png" alt="WinKit Logo" width="160" />

### Yeni Nesil Windows 10 & 11 Sistem İyileştirme, Debloat, Anti-DPI ve İnce Ayar Paketi

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?style=for-the-badge&logo=windows)](https://www.microsoft.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-PyQt6-41CD52?style=for-the-badge&logo=qt)](https://riverbankcomputing.com/software/pyqt/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

</div>

---

## 📌 WinKit Nedir?

**WinKit**, Windows 10 ve Windows 11 işletim sistemlerinde telemetriyi en aza indirmek, gereksiz arka plan servislerini (bloatware) kalıcı olarak tasfiye etmek, DPI tabanlı internet sansürlerini aşmak ve sistem performansını maksimize etmek için geliştirilmiş hepsi-bir-arada sistem yönetim ve ince ayar aracıdır.

Modern **PyQt6** grafik arayüzü ve düşük seviyeli Windows API (`winreg`, `ctypes`, `WMI`, `TrustedInstaller` token impersonation) motoruyla donatılan WinKit, sistem üzerinde cerrahi kontrol sağlar.

---

## 📸 Ekran Görüntüleri (Screenshots)

### 1. ISO Aracı & Katılımsız Kurulum Medyası Düzenleyici
Windows 11 ISO dosyalarını doğrudan modifiye ederek OOBE ekranındaki internet ve Microsoft hesabı zorunluluklarını atlar; TPM 2.0, Secure Boot ve donanım gereksinimlerini otomatik olarak devre dışı bırakır.

<div align="center">
  <img src="1.png" alt="WinKit ISO Aracı" width="850" />
</div>

<br/>

### 2. Debloat & Gelişmiş Sistem Optimizasyonu
Cortana, OneDrive, Copilot, MSN servisleri gibi gereksiz Windows uygulamalarını StateRepository veritabanı seviyesinde temizler. Oyun gecikmelerini azaltmak için FSO, MPO ve özel güç planlarını devreye alır.

<div align="center">
  <img src="2.png" alt="WinKit Debloat & Sistem Optimizasyonu" width="850" />
</div>

<br/>

### 3. Anti-DPI & Güvenli DNS (Zapret ve DoH)
DPI (Derin Paket İnceleme) tabanlı sansür ve engellemeleri aşmak için Zapret V1 & V2 motorunu Windows servisi olarak kurar. Ağ bağdaştırıcılarına Cloudflare DNS-over-HTTPS (DoH) şablonlarını otomatik işler.

<div align="center">
  <img src="3.png" alt="WinKit Anti-DPI ve Güvenli DNS" width="850" />
</div>

<br/>

### 4. Tuş Dönüştürücü (Donanım Seviyesinde Tuş Eşleme)
Klavye tuşlarını Windows çekirdeğinde (`Scancode Map`) düşük gecikmeyle yeniden haritalandırır veya istenmeyen kısayolları (örneğin dil değiştirme tuş kombinasyonlarını) devre dışı bırakır.

<div align="center">
  <img src="4.png" alt="WinKit Tuş Dönüştürücü" width="850" />
</div>

<br/>

### 5. Geri Yükleme & Orijinal Varsayılanlara Dönüş
Uygulanan sistem değişikliklerini, Defender ilkelerini, Windows Update kısıtlamalarını ve ağ yapılandırmasını tek tıkla orijinal Windows varsayılanlarına döndürür; Sistem Geri Yükleme Noktası oluşturur.

<div align="center">
  <img src="5.png" alt="WinKit Geri Yükleme" width="850" />
</div>

<br/>

### 6. Windows Lisanslama & Durum Teşhisi
WMI SoftwareLicensingProduct üzerinden Windows aktivasyon ve dijital lisans durumunu gerçek zamanlı sorgular.

<div align="center">
  <img src="6.png" alt="WinKit Windows Lisanslama" width="850" />
</div>

---

## ⚡ Özellikler Tablosu

| Modül | Açıklama |
| :--- | :--- |
| **Sistem Debloat** | AppX paketleri, bulut önerileri, Başlat menüsü reklam pinleri ve telemetriyi temizler. |
| **Oyun & Performans** | FSO (Fullscreen Optimizations), MPO (Multi-Plane Overlay) ve Ultra Performans Güç Planı. |
| **Windows Defender** | Kurcalamaya Karşı Koruma uyumlu iki kademeli servis yönetimi ve SecHealthUI koruması. |
| **Anti-DPI (Zapret)** | Bol-van Zapret (winws/winws2) motoru ile sansürsüz, hızlı ve şifreli DoH internet erişimi. |
| **ISO Özelleştirme** | Otomatik `autounattend.xml` enjeksiyonu ile sıfır kurulumda kullanıcı hesabı ve donanım bypass. |
| **Tuş Haritalama** | Windows Registry tabanlı sıfır gecikmeli tuş eşleme motoru. |
| **Geri Yükleme** | Yapılan ayarları tek tıkla geri alma ve Sistem Geri Yükleme Noktası yönetimi. |

---

## 🚀 Başlangıç ve Çalıştırma

### Gereksinimler
- **İşletim Sistemi:** Windows 10 (1809+) veya Windows 11 (21H2 - 24H2)
- **Yetki:** Yönetici (Administrator) İzinleri
- **Geliştirme İçin:** Python 3.10+ (veya 3.12 önerilir)

### 1. Depoyu Klonlama ve Çalıştırma
```powershell
# Depoyu klonlayın
git clone https://github.com/Mazi0182/WinKit.git
cd WinKit

# Gerekli kütüphaneleri yükleyin (PyQt6)
pip install -r requirements.txt
# veya çift tıklayarak: kur_gereksinimler.bat

# Yönetici olarak çalıştırın
python winkit_main.py
```

### 2. Tek Parça EXE Olarak Derleme (Standalone Executable)
Projeyi bağımsız tek bir çalıştırılabilir dosya (`dist\winkit.exe`) haline getirmek için:
```powershell
compile.bat
```

---

## 💻 Komut Satırı Arayüzü (CLI)

WinKit, arayüzsüz (headless) ve otomasyon scriptlerinde de tam yetkiyle çalışabilir:

```powershell
# Yardım menüsünü listeler
python winkit_main.py --help

# Sessiz modda debloat ve temizliği yürütür
python winkit_main.py --debloat

# DNS ve DoH ayarlarını DHCP varsayılanlarına sıfırlar
python winkit_main.py --test-dns-reset
```

---

## 🤝 Üçüncü Taraf Araçlar ve Teşekkürler (Third-Party Credits)

WinKit, belirli sistem işlevlerini yerine getirmek amacıyla aşağıdaki saygın açık kaynak ve ücretsiz araçlardan faydalanmakta olup, bu projelerin geliştiricilerine ve hak sahiplerine teşekkür eder:

- **[O&O ShutUp10++](https://www.oo-software.com/en/shutup10)** — *O&O Software GmbH.* Windows gizlilik ve telemetri yapılandırması için kullanılan ücretsiz (Freeware) güvenlik aracıdır.
- **[oscdimg](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/oscdimg-command-line-options)** — *Microsoft Corporation.* Windows ADK bünyesinde yer alan önyüklenebilir Windows ISO oluşturma aracıdır.
- **[7-Zip](https://www.7-zip.org/)** — *Igor Pavlov.* Yüksek sıkıştırma oranına sahip açık kaynaklı (GNU LGPL) arşiv yönetim aracıdır.
- **[Zapret & WinDivert](https://github.com/bol-van/zapret)** — *bol-van & Basil Vadimovich.* DPI engellemelerini aşmak için geliştirilmiş açık kaynaklı ağ paket manipülasyon motorudur.
- **[Microsoft Activation Scripts (MAS)](https://github.com/massgravel/Microsoft-Activation-Scripts)** — *Massgrave Team.* Açık kaynaklı Windows lisans durumu ve SPP yöntemleri referans alınmıştır.

---

## ⚠️ Yasal Uyarı & Sorumluluk Reddi (Disclaimer)

WinKit; Windows işletim sisteminin hassas bileşenlerine, kayıt defteri anahtarlarına ve sistem servislerine doğrudan müdahale eden güçlü bir yönetim aracıdır.

- Yazılım **"olduğu gibi" (AS IS)** sunulmaktadır.
- Bu yazılımın kullanımından doğabilecek veri kaybı, sistem kararsızlığı veya beklenmedik sistem davranışlarından kullanıcı sorumludur.
- Herhangi bir optimizasyon uygulamadan önce **Sistem Geri Yükleme Noktası** oluşturmanız önemle tavsiye edilir.

---

## 📜 Lisans

Bu proje [MIT Lisansı](LICENSE) kapsamında lisanslanmıştır. Detaylar için `LICENSE` dosyasına bakabilirsiniz.
