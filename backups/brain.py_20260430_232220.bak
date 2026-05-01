"""
Rudra Brain — Smart dual-model Ollama wrapper with auto-routing & performance tracking.
═══════════════════════════════════════════════════════════════════════════════
Models:
  • gemma3:4b     → Agentic workflow, conversation, reflection (local)
  • qwen3:1.7b    → Code generation, self-improvement, algorithms (local)

Smart Routing:
  The `ask_smart()` function analyzes the user's request and automatically
  picks the best model — no manual selection needed.
"""

import re
import time
import ollama
from config import (
    AGENT_MODEL, CODE_MODEL,
    AGENT_OPTIONS, CODE_OPTIONS,
    KEEP_ALIVE_AGENT, KEEP_ALIVE_CODE,
    SYSTEM_PROMPT, MAX_RETRIES, RETRY_BACKOFF,
)
import memory as mem_module


# ─── Task Classification Keywords ────────────────────────────────────────────
# These patterns trigger the CODE model (qwen3:1.7b) instead of the agent model.
_CODE_PATTERNS = [
    # Direct code requests - require both a verb and a code-related noun
    r"\b(write|create|build|make|generate|implement|code|develop|rewrite|refactor|optimize)\b.*(function|class|script|program|module|api|app|bot|tool|algorithm|logic|method|snippet)",
    r"\b(fix|debug|patch)\b.*(code|bug|error|function|script|class|module|syntax)",
    # Code blocks or specific syntax
    r"```",                          # User pasted code
    r"\bdef\s+\w+\s*\(",            # Python function definition
    r"\bclass\s+\w+",               # Class definition
    # Complex errors
    r"\b(syntaxerror|traceback|indentationerror|runtimeerror|exception|stack.trace)\b",
    # Language mention with coding intent (any order)
    r"\b(python|javascript|js|c\+\+|cpp|csharp|rust|powershell|bash|sql|html|css)\b.*\b(code|script|example|how|write|create|implement|fix|function|snippet|logic)\b",
    r"\b(code|script|example|how|write|create|implement|fix|function|snippet|logic)\b.*\b(python|javascript|js|c\+\+|cpp|csharp|rust|powershell|bash|sql|html|css)",
]

_CODE_RE = re.compile("|".join(_CODE_PATTERNS), re.IGNORECASE)


def classify_task(user_input: str) -> str:
    """
    Analyze user input and determine which model should handle it.
    Returns 'code' or 'agent'.
    """
    # Check for code patterns
    if _CODE_RE.search(user_input):
        return "code"
    return "agent"


def get_model_label(model_type: str) -> str:
    """Human-readable label for the model being used."""
    if model_type == "code":
        return f"🧬 {CODE_MODEL}"
    return f"🔱 {AGENT_MODEL}"


# ─── Model Health Check ──────────────────────────────────────────────────────
def check_ollama_connection() -> tuple[bool, str]:
    """Check if Ollama server is reachable."""
    try:
        ollama.list()
        return True, "Ollama connected"
    except Exception as e:
        return False, (
            f"Cannot connect to Ollama: {e}\n"
            "  → Make sure Ollama is installed and running.\n"
            "  → Download: https://ollama.com/download\n"
            "  → Start: run 'ollama serve' in a terminal."
        )


def ensure_model(model_name: str) -> bool:
    """Check if model exists, attempt to pull if missing."""
    try:
        models = ollama.list()
        model_names = []
        if hasattr(models, 'models') and models.models:
            model_names = [m.model for m in models.models]
        elif isinstance(models, dict) and 'models' in models:
            model_names = [m.get('model', m.get('name', '')) for m in models['models']]

        # Check for exact or prefix match
        for mn in model_names:
            if model_name == mn or model_name in mn:
                print(f"  ✅ Model '{model_name}' found.")
                return True

        # Not found — try pulling
        print(f"  ⬇️  Pulling model '{model_name}'... (this may take a while)")
        ollama.pull(model_name)
        print(f"  ✅ Model '{model_name}' ready.")
        return True
    except Exception as e:
        print(f"  ❌ Failed to get model '{model_name}': {e}")
        return False


# ─── Core LLM Calls ──────────────────────────────────────────────────────────
def _call(model: str, messages: list, system: str, options: dict, max_tokens: int | None = None, keep_alive: str = "5m") -> tuple[str, float]:
    """
    Internal LLM call with retries and timing.
    Returns (response_text, duration_ms).
    """
    opts = {**options}
    if max_tokens:
        opts["num_predict"] = max_tokens

    full_messages = [{"role": "system", "content": system}] + messages

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.perf_counter()
            res = ollama.chat(
                model=model,
                messages=full_messages,
                options=opts,
                keep_alive=keep_alive,
            )
            duration_ms = (time.perf_counter() - t0) * 1000
            text = res["message"]["content"].strip()
            return text, duration_ms
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))

    return f"[Error after {MAX_RETRIES} retries: {last_error}]", 0.0


