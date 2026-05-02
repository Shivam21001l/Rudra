"""
Rudra Configuration — All settings, paths, model routing, and safety rules.
═══════════════════════════════════════════════════════════════════════════════
"""

from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent.resolve()
MEMORY_FILE    = BASE_DIR / "memory.json"
LOG_FILE       = BASE_DIR / "rudra.log"
BACKUP_DIR     = BASE_DIR / "backups"
TASK_INBOX     = BASE_DIR / "tasks" / "inbox"
TASK_DONE      = BASE_DIR / "tasks" / "done"
UPGRADES_PENDING = BASE_DIR / "upgrades" / "pending"
UPGRADES_HISTORY = BASE_DIR / "upgrades" / "history"

# Create all runtime directories
for _d in [BACKUP_DIR, TASK_INBOX, TASK_DONE, UPGRADES_PENDING, UPGRADES_HISTORY]:
    _d.mkdir(parents=True, exist_ok=True)

# ─── Model Configuration ─────────────────────────────────────────────────────
AGENT_MODEL = "gemma3:4b"        # Local — agentic workflow, conversation, reflection
CODE_MODEL  = "qwen3:1.7b"      # Local — code generation, self-improvement

# ─── LLM Parameters (tuned for 8GB RAM) ─────────────────────────────────────
AGENT_OPTIONS = {
    "temperature": 0.7,
    "top_k": 40,
    "num_predict": 256,       # Keep short — forces concise ReAct responses
    "num_ctx": 4096,          # Explicit context window for 8GB RAM
}

CODE_OPTIONS = {
    "temperature": 0.2,       # Low temp for precision
    "top_k": 20,
    "num_predict": 2048,      # Reduced to prevent rambling/hanging
    "num_ctx": 4096,          # Explicit context window for better memory usage
}

# ─── Resource Management ─────────────────────────────────────────────────────
# How long to keep models loaded in memory after the last request.
KEEP_ALIVE_AGENT = "15m"      # Keep agent loaded — reloading costs 30s+
KEEP_ALIVE_CODE  = "2m"       # Unload code model faster to free VRAM

# ─── Timing ───────────────────────────────────────────────────────────────────
MAX_HISTORY        = 6        # Fewer turns = smaller prompt = faster response
REFLECT_EVERY      = 5        # Reflect after every N turns
EVOLUTION_INTERVAL = 300      # Seconds between autonomous evolution checks (5 min)
HEARTBEAT_INTERVAL = 3600     # Seconds between proactive heartbeat triggers (1 hour)
HEARTBEAT_DELAY    = 300      # Seconds to wait after startup before first heartbeat
MAX_RETRIES        = 2        # LLM call retry count (less retries = faster fail)
RETRY_BACKOFF      = 1.0      # Seconds between retries
SHELL_TIMEOUT      = 30       # Max seconds for shell command execution
MAX_REACT_STEPS    = 5        # Max ReAct steps (reduced to prevent infinite loops)

# ─── System Prompt (compact — smaller = faster on 4B model) ──────────────────
SYSTEM_PROMPT = """You are Rudra, an AI agent on Windows with full system control. Be brief like Jarvis.

SKILLS: shell_execute, read_file, write_file, list_directory, system_stats, web_search, open_app, close_app, list_running_apps, set_volume, get_volume, set_brightness, get_brightness, screenshot, clipboard_read, clipboard_write, network_info, manage_service, lock_screen, sleep_pc, shutdown_pc, restart_pc, get_datetime, installed_apps, wifi_networks.

To use a skill, write on one line:
ACTION: {"skill": "SKILL_NAME", "args": {"key": "value"}}

CRITICAL RULES:
1. NEVER imagine an OBSERVATION. Wait for the system to provide it.
2. If you need to know a value (brightness, volume, etc.), use the 'get' skill first. Do NOT guess.
3. After receiving an OBSERVATION, continue with the next ACTION or finish with:
STATUS: SUCCESS
SUMMARY: <one line result>

Example for brightness:
User: What is the brightness?
Thought: I need to check the current brightness.
ACTION: {"skill": "get_brightness", "args": {}}
[Wait for Observation]
Observation: Current screen brightness is 75%.
STATUS: SUCCESS
SUMMARY: The screen brightness is currently 75%.

Be VERY brief. Max 2 sentences per thought. No filler."""

# ─── Safety — HARD LIMITS (never removed by any rewrite) ─────────────────────
PROTECTED_TOKENS = [
    "PROTECTED_TOKENS", "safety_check", "HARD LIMITS",
    "BACKUP_DIR", "input(", "review_required",
    "BANNED_COMMANDS", "human_approval",
]

# ─── Banned Shell Commands (Windows) ─────────────────────────────────────────
BANNED_COMMANDS = [
    "format c:",
    "format d:",
    "del /f /s /q c:\\",
    "Remove-Item -Recurse -Force C:\\",
    "Remove-Item -Recurse -Force D:\\",
    "rd /s /q c:\\",
    "rd /s /q d:\\",
    "reg delete HKLM",
    "shutdown /s",
    "shutdown /r",
    "bcdedit",
    "diskpart",
    "cipher /w",
    "sfc /scannow",
    "net user administrator",
]

# ─── Evolvable Modules — files the evolution engine can modify ────────────────
EVOLVABLE_MODULES = [
    "brain.py",
    "memory.py",
    "shell.py",
    "reflection.py",
    "benchmarks.py",
    "tasks.py",
]

# NON-evolvable (safety-critical):
# config.py, evolution.py, rudra.py — these are never auto-modified

# ─── Performance Thresholds ───────────────────────────────────────────────────
MAX_ALLOWED_REGRESSION = 1.2   # Reject upgrade if response time increases > 20%
MIN_CODE_LENGTH        = 200   # Reject generated code shorter than this
