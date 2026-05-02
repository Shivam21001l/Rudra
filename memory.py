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
        # Validate and sanitize history before saving
        if "history" in mem:
            mem["history"] = sanitize_history(mem["history"])
        
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
    """Append a message to conversation history with validation."""
    valid_roles = {"user", "assistant", "system"}
    if role not in valid_roles:
        print(f"[Memory] Warning: Invalid role '{role}' for history entry")
        return
    
    entry = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    }
    
    # Sanity check: don't allow empty content
    if not content or not content.strip():
        print("[Memory] Warning: Skipping empty history entry")
        return
    
    mem["history"].append(entry)


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


def validate_conversation_history(history: list) -> tuple[bool, list[dict]]:
    """
    Validate conversation history integrity.
    Returns (is_valid, list_of_issues).
    Checks:
    - Each user message should be followed by an assistant response (or system message)
    - No orphaned assistant messages without preceding user message
    - All entries have required fields (role, content, timestamp)
    """
    issues = []
    valid_roles = {"user", "assistant", "system"}
    
    for i, entry in enumerate(history):
        # Check required fields
        if "role" not in entry or "content" not in entry or "timestamp" not in entry:
            issues.append({"index": i, "type": "missing_fields", "entry": entry})
            continue
        
        # Check valid role
        if entry["role"] not in valid_roles:
            issues.append({"index": i, "type": "invalid_role", "role": entry["role"]})
        
        # Check for reflection-like entries mixed into history
        if "category" in entry or "r" in entry:
            issues.append({"index": i, "type": "reflection_in_history", "entry": entry})
    
    # Check role sequence patterns
    for i in range(len(history) - 1):
        current = history[i]
        next_entry = history[i + 1]
        
        # User messages should generally be followed by assistant (not another user)
        if current.get("role") == "user" and next_entry.get("role") == "user":
            issues.append({
                "index": i,
                "type": "consecutive_user_messages",
                "message": f"User message at {i} followed by another user message at {i+1}"
            })
    
    return len(issues) == 0, issues


def sanitize_history(history: list) -> list[dict]:
    """
    Remove corrupted or invalid entries from conversation history.
    Removes entries that:
    - Have reflection-like structure (category, r fields)
    - Are missing required fields
    - Have invalid roles
    """
    valid_roles = {"user", "assistant", "system"}
    cleaned = []
    
    for entry in history:
        # Skip reflection-like entries
        if "category" in entry or "r" in entry:
            continue
        
        # Skip entries missing required fields
        if not all(k in entry for k in ("role", "content", "timestamp")):
            continue
        
        # Skip entries with invalid roles
        if entry.get("role") not in valid_roles:
            continue
        
        cleaned.append(entry)
    
    return cleaned


def add_history(mem: dict, role: str, content: str):
    """Append a message to conversation history with validation."""
    valid_roles = {"user", "assistant", "system"}
    if role not in valid_roles:
        print(f"[Memory] Warning: Invalid role '{role}' for history entry")
        return
    
    entry = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    }
    
    # Sanity check: don't allow empty content
    if not content or not content.strip():
        print("[Memory] Warning: Skipping empty history entry")
        return
    
    mem["history"].append(entry)


def invalidate_cache():
    """Force next load() to re-read from disk."""
    global _cache
    with _lock:
        _cache = None
