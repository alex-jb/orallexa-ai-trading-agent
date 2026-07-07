#!/usr/bin/env python3
"""
Alert if a decision file is dominated by our_p_yes ≈ 0.5.

Usage:
  python3 audit_uniform_05_collapse.py [path/to/polymarket-decisions.jsonl]

Exit code 0 = OK. Exit code 1 = uniform-0.5 collapse detected (>50% of
decisions collapse to 0.5 ± 0.002). Suitable for cron / launchd hook.
"""
import json, sys
from pathlib import Path

def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path.home() / ".orallexa/markets/polymarket-decisions.jsonl"
    )
    if not path.exists():
        print(f"[audit] file not found: {path}")
        return 0

    decisions = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                decisions.append(json.loads(line))
            except Exception:
                pass

    if not decisions:
        print("[audit] no decisions parsed")
        return 0

    n = len(decisions)
    uniform = sum(
        1 for d in decisions
        if d.get("our_p_yes") is not None and abs(d["our_p_yes"] - 0.5) < 0.002
    )
    pct = uniform / n * 100

    print(f"[audit] total decisions: {n}")
    print(f"[audit] uniform-0.5 count: {uniform} ({pct:.1f}%)")

    if pct > 50:
        print("[audit] ALERT: uniform-0.5 collapse detected — signal is garbage")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
