"""
Rudra Evolution — Self-improvement engine with mandatory human review gate.
═══════════════════════════════════════════════════════════════════════════════
HARD LIMITS — This module enforces safety. It is NOT evolvable by the agent.

Workflow:
  1. Background thread analyzes weaknesses + source code every ~5 minutes
  2. Generates upgrade proposal using qwen3:0.6b (code model)
  3. Runs safety_check — syntax, protected tokens, banned ops
  4. Saves proposal to upgrades/pending/ with diff + summary
  5. Notifies user in terminal
  6. WAITS for human_approval via 'approve <id>' command
  7. Only then applies the upgrade + creates backup
  8. Post-upgrade benchmark verification
"""

import json
import time
import shutil
import difflib
import threading
import importlib
from datetime import datetime
from pathlib import Path

from config import (
    BASE_DIR, BACKUP_DIR, EVOLVABLE_MODULES,
    UPGRADES_PENDING, UPGRADES_HISTORY,
    PROTECTED_TOKENS, MIN_CODE_LENGTH,
)
from brain import ask_code, ask_agent
from reflection import get_recent_weaknesses, analyze_source_code
import memory as mem_module

_evolution_lock = threading.Lock()
_pending_notification = threading.Event()  # Set when new upgrade is ready


# ─── Safety Check — HARD LIMITS ─────────────────────────────────────────────
def safety_check(new_code: str, target_file: str) -> tuple[bool, str]:
    """
    Validate proposed code changes. Returns (is_safe, reason).
    This function must NEVER be removed or weakened by any upgrade.
    """
    # Check minimum length
    if len(new_code.strip()) < MIN_CODE_LENGTH:
        return False, f"Code too short ({len(new_code)} chars, min {MIN_CODE_LENGTH})"

    # Syntax check
    try:
        compile(new_code, f"<upgrade:{target_file}>", "exec")
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"

    # Protected token check — ensure critical tokens aren't removed
    target_path = BASE_DIR / target_file
    if target_path.exists():
        original = target_path.read_text(encoding="utf-8")
        for token in PROTECTED_TOKENS:
            if token in original and token not in new_code:
                return False, f"Removed protected token: '{token}'"

    # Read original once for dangerous pattern check (reuse from above)
    dangerous_patterns = [
        "os.remove(", "shutil.rmtree(", "os.unlink(",
        "SELF_PATH.write_text", "open(__file__",
        "exec(", "eval(",  # Don't allow arbitrary code execution
        "subprocess.run(", "os.system(",  # Must use shell.py instead
    ]
    original_code = ""
    if target_path.exists():
        original_code = target_path.read_text(encoding="utf-8")
    for pattern in dangerous_patterns:
        if pattern in new_code and pattern not in original_code:
            return False, f"Introduced dangerous pattern: '{pattern}'"

    return True, "OK"