def _track_benchmark(operation: str, duration_ms: float, model: str):
    """Record a benchmark if duration is valid."""
    if duration_ms > 0:
        try:
            m = mem_module.load()
            mem_module.add_benchmark(m, operation, duration_ms, model)
            mem_module.save(m)
        except Exception:
            pass  # Don't crash on benchmark failure


def ask_agent(
    messages: list,
    system: str = SYSTEM_PROMPT,
    max_tokens: int | None = None,
    track: bool = True,
) -> str:
    """
    Ask the agentic model (minimax-m2.7) — for conversation, tasks, reflection.
    Automatically records benchmarks.
    """
    text, duration_ms = _call(AGENT_MODEL, messages, system, AGENT_OPTIONS, max_tokens, keep_alive=KEEP_ALIVE_AGENT)
    if track:
        _track_benchmark("ask_agent", duration_ms, AGENT_MODEL)
    return text


def ask_coder(
    messages: list,
    system: str = "You are an expert Python developer. Return only raw Python code unless told otherwise.",
    max_tokens: int | None = None,
    track: bool = True,
) -> str:
    """
    Ask the code model (qwen3:0.6b) — for code generation, self-improvement.
    Automatically records benchmarks.
    """
    text, duration_ms = _call(CODE_MODEL, messages, system, CODE_OPTIONS, max_tokens, keep_alive=KEEP_ALIVE_CODE)
    if track:
        _track_benchmark("ask_coder", duration_ms, CODE_MODEL)
    return text


def ask_smart(
    messages: list,
    user_input: str,
    system: str = SYSTEM_PROMPT,
    max_tokens: int | None = None,
    track: bool = True,
) -> tuple[str, str]:
    """
    Smart routing — analyzes the task and picks the best model automatically.
    Returns (response_text, model_type) where model_type is 'code' or 'agent'.
    """
    model_type = classify_task(user_input)

    if model_type == "code":
        code_system = (
            "You are Rudra, an expert AI coding assistant created by Shiv, running on Windows.\n"
            "You write clean, efficient, well-commented code.\n"
            "If the user asks for code, provide the complete implementation.\n"
            "If asked to explain code, be concise and precise.\n"
            "Use PowerShell for system commands on Windows."
        )
        text, duration_ms = _call(CODE_MODEL, messages, code_system, CODE_OPTIONS, max_tokens, keep_alive=KEEP_ALIVE_CODE)
        if track:
            _track_benchmark("ask_smart_code", duration_ms, CODE_MODEL)
    else:
        text, duration_ms = _call(AGENT_MODEL, messages, system, AGENT_OPTIONS, max_tokens, keep_alive=KEEP_ALIVE_AGENT)
        if track:
            _track_benchmark("ask_smart_agent", duration_ms, AGENT_MODEL)

    return text, model_type


def ask_smart_stream(
    messages: list,
    user_input: str,
    system: str = SYSTEM_PROMPT,
    max_tokens: int | None = None,
):
    """
    Streaming version of ask_smart — yields (text_chunk, model_type) tuples.
    First yield is always ("", model_type) to announce which model was selected.
    """
    model_type = classify_task(user_input)

    if model_type == "code":
        model = CODE_MODEL
        options = {**CODE_OPTIONS}
        keep_alive_val = KEEP_ALIVE_CODE
        system = (
            "You are Rudra, an expert AI coding assistant created by Shiv, running on Windows.\n"
            "You write clean, efficient, well-commented code.\n"
            "If the user asks for code, provide the complete implementation.\n"
            "If asked to explain code, be concise and precise.\n"
            "Use PowerShell for system commands on Windows."
        )
    else:
        model = AGENT_MODEL
        options = {**AGENT_OPTIONS}
        keep_alive_val = KEEP_ALIVE_AGENT

    if max_tokens:
        options["num_predict"] = max_tokens

    # First yield: announce model selection
    yield "", model_type

    full_messages = [{"role": "system", "content": system}] + messages

    try:
        stream = ollama.chat(
            model=model,
            messages=full_messages,
            options=options,
            keep_alive=keep_alive_val,
            stream=True,
        )
        for chunk in stream:
            text = chunk["message"]["content"]
            if text:
                yield text, model_type
    except KeyboardInterrupt:
        # Stop streaming immediately on Ctrl+C
        yield "\n  [Generation Aborted]", model_type
        return
    except Exception as e:
        yield f"\n[Stream error: {e}]", model_type


def ask_agent_stream(
    messages: list,
    system: str = SYSTEM_PROMPT,
    max_tokens: int | None = None,
):
    """
    Streaming version of ask_agent — yields text chunks for real-time display.
    """
    options = {**AGENT_OPTIONS}
    if max_tokens:
        options["num_predict"] = max_tokens

    full_messages = [{"role": "system", "content": system}] + messages

    try:
        stream = ollama.chat(
            model=AGENT_MODEL,
            messages=full_messages,
            options=options,
            keep_alive=KEEP_ALIVE_AGENT,
            stream=True,
        )
        for chunk in stream:
            text = chunk["message"]["content"]
            if text:
                yield text
    except KeyboardInterrupt:
        yield "\n  [Generation Aborted]"
        return
    except Exception as e:
        yield f"\n[Stream error: {e}]"
