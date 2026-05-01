"""
Rudra Memory — Thread-safe persistent JSON memory with auto-compaction.
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import threading
from datetime import datetime
from config import MEMORY_FILE, MAX_HISTORY

_lock = threading.Lock()
_cache: dict | None = None


def _default_memory() -> dict:
    """Fresh memory structure."""
    return {
        "history": [],
        "reflections": [],
        "benchmarks": [],
        "upgrade_log": [],
        "tasks_done": 0,
        "upgrades_applied": 0,
        "upgrades_rejected": 0,
        "turn": 0,
        "created_at": datetime.now().isoformat(),
        "last_active": datetime.now().isoformat(),
    }


def load() -> dict:
    """Load memory from disk (cached after first read)."""
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        if MEMORY_FILE.exists():
            try:
                _cache = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                _cache = _default_memory()
        else:
            _cache = _default_memory()
        return _cache


def save(mem: dict):
    """Save memory to disk with auto-compaction."""
    global _cache
    with _lock:
        # Auto-compact
        mem["history"]     = mem["history"][-(MAX_HISTORY * 2):]
        mem["reflections"] = mem["reflections"][-30:]
        mem["benchmarks"]  = mem["benchmarks"][-100:]
        mem["upgrade_log"] = mem["upgrade_log"][-50:]
        mem["last_active"] = datetime.now().isoformat()

        _cache = mem
        try:
            MEMORY_FILE.write_text(
                json.dumps(mem, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except OSError as e:
            print(f"[Memory] Save error: {e}")


def add_history(mem: dict, role: str, content: str):
    """Append a message to conversation history."""
    mem["history"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    })


def add_reflection(mem: dict, reflection: str, category: str = "general"):
    """Store a structured reflection."""
    mem["reflections"].append({
        "t": datetime.now().isoformat(),
        "r": reflection,
        "category": category,
    })


def add_benchmark(mem: dict, operation: str, duration_ms: float, model: str):
    """Record a performance benchmark."""
    mem["benchmarks"].append({
        "t": datetime.now().isoformat(),
        "op": operation,
        "ms": round(duration_ms, 2),
        "model": model,
    })


def add_upgrade_log(mem: dict, upgrade_id: str, target: str, summary: str, status: str):
    """Log an upgrade event (proposed/approved/rejected/rolled_back)."""
    mem["upgrade_log"].append({
        "t": datetime.now().isoformat(),
        "id": upgrade_id,
        "target": target,
        "summary": summary,
        "status": status,
    })


def increment(mem: dict, key: str, amount: int = 1):
    """Increment a counter in memory."""
    mem[key] = mem.get(key, 0) + amount


def invalidate_cache():
    """Force next load() to re-read from disk."""
    global _cache
    with _lock:
        _cache = None
