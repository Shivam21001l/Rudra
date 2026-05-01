"""
Rudra Reflection — Self-analysis engine that identifies weaknesses and improvement areas.
═══════════════════════════════════════════════════════════════════════════════
Uses minimax-m2.7 to analyze conversations and the agent's own source code.
"""

import threading
from pathlib import Path
from brain import ask_agent
import memory as mem_module
from config import BASE_DIR, EVOLVABLE_MODULES

_reflect_lock = threading.Lock()


def reflect_on_conversation(user_input: str, ai_output: str):
    """
    Background reflection on a conversation turn.
    Categorizes weaknesses and stores structured feedback.
    """
    if not _reflect_lock.acquire(blocking=False):
        return  # Skip if already reflecting
    try:
        prompt = f"""Analyze this conversation turn and identify weaknesses:

USER: {user_input}
AI: {ai_output}

Respond in this exact format (one line each):
CATEGORY: <speed|accuracy|capability|code_quality|none>
WEAKNESS: <one sentence describing the weakness, or "none">
FIX: <one sentence suggestion to improve, or "none">"""

        result = ask_agent(
            [{"role": "user", "content": prompt}],
            system="You are a strict AI critic. Be brief and precise. If there are no weaknesses, say 'none'.",
            max_tokens=120,
            track=False,  # Don't benchmark reflection calls
        )

        # Parse structured response
        category = "general"
        weakness = result
        for line in result.splitlines():
            line = line.strip()
            if line.startswith("CATEGORY:"):
                category = line.split(":", 1)[1].strip().lower()
            elif line.startswith("WEAKNESS:"):
                weakness = line.split(":", 1)[1].strip()

        if "none" not in weakness.lower():
            mem = mem_module.load()
            mem_module.add_reflection(mem, weakness, category)
            mem_module.save(mem)
    except Exception:
        pass  # Reflection is non-critical
    finally:
        _reflect_lock.release()


def analyze_source_code() -> str | None:
    """
    Proactively analyze the agent's own source code for improvement opportunities.
    Returns a structured analysis or None if nothing to improve.
    """
    if not _reflect_lock.acquire(blocking=False):
        return None
    try:
        # Read all evolvable modules
        code_snippets = []
        for mod_name in EVOLVABLE_MODULES:
            mod_path = BASE_DIR / mod_name
            if mod_path.exists():
                code = mod_path.read_text(encoding="utf-8")
                code_snippets.append(f"### {mod_name} ({len(code)} bytes)\n```python\n{code}\n```")

        if not code_snippets:
            return None

        all_code = "\n\n".join(code_snippets)

        prompt = f"""Analyze these Python modules for improvement opportunities.
Focus on: performance, code quality, missing features, bugs, redundancy.

{all_code}

Respond in this exact format:
TARGET: <filename to improve>
PRIORITY: <high|medium|low>
DESCRIPTION: <one paragraph describing the improvement>
EXPECTED_GAIN: <what gets better — speed, reliability, capability>

If there's genuinely nothing to improve, respond: NO_IMPROVEMENT"""

        result = ask_agent(
            [{"role": "user", "content": prompt}],
            system="You are a senior Python architect doing a code review. Be specific and actionable.",
            max_tokens=300,
            track=False,
        )

        if "NO_IMPROVEMENT" in result:
            return None
        return result
    except Exception:
        return None
    finally:
        _reflect_lock.release()


def get_recent_weaknesses(mem: dict, count: int = 5) -> str:
    """Get a formatted string of recent weaknesses for the evolution engine."""
    reflections = mem.get("reflections", [])
    if not reflections:
        return "No weaknesses recorded yet."

    recent = reflections[-count:]
    lines = []
    for r in recent:
        cat = r.get("category", "general")
        text = r.get("r", "")
        lines.append(f"[{cat}] {text}")
    return " | ".join(lines)
