"""
Rudra Shell — Windows PowerShell command execution with safety guards.
═══════════════════════════════════════════════════════════════════════════════
"""

import subprocess
from config import BANNED_COMMANDS, SHELL_TIMEOUT


def is_safe(cmd: str) -> tuple[bool, str]:
    """Check if a command is safe to execute."""
    cmd_lower = cmd.lower().strip()
    for banned in BANNED_COMMANDS:
        if banned.lower() in cmd_lower:
            return False, f"BLOCKED — matches banned pattern: '{banned}'"
    return True, "OK"


def run(cmd: str) -> str:
    """
    Execute a PowerShell command and return output.
    Returns truncated output (max 2000 chars).
    """
    safe, reason = is_safe(cmd)
    if not safe:
        return f"[{reason}]"

    proc = None
    try:
        # Prevent terminal window from flashing
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        )
        stdout, stderr = proc.communicate(timeout=SHELL_TIMEOUT)
        output = (stdout or stderr or "(no output)").strip()
        # Truncate long output
        if len(output) > 2000:
            output = output[:1950] + "\n... [truncated]"
        return output
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
            stdout, stderr = proc.communicate()
        return f"[Timeout — command exceeded {SHELL_TIMEOUT}s]"
    except KeyboardInterrupt:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        return "[Aborted by user]"
    except FileNotFoundError:
        return "[Error] PowerShell not found. Ensure PowerShell is in PATH."
    except Exception as e:
        return f"[Error] {e}"


def parse_action(reply: str) -> str | None:
    """Extract a shell command from an ACTION: block in LLM reply."""
    if "ACTION:" not in reply:
        return None
    for line in reply.split("ACTION:")[1].strip().splitlines():
        line = line.strip()
        if line and not line.startswith("REASON:"):
            return line
    return None
