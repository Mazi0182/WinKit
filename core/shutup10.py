"""
WinKit Core ShutUp10 Privacy Module
Handles O&O ShutUp10 config rule parsing, category translation, and Turkish localization.
"""

import re
from typing import List, Tuple

OOSU_CATEGORY_TR = {
    "Privacy": "Gizlilik",
    "Activity History and Clipboard": "Etkinlik ve Pano",
    "App Privacy": "Uygulama İzinleri",
    "Security": "Güvenlik",
    "Microsoft Edge (new Chromium)": "Microsoft Edge",
    "Microsoft Edge (new version based on Chromium)": "Microsoft Edge",
    "Microsoft Edge legacy": "Edge Legacy",
    "Microsoft Edge (legacy version)": "Eski Microsoft Edge",
    "Synchronization of Windows Settings": "Windows Eşitleme",
    "Cortana": "Cortana",
    "Cortana (Personal Assistant)": "Cortana",
    "Copilot & Windows AI": "Copilot ve Windows AI",
    "Location Services": "Konum Servisleri",
    "User Behavior": "Kullanıcı Deneyimi",
    "Windows Update": "Windows Update",
    "Windows Explorer": "Dosya Gezgini",
    "Microsoft Defender and SpyNet": "Defender ve SpyNet",
    "Microsoft Defender and Microsoft SpyNet": "Defender ve SpyNet",
    "Lock Screen": "Kilit Ekranı",
    "Mobile Devices": "Mobil Cihazlar",
    "Search": "Arama",
    "Taskbar": "Görev Çubuğu",
    "Miscellaneous": "Diğer Ayarlar",
    "Gaming": "Oyun",
}

OOSU_TERM_TR = {
    "user account information": "kullanıcı hesabı bilgilerine",
    "voice activation when device is locked": "cihaz kilitliyken sesle etkinleştirmeye",
    "voice activation": "sesle etkinleştirmeye",
    "loosely coupled devices": "eşleştirilmiş cihazlara",
    "wireless connections": "kablosuz bağlantılara",
    "wireless technology": "kablosuz teknolojilere",
    "music libraries": "müzik kitaplıklarına",
    "downloads folder": "İndirilenler klasörüne",
    "the file system": "dosya sistemine",
    "call history": "arama geçmişine",
    "phone calls": "telefon aramalarına",
    "eye tracking": "göz izlemeye",
    "notifications": "bildirimlere",
    "microphone": "mikrofona",
    "calendar": "takvime",
    "camera": "kameraya",
    "contacts": "kişilere",
    "documents": "belgelere",
    "email": "e-postaya",
    "images": "resimlere",
    "messages": "mesajlara",
    "movements": "hareket verilerine",
    "tasks": "görevlere",
    "videos": "videolara",
}

