"""
WinKit - Core DPI Test Engine Module
Performs real browser TLS/HTTP simulation, deep packet inspection testing,
strategy probing (Zapret v1/v2), and diagnostic report generation.
"""

import os
import re
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional

from core.constants import CREATE_NO_WINDOW
from core.system import get_documents_directory, get_winkit_data_directory


def get_dpi_report_path() -> Path:
    return get_winkit_data_directory() / "winkit_dpitester.txt"


def run_dpi_test(
    zapret_ver: str,
    domains: List[str],
    scan_level: str,
    test_http: bool,
    test_tls12: bool,
    test_tls13: bool,
    log_callback: Callable[[List[tuple]], None],
    cancel_check: Optional[Callable[[], bool]] = None,
    custom_source_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Kapsamlı DPI bypass stratejilerini test eder.
    log_callback: [("metin", "renk_kodu"), ...] formatında segmentleri alır.
    """
    report_buffer = []

    def emit_log(segments):
        if log_callback:
            log_callback(segments)
        line_text = "".join(text for text, _ in segments)
        report_buffer.append(line_text)

    def is_cancelled():
        return bool(cancel_check and cancel_check())

    try:
        subprocess.run(
            ["netsh", "interface", "tcp", "set", "global", "timestamps=enabled"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )

        base_dir = Path(__file__).resolve().parent.parent
        source_dir = custom_source_dir or (base_dir / "zapret")
        install_dir = get_documents_directory() / "Zapret"

        if zapret_ver == "v1":
            winws_exe = source_dir / "winws.exe"
            if not winws_exe.is_file():
                winws_exe = install_dir / "winws.exe"
        else:
            winws_exe = source_dir / "winws2.exe"
            if not winws_exe.is_file():
                winws_exe = install_dir / "winws2.exe"
            if not winws_exe.is_file():
                winws_exe = source_dir / "winws.exe"

        if not winws_exe.is_file():
            emit_log([
                ("• ", "#8C9BA8"),
                ("HATA: ", "#FF5C6B"),
                (f"Zapret motoru ({winws_exe.name}) bulunamadi!\n", "#E7ECF2"),
            ])
            return {"success": False, "error": "Zapret binary not found", "working": []}

        lua_dir = source_dir / "lua"
        if not lua_dir.is_dir():
            lua_dir = install_dir / "lua"

        lua_init_args = []
        if zapret_ver == "v2" and lua_dir.is_dir():
            lib_f = lua_dir / "zapret-lib.lua"
            anti_f = lua_dir / "zapret-antidpi.lua"
            if lib_f.is_file():
                lua_init_args.append(f'--lua-init=@"{lib_f}"')
            if anti_f.is_file():
                lua_init_args.append(f'--lua-init=@"{anti_f}"')

        emit_log([
            ("================================================================\n", "#00B4D8"),
            (f"   WINkit DPI TEST ARACI (Zapret {zapret_ver.upper()})\n", "#00B4D8"),
            ("   Gercek Tarayici Simulasyonu & Derin DPI Analizi\n", "#8B96A2"),
            ("================================================================\n", "#00B4D8"),
        ])
        emit_log([
            ("> Hedef Alan Adlari : ", "#C9D0D7"),
            (", ".join(domains) + "\n", "#FFD166"),
            ("> Tarama Seviyesi   : ", "#C9D0D7"),
            (f"{scan_level}\n", "#55D67A"),
            ("> Test Motoru       : ", "#C9D0D7"),
            (f"{winws_exe.name}\n\n", "#55D67A"),
        ])

        if zapret_ver == "v1":
            http_strategies_all = [
                {"Name": "HTTP: Hostcase", "Args": "--wf-tcp=80 --hostcase", "Level": "BASIC"},
                {"Name": "HTTP: Methodeol", "Args": "--wf-tcp=80 --methodeol", "Level": "BASIC"},
                {"Name": "HTTP: Domcase", "Args": "--wf-tcp=80 --domcase", "Level": "SMART"},
                {"Name": "HTTP: Fake ts=-1000", "Args": "--wf-tcp=80 --dpi-desync=fake --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000", "Level": "BASIC"},
                {"Name": "HTTP: Fake autottl=-2,3-20", "Args": "--wf-tcp=80 --dpi-desync=fake --dpi-desync-autottl=-2:3-20", "Level": "BASIC"},
                {"Name": "HTTP: Fake badsum", "Args": "--wf-tcp=80 --dpi-desync=fake --dpi-desync-fooling=badsum", "Level": "SMART"},
                {"Name": "HTTP: Fake md5sig", "Args": "--wf-tcp=80 --dpi-desync=fake --dpi-desync-fooling=md5sig", "Level": "BASIC"},
                {"Name": "HTTP: Split2 pos=1", "Args": "--wf-tcp=80 --dpi-desync=split2 --dpi-desync-split-pos=1", "Level": "BASIC"},
                {"Name": "HTTP: Split2 pos=host", "Args": "--wf-tcp=80 --dpi-desync=split2 --dpi-desync-split-pos=host", "Level": "SMART"},
                {"Name": "HTTP: Disorder2 pos=1", "Args": "--wf-tcp=80 --dpi-desync=disorder2 --dpi-desync-split-pos=1", "Level": "SMART"},
                {"Name": "HTTP: Fake ts + split2 pos=1", "Args": "--wf-tcp=80 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=1", "Level": "SMART"},
                {"Name": "HTTP: Fake autottl + split2 pos=1", "Args": "--wf-tcp=80 --dpi-desync=fake,split2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=1", "Level": "DEEP"},
                {"Name": "HTTP: Multisplit pos=1,midsld", "Args": "--wf-tcp=80 --dpi-desync=multisplit --dpi-desync-split-pos=1,midsld", "Level": "DEEP"},
            ]
            tls_strategies_all = [
                {"Name": "TLS: Fake ts=-1000", "Args": "--wf-tcp=443 --dpi-desync=fake --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000", "Level": "BASIC"},
                {"Name": "TLS: Fake ts=-1000 + split2 pos=1", "Args": "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=1", "Level": "BASIC"},
                {"Name": "TLS: Fake ts=-1000 + split2 pos=2", "Args": "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=2", "Level": "BASIC"},
                {"Name": "TLS: Fake ts=-1000 + split2 pos=1,midsld", "Args": "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=1,midsld", "Level": "BASIC"},
                {"Name": "TLS: Fake ts=-1000 + split2 pos=2,midsld", "Args": "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=2,midsld", "Level": "SMART"},
                {"Name": "TLS: Fake ts=-1000 + disorder2 pos=1,midsld", "Args": "--wf-tcp=443 --dpi-desync=fake,disorder2 --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=1,midsld", "Level": "SMART"},
                {"Name": "TLS: Fake ts=-1000 + multisplit pos=1,midsld", "Args": "--wf-tcp=443 --dpi-desync=fake,multisplit --dpi-desync-fooling=ts --dpi-desync-ts-increment=-1000 --dpi-desync-split-pos=1,midsld", "Level": "SMART"},
                {"Name": "TLS: Fake autottl=-2,3-20", "Args": "--wf-tcp=443 --dpi-desync=fake --dpi-desync-autottl=-2:3-20", "Level": "BASIC"},
                {"Name": "TLS: Fake autottl=-1,2-20", "Args": "--wf-tcp=443 --dpi-desync=fake --dpi-desync-autottl=-1:2-20", "Level": "SMART"},
                {"Name": "TLS: Fake autottl=-2,3-20 + split2 pos=1", "Args": "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=1", "Level": "BASIC"},
                {"Name": "TLS: Fake autottl=-2,3-20 + split2 pos=1,midsld", "Args": "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=1,midsld", "Level": "BASIC"},
                {"Name": "TLS: Fake autottl=-2,3-20 + split2 pos=2,midsld", "Args": "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=2,midsld", "Level": "SMART"},
                {"Name": "TLS: Fake autottl=-2,3-20 + disorder2 pos=1,midsld", "Args": "--wf-tcp=443 --dpi-desync=fake,disorder2 --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=1,midsld", "Level": "SMART"},
                {"Name": "TLS: Fake autottl=-2,3-20 + multisplit pos=1,midsld", "Args": "--wf-tcp=443 --dpi-desync=fake,multisplit --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=1,midsld", "Level": "SMART"},
                {"Name": "TLS: Fakedsplit autottl=-2,3-20 pos=midsld", "Args": "--wf-tcp=443 --dpi-desync=fakedsplit --dpi-desync-autottl=-2:3-20 --dpi-desync-split-pos=midsld", "Level": "SMART"},
                {"Name": "TLS: Fake md5sig", "Args": "--wf-tcp=443 --dpi-desync=fake --dpi-desync-fooling=md5sig", "Level": "BASIC"},
                {"Name": "TLS: Fake md5sig + split2 pos=2", "Args": "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=md5sig --dpi-desync-split-pos=2", "Level": "BASIC"},
                {"Name": "TLS: Fake md5sig + split2 pos=1,midsld", "Args": "--wf-tcp=443 --dpi-desync=fake,split2 --dpi-desync-fooling=md5sig --dpi-desync-split-pos=1,midsld", "Level": "SMART"},
                {"Name": "TLS: Fake badsum", "Args": "--wf-tcp=443 --dpi-desync=fake --dpi-desync-fooling=badsum", "Level": "SMART"},
                {"Name": "TLS: Split2 pos=1", "Args": "--wf-tcp=443 --dpi-desync=split2 --dpi-desync-split-pos=1", "Level": "BASIC"},
                {"Name": "TLS: Split2 pos=2", "Args": "--wf-tcp=443 --dpi-desync=split2 --dpi-desync-split-pos=2", "Level": "BASIC"},
                {"Name": "TLS: Split2 pos=midsld", "Args": "--wf-tcp=443 --dpi-desync=split2 --dpi-desync-split-pos=midsld", "Level": "SMART"},
                {"Name": "TLS: Disorder2 pos=1", "Args": "--wf-tcp=443 --dpi-desync=disorder2 --dpi-desync-split-pos=1", "Level": "BASIC"},
                {"Name": "TLS: Disorder2 pos=midsld", "Args": "--wf-tcp=443 --dpi-desync=disorder2 --dpi-desync-split-pos=midsld", "Level": "SMART"},
                {"Name": "TLS: Multisplit pos=1,midsld", "Args": "--wf-tcp=443 --dpi-desync=multisplit --dpi-desync-split-pos=1,midsld", "Level": "SMART"},
                {"Name": "TLS: Multidisorder pos=1,midsld", "Args": "--wf-tcp=443 --dpi-desync=multidisorder --dpi-desync-split-pos=1,midsld", "Level": "DEEP"},
            ]
        else:
            http_strategies_all = [
                {"Name": "HTTP: Hostcase", "Args": "--wf-tcp-out=80 --payload=http_req --lua-desync=http_hostcase", "Level": "BASIC"},
                {"Name": "HTTP: Methodeol", "Args": "--wf-tcp-out=80 --payload=http_req --lua-desync=http_methodeol", "Level": "BASIC"},
                {"Name": "HTTP: Domcase", "Args": "--wf-tcp-out=80 --payload=http_req --lua-desync=http_domcase", "Level": "SMART"},
                {"Name": "HTTP: Fake tcp_ts=-1000", "Args": "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:tcp_ts=-1000", "Level": "BASIC"},
                {"Name": "HTTP: Fake autottl=-2,3-20", "Args": "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:ip_autottl=-2,3-20", "Level": "BASIC"},
                {"Name": "HTTP: Fake tcp_md5", "Args": "--wf-tcp-out=80 --payload=http_req --lua-desync=fake:blob=fake_default_http:tcp_md5", "Level": "BASIC"},
                {"Name": "HTTP: Multisplit pos=1,midsld", "Args": "--wf-tcp-out=80 --payload=http_req --lua-desync=multisplit:pos=1,midsld", "Level": "SMART"},
            ]
            tls_strategies_all = [
                {"Name": "TLS: Fake tcp_ts=-1000", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000", "Level": "BASIC"},
                {"Name": "TLS: Fake tcp_ts=-1000 + multisplit pos=2", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=multisplit:pos=2", "Level": "BASIC"},
                {"Name": "TLS: Fake tcp_ts=-1000 + multisplit pos=1,midsld", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=multisplit:pos=1,midsld", "Level": "BASIC"},
                {"Name": "TLS: Fake tcp_ts=-1000 + multisplit pos=2,midsld", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=multisplit:pos=2,midsld", "Level": "SMART"},
                {"Name": "TLS: Fake tcp_ts=-1000 + split pos=1", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=split:pos=1", "Level": "SMART"},
                {"Name": "TLS: Fake tcp_ts=-1000 + multidisorder pos=1,midsld", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000 --lua-desync=multidisorder:pos=1,midsld", "Level": "SMART"},
                {"Name": "TLS: Fake tcp_ts=-1000 + tls_mod=rnd,dupsid", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000:tls_mod=rnd,dupsid", "Level": "SMART"},
                {"Name": "TLS: Fake tcp_ts=-1000 + tls_mod=rnd,dupsid,padencap:repeats=2", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_ts=-1000:tls_mod=rnd,dupsid,padencap:repeats=2", "Level": "SMART"},
                {"Name": "TLS: Fake autottl=-2,3-20", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-2,3-20", "Level": "BASIC"},
                {"Name": "TLS: Fake autottl=-1,2-20", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-1,2-20", "Level": "SMART"},
                {"Name": "TLS: Fake autottl=-2,3-20 + dupsid + multisplit pos=2", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-2,3-20:tls_mod=rnd,dupsid --lua-desync=multisplit:pos=2", "Level": "BASIC"},
                {"Name": "TLS: Fake autottl=-2,3-20 + dupsid/padencap + multisplit midsld", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-2,3-20:tls_mod=rnd,dupsid,padencap:repeats=2 --lua-desync=multisplit:pos=1,midsld", "Level": "BASIC"},
                {"Name": "TLS: Fake autottl=-2,3-20 + multidisorder pos=1,midsld", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:ip_autottl=-2,3-20:tls_mod=rnd,dupsid --lua-desync=multidisorder:pos=1,midsld", "Level": "SMART"},
                {"Name": "TLS: Fakedsplit autottl=-2,3-20 pos=midsld", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fakedsplit:ip_autottl=-2,3-20:pos=midsld", "Level": "SMART"},
                {"Name": "TLS: Fake tcp_md5", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_md5", "Level": "BASIC"},
                {"Name": "TLS: Fake tcp_md5 + multisplit pos=2", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=fake:blob=fake_default_tls:tcp_md5:tls_mod=rnd,dupsid:repeats=1 --lua-desync=multisplit:pos=2", "Level": "BASIC"},
                {"Name": "TLS: Multisplit pos=1,midsld", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multisplit:pos=1,midsld", "Level": "SMART"},
                {"Name": "TLS: Multidisorder pos=1,midsld", "Args": "--wf-tcp-out=443 --payload=tls_client_hello --lua-desync=multidisorder:pos=1,midsld", "Level": "DEEP"},
            ]

        def filter_strats(s_list, lvl):
            if lvl == "BASIC":
                return [s for s in s_list if s["Level"] == "BASIC"]
            elif lvl == "SMART":
                return [s for s in s_list if s["Level"] in ("BASIC", "SMART")]
            return s_list

        http_strats = filter_strats(http_strategies_all, scan_level)
        tls_strats = filter_strats(tls_strategies_all, scan_level)

        def stop_zapret_proc():
            subprocess.run(
                ["taskkill", "/F", "/IM", "winws.exe", "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
            subprocess.run(
                ["taskkill", "/F", "/IM", "winws2.exe", "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
            time.sleep(0.15)

        def curl_test(dom, proto):
            ciphers = "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384"
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
            cmd = [
                "curl.exe", "-s", "-o", "NUL",
                "-w", "%{http_code}",
                "--connect-timeout", "2",
                "--max-time", "3",
                "-A", ua,
            ]
            if proto == "HTTP":
                cmd.append(f"http://{dom}")
            elif proto == "HTTPS TLS 1.2":
                cmd.extend(["--tlsv1.2", "--tls-max", "1.2", "--ciphers", ciphers, f"https://{dom}"])
            elif proto == "HTTPS TLS 1.3":
                cmd.extend(["--tlsv1.3", "--tls-max", "1.3", f"https://{dom}"])
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", creationflags=CREATE_NO_WINDOW, timeout=4, check=False)
                out = res.stdout.strip()
                return out if out else "000"
            except Exception:
                return "000"

        def is_success(code):
            return bool(re.match(r"^(200|204|301|302|303|304|307|308|400|401|403|404|405|500|502|503|530)$", str(code).strip()))

        working_results = []
        total_target_count = 0

        for dom in domains:
            if is_cancelled():
                break
            test_protocols = []
            if test_http:
                test_protocols.append(("HTTP", http_strats))
            if test_tls12:
                test_protocols.append(("HTTPS TLS 1.2", tls_strats))
            if test_tls13:
                test_protocols.append(("HTTPS TLS 1.3", tls_strats))

            for proto, strats in test_protocols:
                if is_cancelled():
                    break
                total_target_count += 1
                emit_log([
                    ("----------------------------------------------------------------\n", "#3A444E"),
                    (f" Hedef: {dom} [{proto}] (Toplam {len(strats)} Strateji Denenecek)\n", "#00B4D8"),
                    ("----------------------------------------------------------------\n", "#3A444E"),
                ])

                stop_zapret_proc()
                nobypass = curl_test(dom, proto)
                if is_success(nobypass):
                    emit_log([("[+] ", "#55D67A"), (f"Bypass OLMADAN zaten aciliyor (HTTP Kodu: {nobypass})\n", "#55D67A")])
                else:
                    emit_log([("[-] ", "#FFD166"), (f"Engel Algilandi (Bypass kapali HTTP Kodu: {nobypass})\n", "#FFD166")])

                target_working = 0
                for idx, strat in enumerate(strats, 1):
                    if is_cancelled():
                        stop_zapret_proc()
                        emit_log([("\n[!] ", "#FFB86C"), ("Test kullanıcı tarafından iptal edildi.\n", "#FFB86C")])
                        break

                    strat_name = strat["Name"]
                    strat_args = strat["Args"]

                    emit_log([("  ", "#C9D0D7"), (f"[{idx}/{len(strats)}] {strat_name} ... ", "#AEB8C3")])
                    stop_zapret_proc()

                    full_cmd = [str(winws_exe)]
                    if zapret_ver == "v2":
                        full_cmd.extend(["--wf-l3=ipv4", *lua_init_args])
                    else:
                        full_cmd.extend(["--wf-l3=ipv4"])
                    
                    full_cmd.extend(strat_args.split())

                    proc = None
                    try:
                        proc = subprocess.Popen(full_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                    except Exception as e:
                        emit_log([(f"Calistirilamadi ({e})\n", "#FF5C6B")])
                        continue

                    time.sleep(0.40)
                    res1 = curl_test(dom, proto)
                    res2 = "000"
                    if is_success(res1):
                        time.sleep(0.15)
                        res2 = curl_test(dom, proto)

                    stop_zapret_proc()

                    if is_success(res1) and is_success(res2):
                        target_working += 1
                        emit_log([(f"ÇALIŞTI! (HTTP: {res1}, {res2})\n", "#55D67A")])
                        working_results.append({
                            "Domain": dom,
                            "Proto": proto,
                            "Name": strat_name,
                            "Args": strat_args,
                            "Code": f"{res1}, {res2}",
                        })
                    else:
                        emit_log([(f"Başarısız ({res1}, {res2})\n", "#717D88")])

                summary_color = "#55D67A" if target_working > 0 else "#FF5C6B"
                emit_log([(f"\n>>> {dom} [{proto}] Sonuçları: {target_working} / {len(strats)} strateji ÇALIŞTI.\n\n", summary_color)])

        stop_zapret_proc()

        # Özet Rapor
        emit_log([
            ("\n================================================================\n", "#00B4D8"),
            ("                  TÜM TEST SONUÇLARI ÖZETİ                      \n", "#00B4D8"),
            ("================================================================\n", "#00B4D8"),
        ])

        if working_results:
            emit_log([("[+] ÇALIŞAN STRATEJİLER LİSTESİ:\n", "#55D67A")])
            for r in working_results:
                emit_log([
                    (f"  • {r['Domain']} [{r['Proto']}] -> {r['Name']} (HTTP: {r['Code']})\n", "#E7ECF2")
                ])
        else:
            emit_log([("[!] Hiçbir strateji başarılı olamadı.\n", "#FF5C6B")])

        emit_log([
            ("\n================================================================\n", "#00B4D8"),
            ("         ORTAK KURAL KESİŞİMİ (COMMON WORKING STRATEGIES)       \n", "#00B4D8"),
            ("================================================================\n", "#00B4D8"),
        ])

        https_working = [r for r in working_results if "HTTPS" in r["Proto"]]
        if https_working:
            strat_counts = {}
            for r in https_working:
                name = r["Name"]
                strat_counts[name] = strat_counts.get(name, 0) + 1

            target_https_count = len(domains) * ((1 if test_tls12 else 0) + (1 if test_tls13 else 0))
            universal = [name for name, count in strat_counts.items() if count >= target_https_count]

            if universal:
                emit_log([("\n[***] TÜM HEDEFLERDE VE PROTOKOLLERDE ÇALIŞAN EVRENSEL STRATEJİLER:\n", "#55D67A")])
                for u in universal:
                    ex_strat = next(r for r in https_working if r["Name"] == u)
                    emit_log([
                        (f"  ★ {u}\n", "#55D67A"),
                        (f"     Parametre: {winws_exe.name} {ex_strat['Args']}\n\n", "#FFD166"),
                    ])
            else:
                emit_log([
                    ("\n[!] Tüm hedeflerde ortak çalışan tek bir kural bulunamadı.\n", "#FFD166"),
                    ("    En çok çalışan kurallar:\n", "#E7ECF2"),
                ])
                sorted_strats = sorted(strat_counts.items(), key=lambda x: x[1], reverse=True)
                for name, count in sorted_strats[:3]:
                    emit_log([(f"  • {name} ({count}/{target_https_count} başarılı)\n", "#FFD166")])

        try:
            report_file = get_dpi_report_path()
            report_file.write_text("".join(report_buffer), encoding="utf-8", errors="replace")
            emit_log([
                ("\n[+] Ayrıntılı test raporu kaydedildi: ", "#00B4D8"),
                (f"{report_file}\n", "#55D67A"),
            ])
        except Exception as e:
            emit_log([(f"\n[!] Rapor dosyaya kaydedilemedi: {e}\n", "#FF5C6B")])

        return {"success": True, "working": working_results, "cancelled": is_cancelled()}

    except Exception as exc:
        emit_log([("• ", "#8C9BA8"), ("HATA: ", "#FF5C6B"), (f"{exc}\n", "#E7ECF2")])
        return {"success": False, "error": str(exc), "working": []}