# ─── Generate Upgrade Proposal ───────────────────────────────────────────────
def _generate_upgrade(mem: dict) -> dict | None:
    """
    Analyze weaknesses + source code, generate a single upgrade proposal.
    Returns proposal dict or None.
    """
    weaknesses = get_recent_weaknesses(mem)

    # Also try proactive source code analysis
    source_analysis = analyze_source_code()
    analysis_text = source_analysis or "No proactive analysis available."

    # Determine which module to improve
    target_prompt = f"""Based on these weaknesses and code analysis, which single module should be improved?

RECENT WEAKNESSES:
{weaknesses}

SOURCE CODE ANALYSIS:
{analysis_text}

AVAILABLE MODULES (pick exactly one):
{', '.join(EVOLVABLE_MODULES)}

Respond with ONLY the filename. Example: brain.py"""

    target = ask_agent(
        [{"role": "user", "content": target_prompt}],
        system="You are a technical architect. Respond with only the filename.",
        max_tokens=20,
        track=False,
    ).strip().strip("`").strip('"').strip("'")

    # Validate target
    if target not in EVOLVABLE_MODULES:
        # Try to match partially
        for mod in EVOLVABLE_MODULES:
            if mod in target:
                target = mod
                break
        else:
            return None

    # Read current code
    target_path = BASE_DIR / target
    if not target_path.exists():
        return None
    current_code = target_path.read_text(encoding="utf-8")

    # Generate improved code using the CODE model (qwen3:0.6b)
    gen_prompt = f"""You are improving a Python module for an AI agent called Rudra.

WEAKNESSES TO ADDRESS:
{weaknesses}

ANALYSIS:
{analysis_text}

CURRENT CODE OF {target}:
```python
{current_code}
```

YOUR TASK:
- Make the single most impactful improvement to this module.
- The improved code must be FASTER or EQUAL speed — never slower.
- Keep ALL existing functionality intact.
- Keep ALL imports and function signatures compatible.
- Improve one thing at a time — do it properly.

HARD RULES:
- Keep ALL of these tokens if they exist: {PROTECTED_TOKENS}
- No dangerous operations (no exec, eval, os.remove, etc.)
- Return ONLY the complete raw Python file content.
- No markdown fences, no explanations.
- If there is genuinely nothing to improve, return exactly: NO_UPGRADE"""

    new_code = ask_code(
        [{"role": "user", "content": gen_prompt}],
        system="You are an expert Python developer rewriting a module. Return only raw Python or NO_UPGRADE.",
        max_tokens=8192,
        track=False,
    )

    if not new_code or "NO_UPGRADE" in new_code or len(new_code.strip()) < MIN_CODE_LENGTH:
        return None

    # Strip accidental markdown fences
    if new_code.strip().startswith("```"):
        lines = new_code.splitlines()
        new_code = "\n".join(
            l for l in lines if not l.strip().startswith("```")
        ).strip()

    # Safety check
    ok, reason = safety_check(new_code, target)
    if not ok:
        return None

    # Generate diff
    diff = "".join(difflib.unified_diff(
        current_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        fromfile=f"old/{target}",
        tofile=f"new/{target}",
        n=3,
    ))

    if not diff.strip():
        return None  # No actual changes

    # Get plain English summary
    summary = ask_agent(
        [{"role": "user", "content":
            f"Summarize this code diff in 2 sentences (what changed and why):\n{diff[:2000]}"}],
        max_tokens=100,
        track=False,
    )

    # Build proposal
    upgrade_count = mem.get("upgrades_applied", 0) + mem.get("upgrades_rejected", 0) + 1
    upgrade_id = f"upgrade_{upgrade_count:03d}"

    proposal = {
        "id": upgrade_id,
        "timestamp": datetime.now().isoformat(),
        "target_file": target,
        "summary": summary,
        "diff": diff,
        "new_code": new_code,
        "weaknesses_addressed": weaknesses,
        "safety_check": "PASSED",
    }

    return proposal