OOSU_EXACT_TR = {'Activate deferring of upgrades': 'Sürüm yükseltmelerini ertelemeyi etkinleştir', 'Allow user control of local AI features': 'Yerel yapay zekâ özelliklerinin kullanıcı tarafından yönetilmesine izin ver', 'Cortana and search are disallowed to use location': 'Cortana ve aramanın konum verilerine erişimini engelle', 'Disable "Meet now" in the task bar': 'Görev çubuğundaki Şimdi Toplan özelliğini kapat', 'Disable AI-generated themes': 'Yapay zekâ ile üretilen temaları kapat', 'Disable AI-powered history search': 'Yapay zekâ destekli geçmiş aramasını kapat', 'Disable AI-powered image fill in Microsoft Paint': 'Paint uygulamasındaki yapay zekâ dolgu özelliğini kapat', 'Disable Bing Chat eligibility in Windows Copilot': 'Windows Copilot içindeki Bing Chat uygunluğunu kapat', 'Disable Bing Chat on new tab page': 'Yeni sekmedeki Bing Chat özelliğini kapat', 'Disable Cocreator in Microsoft Paint': 'Paint uygulamasındaki Cocreator yapay zekâ özelliğini kapat', 'Disable Copilot access to page context': "Copilot'un sayfa içeriğine erişimini engelle", 'Disable Cortana above lock screen': 'Kilit ekranı üzerinde Cortana erişimini kapat', 'Disable Cortana in Microsoft Edge': 'Microsoft Edge içindeki Cortana entegrasyonunu kapat', 'Disable Edge Secure Network (built-in VPN)': 'Edge Güvenli Ağ özelliğini (yerleşik VPN) kapat', 'Disable Edge bar': 'Edge kenar çubuğunu kapat', 'Disable Enhanced Spell Checking': 'Gelişmiş çevrimiçi yazım denetimini kapat', 'Disable Input Personalization': 'Giriş kişiselleştirmeyi (yazma ve çizim verilerini) kapat', 'Disable Internet access of Windows Media Digital Rights Management (DRM)': 'Windows Media DRM internet erişimini kapat', 'Disable Inventory Collector': 'Donanım ve yazılım envanter toplayıcısını kapat', 'Disable Key Management Service Online Activation': 'KMS çevrimiçi lisans doğrulamasını kapat', 'Disable Microsoft Edge launch in the background': "Microsoft Edge'in arka planda başlatılmasını engelle", 'Disable Microsoft OneDrive': 'Microsoft OneDrive bulut eşitlemesini kapat', 'Disable Microsoft SpyNet membership': 'Microsoft SpyNet / Cloud Protection üyeliğini kapat', 'Disable NFC (Near Field Communication)': 'NFC (Yakın Alan İletişimi) teknolojisini kapat', 'Disable Network Connectivity Status Indicator': 'Ağ Bağlantısı Durum Göstergesi (NCSI) telemetrisini kapat', 'Disable OneDrive access to network before login': 'Oturum açılmadan önce OneDrive ağ erişimini engelle', 'Disable People icon in the taskbar': 'Görev çubuğundaki Kişiler simgesini kaldır', 'Disable Phone Link app': 'Telefon Bağlantısı uygulamasını kapat', 'Disable Sidebar in Microsoft Edge': 'Microsoft Edge kenar çubuğunu kapat', 'Disable SmartScreen Filter': 'SmartScreen filtresini kapat', 'Disable WiFi Direct': 'Wi-Fi Direct doğrudan bağlantı teknolojisini kapat', 'Disable Windows Copilot+ Recall': 'Windows Recall (ekran geçmişi kaydetme) özelliğini kapat', 'Disable Windows Error Reporting': 'Windows Hata Raporlama telemetrisini kapat', 'Disable Windows Geolocation Service': 'Windows Konum Belirleme Hizmetini kapat', 'Disable Windows Media Player Diagnostics': 'Windows Media Player tanılama verilerini kapat', 'Disable Windows Spotlight': 'Windows Spotlight (Öne Çıkanlar) kilit ekranı akışını kapat', 'Disable Windows Updates for other products (e.g. Microsoft Office)': 'Diğer Microsoft ürünleri (Office vb.) için güncellemeleri kapat', 'Disable Windows dynamic configuration and update rollouts': 'Windows dinamik yapılandırma ve otomatik özellik dağıtımlarını kapat', 'Disable Windows tracking of app starts': 'Windows uygulama başlatma takibini kapat', 'Disable Xbox Game Bar and Game DVR': 'Xbox Game Bar ve ekran kaydı motorunu kapat', 'Disable access to local language for browsers': 'Tarayıcıların yerel sistem diline erişimini engelle', 'Disable access to mobile devices': 'Mobil cihazlara erişimi kapat', 'Disable ads in Windows Explorer/OneDrive': 'Dosya Gezgini ve OneDrive içi öneri ve reklamları kapat', 'Disable advertisements via Bluetooth': 'Bluetooth üzerinden iletilen reklamları kapat', 'Disable and reset Advertising ID and info': 'Reklam Kimliğini kapat ve sıfırla', 'Disable and reset Cortana': "Cortana'yı kapat ve kişisel verileri sıfırla", 'Disable app access to calendar': 'Uygulamaların takvime erişimini kapat', 'Disable app access to call history': 'Uygulamaların arama geçmişine erişimini kapat', 'Disable app access to camera': 'Uygulamaların kameraya erişimini kapat', 'Disable app access to contacts': 'Uygulamaların kişilere erişimini kapat', 'Disable app access to device location': 'Uygulamaların cihaz konumuna erişimini kapat', 'Disable app access to diagnostics information': 'Uygulamaların tanılama verilerine erişimini kapat', 'Disable app access to documents': 'Uygulamaların Belgeler klasörüne erişimini kapat', 'Disable app access to downloads folder': 'Uygulamaların İndirilenler klasörüne erişimini kapat', 'Disable app access to email': 'Uygulamaların e-postalara erişimini kapat', 'Disable app access to eye tracking': 'Uygulamaların göz izleme donanımına erişimini kapat', 'Disable app access to images': 'Uygulamaların Resimler klasörüne erişimini kapat', 'Disable app access to loosely coupled devices': 'Uygulamaların eşleştirilmiş cihazlara erişimini kapat', 'Disable app access to messages': 'Uygulamaların SMS ve iletilere erişimini kapat', 'Disable app access to microphone': 'Uygulamaların mikrofona erişimini kapat', 'Disable app access to movements': 'Uygulamaların hareket sensörlerine erişimini kapat', 'Disable app access to music libraries': 'Uygulamaların Müzik kitaplığına erişimini kapat', 'Disable app access to notifications': 'Uygulamaların bildirimlere erişimini kapat', 'Disable app access to phone calls': 'Uygulamaların telefon aramalarına erişimini kapat', 'Disable app access to tasks': 'Uygulamaların görevler listesine erişimini kapat', 'Disable app access to the file system': 'Uygulamaların tüm dosya sistemine doğrudan erişimini kapat', 'Disable app access to use voice activation': 'Uygulamaların sesle etkinleştirme kullanmasını engelle', 'Disable app access to use voice activation when device is locked': 'Cihaz kilitliyken uygulamaların sesle etkinleştirilmesini engelle', 'Disable app access to user account information': 'Uygulamaların kullanıcı hesap bilgilerine erişimini kapat', 'Disable app access to videos': 'Uygulamaların Videolar klasörüne erişimini kapat', 'Disable app access to wireless connections': 'Uygulamaların kablosuz bağlantıları yönetmesini engelle', 'Disable app access to wireless technology': 'Uygulamaların kablosuz teknolojilere erişimini kapat', 'Disable app notifications': 'Uygulama bildirimlerini kapat', 'Disable application telemetry': 'Uygulama kullanım telemetrisini kapat', 'Disable automatic Windows Updates': 'Otomatik Windows Update güncellemelerini kapat', 'Disable automatic app updates through Windows Update': 'Mağaza uygulamalarının otomatik güncellenmesini kapat', 'Disable automatic completion of web addresses in address bar': 'Adres çubuğunda web adreslerinin otomatik tamamlanmasını kapat', 'Disable automatic download and update of map data': 'Harita verilerinin otomatik indirilip güncellenmesini kapat', "Disable automatic downloading manufacturers' apps and icons for devices": 'Cihazlar için üretici uygulamalarının ve simgelerinin otomatik indirilmesini kapat', 'Disable automatic driver updates through Windows Update': 'Windows Update üzerinden otomatik sürücü güncellemelerini kapat', 'Disable automatic installation of recommended Windows Store Apps': 'Önerilen Mağaza uygulamalarının otomatik yüklenmesini kapat', 'Disable automatic redirection from Internet Explorer to Microsoft Edge': "Internet Explorer'dan Edge'e otomatik yönlendirmeyi kapat", 'Disable automatic sign-in from web to browser': 'Web sitelerinden tarayıcıya otomatik oturum açmayı kapat', 'Disable backup of text messages into the cloud': 'Kısa mesajların buluta yedeklenmesini kapat', 'Disable biometrical features': 'Windows Hello biyometrik kimlik doğrulama özelliklerini kapat', 'Disable built-in AI APIs for websites': "Web siteleri için yerleşik yapay zekâ API'lerini engelle", 'Disable camera in logon screen': 'Kilit ve oturum açma ekranında kamerayı kapat', 'Disable check for saved payment methods by sites': 'Sitelerin kayıtlı ödeme yöntemlerini sorgulamasını engelle', 'Disable cloud search': 'Windows Arama bulut senkronizasyonunu kapat', 'Disable cloud-based tab services': 'Bulut tabanlı sekme ve geçmiş senkronizasyonunu kapat', 'Disable connecting the PC to mobile devices': 'Bilgisayarın mobil cihazlara bağlanmasını kapat', 'Disable content on new tab page': 'Yeni sekme sayfasındaki haber ve web içeriklerini kapat', 'Disable default browser campaigns': "Edge'i varsayılan tarayıcı yapma kampanyalarını kapat", 'Disable diagnostic data collection': 'Tanılama ve hata verisi toplamayı kapat', 'Disable diagnostic data from customizing user experiences': 'Tanılama verileriyle kullanıcı deneyimini özelleştirmeyi kapat', 'Disable diagnostic log collection': 'Tanılama günlüklerinin toplanmasını kapat', 'Disable display web results in Search': "Windows Arama'da Bing web sonuçlarını göstermeyi kapat", 'Disable download and updates of speech recognition and speech synthesis models': 'Konuşma tanıma ve sentezleme modellerinin indirilmesini kapat', 'Disable downloading of OneSettings configuration settings': 'OneSettings uzaktan yapılandırma indirmelerini kapat', 'Disable extension of Windows search with Bing': "Windows Arama'nın Bing ile genişletilmesini kapat", 'Disable feedback reminders': 'Windows geri bildirim anımsatıcılarını kapat', 'Disable form suggestions': 'Web formları otomatik önerilerini kapat', 'Disable fun facts, tips, tricks, and more on your lock screen': 'Kilit ekranındaki ipuçları, eğlenceli bilgiler ve önerileri kapat', 'Disable functionality to locate the system': 'Sistemin coğrafi konumunu belirleme işlevini kapat', 'Disable inline Compose feature': 'Tarayıcı içi yapay zekâ metin yazma (Compose) özelliğini kapat', 'Disable loading the start and new tab pages in the background': 'Başlangıç ve yeni sekme sayfalarının arka planda ön yüklenmesini kapat', 'Disable mobile broadband (cellular/WWAN)': 'Mobil geniş bant (hücresel veri / WWAN) bağlantısını kapat', 'Disable news and interests in the task bar': 'Görev çubuğundaki Haberler ve İlgi Alanlarını kapat', 'Disable notifications on lock screen': 'Kilit ekranında uygulama bildirimlerinin gösterilmesini kapat', 'Disable occassionally showing app suggestions in Start menu': 'Başlat menüsünde ara sıra gösterilen uygulama önerilerini kapat', 'Disable online speech recognition': 'Çevrimiçi bulut konuşma tanıma hizmetini kapat', 'Disable optional updates (including preview updates)': 'Önizleme dahil isteğe bağlı güncellemeleri kapat', 'Disable page prediction': 'Web sayfalarını önceden tahmin edip yüklemeyi kapat', 'Disable password reveal button': 'Parola giriş alanlarındaki parolanı göster (göz) düğmesini kapat', 'Disable personalizing advertising, search, news and other services': 'Kişiselleştirilmiş reklam, arama ve haber hizmetlerini kapat', 'Disable preload of pages for faster browsing and searching': 'Hızlı gezinme için sayfaların önceden yüklenmesini kapat', 'Disable prompts to make Edge the default browser': "Edge'i varsayılan tarayıcı yapma uyarılarını kapat", 'Disable recommendations in settings': 'Windows Ayarlar uygulamasındaki öneri ve tavsiyeleri kapat', 'Disable recordings of user activity': 'Kullanıcı etkinlik geçmişi kayıtlarını kapat', 'Disable remote assistance connections to this computer': 'Bu bilgisayara uzaktan yardım bağlantılarını kapat', 'Disable remote connections to this computer': 'Bu bilgisayara Uzak Masaüstü bağlantılarını kapat', 'Disable reporting of malware infection information': "Kötü amaçlı yazılım bulaşma bilgilerinin Microsoft'a raporlanmasını kapat", 'Disable saving passwords for websites': 'Tarayıcıda web siteleri için parola kaydetmeyi kapat', 'Disable scripting functionality to locate the system': 'Web sitelerinin betikler üzerinden cihaz konumunu bulmasını engelle', 'Disable search and website suggestions': 'Arama ve web sitesi otomatik önerilerini kapat', 'Disable search box in task bar': 'Görev çubuğu arama kutusunu kapat', 'Disable search with AI in search box': 'Arama kutusundaki yapay zekâ arama özelliğini kapat', 'Disable sending URLs from apps to Windows Store': "Uygulamalardan Windows Store'a web adresi gönderilmesini kapat", 'Disable sensors for locating the system and its orientation': 'Konum ve yön belirleme sensörlerini kapat', 'Disable sharing of handwriting data': 'El yazısı tanıma verilerinin Microsoft ile paylaşılmasını kapat', 'Disable sharing of handwriting error reports': "El yazısı hata raporlarının Microsoft'a gönderilmesini kapat", 'Disable shopping assistant': 'Alışveriş ve kupon bulma yardımcısını kapat', 'Disable shopping assistant in Microsoft Edge': 'Microsoft Edge alışveriş yardımcısını kapat', 'Disable showing search history': 'Arama kutusunda arama geçmişini göstermeyi kapat', 'Disable showing suggested content in the Settings app': 'Ayarlar uygulamasında önerilen içerikleri göstermeyi kapat', 'Disable showing suggestions for using mobile devices with Windows': 'Windows ile mobil cihaz kullanımına ilişkin önerileri kapat', 'Disable site safety services for more information about a visited website': 'Ziyaret edilen web siteleri için güvenlik telemetrisi sorgulamasını kapat', 'Disable sites saving protected media licenses on my device': 'Web sitelerinin cihaza korumalı medya lisansı kaydetmesini engelle', 'Disable spotlight experiences and recommendations': 'Windows Spotlight deneyim ve önerilerini kapat', 'Disable startup boost': 'Microsoft Edge başlangıç hızlandırma arka plan sürecini kapat', 'Disable storage of clipboard history': 'Pano geçmişinin (Win+V) yerel olarak saklanmasını kapat', 'Disable storing and autocompleting of credit card data on websites': 'Web sitelerinde kredi kartı bilgilerinin saklanmasını ve otomatik doldurulmasını kapat', "Disable storing users' activity history": 'Kullanıcı etkinlik geçmişinin saklanmasını kapat', 'Disable submitting data samples to Microsoft': "Şüpheli dosya ve veri örneklerinin Microsoft'a gönderilmesini kapat", 'Disable suggestion of similar sites when website cannot be found': 'Web sitesi bulunamadığında benzer site önerilmesini kapat', 'Disable suggestions from local providers': 'Arama kutusunda yerel sağlayıcı önerilerini kapat', 'Disable suggestions in Start': 'Başlat menüsünde uygulama önerilerini kapat', 'Disable suggestions in the timeline': 'Zaman çizelgesinde (Timeline) önerileri kapat', 'Disable synchronization of accessibility settings': 'Erişilebilirlik ayarlarının cihazlar arasında eşitlenmesini kapat', 'Disable synchronization of advanced Windows settings': 'Gelişmiş Windows ayarlarının bulutla eşitlenmesini kapat', 'Disable synchronization of all settings': 'Tüm Windows ayarlarının Microsoft hesabıyla eşitlenmesini kapat', 'Disable synchronization of browser settings': 'Tarayıcı geçmişi ve ayarlarının eşitlenmesini kapat', 'Disable synchronization of credentials (passwords)': 'Kayıtlı parola ve kimlik bilgilerinin bulutla eşitlenmesini kapat', 'Disable synchronization of design settings': 'Tema ve tasarım ayarlarının bulutla eşitlenmesini kapat', 'Disable synchronization of language settings': 'Dil ve klavye tercihlerinin bulutla eşitlenmesini kapat', 'Disable telemetry': 'Windows telemetri ve arka plan veri toplamayı kapat', 'Disable text prediction in forms': 'Web formlarında metin tahminini kapat', 'Disable text suggestions when typing on the software keyboard': 'Dokunmatik ve ekran klavyesinde metin önerilerini kapat', 'Disable the Copilot button from the taskbar': 'Görev çubuğundaki Copilot düğmesini kaldır', 'Disable the Image Creator in Microsoft Paint': 'Paint uygulamasındaki Image Creator yapay zekâ görsel oluşturucusunu kapat', 'Disable the Microsoft Account Sign-In Button': 'Microsoft Hesabı ile oturum açma düğmesini gizle', 'Disable the Windows Copilot': 'Windows Copilot yapay zekâ asistanını tamamen kapat', 'Disable the Windows Customer Experience Improvement Program': 'Windows Müşteri Deneyimi Geliştirme Programını (CEIP) kapat', 'Disable the ability for apps to take screenshots': 'Uygulamaların otomatik ekran görüntüsü almasını engelle', 'Disable the ability for apps to take screenshots without borders': 'Uygulamaların kenarlık olmadan ekran görüntüsü almasını engelle', 'Disable the ability for desktop apps to take screenshots': 'Masaüstü uygulamalarının ekran görüntüsü almasını engelle', 'Disable the ability for desktop apps to take screenshots without margins': 'Masaüstü programlarının kenarlıksız ekran görüntüsü almasını engelle', 'Disable the desktop icon for information on "Windows Spotlight"': 'Masaüstündeki Windows Spotlight bilgi simgesini kaldır', 'Disable the possibility of suggesting to finish the setup of the device': 'Cihaz kurulumunu tamamlama önerisi bildirimlerini kapat', 'Disable the provision of recall functionality to all users': 'Recall işlevinin tüm kullanıcılar için sağlanmasını kapat', 'Disable the search highlights in the taskbar': 'Görev çubuğu aramasında öne çıkan görsel ve içerikleri kapat', 'Disable the standard app for the headset button': 'Kulaklık düğmesi için atanan varsayılan uygulamayı kapat', 'Disable the submission of user activities to Microsoft': 'Kullanıcı etkinliklerinin Microsoft bulutuna gönderilmesini kapat', 'Disable the transfer of the clipboard to other devices via the cloud': 'Pano içeriğinin bulut üzerinden diğer cihazlara aktarılmasını kapat', 'Disable tips, tricks, and suggestions when using Windows': 'Windows kullanım ipuçları ve önerilerini kapat', 'Disable tips, tricks, and suggestions while using Windows': 'Windows kullanımı sırasında çıkan ipuçlarını kapat', 'Disable tracking in the web': 'Web sitelerinde kullanıcı takibini (Do Not Track) engelle', 'Disable transmission of typing information': 'Klavye yazım alışkanlıkları bilgilerinin iletilmesini kapat', 'Disable typosquatting checker for site addresses': 'Yazım hatası içeren sahte alan adı (typosquatting) denetimini kapat', 'Disable unsolicited network traffic on the offline maps settings page': 'Çevrimdışı haritalar sayfasındaki istenmeyen ağ trafiğini kapat', 'Disable updates to the speech recognition and speech synthesis modules.': 'Konuşma tanıma ve sentezleme modülleri güncellemelerini kapat', 'Disable use of web service to resolve navigation errors': 'Ağ gezinme hatalarını çözmek için web hizmeti kullanımını kapat', 'Disable user feedback in toolbar': 'Araç çubuğundaki kullanıcı geri bildirim istemlerini kapat', 'Disable user steps recorder': 'Windows Sorun Adımları Kaydedicisini (PSR) kapat', 'Disable visual search': 'Görsel arama (resimle arama) özelliğini kapat', 'Disable web search from Windows Desktop Search': "Windows Arama'dan internette arama yapılmasını kapat", 'Disable wireless display (Miracast/WiDi)': 'Kablosuz ekran (Miracast / WiDi) yansıtma bağlantılarını kapat', 'Do not optimize web search results on the task bar for screen reader': 'Görev çubuğu web sonuçlarını ekran okuyucu için optimize etme', 'Do not show recently opened items in Jump Lists on "Start" or the taskbar': 'Başlat veya görev çubuğu atlama listelerinde son açılan öğeleri gösterme', 'Hide Adobe Acrobat subscription button': 'Adobe Acrobat abonelik düğmesini gizle', 'Hide Microsoft 365 Copilot chat icon': 'Microsoft 365 Copilot sohbet simgesini gizle', 'Hide Microsoft Rewards': 'Microsoft Rewards ödül bildirimlerini ve simgelerini gizle', 'Hide default top sites on new tab page': 'Yeni sekme sayfasındaki varsayılan popüler siteleri gizle', 'Hide first run experience and splash screen': 'İlk çalıştırma sihirbazını ve açılış ekranını gizle', 'Prohibit apps from running in the background': 'Uygulamaların arka planda çalışmasını engelle', 'Restrict Bluetooth pairing': 'Bluetooth eşleştirmesini güvenlik için sınırlandır'}

