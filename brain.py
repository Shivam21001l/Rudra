"""
Rudra Brain — Model routing, Ollama connection, task classification,
and all LLM interaction functions.

╔══════════════════════════════════════════════════════════════════════╗
║  Dual-Model Architecture:                                            ║
║  • gemma3:4b  — conversation, agentic tasks, general Q&A            ║
║  • qwen3:1.7b — code generation, algorithms, debugging              ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import time
import ollama

from config import (
    AGENT_MODEL, CODE_MODEL,
    AGENT_OPTIONS, CODE_OPTIONS,
    KEEP_ALIVE_AGENT, KEEP_ALIVE_CODE,
    SYSTEM_PROMPT, MAX_RETRIES, RETRY_BACKOFF,
)

# ─── Task Classification Keywords ────────────────────────────────────────────

_CODE_KEYWORDS = [
    "code", "write", "script", "function", "debug", "fix bug", "program",
    "algorithm", "class", "import", "python", "powershell", "implement",
    "def ", "loop", "syntax", "error in", "compile", "refactor", "snippet",
    "method", "variable", "array", "list", "dict", "json", "parse",
    "regex", "api", "module", "library", "pip", "package",
]

# ─── Task Classifier ─────────────────────────────────────────────────────────

def classify_task(text: str) -> str:
    """
    Classify user input as 'code' or 'agent' task.
    Returns 'code' if coding-related, else 'agent'.
    """
    t = text.lower()
    return "code" if any(k in t for k in _CODE_KEYWORDS) else "agent"


def get_model_label(model_type: str) -> str:
    """Return a human-readable label for the selected model."""
    if model_type == "code":
        return f"💻 Coder ({CODE_MODEL})"
    return f"🔱 Agent ({AGENT_MODEL})"


# ─── Ollama Connection & Model Management ────────────────────────────────────

def check_ollama_connection() -> tuple[bool, str]:
    """
    Verify Ollama is running and reachable.
    Returns (True, "Connected") or (False, error_message).
    """
    try:
        ollama.list()
        return True, "Connected"
    except Exception as e:
        return False, f"Cannot reach Ollama at localhost:11434 — is it running? ({e})"


def ensure_model(model: str) -> None:
    """
    Check if a model is available locally.
    If not, pull it automatically (one-time download).
    """
    try:
        available = [m.model for m in ollama.list().models]
        # Normalize: ollama sometimes appends ':latest'
        available_normalized = [m.split(":")[0] for m in available]
        model_base = model.split(":")[0]

        if model_base not in available_normalized and model not in available:
            print(f"  📥 Pulling {model} (first time — may take a few minutes)...")
            for progress in ollama.pull(model, stream=True):
                status = progress.get("status", "")
                if status and "pulling" in status.lower():
                    print(f"  ⏳ {status}", end="\r")
            print(f"  ✅ {model} ready          ")
        else:
            print(f"  ✅ {model} ready")
    except Exception as e:
        print(f"  ⚠️  Could not verify {model}: {e}")
        print(f"  ℹ️  Continuing anyway — model may still work.")


# ─── Non-Streaming LLM Call ──────────────────────────────────────────────────

def ask_agent(
    messages: list,
    system: str = SYSTEM_PROMPT,
    model: str | None = None,
    max_tokens: int | None = None,
    track: bool = True,
) -> str:
    """
    Blocking (non-streaming) call to the agent model.
    Used for internal tasks like reflection and evolution.
    Returns the full response string.
    """
    target_model = model or AGENT_MODEL
    options = {**AGENT_OPTIONS}
    if max_tokens:
        options["num_predict"] = max_tokens

    full_messages = [{"role": "system", "content": system}] + messages

    for attempt in range(MAX_RETRIES):
        try:
            resp = ollama.chat(
                model=target_model,
                messages=full_messages,
                options=options,
                keep_alive=KEEP_ALIVE_AGENT,
            )
            return resp["message"]["content"]
        except KeyboardInterrupt:
            return "[Aborted]"
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
            else:
                return f"[Error after {MAX_RETRIES} attempts] {e}"

    return "[Error] Max retries exceeded"


def ask_code(
    messages: list,
    system: str | None = None,
    max_tokens: int | None = None,
    track: bool = True,
) -> str:
    """
    Blocking (non-streaming) call to the code model.
    Used when code generation is needed without streaming.
    """
    code_system = system or (
        "You are Rudra, an expert AI coding assistant created by Shiv, running on Windows.\n"
        "You write clean, efficient, well-commented code.\n"
        "Provide complete implementations. Use PowerShell for Windows system commands."
    )
    options = {**CODE_OPTIONS}
    if max_tokens:
        options["num_predict"] = max_tokens

    full_messages = [{"role": "system", "content": code_system}] + messages

    for attempt in range(MAX_RETRIES):
        try:
            resp = ollama.chat(
                model=CODE_MODEL,
                messages=full_messages,
                options=options,
                keep_alive=KEEP_ALIVE_CODE,
            )
            return resp["message"]["content"]
        except KeyboardInterrupt:
            return "[Aborted]"
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
            else:
                return f"[Error after {MAX_RETRIES} attempts] {e}"

    return "[Error] Max retries exceeded"


# ─── Streaming LLM Calls ─────────────────────────────────────────────────────

def ask_smart_stream(
    messages: list,
    user_input: str,
    system: str = SYSTEM_PROMPT,
    max_tokens: int | None = None,
):
    """
    Smart streaming — auto-routes to the best model based on task type.
    Yields (text_chunk, model_type) tuples.
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
        yield "\n [Generation Aborted]", model_type
        return
    except Exception as e:
        yield f"\n[Stream error: {e}]", model_type


def ask_agent_stream(
    messages: list,
    system: str = SYSTEM_PROMPT,
    max_tokens: int | None = None,
):
    """
    Streaming call always using the agent model.
    Yields plain text chunks (no model_type tuple).
    Used by internal subsystems that don't need smart routing.
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
        yield "\n [Generation Aborted]"
        return
    except Exception as e:
        yield f"\n[Stream error: {e}]"