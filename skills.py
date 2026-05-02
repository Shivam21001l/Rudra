"""
Rudra AgentSkills — Full system authority + modular skill registry.
═══════════════════════════════════════════════════════════════════════════════
Each skill is a callable returning a string. Executed by the ReAct loop.
"""

import json
import os
import time
import re
import subprocess
from pathlib import Path
from shell import run as run_shell

# ─── Lazy psutil ─────────────────────────────────────────────────────────────
_psutil = None

def _get_psutil():
    global _psutil
    if _psutil is None:
        try:
            import psutil as _ps
            _psutil = _ps
        except ImportError:
            _psutil = False
    return _psutil


# ═══════════════════════════════════════════════════════════════════════════════
#  SKILL REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════
class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, dict] = {}

    def register(self, name: str, func, description: str):
        self._skills[name] = {"func": func, "description": description}

    def execute(self, name: str, args: dict) -> str:
        if name not in self._skills:
            available = ", ".join(self._skills.keys())
            return f"[Error] Skill '{name}' not found. Available: {available}"
        try:
            result = self._skills[name]["func"](**args)
            return str(result) if result is not None else "(no output)"
        except TypeError as e:
            return f"[Error] Wrong arguments for '{name}': {e}"
        except Exception as e:
            return f"[Error executing {name}] {e}"

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())


registry = SkillRegistry()


# ═══════════════════════════════════════════════════════════════════════════════
#  1. SHELL EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════
def execute_shell(cmd: str) -> str:
    return run_shell(cmd)

registry.register("shell_execute", execute_shell,
    'Execute a PowerShell command. Args: {"cmd": "<command>"}')


# ═══════════════════════════════════════════════════════════════════════════════
#  2. FILE SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════
def read_file(path: str) -> str:
    try:
        p = Path(path)
        if not p.is_absolute():
            p = Path(os.getcwd()) / p
        if not p.exists():
            return f"[Error] File not found: {p}"
        if p.stat().st_size > 100_000:
            return f"[Error] File too large ({p.stat().st_size} bytes). Max 100KB."
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"[Error] Cannot read binary file: {path}"
    except Exception as e:
        return f"[Error] {e}"


def write_file(path: str, content: str) -> str:
    try:
        p = Path(path)
        if not p.is_absolute():
            p = Path(os.getcwd()) / p
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} chars to {p}"
    except Exception as e:
        return f"[Error] {e}"


def list_directory(path: str = ".") -> str:
    try:
        p = Path(path)
        if not p.is_absolute():
            p = Path(os.getcwd()) / p
        if not p.exists():
            return f"[Error] Directory not found: {p}"
        if not p.is_dir():
            return f"[Error] Not a directory: {p}"
        entries = []
        for item in sorted(p.iterdir()):
            kind = "DIR " if item.is_dir() else "FILE"
            size = ""
            if item.is_file():
                sz = item.stat().st_size
                if sz > 1024 * 1024:
                    size = f" ({sz // (1024*1024)}MB)"
                elif sz > 1024:
                    size = f" ({sz // 1024}KB)"
                else:
                    size = f" ({sz}B)"
            entries.append(f"  {kind}  {item.name}{size}")
        if not entries:
            return f"(empty directory: {p})"
        return f"Contents of {p}:\n" + "\n".join(entries[:50])
    except Exception as e:
        return f"[Error] {e}"


registry.register("read_file", read_file,
    'Read file contents. Args: {"path": "<file_path>"}')
registry.register("write_file", write_file,
    'Write text to a file. Args: {"path": "<file_path>", "content": "<text>"}')
registry.register("list_directory", list_directory,
    'List files in a directory. Args: {"path": "<dir_path>"}')