OOSU_PHRASE_TR = {
    "automatic redirection from Internet Explorer to Microsoft Edge": "Internet Explorer'dan Microsoft Edge'e otomatik yönlendirmeyi",
    "preload of pages for faster browsing and searching": "hızlı gezinme için sayfaların önceden yüklenmesini",
    "loading the start and new tab pages in the background": "başlangıç ve yeni sekme sayfalarının arka planda yüklenmesini",
    "suggestion of similar sites when website cannot be found": "site bulunamadığında benzer site önerilerini",
    "automatic download and update of map data": "harita verilerinin otomatik indirilip güncellenmesini",
    "sensors for locating the system and its orientation": "konum ve yön belirleme sensörlerini",
    "scripting functionality to locate the system": "konum belirleyen betik işlevini",
    "functionality to locate the system": "sistemin konumunu belirleme işlevini",
    "AI-powered history search": "yapay zekâ destekli geçmiş aramasını",
    "built-in AI APIs for websites": "siteler için yerleşik yapay zekâ API'lerini",
    "Copilot access to page context": "Copilot'un sayfa içeriğine erişimini",
    "AI-generated themes": "yapay zekâ ile oluşturulan temaları",
    "diagnostic data collection": "tanılama verisi toplamayı",
    "submitting data samples to Microsoft": "veri örneklerinin Microsoft'a gönderilmesini",
    "reporting of malware infection information": "zararlı yazılım bulaşma bilgilerinin bildirilmesini",
    "Microsoft SpyNet membership": "Microsoft SpyNet üyeliğini",
    "Network Connectivity Status Indicator": "Ağ Bağlantısı Durum Göstergesini",
    "occassionally showing app suggestions in Start menu": "Başlat menüsünde uygulama önerileri gösterilmesini",
    "showing suggested content in the Settings app": "Ayarlar uygulamasında önerilen içerikleri",
    "text suggestions when typing on the software keyboard": "ekran klavyesi yazım önerilerini",
    "sending URLs from apps to Windows Store": "uygulama adreslerinin Windows Store'a gönderilmesini",
    "storage of clipboard history": "pano geçmişinin kaydedilmesini",
    "synchronization of accessibility settings": "erişilebilirlik ayarlarının eşitlenmesini",
    "synchronization of advanced Windows settings": "gelişmiş Windows ayarlarının eşitlenmesini",
    "synchronization of browser settings": "tarayıcı ayarlarının eşitlenmesini",
    "synchronization of credentials (passwords)": "kimlik bilgilerinin eşitlenmesini",
    "synchronization of design settings": "tasarım ayarlarının eşitlenmesini",
    "synchronization of language settings": "dil ayarlarının eşitlenmesini",
    "synchronization of all settings": "tüm ayarların eşitlenmesini",
    "Microsoft Edge launch in the background": "Microsoft Edge'in arka planda başlatılmasını",
    "OneDrive access to network before login": "oturum öncesinde OneDrive ağ erişimini",
    "optional updates (including preview updates)": "önizleme dahil isteğe bağlı güncellemeleri",
    "automatic Windows Updates": "otomatik Windows güncellemelerini",
    "Xbox Game Bar and Game DVR": "Xbox Game Bar ve Game DVR'ı",
    "wireless display (Miracast/WiDi)": "kablosuz ekranı (Miracast/WiDi)",
    "mobile broadband (cellular/WWAN)": "mobil geniş bandı (hücresel/WWAN)",
    "camera in logon screen": "oturum açma ekranındaki kamerayı",
    "advertisements via Bluetooth": "Bluetooth üzerinden reklamları",
    "access to local language for browsers": "tarayıcıların yerel dil bilgisine erişimini",
    "notifications on lock screen": "kilit ekranı bildirimlerini",
    "password reveal button": "parola gösterme düğmesini",
    "Microsoft Account Sign-In Button": "Microsoft hesabı oturum açma düğmesini",
    "cloud-based tab services": "bulut tabanlı sekme hizmetlerini",
    "shopping assistant in Microsoft Edge": "Microsoft Edge alışveriş yardımcısını",
    "shopping assistant": "alışveriş yardımcısını",
    "Sidebar in Microsoft Edge": "Microsoft Edge yan panelini",
    "Bing Chat on new tab page": "yeni sekmedeki Bing Chat'i",
    "content on new tab page": "yeni sekme içeriğini",
    "default browser campaigns": "varsayılan tarayıcı kampanyalarını",
    "startup boost": "başlangıç hızlandırmayı",
    "Enhanced Spell Checking": "gelişmiş yazım denetimini",
    "inline Compose feature": "satır içi Yazma özelliğini",
    "tracking in the web": "web izlemeyi",
    "form suggestions": "form önerilerini",
    "search and website suggestions": "arama ve site önerilerini",
    "suggestions from local providers": "yerel sağlayıcı önerilerini",
    "showing search history": "arama geçmişinin gösterilmesini",
    "visual search": "görsel aramayı",
    "page prediction": "sayfa tahminini",
    "user feedback in toolbar": "araç çubuğu geri bildirimini",
    "Edge bar": "Edge çubuğunu",
    "Microsoft OneDrive": "Microsoft OneDrive'ı",
    "Windows Geolocation Service": "Windows Konum Belirleme Hizmetini",
    "WiFi Direct": "WiFi Direct'i",
    "NFC (Near Field Communication)": "NFC'yi",
    "app notifications": "uygulama bildirimlerini",
    "recommendations in settings": "Ayarlar önerilerini",
    "SmartScreen Filter": "SmartScreen filtresini",
    "prompts to make Edge the default browser": "Edge'i varsayılan tarayıcı yapma istemlerini",
    "Edge Secure Network (built-in VPN)": "Edge Güvenli Ağ özelliğini (yerleşik VPN)",
    "Cortana in Microsoft Edge": "Microsoft Edge içindeki Cortana'yı",
    "automatic sign-in from web to browser": "web sitelerinden tarayıcıya otomatik oturum açmayı",
    "text prediction in forms": "formlardaki metin tahminini",
    "saving passwords for websites": "siteler için parola kaydetmeyi",
    "typosquatting checker for site addresses": "benzer yazımlı sahte adres denetimini",
    "unsolicited network traffic on the offline maps settings page": "çevrimdışı harita ayarlarındaki istenmeyen ağ trafiğini",
    "use of web service to resolve navigation errors": "gezinme hatalarında web hizmeti kullanımını",
    "the standard app for the headset button": "kulaklık düğmesinin varsayılan uygulamasını",
    "ads in Windows Explorer/OneDrive": "Dosya Gezgini ve OneDrive reklamlarını",
    "spotlight experiences and recommendations": "Spotlight deneyimlerini ve önerilerini",
    "preload of pages for faster browsing and searching": "hızlı gezinme ve arama için sayfa ön yüklemeyi",
    "sites saving protected media licenses on my device": "sitelerin korumalı medya lisanslarını cihaza kaydetmesini",
    "safety services for more information about a visited website": "ziyaret edilen siteler için güvenlik bilgi hizmetlerini",
    "automatic completion of web addresses in address bar": "adres çubuğunda web adreslerini otomatik tamamlamayı",
    "check for saved payment methods by sites": "sitelerin kayıtlı ödeme yöntemlerini denetlemesini",
    "wireless display": "kablosuz ekranı",
    "mobile broadband": "mobil geniş bandı",
}

