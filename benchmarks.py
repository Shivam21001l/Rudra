"""
Rudra Benchmarks — Performance tracking, trend analysis, and regression detection.
═══════════════════════════════════════════════════════════════════════════════
"""

from config import MAX_ALLOWED_REGRESSION


def get_avg_response_time(mem: dict, model: str | None = None, last_n: int = 20) -> float:
    """Get average response time in ms for recent calls."""
    benchmarks = mem.get("benchmarks", [])
    if model:
        benchmarks = [b for b in benchmarks if b.get("model") == model]
    recent = benchmarks[-last_n:]
    if not recent:
        return 0.0
    return sum(b["ms"] for b in recent) / len(recent)


def get_trend(mem: dict, model: str | None = None) -> str:
    """Compare recent performance vs older performance."""
    benchmarks = mem.get("benchmarks", [])
    if model:
        benchmarks = [b for b in benchmarks if b.get("model") == model]
    if len(benchmarks) < 10:
        return "insufficient_data"

    mid = len(benchmarks) // 2
    old_avg = sum(b["ms"] for b in benchmarks[:mid]) / mid
    new_avg = sum(b["ms"] for b in benchmarks[mid:]) / (len(benchmarks) - mid)

    if old_avg == 0:
        return "no_baseline"
    ratio = new_avg / old_avg
    if ratio < 0.9:
        return f"improving ({(1 - ratio) * 100:.0f}% faster)"
    elif ratio > 1.1:
        return f"degrading ({(ratio - 1) * 100:.0f}% slower)"
    return "stable"


def check_regression(mem: dict, model: str | None = None) -> tuple[bool, float]:
    """
    Check if performance has regressed beyond threshold.
    Returns (has_regressed, ratio).
    """
    benchmarks = mem.get("benchmarks", [])
    if model:
        benchmarks = [b for b in benchmarks if b.get("model") == model]
    if len(benchmarks) < 10:
        return False, 1.0

    # Compare last 5 vs previous 5
    prev = benchmarks[-10:-5]
    curr = benchmarks[-5:]

    prev_avg = sum(b["ms"] for b in prev) / len(prev)
    curr_avg = sum(b["ms"] for b in curr) / len(curr)

    if prev_avg == 0:
        return False, 1.0

    ratio = curr_avg / prev_avg
    return ratio > MAX_ALLOWED_REGRESSION, ratio


def format_stats(mem: dict) -> str:
    """Format benchmark stats for display."""
    from config import AGENT_MODEL, CODE_MODEL

    lines = ["📊 Performance Benchmarks", "─" * 40]

    for model in [AGENT_MODEL, CODE_MODEL]:
        avg = get_avg_response_time(mem, model)
        trend = get_trend(mem, model)
        count = len([b for b in mem.get("benchmarks", []) if b.get("model") == model])

        lines.append(f"  {model}:")
        lines.append(f"    Avg response:  {avg:.0f}ms")
        lines.append(f"    Trend:         {trend}")
        lines.append(f"    Total calls:   {count}")

    regressed, ratio = check_regression(mem)
    if regressed:
        lines.append(f"\n  ⚠️  Regression detected: {ratio:.2f}x slower than baseline")

    return "\n".join(lines)