# ═══════════════════════════════════════════════════════════════════════════════
#  3. SYSTEM STATS
# ═══════════════════════════════════════════════════════════════════════════════
def get_system_stats() -> str:
    ps = _get_psutil()
    if ps is False:
        return run_shell(
            "Get-CimInstance Win32_OperatingSystem | "
            "Select-Object FreePhysicalMemory, TotalVisibleMemorySize | Format-List"
        )
    try:
        cpu = ps.cpu_percent(interval=0.3)
        ram = ps.virtual_memory()
        disk = ps.disk_usage("C:\\")
        alerts = []
        if cpu > 80:
            alerts.append(f"⚠️ HIGH CPU: {cpu}%")
        if ram.percent > 85:
            alerts.append(f"⚠️ HIGH RAM: {ram.percent}%")
        report = (
            f"CPU: {cpu}% | RAM: {ram.percent}% "
            f"({ram.used // (1024**3)}GB/{ram.total // (1024**3)}GB) | "
            f"Disk C: {disk.percent}% (Free: {disk.free // (1024**3)}GB)"
        )
        if alerts:
            report = "\n".join(alerts) + "\n" + report
        return report
    except Exception as e:
        return f"[Error] {e}"

registry.register("system_stats", get_system_stats,
    'Get CPU, RAM, Disk usage. Args: {}')


