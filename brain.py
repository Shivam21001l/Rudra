# Improved code with reduced retries for faster performance
import ollama

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