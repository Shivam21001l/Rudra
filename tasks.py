"""
Rudra Tasks — Proactive heartbeat daemon and background task runner.
═══════════════════════════════════════════════════════════════════════════════
Runs a lightweight ReAct loop on a timer to check system health.
Designed for 8GB RAM — skips heartbeat if system is under pressure.
"""

import time
import json
import threading
from brain import ask_agent
import memory as mem_module
from config import HEARTBEAT_INTERVAL, HEARTBEAT_DELAY
from skills import registry


# ─── Resource Gate ────────────────────────────────────────────────────────────
def _system_under_pressure() -> bool:
    """Check if the system is too busy to run a heartbeat."""
    try:
        import psutil
        ram = psutil.virtual_memory()
        if ram.percent > 85:
            return True
        cpu = psutil.cpu_percent(interval=0.2)
        if cpu > 80:
            return True
    except ImportError:
        pass  # No psutil = can't check, proceed anyway
    except Exception:
        pass
    return False


# ─── Heartbeat ReAct Loop ────────────────────────────────────────────────────
def trigger_heartbeat():
    """
    Proactive heartbeat: asks the agent model to check system stats.
    Uses a mini ReAct loop (max 3 steps) to be fast and lightweight.
    """
    # Skip if system is under pressure — don't add load
    if _system_under_pressure():
        return

    try:
        prompt = (
            "Proactive Heartbeat: Check system stats using system_stats skill. "
            "If anything is abnormal (CPU > 80%, RAM > 90%), report a warning. "
            "Otherwise say all is well. Be brief."
        )
        messages = [{"role": "user", "content": prompt}]

        max_steps = 3
        for step in range(max_steps):
            reply = ask_agent(messages, max_tokens=256, track=False)
            messages.append({"role": "assistant", "content": reply})

            if "STATUS: SUCCESS" in reply:
                summary = ""
                for line in reply.splitlines():
                    if line.strip().startswith("SUMMARY:"):
                        summary = line.split("SUMMARY:", 1)[1].strip()
                break

            # Try to extract ACTION
            action_data = None
            for line in reply.splitlines():
                if line.strip().startswith("ACTION:"):
                    raw = line.split("ACTION:", 1)[1].strip()
                    try:
                        action_data = json.loads(raw)
                    except json.JSONDecodeError:
                        pass
                    break

            if action_data:
                skill_name = action_data.get("skill", "")
                skill_args = action_data.get("args", {})
                output = registry.execute(skill_name, skill_args)
                # Truncate to save context
                if len(output) > 800:
                    output = output[:750] + "\n... [truncated]"
                messages.append({"role": "user", "content": f"OBSERVATION:\n{output}"})
            else:
                break  # No action and no success = conversational, stop

        # Log heartbeat to memory
        mem = mem_module.load()
        mem_module.add_history(mem, "system", "[HEARTBEAT OK]")
        mem_module.save(mem)

    except Exception as e:
        # Silently log — never crash the daemon
        try:
            mem = mem_module.load()
            mem_module.add_history(mem, "system", f"[HEARTBEAT ERROR] {e}")
            mem_module.save(mem)
        except Exception:
            pass


# ─── Daemon Loop ─────────────────────────────────────────────────────────────
def daemon_loop():
    """Main daemon loop: waits for initial delay, then runs heartbeat on interval."""
    # Wait before first heartbeat to let the system settle after startup
    time.sleep(HEARTBEAT_DELAY)

    while True:
        try:
            trigger_heartbeat()
        except Exception:
            pass
        time.sleep(HEARTBEAT_INTERVAL)


def start_daemon():
    """Start the heartbeat daemon in a background thread."""
    t = threading.Thread(target=daemon_loop, daemon=True, name="heartbeat-daemon")
    t.start()
    return t