# ═══════════════════════════════════════════════════════════════════════════════
#  4. WEB SEARCH
# ═══════════════════════════════════════════════════════════════════════════════
def web_search(query: str) -> str:
    import urllib.request
    import urllib.parse
    snippets = []
    try:
        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(url, data=data,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        for m in re.finditer(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
            text = re.sub(r"<[^>]+>", "", m.group(1)).replace("\n", " ").strip()
            if text and len(text) > 20:
                snippets.append(text)
    except Exception:
        pass
    if not snippets:
        try:
            import urllib.parse
            wiki_url = (
                "https://en.wikipedia.org/w/api.php?action=query&list=search"
                f"&srsearch={urllib.parse.quote(query)}&utf8=&format=json"
            )
            with urllib.request.urlopen(wiki_url, timeout=8) as resp:
                w_data = json.loads(resp.read().decode("utf-8"))
            for item in w_data.get("query", {}).get("search", [])[:3]:
                clean = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
                snippets.append(f"{item['title']}: {clean}")
        except Exception:
            pass
    if not snippets:
        return "No search results found. Try rephrasing."
    return "\n\n".join(snippets[:5])

registry.register("web_search", web_search,
    'Search the web. Args: {"query": "<search terms>"}')


# ═══════════════════════════════════════════════════════════════════════════════
#  5. APP CONTROL
# ═══════════════════════════════════════════════════════════════════════════════
_APP_ALIASES = {
    "chrome": "chrome", "browser": "chrome", "google chrome": "chrome",
    "firefox": "firefox", "edge": "msedge", "notepad": "notepad",
    "calculator": "calc", "calc": "calc", "explorer": "explorer",
    "file explorer": "explorer", "files": "explorer", "cmd": "cmd",
    "terminal": "wt", "powershell": "powershell", "paint": "mspaint",
    "task manager": "taskmgr", "settings": "ms-settings:",
    "control panel": "control", "snipping tool": "SnippingTool",
    "vscode": "code", "vs code": "code", "word": "winword",
    "excel": "excel", "powerpoint": "powerpnt", "spotify": "spotify",
    "discord": "discord", "telegram": "telegram", "whatsapp": "whatsapp:",
}

def open_app(name: str) -> str:
    lookup = name.lower().strip()
    target = _APP_ALIASES.get(lookup, name)
    if ":" in target:
        result = run_shell(f'Start-Process "{target}"')
    else:
        result = run_shell(f"Start-Process {target}")
    if "[Error]" in result or "[BLOCKED]" in result:
        return f"Failed to open '{name}': {result}"
    return f"Successfully launched {name}."

def close_app(name: str) -> str:
    lookup = name.lower().strip()
    target = _APP_ALIASES.get(lookup, name)
    result = run_shell(f"Stop-Process -Name {target} -Force -ErrorAction SilentlyContinue")
    if "[Error]" in result:
        return f"Failed to close '{name}': {result}"
    return f"Sent close signal to {name}."

def list_running_apps() -> str:
    return run_shell(
        "Get-Process | Sort-Object WorkingSet64 -Descending | "
        "Select-Object -First 15 Name, @{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB,1)}}, CPU | "
        "Format-Table -AutoSize"
    )

registry.register("open_app", open_app,
    'Open a Windows app. Args: {"name": "chrome|notepad|vscode|..."}')
registry.register("close_app", close_app,
    'Close a running app. Args: {"name": "chrome|notepad|..."}')
registry.register("list_running_apps", list_running_apps,
    'List top processes by memory. Args: {}')


# ═══════════════════════════════════════════════════════════════════════════════
#  6. VOLUME CONTROL
# ═══════════════════════════════════════════════════════════════════════════════
def set_volume(level: int = -1, mute: bool = False) -> str:
    """Set system volume (0-100) or toggle mute."""
    try:
        if mute:
            # Toggle mute via SendKeys (virtual key 0xAD = VK_VOLUME_MUTE)
            run_shell(
                '$wshell = New-Object -ComObject WScript.Shell; '
                '$wshell.SendKeys([char]173)'
            )
            return "Toggled mute."
        if level < 0 or level > 100:
            return "[Error] Volume must be 0-100."

        # Use PowerShell + COM to set exact volume percentage
        scalar = level / 100.0
        ps_cmd = (
            'Add-Type -TypeDefinition @"\n'
            'using System;\n'
            'using System.Runtime.InteropServices;\n'
            '\n'
            '[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n'
            'interface IAudioEndpointVolume {\n'
            '    int NotImpl1(); int NotImpl2(); int NotImpl3(); int NotImpl4();\n'
            '    int SetMasterVolumeLevelScalar(float fLevel, System.Guid pguidEventContext);\n'
            '    int GetMasterVolumeLevelScalar(out float pfLevel);\n'
            '}\n'
            '\n'
            '[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n'
            'interface IMMDevice { int Activate(ref System.Guid iid, int dwClsCtx, IntPtr pActivationParams, [MarshalAs(UnmanagedType.IUnknown)] out object ppInterface); }\n'
            '\n'
            '[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n'
            'interface IMMDeviceEnumerator { int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice ppDevice); }\n'
            '\n'
            '[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator {}\n'
            '\n'
            'public class AudioHelper {\n'
            '    public static void SetVolume(float level) {\n'
            '        var enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumerator());\n'
            '        IMMDevice device;\n'
            '        enumerator.GetDefaultAudioEndpoint(0, 1, out device);\n'
            '        Guid iid = typeof(IAudioEndpointVolume).GUID;\n'
            '        object o;\n'
            '        device.Activate(ref iid, 23, IntPtr.Zero, out o);\n'
            '        var volume = (IAudioEndpointVolume)o;\n'
            '        volume.SetMasterVolumeLevelScalar(level, Guid.Empty);\n'
            '    }\n'
            '}\n'
            '"@ -ErrorAction SilentlyContinue;\n'
            f'[AudioHelper]::SetVolume({scalar})'
        )
        result = run_shell(ps_cmd)
        if "[Error]" in result:
            return f"Volume command failed: {result}"
        return f"Volume set to {level}%."
    except Exception as e:
        return f"[Error] {e}"

registry.register("set_volume", set_volume,
    'Set system volume. Args: {"level": 50} or {"mute": true}')


# ═══════════════════════════════════════════════════════════════════════════════
#  7. BRIGHTNESS CONTROL
# ═══════════════════════════════════════════════════════════════════════════════
def set_brightness(level: int) -> str:
    """Set screen brightness (0-100). Works on laptops with WMI support."""
    if level < 0 or level > 100:
        return "[Error] Brightness must be 0-100."
    try:
        run_shell(f"Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods | Invoke-WmiMethod -Name WmiSetBrightness -ArgumentList 1,{level}")
        # Verify the change
        check = run_shell("Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness | Select -ExpandProperty CurrentBrightness")
        if check and check.strip().isdigit():
            actual = int(check.strip())
            if abs(actual - level) <= 2:
                return f"Brightness successfully set and verified at {actual}%."
            else:
                return f"Attempted to set brightness to {level}%, but system reports it is at {actual}%. Your monitor may not support WMI brightness control."
        return f"Brightness command sent, but verification failed."
    except Exception as e:
        return f"[Error] {e}"

registry.register("set_brightness", set_brightness,
    'Set screen brightness (0-100). Args: {"level": 70}')


# ═══════════════════════════════════════════════════════════════════════════════
#  8. SCREENSHOT
# ═══════════════════════════════════════════════════════════════════════════════
def screenshot(filename: str = "") -> str:
    """Take a screenshot and save to Desktop."""
    try:
        if not filename:
            filename = f"screenshot_{int(time.time())}.png"
        desktop = Path(os.path.expanduser("~/Desktop"))
        save_path = desktop / filename
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "$bitmap = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height); "
            "$graphics = [System.Drawing.Graphics]::FromImage($bitmap); "
            "$graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size); "
            f"$bitmap.Save('{save_path}'); "
            "$graphics.Dispose(); $bitmap.Dispose()"
        )
        result = run_shell(ps_cmd)
        if "[Error]" in result:
            return f"Screenshot failed: {result}"
        return f"Screenshot saved to {save_path}"
    except Exception as e:
        return f"[Error] {e}"

registry.register("screenshot", screenshot,
    'Take a screenshot. Args: {} or {"filename": "name.png"}')


# ═══════════════════════════════════════════════════════════════════════════════
#  9. CLIPBOARD
# ═══════════════════════════════════════════════════════════════════════════════
def clipboard_read() -> str:
    """Read current clipboard text content."""
    try:
        result = run_shell("Get-Clipboard")
        return result if result else "(clipboard is empty)"
    except Exception as e:
        return f"[Error] {e}"

def clipboard_write(text: str) -> str:
    """Write text to the clipboard."""
    try:
        # Escape for PowerShell
        safe_text = text.replace("'", "''")
        run_shell(f"Set-Clipboard -Value '{safe_text}'")
        return f"Copied {len(text)} chars to clipboard."
    except Exception as e:
        return f"[Error] {e}"

registry.register("clipboard_read", clipboard_read,
    'Read clipboard text. Args: {}')
registry.register("clipboard_write", clipboard_write,
    'Copy text to clipboard. Args: {"text": "<content>"}')


# ═══════════════════════════════════════════════════════════════════════════════
#  10. NETWORK INFO
# ═══════════════════════════════════════════════════════════════════════════════
def network_info() -> str:
    """Get network configuration — IP, WiFi, DNS."""
    try:
        parts = []
        # IP config
        ip_result = run_shell(
            "Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | "
            "Select-Object InterfaceAlias, "
            "@{N='IP';E={$_.IPv4Address.IPAddress}}, "
            "@{N='Gateway';E={$_.IPv4DefaultGateway.NextHop}} | "
            "Format-Table -AutoSize"
        )
        parts.append(f"Network:\n{ip_result}")
        # WiFi
        wifi = run_shell("netsh wlan show interfaces | findstr /R \"SSID Signal\"")
        if wifi and "[Error]" not in wifi:
            parts.append(f"WiFi:\n{wifi}")
        # Public IP (fast)
        try:
            import urllib.request
            with urllib.request.urlopen("https://api.ipify.org", timeout=3) as r:
                pub_ip = r.read().decode()
            parts.append(f"Public IP: {pub_ip}")
        except Exception:
            parts.append("Public IP: (could not fetch)")
        return "\n".join(parts)
    except Exception as e:
        return f"[Error] {e}"

registry.register("network_info", network_info,
    'Get network info (IP, WiFi, DNS). Args: {}')


# ═══════════════════════════════════════════════════════════════════════════════
#  11. SERVICE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════
def manage_service(name: str, action: str = "status") -> str:
    """Manage Windows services. Actions: status, start, stop, restart."""
    action = action.lower().strip()
    if action == "status":
        return run_shell(f"Get-Service -Name '{name}' | Format-List Name, Status, StartType")
    elif action == "start":
        return run_shell(f"Start-Service -Name '{name}' -ErrorAction SilentlyContinue; Get-Service -Name '{name}' | Select Status")
    elif action == "stop":
        return run_shell(f"Stop-Service -Name '{name}' -Force -ErrorAction SilentlyContinue; Get-Service -Name '{name}' | Select Status")
    elif action == "restart":
        return run_shell(f"Restart-Service -Name '{name}' -Force -ErrorAction SilentlyContinue; Get-Service -Name '{name}' | Select Status")
    else:
        return f"[Error] Unknown action '{action}'. Use: status, start, stop, restart"

registry.register("manage_service", manage_service,
    'Manage Windows services. Args: {"name": "wuauserv", "action": "status|start|stop|restart"}')


# ═══════════════════════════════════════════════════════════════════════════════
#  12. POWER CONTROLS (with safety)
# ═══════════════════════════════════════════════════════════════════════════════
def lock_screen() -> str:
    """Lock the computer screen."""
    try:
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"], creationflags=CREATE_NO_WINDOW)
        return "Screen locked."
    except Exception as e:
        return f"[Error] {e}"

def sleep_pc() -> str:
    """Put the computer to sleep."""
    try:
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["powershell", "-Command",
             "Add-Type -AssemblyName System.Windows.Forms; "
             "[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"],
            shell=False,
            creationflags=CREATE_NO_WINDOW,
        )
        return "Computer going to sleep..."
    except Exception as e:
        return f"[Error] {e}"

