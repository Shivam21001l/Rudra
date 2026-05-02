"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  RUDRA — Self-Evolving AI Agent for Windows                                ║
║  Created by Shiv | Dual-Model Architecture | Auto Self-Improving           ║
╚══════════════════════════════════════════════════════════════════════════════╝

Entry point. Orchestrates the desktop GUI, WebSocket server, evolution,
benchmarks, and background heartbeat daemon.

Smart Routing:
  Every user message is analyzed and routed to the best model:
    • gemma3:4b     — conversation, agentic tasks, general Q&A
    • qwen3:1.7b    — code generation, algorithms, debugging

Behaviour:
  All commands and answers execute directly — no approval prompts.
  Human approval is ONLY required for self-modification via /upgrade.

Commands:
  exit / quit      — Save and exit
  status           — Show agent stats
  /upgrade         — Trigger self-improvement (asks for approval)
  upgrades         — List pending upgrade proposals
  approve <id>     — Apply an upgrade after review
  reject <id>      — Discard an upgrade (optional reason after id)
  benchmark        — Show performance trends
  rollback <file>  — Roll back last change to a file
  backups          — List all backups
"""

import sys
import json
import re
import threading
import time
import platform

# --- WMI HANG FIX ---
# Prevent WMI queries from hanging when `ollama` client builds its User-Agent
_original_machine = platform.machine
platform.machine = lambda: "AMD64"
_original_system = platform.system
platform.system = lambda: "Windows"
_original_python_version = platform.python_version
platform.python_version = lambda: "3.13.0"
# --------------------

# ─── Dependency check ─────────────────────────────────────────────────────────
try:
    import colorama
    colorama.init()
except ImportError:
    pass  # Colors optional

from config import (
    AGENT_MODEL, CODE_MODEL, MAX_HISTORY,
    REFLECT_EVERY, EVOLUTION_INTERVAL, MAX_REACT_STEPS,
)
from brain import (
    check_ollama_connection, ensure_model,
    ask_agent, ask_smart_stream, get_model_label, classify_task,
)
from skills import registry
import memory as mem_module
import benchmarks
import evolution
import reflection
import tasks


# ─── Colors (graceful fallback if no colorama) ────────────────────────────────
class C:
    CYAN    = "\033[96m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    MAGENTA = "\033[95m"
    BLUE    = "\033[94m"
    DIM     = "\033[2m"
    BOLD    = "\033[1m"
    RESET   = "\033[0m"


# ─── Logging ──────────────────────────────────────────────────────────────────
_log_lock = threading.Lock()

def log(msg: str):
    from datetime import datetime
    from config import LOG_FILE
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with _log_lock:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


# ─── Action Extraction ───────────────────────────────────────────────────────
def extract_action(text: str) -> dict | None:
    """Extract the ACTION JSON from model output."""
    action_idx = text.find("ACTION:")
    if action_idx == -1:
        return None
    
    start = text.find("{", action_idx)
    if start == -1:
        return None
    
    raw = text[start:]
    depth = 0
    end = 0
    for i, ch in enumerate(raw):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == 0:
        return None
    try:
        return json.loads(raw[:end])
    except json.JSONDecodeError:
        return None


# ─── Startup ──────────────────────────────────────────────────────────────────
def startup():
    """Verify environment and display banner."""
    mem = mem_module.load()
    version = mem.get("upgrades_applied", 0)

    print(f"\n{C.CYAN}{'═' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  🔱  RUDRA v{version}  |  Self-Evolving AI Agent  |  Windows{C.RESET}")
    print(f"{C.DIM}  Agent: {AGENT_MODEL}  |  Coder: {CODE_MODEL}{C.RESET}")
    print(f"{C.DIM}  Smart routing: auto-selects best model per task{C.RESET}")
    print(f"{C.DIM}  Direct execution — no approval prompts (except /upgrade){C.RESET}")
    print(f"{C.DIM}  Turns: {mem.get('turn', 0)}  |  Tasks: {mem.get('tasks_done', 0)}  |  Upgrades: {version}{C.RESET}")
    print(f"{C.DIM}  Skills: {', '.join(registry.list_skills())}{C.RESET}")
    print(f"{C.CYAN}{'═' * 60}{C.RESET}")
    print(f"{C.DIM}  Commands: exit | status | /upgrade | upgrades | approve | reject | benchmark{C.RESET}")
    print()

    # Check Ollama
    ok, msg = check_ollama_connection()
    if not ok:
        print(f"{C.RED}  ❌ {msg}{C.RESET}")
        print(f"{C.YELLOW}  Rudra needs Ollama running to function.{C.RESET}")
        sys.exit(1)
    print(f"  {C.GREEN}✅ Ollama connected{C.RESET}")

    # Ensure models
    ensure_model(AGENT_MODEL)
    ensure_model(CODE_MODEL)
    print()

    # Show pending upgrades if any
    pending = evolution.list_pending()
    if pending:
        print(f"  {C.YELLOW}🔔 {len(pending)} pending upgrade(s) waiting for review.{C.RESET}")
        print(f"  {C.DIM}   Type 'upgrades' to see them.{C.RESET}\n")


# ─── Command Handlers ────────────────────────────────────────────────────────
def handle_status(mem: dict):
    """Display agent status."""
    print(f"\n{C.CYAN}{'─' * 40}{C.RESET}")
    print(f"  {C.BOLD}🔱 Rudra Status{C.RESET}")
    print(f"  Version (upgrades):  {mem.get('upgrades_applied', 0)}")
    print(f"  Turns:               {mem.get('turn', 0)}")
    print(f"  Tasks done:          {mem.get('tasks_done', 0)}")
    print(f"  Reflections stored:  {len(mem.get('reflections', []))}")
    print(f"  Upgrades rejected:   {mem.get('upgrades_rejected', 0)}")
    print(f"  Pending upgrades:    {len(evolution.list_pending())}")
    print(f"  Agent model:         {AGENT_MODEL}")
    print(f"  Code model:          {CODE_MODEL}")
    print(f"  Active skills:       {', '.join(registry.list_skills())}")
    print(f"{C.CYAN}{'─' * 40}{C.RESET}\n")


def handle_upgrades():
    """List all pending upgrade proposals."""
    pending = evolution.list_pending()
    if not pending:
        print(f"\n  {C.GREEN}✅ No pending upgrades.{C.RESET}\n")
        return

    print(f"\n{C.YELLOW}{'─' * 50}{C.RESET}")
    print(f"  {C.BOLD}🔔 Pending Upgrades{C.RESET}")
    for p in pending:
        print(f"\n  {C.BOLD}{p['id']}{C.RESET} → {p['target_file']}")
        print(f"  {C.DIM}{p['timestamp']}{C.RESET}")
        print(f"  {p['summary']}")
        # Show diff preview (first 15 lines)
        diff_lines = p.get("diff", "").splitlines()[:15]
        if diff_lines:
            print(f"\n  {C.DIM}Diff preview:{C.RESET}")
            for dl in diff_lines:
                if dl.startswith("+") and not dl.startswith("+++"):
                    print(f"    {C.GREEN}{dl}{C.RESET}")
                elif dl.startswith("-") and not dl.startswith("---"):
                    print(f"    {C.RED}{dl}{C.RESET}")
                else:
                    print(f"    {C.DIM}{dl}{C.RESET}")
            if len(p.get("diff", "").splitlines()) > 15:
                print(f"    {C.DIM}... ({len(p['diff'].splitlines()) - 15} more lines){C.RESET}")

    print(f"\n  {C.YELLOW}approve <id>{C.RESET} to apply  |  {C.YELLOW}reject <id> [reason]{C.RESET} to discard")
    print(f"{C.YELLOW}{'─' * 50}{C.RESET}\n")


def handle_approve(args: str):
    """Approve a pending upgrade."""
    upgrade_id = args.strip()
    if not upgrade_id:
        print(f"  {C.RED}Usage: approve <upgrade_id>{C.RESET}")
        return
    result = evolution.human_approval(upgrade_id, approved=True)
    print(f"\n  {result}\n")


def handle_reject(args: str):
    """Reject a pending upgrade."""
    parts = args.strip().split(maxsplit=1)
    if not parts:
        print(f"  {C.RED}Usage: reject <upgrade_id> [reason]{C.RESET}")
        return
    upgrade_id = parts[0]
    reason = parts[1] if len(parts) > 1 else ""
    result = evolution.human_approval(upgrade_id, approved=False, reason=reason)
    print(f"\n  {result}\n")


def handle_benchmark(mem: dict):
    """Display performance benchmarks."""
    print(f"\n{benchmarks.format_stats(mem)}\n")


def handle_rollback(args: str):
    """Roll back a file to its latest backup."""
    target = args.strip()
    if not target:
        # Show available backups
        bks = evolution.list_backups()
        if bks:
            print(f"\n  Available backups:")
            for b in bks[:10]:
                print(f"    {b}")
            print(f"\n  {C.YELLOW}Usage: rollback <filename.py>{C.RESET}\n")
        else:
            print(f"\n  {C.DIM}No backups available.{C.RESET}\n")
        return
    result = evolution.rollback(target)
    print(f"\n  {result}\n")


def handle_backups():
    """List all backups."""
    bks = evolution.list_backups()
    if not bks:
        print(f"\n  {C.DIM}No backups.{C.RESET}\n")
        return
    print(f"\n  {C.BOLD}💾 Backups:{C.RESET}")
    for b in bks:
        print(f"    {b}")
    print()


def handle_upgrade_now():
    """
    On-demand self-improvement triggered by /upgrade.
    Analyzes code, generates a proposal, shows it, and asks for approval.
    This is the ONLY command that requires human confirmation.
    """
    print(f"\n  {C.MAGENTA}🔍 Analyzing Rudra's code for improvements...{C.RESET}")
    print(f"  {C.DIM}   (this may take a minute){C.RESET}\n")

    mem = mem_module.load()

    # Check if enough reflections exist
    if len(mem.get("reflections", [])) < 2:
        print(f"  {C.YELLOW}⚠️  Not enough conversation history for analysis.{C.RESET}")
        print(f"  {C.DIM}   Chat more with Rudra first — reflections build over time.{C.RESET}\n")
        return

    # Check pending proposals limit
    pending = evolution.list_pending()
    if len(pending) >= 3:
        print(f"  {C.YELLOW}⚠️  Already {len(pending)} pending upgrades. Review those first.{C.RESET}")
        print(f"  {C.DIM}   Type 'upgrades' to see them.{C.RESET}\n")
        return

    # Generate upgrade proposal
    try:
        proposal = evolution._generate_upgrade(mem)
    except Exception as e:
        print(f"  {C.RED}❌ Evolution error: {e}{C.RESET}\n")
        return

    if not proposal:
        print(f"  {C.GREEN}✅ Rudra is already optimal — no improvements found.{C.RESET}\n")
        return

    # Show the proposal
    print(f"  {C.BOLD}{C.MAGENTA}🔔 Upgrade Proposal: {proposal['id']}{C.RESET}")
    print(f"  {C.DIM}Target: {proposal['target_file']}{C.RESET}")
    print(f"  {proposal['summary']}\n")

    # Show diff preview
    diff_lines = proposal.get("diff", "").splitlines()[:20]
    if diff_lines:
        print(f"  {C.DIM}Diff preview:{C.RESET}")
        for dl in diff_lines:
            if dl.startswith("+") and not dl.startswith("+++"):
                print(f"    {C.GREEN}{dl}{C.RESET}")
            elif dl.startswith("-") and not dl.startswith("---"):
                print(f"    {C.RED}{dl}{C.RESET}")
            else:
                print(f"    {C.DIM}{dl}{C.RESET}")
        total_diff_lines = len(proposal.get("diff", "").splitlines())
        if total_diff_lines > 20:
            print(f"    {C.DIM}... ({total_diff_lines - 20} more lines){C.RESET}")
    print()

    # THIS is the approval gate — the ONLY place Rudra asks for confirmation
    try:
        confirm = input(f"  {C.YELLOW}   Apply this upgrade? (y/n): {C.RESET}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        confirm = "n"

    if confirm == "y":
        evolution.save_proposal(proposal)
        result = evolution.human_approval(proposal["id"], approved=True)
        print(f"\n  {result}\n")
    else:
        evolution.save_proposal(proposal)
        evolution.human_approval(proposal["id"], approved=False, reason="Declined via /upgrade")
        print(f"\n  {C.DIM}⛔ Upgrade declined.{C.RESET}\n")


# ─── Terminal Chat Response with ReAct Loop ───────────────────────────────────
def respond(user_input: str, mem: dict) -> str:
    """
    Generate a response using the ReAct loop with skills.
    Works the same as the WebSocket version but in the terminal.
    """
    try:
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in mem["history"][-MAX_HISTORY:]
        ]
        messages.append({"role": "user", "content": user_input})

        # Determine which model handles this
        model_type = classify_task(user_input)
        label = get_model_label(model_type)
        color = C.BLUE if model_type == "code" else C.GREEN
        print(f"\n  {C.DIM}[{label}]{C.RESET}")

        # ─── ReAct Loop ──────────────────────────────────────────────
        step = 0
        final_reply = ""

        while step < MAX_REACT_STEPS:
            step += 1

            # Stream the LLM response
            print(f"  {color}🔱  ", end="", flush=True)
            full_reply = []
            first_chunk = True

            for chunk_text, chunk_model in ask_smart_stream(messages, user_input):
                if first_chunk:
                    first_chunk = False
                    continue  # Skip the model announcement chunk
                print(chunk_text, end="", flush=True)
                full_reply.append(chunk_text)

            print(f"{C.RESET}")
            reply = "".join(full_reply)

            if "[Generation Aborted]" in reply:
                return "[Aborted]"

            # ── Check: ACTION to execute? ──
            action_data = extract_action(reply)
            
            # Prevent hallucinated observations in the same turn
            if action_data and "OBSERVATION:" in reply:
                reply = reply.split("OBSERVATION:")[0].strip()
                # If splitting left it empty or removed the ACTION, try to recover
                if "ACTION:" not in reply:
                    # Use robust extract_action on the full reply to get the action JSON
                    full_text = "".join(full_reply)
                    recovered_action = extract_action(full_text)
                    if recovered_action:
                        # Reconstruct a minimal valid reply with the action
                        reply = f"ACTION: {json.dumps(recovered_action, ensure_ascii=False)}"
                    else:
                        # Both extraction attempts failed — keep the original pre-truncation reply
                        reply = "".join(full_reply)
                        log(f"[Warn] Could not extract ACTION after OBSERVATION split; keeping full reply")

            # Only append non-empty, well-formed assistant messages
            if reply and reply.strip():
                messages.append({"role": "assistant", "content": reply})

            if action_data:
                skill_name = action_data.get("skill", "")
                skill_args = action_data.get("args", {})

                print(f"\n  {C.YELLOW}⚙️  {skill_name}({json.dumps(skill_args, ensure_ascii=False)}){C.RESET}")

                # Execute skill
                output = registry.execute(skill_name, skill_args)

                # Truncate for display
                display_output = output
                if len(display_output) > 500:
                    display_output = display_output[:450] + "\n... [truncated]"
                print(f"  {C.DIM}📋 {display_output}{C.RESET}\n")

                # Truncate for context
                if len(output) > 1500:
                    output = output[:1400] + "\n... [truncated]"

                # Feed observation back to LLM
                messages.append({"role": "user", "content": f"OBSERVATION:\n{output}"})
                mem_module.increment(mem, "tasks_done")
                continue  # Skip success check this turn; let LLM process the observation next turn

            # ── Check: Task complete? ──
            if "STATUS: SUCCESS" in reply:
                for line in reply.splitlines():
                    if line.strip().startswith("SUMMARY:"):
                        final_reply = line.split("SUMMARY:", 1)[1].strip()
                if final_reply:
                    print(f"\n  {C.GREEN}✅ Done: {final_reply}{C.RESET}\n")
                break

            # No ACTION and no SUCCESS → conversational reply, done
            break

        return final_reply or reply[:500]

    except KeyboardInterrupt:
        print(f"{C.RESET}\n  {C.YELLOW}⚠️  Task aborted by user.{C.RESET}\n")
        return "[Aborted]"


# ─── Entry Point ──────────────────────────────────────────────────────────────
def main():
    startup()

    # Start background daemons
    tasks.start_daemon()
    evolution.start_evolution(EVOLUTION_INTERVAL)

    log("Rudra started (TUI Mode)")

    # Load memory state
    mem = mem_module.load()

    while True:
        try:
            print()
            user_input = input(f"  {C.BOLD}{C.CYAN}👤 You:{C.RESET} ").strip()
            if not user_input:
                continue

            cmd_lower = user_input.lower()
            if cmd_lower in ["exit", "quit"]:
                print(f"  {C.DIM}Saving memory & shutting down...{C.RESET}")
                break
            elif cmd_lower == "status":
                handle_status(mem)
                continue
            elif cmd_lower in ["upgrades", "/upgrades"]:
                handle_upgrades()
                continue
            elif cmd_lower.startswith("approve "):
                pid = user_input.split(" ", 1)[1].strip()
                handle_approve(pid)
                continue
            elif cmd_lower.startswith("reject "):
                handle_reject(user_input)
                continue
            elif cmd_lower == "benchmark":
                handle_benchmark(mem)
                continue
            elif cmd_lower.startswith("rollback "):
                fname = user_input.split(" ", 1)[1].strip()
                handle_rollback(fname)
                continue
            elif cmd_lower == "backups":
                handle_backups()
                continue
            elif cmd_lower == "/upgrade":
                handle_upgrade_now()
                continue

            # Route everything else to the agent
            log(f"User: {user_input}")
            reply = respond(user_input, mem)
            log(f"Rudra: {reply}")

            # Increment turn counter
            mem["turn"] = mem.get("turn", 0) + 1

            # Store conversation in memory
            mem_module.add_history(mem, "user", user_input)
            mem_module.add_history(mem, "assistant", reply[:500])

            # Reflection trigger (background, every N turns)
            if mem["turn"] % REFLECT_EVERY == 0:
                print(f"  {C.DIM}Rudra is reflecting...{C.RESET}")
                import threading as _t
                _t.Thread(
                    target=reflection.reflect_on_conversation,
                    args=(user_input, reply),
                    daemon=True,
                ).start()

            # Save
            mem_module.save(mem)

        except KeyboardInterrupt:
            print(f"\n  {C.YELLOW}Interrupt received. Type 'exit' to quit.{C.RESET}")
        except EOFError:
            break
        except Exception as e:
            print(f"\n  {C.RED}❌ Error: {e}{C.RESET}")

    log("Rudra stopped")


if __name__ == "__main__":
    main()
