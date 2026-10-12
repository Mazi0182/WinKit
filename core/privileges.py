"""
WinKit Core Privileges Module
Provides elevated privilege execution:
- Process token privileges (SeDebugPrivilege, SeTakeOwnershipPrivilege, etc.)
- SYSTEM token impersonation / scheduled execution
- TrustedInstaller execution via service token duplication
"""

import os
import sys
import ctypes
import tempfile
import subprocess
import secrets
import time
import base64
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000

def enable_process_privileges():
    """Enable critical privileges for current process using ntdll RtlAdjustPrivilege."""
    ntdll = ctypes.windll.ntdll
    # 9: SeTakeOwnershipPrivilege
    # 17: SeBackupPrivilege
    # 18: SeRestorePrivilege
    # 20: SeDebugPrivilege
    # 29: SeImpersonatePrivilege
    privileges = [9, 17, 18, 20, 29]
    enabled = ctypes.c_bool()
    results = {}
    for priv in privileges:
        status = ntdll.RtlAdjustPrivilege(priv, True, False, ctypes.byref(enabled))
        results[priv] = (status == 0)
    return results

def run_powershell_checked(script: str, timeout: int = 120) -> str:
    """
    PowerShell betiğini UTF-8 çıktıyla çalıştırır, hata durumunda RuntimeError fırlatır.
    Win32 komut satırı sınırlarını aşmamak için 3000 karakterden uzun betikleri geçici dosyadan yürütür.
    """
    full_script = (
        "$ProgressPreference = 'SilentlyContinue'\n"
        "$WarningPreference = 'SilentlyContinue'\n"
        "$InformationPreference = 'SilentlyContinue'\n"
        "$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
        "try {\n& {\n" + script + "\n}\n} catch {\n"
        "[Console]::Error.WriteLine([string]$_.Exception.Message)\n"
        "exit 1\n}\n"
    )
    temp_ps1 = None
    try:
        if len(full_script) > 3000:
            fd, temp_ps1 = tempfile.mkstemp(prefix="winkit_run_", suffix=".ps1")
            with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                f.write(full_script)
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-OutputFormat", "Text",
                "-ExecutionPolicy", "Bypass",
                "-File", temp_ps1,
            ]
        else:
            encoded = base64.b64encode(full_script.encode("utf-16le")).decode("ascii")
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-OutputFormat", "Text",
                "-ExecutionPolicy", "Bypass",
                "-EncodedCommand", encoded,
            ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=timeout,
            check=False,
        )
    finally:
        if temp_ps1 and os.path.exists(temp_ps1):
            try:
                os.unlink(temp_ps1)
            except OSError:
                pass
    if result.returncode != 0:
        raw = (result.stderr + "\n" + result.stdout).strip()
        lines = [
            line.strip()
            for line in raw.splitlines()
            if line.strip() and not line.strip().startswith(("#<", "<Objs", "<Obj", "<TN", "<T>", "<MS>", "<I64", "<PR", "<AV", "<SD", "</Obj", "</MS", "</TN", "</PR"))
        ]
        detail = lines[-1] if lines else f"PowerShell kodu {result.returncode}"
        raise RuntimeError(detail[:260])
    return result.stdout