def shutdown_pc(cancel: bool = False) -> str:
    """Shutdown PC with 30s countdown. Pass cancel=true to abort."""
    try:
        CREATE_NO_WINDOW = 0x08000000
        if cancel:
            subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=CREATE_NO_WINDOW)
            return "Shutdown cancelled."
        subprocess.Popen(["shutdown", "/s", "/t", "30"], creationflags=CREATE_NO_WINDOW)
        return "⚠️ Shutting down in 30 seconds. Say 'cancel shutdown' or run shutdown_pc(cancel=true) to abort."
    except Exception as e:
        return f"[Error] {e}"

def restart_pc(cancel: bool = False) -> str:
    """Restart PC with 30s countdown. Pass cancel=true to abort."""
    try:
        CREATE_NO_WINDOW = 0x08000000
        if cancel:
            subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=CREATE_NO_WINDOW)
            return "Restart cancelled."
        subprocess.Popen(["shutdown", "/r", "/t", "30"], creationflags=CREATE_NO_WINDOW)
        return "⚠️ Restarting in 30 seconds. Say 'cancel restart' or run restart_pc(cancel=true) to abort."
    except Exception as e:
        return f"[Error] {e}"

registry.register("lock_screen", lock_screen,
    'Lock the screen. Args: {}')
