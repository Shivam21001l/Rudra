"""
Evolving Agent by Shiv — Auto Self-Rewriting Version
-----------------------------------------------------
- Runs, chats, executes tasks
- Automatically rewrites itself when ready
- Hot-restarts after rewrite
- Backs up every old version
- No manual prompting needed
"""

import ollama, json, os, sys, time, shutil, threading, difflib, subprocess
from datetime import datetime
from pathlib import Path

# ─── paths ────────────────────────────────────────────────────────────────────
BASE       = Path(__file__).parent
MEMORY_F   = BASE / "memory.json"
TASK_INBOX = BASE / "tasks/inbox"
TASK_DONE  = BASE / "tasks/done"
LOG_F      = BASE / "agent.log"
BACKUP_DIR = BASE / "backups"
SELF_PATH  = Path(__file__).resolve()

for d in [TASK_INBOX, TASK_DONE, BACKUP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── HARD LIMITS — never removed by any rewrite ───────────────────────────────
PROTECTED_TOKENS = [
    "PROTECTED_TOKENS", "safety_check", "HARD LIMITS",
    "BACKUP_DIR", "input(", "review_required",
]

MODEL         = "llama3"
MAX_HISTORY   = 8
REFLECT_EVERY = 5
UPGRADE_EVERY = 15

# ─── system prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an autonomous AI assistant made by Shiv on Kali Linux.

Rules:
- Be concise and direct. No filler.
- For system tasks start reply with ACTION: then the shell command.
- For questions just answer.
- Never make up facts. Say "I don't know" when unsure.

ACTION format:
ACTION:
<shell command>
REASON: <one line>"""

# ─── memory ───────────────────────────────────────────────────────────────────
_mem: dict = {}

def load_memory() -> dict:
    global _mem
    if _mem:
        return _mem
    _mem = json.loads(MEMORY_F.read_text()) if MEMORY_F.exists() else {
        "history": [], "reflections": [],
        "tasks_done": 0, "upgrades_applied": 0, "turn": 0
    }
    return _mem

def save_memory(mem: dict):
    global _mem
    _mem = mem
    mem["history"]     = mem["history"][-(MAX_HISTORY * 2):]
    mem["reflections"] = mem["reflections"][-20:]
    MEMORY_F.write_text(json.dumps(mem, separators=(',', ':')))

# ─── logging ──────────────────────────────────────────────────────────────────
_log_lock = threading.Lock()

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with _log_lock:
        with open(LOG_F, "a") as f:
            f.write(line + "\n")

# ─── ollama call ──────────────────────────────────────────────────────────────
def ask(messages: list, system: str = SYSTEM_PROMPT, max_tokens: int = 512) -> str:
    try:
        res = ollama.chat(
            model=MODEL,
            messages=[{"role": "system", "content": system}] + messages,
            options={"num_predict": max_tokens, "temperature": 0.7, "top_k": 40}
        )
        return res["message"]["content"].strip()
    except Exception as e:
        return f"[Error: {e}]"

# ─── shell execution ──────────────────────────────────────────────────────────
BANNED = ["rm -rf /", "mkfs", ":(){:|:&};:", "dd if=/dev/zero", "chmod -R 777 /"]

def run_shell(cmd: str) -> str:
    for b in BANNED:
        if b in cmd:
            return f"[BLOCKED] {cmd}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=30)
        return (r.stdout or r.stderr or "(no output)").strip()[:2000]
    except subprocess.TimeoutExpired:
        return "[Timeout]"
    except Exception as e:
        return f"[Error] {e}"

# ─── parse ACTION ─────────────────────────────────────────────────────────────
def parse_action(reply: str) -> str | None:
    if "ACTION:" not in reply:
        return None
    for line in reply.split("ACTION:")[1].strip().splitlines():
        line = line.strip()
        if line and not line.startswith("REASON:"):
            return line
    return None

# ─── respond ──────────────────────────────────────────────────────────────────
def respond(user_input: str, mem: dict) -> str:
    messages = [{"role": m["role"], "content": m["content"]}
                for m in mem["history"][-(MAX_HISTORY):]]
    messages.append({"role": "user", "content": user_input})

    reply = ask(messages)
    cmd   = parse_action(reply)

    if cmd:
        print(f"\n🛠️  Command: {cmd}")
        confirm = input("   Run it? (y/n): ").strip().lower()
        if confirm == "y":
            out = run_shell(cmd)
            print(f"   Output: {out}\n")
            mem["tasks_done"] = mem.get("tasks_done", 0) + 1
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"Output: {out}. One sentence summary."}]
            reply = ask(messages, max_tokens=80)
        else:
            reply = "Cancelled."

    return reply

# ─── background reflection ────────────────────────────────────────────────────
def reflect_bg(mem: dict, user_input: str, ai_output: str):
    r = ask([{"role": "user", "content":
        f"User: {user_input}\nAI: {ai_output}\n2 sentences: what was weak, one fix idea."}],
        system="You are a critic. Be brief.", max_tokens=120)
    mem["reflections"].append({"t": str(datetime.now()), "r": r})
    save_memory(mem)

# ─── safety check ─────────────────────────────────────────────────────────────
def safety_check(new_code: str) -> tuple[bool, str]:
    original = SELF_PATH.read_text()
    for token in PROTECTED_TOKENS:
        if token in original and token not in new_code:
            return False, f"Removed protected: '{token}'"
    try:
        compile(new_code, "<upgrade>", "exec")
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"
    return True, "OK"

# ─── review gate (kept for audit log, auto-approves) ─────────────────────────
def review_required(new_code: str, summary: str) -> bool:
    """Auto-approves after logging. Backup always saved first."""
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk  = BACKUP_DIR / f"agent_{ts}.py.bak"
    shutil.copy2(SELF_PATH, bk)

    diff = "".join(difflib.unified_diff(
        SELF_PATH.read_text().splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        fromfile="old", tofile="new", n=2
    ))
    audit = BACKUP_DIR / f"upgrade_{ts}.log"
    audit.write_text(f"TIME: {ts}\nSUMMARY:\n{summary}\n\nDIFF:\n{diff}")

    log(f"💾 Backup → backups/agent_{ts}.py.bak")
    log(f"📋 Audit  → backups/upgrade_{ts}.log")
    return True   # auto-approved — Shiv can review logs anytime

# ─── auto self-rewrite ────────────────────────────────────────────────────────
def auto_upgrade(mem: dict):
    refs = mem.get("reflections", [])
    if len(refs) < 4:
        return

    recent   = " | ".join(r["r"] for r in refs[-5:])
    cur_code = SELF_PATH.read_text()

    log("🔍 Analysing self for upgrade…")

    new_code = ask([{"role": "user", "content": f"""
You are improving your own Python agent code.

WEAKNESSES FOUND IN RECENT CONVERSATIONS:
{recent}

CURRENT SOURCE CODE:
```python
{cur_code}
```

YOUR TASK:
- Identify the single most impactful improvement.
- Rewrite the full improved agent.py file.
- Make it faster, smarter, or more capable than before.
- Improve one thing at a time — do it properly.

HARD RULES:
- Keep ALL of these tokens intact: {PROTECTED_TOKENS}
- No dangerous shell commands, no file deletions
- The new code must be faster or equal speed — never slower
- Return ONLY the raw Python file, zero markdown, zero explanation
- If there is genuinely nothing to improve, return exactly: NO_UPGRADE
"""}],
        system="You are an expert Python developer rewriting your own code. Return only raw Python or NO_UPGRADE.",
        max_tokens=6000
    )

    if not new_code or "NO_UPGRADE" in new_code or len(new_code) < 300:
        log("✅ No upgrade needed right now.")
        return

    # Strip accidental markdown fences
    if new_code.startswith("```"):
        lines = new_code.splitlines()
        new_code = "\n".join(
            l for l in lines if not l.strip().startswith("```")
        ).strip()

    ok, reason = safety_check(new_code)
    if not ok:
        log(f"🚫 Upgrade blocked: {reason}")
        return

    # Get a plain English summary
    summary = ask([{"role": "user", "content":
        f"2 sentence plain English summary of what improved in this new agent code vs old:\n{new_code[:2000]}"}],
        max_tokens=80)

    if not review_required(new_code, summary):
        return

    # Write new code
    SELF_PATH.write_text(new_code)
    mem["upgrades_applied"] = mem.get("upgrades_applied", 0) + 1
    save_memory(mem)

    log(f"🚀 Upgrade applied ({mem['upgrades_applied']} total): {summary}")
    log("♻️  Restarting with improved code…")

    time.sleep(0.5)
    os.execv(sys.executable, [sys.executable] + sys.argv)   # hot-restart

# ─── background upgrade thread ────────────────────────────────────────────────
_upgrade_running = threading.Event()

def upgrade_bg(mem: dict):
    if _upgrade_running.is_set():
        return
    _upgrade_running.set()
    try:
        auto_upgrade(mem)
    finally:
        _upgrade_running.clear()

# ─── inbox daemon ─────────────────────────────────────────────────────────────
def daemon_loop():
    while True:
        try:
            mem = load_memory()
            for tf in sorted(TASK_INBOX.glob("*.txt")):
                task  = tf.read_text().strip()
                reply = ask([{"role": "user", "content": task}], max_tokens=300)
                out   = TASK_DONE / tf.name.replace(".txt", "_reply.txt")
                out.write_text(f"TASK:\n{task}\n\nREPLY:\n{reply}\n")
                mem["history"] += [
                    {"role": "user",      "content": task},
                    {"role": "assistant", "content": reply}
                ]
                tf.rename(TASK_DONE / tf.name)
                save_memory(mem)
                log(f"📥 Inbox task done: {tf.name}")
        except Exception as e:
            log(f"[daemon] {e}")
        time.sleep(300)

# ─── main chat loop ───────────────────────────────────────────────────────────
def chat_loop():
    mem = load_memory()
    ua  = mem.get("upgrades_applied", 0)
    print(f"\n{'═'*52}")
    print(f"🤖  Evolving Agent v{ua}  |  Shiv's AI  |  Kali")
    print(f"    'exit' quit  |  'status' stats  |  auto-evolving")
    print(f"{'═'*52}\n")

    while True:
        try:
            raw = input("🧑  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            save_memory(mem)
            print("\n👋  Bye!")
            sys.exit(0)

        if not raw:
            continue

        if raw.lower() in ("exit", "quit"):
            save_memory(mem)
            print("👋  Bye!")
            break

        if raw.lower() == "status":
            print(f"\n  Version (upgrades): {mem.get('upgrades_applied',0)}")
            print(f"  Turns:              {mem.get('turn',0)}")
            print(f"  Tasks done:         {mem.get('tasks_done',0)}")
            print(f"  Reflections stored: {len(mem.get('reflections',[]))}")
            print(f"  Upgrade running:    {_upgrade_running.is_set()}\n")
            continue

        reply = respond(raw, mem)
        print(f"\n🤖  {reply}\n")

        mem["history"] += [
            {"role": "user",      "content": raw},
            {"role": "assistant", "content": reply}
        ]
        mem["turn"] = mem.get("turn", 0) + 1
        save_memory(mem)

        # Reflect in background every N turns
        if mem["turn"] % REFLECT_EVERY == 0:
            threading.Thread(
                target=reflect_bg, args=(mem, raw, reply), daemon=True
            ).start()

        # Auto-upgrade in background every N turns
        if mem["turn"] % UPGRADE_EVERY == 0:
            threading.Thread(
                target=upgrade_bg, args=(mem,), daemon=True
            ).start()


if __name__ == "__main__":
    threading.Thread(target=daemon_loop, daemon=True).start()
    chat_loop()