def run_powershell_as_system(script_text: str, timeout: int = 120) -> tuple[bool, str]:
    """Execute PowerShell script under NT AUTHORITY\\SYSTEM using an ephemeral scheduled task."""
    enable_process_privileges()
    task_name = f"WinKit_SysTask_{secrets.token_hex(6)}"
    
    prog_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "WinKit" / "SystemTasks"
    prog_data.mkdir(parents=True, exist_ok=True)
    
    # Ensure SYSTEM has access
    try:
        subprocess.run(
            [
                "icacls.exe", str(prog_data), "/inheritance:e",
                "/grant:r", "*S-1-5-18:(OI)(CI)F",
                "/grant:r", "*S-1-5-32-544:(OI)(CI)F",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=10,
            check=False,
        )
    except Exception:
        pass

    script_fd, script_path = tempfile.mkstemp(prefix="winkit_sys_", suffix=".ps1", dir=str(prog_data))
    status_fd, status_path = tempfile.mkstemp(prefix="winkit_sys_", suffix=".status", dir=str(prog_data))
    os.close(status_fd)
    try:
        os.unlink(status_path)
    except OSError:
        pass

    escaped_status = status_path.replace("'", "''")
    wrapper = f"""
$ErrorActionPreference = 'Stop'
$statusPath = '{escaped_status}'
try {{
{script_text}
    Set-Content -LiteralPath $statusPath -Value 'OK' -Encoding UTF8 -Force
}} catch {{
    $errMsg = [string]$_.Exception.Message
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($errMsg))
    Set-Content -LiteralPath $statusPath -Value ('ERROR:' + $b64) -Encoding UTF8 -Force
}}
"""
    with os.fdopen(script_fd, "w", encoding="utf-8", newline="\n") as sf:
        sf.write(wrapper)

    action = (
        f'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{script_path}"'
    )
    created = False
    try:
        subprocess.run(["sc.exe", "start", "Schedule"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=5)
        create_res = subprocess.run(
            ["schtasks.exe", "/create", "/tn", task_name, "/sc", "ONCE", "/st", "00:00", "/ru", "SYSTEM", "/rl", "HIGHEST", "/tr", action, "/f"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=15,
        )
        created = (create_res.returncode == 0)
        if not created:
            return False, f"Failed to create SYSTEM task: {create_res.stderr.strip() or create_res.stdout.strip()}"

        run_res = subprocess.run(
            ["schtasks.exe", "/run", "/tn", task_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=15,
        )
        if run_res.returncode != 0:
            return False, f"Failed to start SYSTEM task: {run_res.stderr.strip()}"

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if os.path.isfile(status_path):
                try:
                    content = Path(status_path).read_text(encoding="utf-8-sig", errors="replace").strip()
                except OSError:
                    content = ""
                if content == "OK":
                    return True, ""
                if content.startswith("ERROR:"):
                    try:
                        err_decoded = base64.b64decode(content.partition(":")[2]).decode("utf-8", errors="replace")
                    except Exception:
                        err_decoded = content
                    return False, err_decoded
            time.sleep(0.1)
        return False, "SYSTEM task execution timed out."
    except Exception as exc:
        return False, str(exc)
    finally:
        if created:
            subprocess.run(["schtasks.exe", "/delete", "/tn", task_name, "/f"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=10)
        for p in (script_path, status_path):
            try:
                os.unlink(p)
            except OSError:
                pass

def run_powershell_as_trustedinstaller(script_text: str, timeout: int = 120) -> tuple[bool, str]:
    """Execute PowerShell code under TrustedInstaller token using process token stealing."""
    enable_process_privileges()
    payload = base64.b64encode(str(script_text).encode("utf-16le")).decode("ascii")
    
    launcher_script = rf"""
$ErrorActionPreference = 'Stop'
& sc.exe start TrustedInstaller 2>$null | Out-Null
$deadline = (Get-Date).AddSeconds(20)
do {{
    $service = Get-CimInstance Win32_Service -Filter "Name='TrustedInstaller'" -ErrorAction SilentlyContinue
    if ($service -and [int]$service.ProcessId -gt 0) {{ break }}
    Start-Sleep -Milliseconds 200
}} while ((Get-Date) -lt $deadline)

if (-not $service -or [int]$service.ProcessId -le 0) {{
    throw 'TrustedInstaller service could not be started.'
}}

if (-not ([System.Management.Automation.PSTypeName]'WinKitTILauncher').Type) {{
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class WinKitTILauncher
{{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct STARTUPINFO
    {{
        public int cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }}

    [StructLayout(LayoutKind.Sequential)]
    private struct PROCESS_INFORMATION
    {{
        public IntPtr hProcess, hThread;
        public int dwProcessId, dwThreadId;
    }}

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(int access, bool inherit, int pid);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool OpenProcessToken(IntPtr proc, int access, out IntPtr token);

    [DllImport("ntdll.dll")]
    public static extern int RtlAdjustPrivilege(int priv, bool enable, bool curThread, out bool enabled);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool ImpersonateLoggedOnUser(IntPtr token);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool RevertToSelf();

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool DuplicateTokenEx(IntPtr existing, int access, IntPtr attr, int impLevel, int tokenType, out IntPtr newToken);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateProcessWithTokenW(IntPtr token, int flags, string app, StringBuilder cmd, int creationFlags, IntPtr env, string dir, ref STARTUPINFO si, out PROCESS_INFORMATION pi);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateProcessAsUserW(IntPtr token, string app, StringBuilder cmd, IntPtr pAttr, IntPtr tAttr, bool inherit, int creationFlags, IntPtr env, string dir, ref STARTUPINFO si, out PROCESS_INFORMATION pi);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern int WaitForSingleObject(IntPtr handle, int ms);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetExitCodeProcess(IntPtr proc, out int exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool TerminateProcess(IntPtr proc, int exitCode);

    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);

    public static int Run(int pid, string app, string cmd, int timeoutMs)
    {{
        bool prev;
        RtlAdjustPrivilege(20, true, false, out prev);
        RtlAdjustPrivilege(29, true, false, out prev);

        IntPtr proc = OpenProcess(0x1400, false, pid);
        if (proc == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());

        IntPtr token = IntPtr.Zero, primary = IntPtr.Zero;
        PROCESS_INFORMATION child = new PROCESS_INFORMATION();
        try
        {{
            if (!OpenProcessToken(proc, 0x000B, out token)) throw new Win32Exception(Marshal.GetLastWin32Error());
            if (!DuplicateTokenEx(token, 0x02000000, IntPtr.Zero, 2, 1, out primary)) throw new Win32Exception(Marshal.GetLastWin32Error());

            STARTUPINFO si = new STARTUPINFO();
            si.cb = Marshal.SizeOf(typeof(STARTUPINFO));
            si.lpDesktop = "";
            StringBuilder sbCmd = new StringBuilder(cmd);
            bool ok = CreateProcessWithTokenW(primary, 0, app, sbCmd, 0x08000000, IntPtr.Zero, Environment.SystemDirectory, ref si, out child);
            if (!ok)
            {{
                sbCmd = new StringBuilder(cmd);
                ok = CreateProcessAsUserW(primary, app, sbCmd, IntPtr.Zero, IntPtr.Zero, false, 0x08000000, IntPtr.Zero, Environment.SystemDirectory, ref si, out child);
            }}
            if (!ok) throw new Win32Exception(Marshal.GetLastWin32Error());

            int wait = WaitForSingleObject(child.hProcess, timeoutMs);
            if (wait == 0x102)
            {{
                TerminateProcess(child.hProcess, 1460);
                throw new TimeoutException("TrustedInstaller execution timed out.");
            }}
            int exitCode;
            if (!GetExitCodeProcess(child.hProcess, out exitCode)) throw new Win32Exception(Marshal.GetLastWin32Error());
            return exitCode;
        }}
        finally
        {{
            if (child.hThread != IntPtr.Zero) CloseHandle(child.hThread);
            if (child.hProcess != IntPtr.Zero) CloseHandle(child.hProcess);
            if (primary != IntPtr.Zero) CloseHandle(primary);
            if (token != IntPtr.Zero) CloseHandle(token);
            if (proc != IntPtr.Zero) CloseHandle(proc);
        }}
    }}
}}
'@
}}

$tempDir = Join-Path $env:SystemRoot 'Temp'
if (-not (Test-Path $tempDir)) {{ New-Item -Path $tempDir -ItemType Directory -Force | Out-Null }}
$tempScript = Join-Path $tempDir ('winkit_ti_' + [Guid]::NewGuid().ToString('N') + '.ps1')
$rawBytes = [Convert]::FromBase64String('{payload}')
$scriptContent = [System.Text.Encoding]::Unicode.GetString($rawBytes)
[System.IO.File]::WriteAllText($tempScript, $scriptContent, [System.Text.Encoding]::UTF8)

$psPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$cmd = '"' + $psPath + '" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $tempScript + '"'

try {{
    $exitCode = [WinKitTILauncher]::Run([int]$service.ProcessId, $psPath, $cmd, {int(timeout * 1000)})
    if ($exitCode -ne 0) {{
        throw "TrustedInstaller execution failed with exit code $exitCode."
    }}
}}
finally {{
    if (Test-Path -LiteralPath $tempScript) {{
        Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
    }}
}}
"""
    return run_powershell_as_system(launcher_script, timeout=timeout + 30)