registry.register("sleep_pc", sleep_pc,
    'Put PC to sleep. Args: {}')
registry.register("shutdown_pc", shutdown_pc,
    'Shutdown with 30s countdown. Args: {} or {"cancel": true} to abort')
registry.register("restart_pc", restart_pc,
    'Restart with 30s countdown. Args: {} or {"cancel": true} to abort')


# ═══════════════════════════════════════════════════════════════════════════════
#  13. DATE/TIME
# ═══════════════════════════════════════════════════════════════════════════════
def get_datetime() -> str:
    """Get current date and time."""
    from datetime import datetime
    now = datetime.now()
    return now.strftime("Date: %A, %B %d, %Y | Time: %I:%M:%S %p")

registry.register("get_datetime", get_datetime,
    'Get current date and time. Args: {}')


# ═══════════════════════════════════════════════════════════════════════════════
#  14. INSTALLED APPS
# ═══════════════════════════════════════════════════════════════════════════════
def installed_apps(search: str = "") -> str:
    """List installed applications, optionally filtered."""
    filter_part = ""
    if search:
        filter_part = f" | Where-Object {{ $_.DisplayName -like '*{search}*' }}"
    return run_shell(
        "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*,"
        "HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* "
        f"| Select-Object DisplayName, DisplayVersion, Publisher{filter_part} "
        "| Sort-Object DisplayName | Format-Table -AutoSize"
    )

registry.register("installed_apps", installed_apps,
    'List installed apps. Args: {} or {"search": "chrome"}')


# ═══════════════════════════════════════════════════════════════════════════════
#  15. WIFI NETWORKS
# ═══════════════════════════════════════════════════════════════════════════════
def wifi_networks() -> str:
    """List available WiFi networks."""
    return run_shell("netsh wlan show networks mode=bssid | findstr /R \"SSID Signal Authentication\"")

registry.register("wifi_networks", wifi_networks,
    'List available WiFi networks. Args: {}')