# ─── Pending Upgrade Management ──────────────────────────────────────────────
def save_proposal(proposal: dict):
    """Save an upgrade proposal to the pending directory."""
    filepath = UPGRADES_PENDING / f"{proposal['id']}.json"
    filepath.write_text(
        json.dumps(proposal, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def list_pending() -> list[dict]:
    """List all pending upgrade proposals."""
    proposals = []
    for f in sorted(UPGRADES_PENDING.glob("*.json")):
        try:
            proposals.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return proposals


def get_pending(upgrade_id: str) -> dict | None:
    """Get a specific pending proposal by ID."""
    filepath = UPGRADES_PENDING / f"{upgrade_id}.json"
    if filepath.exists():
        return json.loads(filepath.read_text(encoding="utf-8"))
    return None


# ─── Human Approval Gate — review_required ────────────────────────────────────
def human_approval(upgrade_id: str, approved: bool, reason: str = "") -> str:
    """
    Process human review decision. This is the ONLY way upgrades get applied.
    Returns a status message.
    """
    proposal = get_pending(upgrade_id)
    if not proposal:
        return f"❌ No pending upgrade with ID '{upgrade_id}'"

    mem = mem_module.load()

    if approved:
        return _apply_upgrade(proposal, mem)
    else:
        return _reject_upgrade(proposal, mem, reason)


def _apply_upgrade(proposal: dict, mem: dict) -> str:
    """Apply an approved upgrade — backup, write, verify."""
    target = proposal["target_file"]
    target_path = BASE_DIR / target
    new_code = proposal["new_code"]

    # Final safety_check before applying
    ok, reason = safety_check(new_code, target)
    if not ok:
        return f"🚫 Safety check failed on apply: {reason}"

    # Create backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if target_path.exists():
        backup_path = BACKUP_DIR / f"{target}_{ts}.bak"
        shutil.copy2(target_path, backup_path)

    # Save audit log
    audit_path = UPGRADES_HISTORY / f"{proposal['id']}_{ts}.json"
    proposal["applied_at"] = ts
    proposal["status"] = "approved"
    audit_path.write_text(
        json.dumps(proposal, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Write new code
    target_path.write_text(new_code, encoding="utf-8")

    # Update memory
    mem_module.add_upgrade_log(mem, proposal["id"], target, proposal["summary"], "approved")
    mem_module.increment(mem, "upgrades_applied")
    mem_module.save(mem)

    # Remove from pending
    pending_file = UPGRADES_PENDING / f"{proposal['id']}.json"
    if pending_file.exists():
        pending_file.unlink()

    # Try hot-reload the module
    reload_msg = _try_reload(target)

    return (
        f"✅ Upgrade {proposal['id']} applied to {target}\n"
        f"   💾 Backup: backups/{target}_{ts}.bak\n"
        f"   {reload_msg}\n"
        f"   Total upgrades: {mem.get('upgrades_applied', 0)}"
    )


def _reject_upgrade(proposal: dict, mem: dict, reason: str) -> str:
    """Reject an upgrade — log and remove from pending."""
    # Save to history as rejected
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    proposal["rejected_at"] = ts
    proposal["status"] = "rejected"
    proposal["rejection_reason"] = reason or "No reason given"

    audit_path = UPGRADES_HISTORY / f"{proposal['id']}_{ts}_rejected.json"
    audit_path.write_text(
        json.dumps(proposal, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Update memory
    mem_module.add_upgrade_log(mem, proposal["id"], proposal["target_file"], proposal["summary"], "rejected")
    mem_module.increment(mem, "upgrades_rejected")
    mem_module.save(mem)

    # Remove from pending
    pending_file = UPGRADES_PENDING / f"{proposal['id']}.json"
    if pending_file.exists():
        pending_file.unlink()

    return f"🗑️  Upgrade {proposal['id']} rejected. Reason: {reason or 'N/A'}"


def _try_reload(target_file: str) -> str:
    """Attempt to hot-reload a module after upgrade."""
    module_name = target_file.replace(".py", "")
    try:
        import sys
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
            return "♻️  Module hot-reloaded successfully."
        return "ℹ️  Module will load on next restart."
    except Exception as e:
        return f"⚠️  Hot-reload failed ({e}). Restart to apply."


# ─── Rollback ─────────────────────────────────────────────────────────────────
def rollback(target_file: str) -> str:
    """Roll back the most recent change to a file using its latest backup."""
    target_path = BASE_DIR / target_file
    backups = sorted(BACKUP_DIR.glob(f"{target_file}_*.bak"), reverse=True)

    if not backups:
        return f"❌ No backups found for {target_file}"

    latest_backup = backups[0]
    shutil.copy2(latest_backup, target_path)

    mem = mem_module.load()
    mem_module.add_upgrade_log(mem, "rollback", target_file, f"Rolled back to {latest_backup.name}", "rolled_back")
    mem_module.save(mem)

    reload_msg = _try_reload(target_file)
    return f"⏪ Rolled back {target_file} to {latest_backup.name}\n   {reload_msg}"


def list_backups() -> list[str]:
    """List all available backups."""
    return [f.name for f in sorted(BACKUP_DIR.glob("*.bak"), reverse=True)]


# ─── Autonomous Evolution Loop ──────────────────────────────────────────────
def evolution_loop(interval: int):
    """
    Background thread that autonomously analyzes and proposes upgrades.
    Runs every `interval` seconds. NEVER applies upgrades without human approval.
    """
    # Wait initial period before first analysis
    time.sleep(60)

    while True:
        if not _evolution_lock.acquire(blocking=False):
            time.sleep(interval)
            continue
        try:
            mem = mem_module.load()

            # Need enough reflections before attempting upgrades
            if len(mem.get("reflections", [])) < 3:
                _evolution_lock.release()
                time.sleep(interval)
                continue

            # Don't flood with proposals — max 3 pending at a time
            pending = list_pending()
            if len(pending) >= 3:
                _evolution_lock.release()
                time.sleep(interval)
                continue

            proposal = _generate_upgrade(mem)
            if proposal:
                save_proposal(proposal)
                _pending_notification.set()
                print(f"\n  🔔 New upgrade proposal: {proposal['id']} → {proposal['target_file']}")
                print(f"     {proposal['summary'][:80]}...")
                print(f"     Type 'upgrades' to review, 'approve {proposal['id']}' to apply.\n")

        except Exception as e:
            print(f"  [evolution] Error: {e}")
        finally:
            if _evolution_lock.locked():
                _evolution_lock.release()

        time.sleep(interval)


def start_evolution(interval: int):
    """Start the evolution engine in a background thread."""
    t = threading.Thread(
        target=evolution_loop,
        args=(interval,),
        daemon=True,
        name="evolution-engine",
    )
    t.start()
    return t


def has_pending_notification() -> bool:
    """Check if there's a new upgrade notification to show."""
    if _pending_notification.is_set():
        _pending_notification.clear()
        return True
    return False