def load_oosu_config_rules(config_path: str) -> List[Tuple[str, str, str, str]]:
    """O&O dışa aktarımındaki bütün seçenekleri, sırasını ve +/- durumunu okur."""
    pattern = re.compile(
        r"^([A-Z]\d{3})\s+([+-])\s+#\s*(.*?)\s+\(Category:\s*(.*?)\)\s*$"
    )
    rules = []
    try:
        with open(config_path, "r", encoding="utf-8-sig", errors="replace") as cfg:
            for raw_line in cfg:
                match = pattern.match(raw_line.strip())
                if not match:
                    continue
                code, sign, description, category = match.groups()
                rules.append((
                    code,
                    sign,
                    description.strip(),
                    OOSU_CATEGORY_TR.get(category.strip(), category.strip()),
                ))
    except OSError:
        return []
    return rules

def localize_oosu_description(description: str) -> str:
    """Tüm OOSU kurallarını pürüzsüz Türkçeye çevirir."""
    desc_clean = description.strip()
    if desc_clean in OOSU_EXACT_TR:
        return OOSU_EXACT_TR[desc_clean]
    
    prefix = "Disable app access to "
    if desc_clean.startswith(prefix):
        raw_target = desc_clean[len(prefix):].strip()
        target = OOSU_TERM_TR.get(raw_target, raw_target)
        return f"Uygulamaların {target} erişimini kapat"
        
    if desc_clean.startswith("Disable "):
        subject = desc_clean[len("Disable "):].strip()
        if subject in OOSU_PHRASE_TR:
            return f"{OOSU_PHRASE_TR[subject]} kapat"
            
    return OOSU_EXACT_TR.get(desc_clean, desc_clean)

def get_detailed_shutup_tooltip(code: str, desc: str, category: str) -> str:
    """Her kural için ne işe yaradığı ve kapatıldığında ne olacağını açıklayan profesyonel tooltip."""
    d_clean = desc.strip()
    c_clean = category.strip()

    # Kategori bazlı detaylı açıklamalar
    cat_details = {
        "Uygulama İzinleri": (
            "Uygulamaların bu donanım bileşenine veya veri alanına arka planda ve doğrudan erişmesini engeller.\n"
            "• Ne Yapar: Belirtilen sistem kaynağına (kamera, mikrofon, konum, kişiler vb.) Windows Store ve masaüstü uygulamalarının erişim izinlerini kısıtlar.\n"
            "• Kapatılırsa: İlgili donanım veya veriyi kullanması gereken uygulamalar (örneğin sesli görüşme veya harita uygulamaları) erişim hatası verebilir veya izin isteme penceresi açabilir."
        ),
        "Gizlilik": (
            "Windows'un kullanıcı kullanım alışkanlıklarını, hata günlüklerini ve tanılama verilerini kaydetmesini engeller.\n"
            "• Ne Yapar: Tanılama, envanter, el yazısı takibi ve kullanım geçmişi verilerinin toplanmasını durdurur.\n"
            "• Kapatılırsa: Microsoft'a kullanıcı davranış veya hata verisi gitmez; kişiselleştirilmiş ipuçları ve öneriler devre dışı kalır. Gizlilik en üst düzeye çıkar."
        ),
        "Etkinlik ve Pano": (
            "Kullanıcı etkinlik geçmişinin ve pano verilerinin buluta veya yerel hafızaya kaydedilmesini önler.\n"
            "• Ne Yapar: Son açılan dosyalar, zaman çizelgesi kayıtları ve bulut pano (Ctrl+C geçmişi) senkronizasyonunu yönetir.\n"
            "• Kapatılırsa: Panoya kopyalanan hassas veriler (parolalar vb.) cihazlar arasında senkronize edilmez ve geçmişte saklanmaz."
        ),
        "Güvenlik": (
            "Güvenlik telemetrisini ve şüpheli veri gönderme mekanizmalarını yönetir.\n"
            "• Ne Yapar: Hata raporlama, DRM internet doğrulaması ve uzaktan tanılama işlevlerini sınırlar.\n"
            "• Kapatılırsa: Sistem dışarıyla gereksiz tanılama trafiği oluşturmaz; ağ kullanımı ve gizlilik korunur."
        ),
        "Microsoft Edge": (
            "Microsoft Edge tarayıcısının arka plan izleme, telemetri, başlangıç hızlandırma ve yapay zekâ entegrasyonlarını kapatır.\n"
            "• Ne Yapar: Edge'in kapalıyken bile arka planda çalışmasını, sayfa ön yüklemesini ve arama telemetrisini durdurur.\n"
            "• Kapatılırsa: Edge arka planda RAM ve CPU tüketmez, gezinme geçmişi Microsoft sunucularına gönderilmez."
        ),
        "Windows Eşitleme": (
            "Windows ayarlarının Microsoft hesabınız üzerinden buluta yedeklenmesini ve eşitlenmesini kapatır.\n"
            "• Ne Yapar: Tema, şifreler, dil ve erişilebilirlik tercihlerinizin diğer Windows cihazlarınıza otomatik aktarılmasını engeller.\n"
            "• Kapatılırsa: Ayarlarınız sadece bu yerel bilgisayarda geçerli kalır; Microsoft sunucularında saklanmaz."
        ),
        "Cortana ve Yapay Zeka": (
            "Windows Copilot, Recall ve Cortana yapay zekâ servislerini devre dışı bırakır.\n"
            "• Ne Yapar: Ekran görüntüsü geçmişi analizi (Recall), yapay zekâ sohbet asistanı ve çevrimiçi konuşma tanımayı kapatır.\n"
            "• Kapatılırsa: Cihazınızda ekran görüntüsü veya tuş geçmişi taranmaz; yapay zekâ arka plan servisleri durur, CPU ve pil tasarrufu sağlanır."
        ),
        "Copilot ve Windows AI": (
            "Windows Copilot, Recall ve Cortana yapay zekâ servislerini devre dışı bırakır.\n"
            "• Ne Yapar: Ekran görüntüsü geçmişi analizi (Recall), yapay zekâ sohbet asistanı ve çevrimiçi konuşma tanımayı kapatır.\n"
            "• Kapatılırsa: Cihazınızda ekran görüntüsü veya tuş geçmişi taranmaz; yapay zekâ arka plan servisleri durur, CPU ve pil tasarrufu sağlanır."
        ),
        "Konum Servisleri": (
            "Windows Konum Belirleme Hizmetini ve konum sensörlerini tamamen kapatır.\n"
            "• Ne Yapar: GPS, Wi-Fi ve IP tabanlı coğrafi konum tespitini durdurur.\n"
            "• Kapatılırsa: Web siteleri ve uygulamalar fiziksel konumunuzu öğrenemez; Harita ve Hava Durumu gibi uygulamalarda konumu elle seçmeniz gerekir."
        ),
        "Windows Update": (
            "Windows Update'in arka plandaki agresif güncelleme ve sürücü indirme davranışlarını kısıtlar.\n"
            "• Ne Yapar: Otomatik sürücü güncellemelerini, P2P bant genişliği paylaşımını ve önizleme yamalarını kapatır.\n"
            "• Kapatılırsa: Oyun veya iş sırasında beklenmeyen yeniden başlatmalar ve bant genişliği kayıpları engellenir."
        ),
        "Arama": (
            "Windows Arama kutusundaki Bing web sonuçlarını, bulut aramasını ve reklam vurgularını kaldırır.\n"
            "• Ne Yapar: Başlat menüsü aramasını yalnızca yerel dosya ve programlarla sınırlar.\n"
            "• Kapatılırsa: Arama gecikmesi sıfırlanır; yazdığınız her harf Microsoft Bing sunucularına gönderilmez."
        ),
        "Kilit Ekranı": (
            "Kilit ekranındaki reklamları, ipuçlarını ve Windows Spotlight arka plan akışını kapatır.\n"
            "• Ne Yapar: Kilit ekranında Microsoft önerileri ve sponsorlu içerik gösterilmesini engeller.\n"
            "• Kapatılırsa: Sade, dikkat dağıtmayan ve internet tüketmeyen temiz bir kilit ekranı elde edilir."
        ),
        "Mobil Cihazlar": (
            "Bilgisayarın mobil cihazlara ve telefonlara uzaktan bağlanma servislerini durdurur.\n"
            "• Ne Yapar: Telefon Bağlantısı ve cihazlar arası etkinlik aktarımını kapatır.\n"
            "• Kapatılırsa: Arka planda çalışan CDP ve PhoneLink servisleri durur, ağ trafiği ve RAM serbest kalır."
        ),
    }

    explanation = cat_details.get(
        c_clean,
        "Bu ayar ilgili Windows özelliğini devre dışı bırakarak arka plan veri trafiğini ve telemetri kaydını engeller.\n"
        "• Ne Yapar: Sistemin ilgili bileşenini kullanıcı gizliliği lehine yapılandırır.\n"
        "• Kapatılırsa: İlgili servisin çevrimiçi veya arka plan işlevi durdurulur; gizlilik ve sistem performansı artar."
    )

    return f"【{code}】 {d_clean}\nKategori: {c_clean}\n\n{explanation}"
