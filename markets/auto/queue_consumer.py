"""queue_consumer.py — flush ~/.orallexa/markets/queue/pending into
the Polymarket decisions audit log.

Why this exists (2026-06-30 cross-stack audit finding):
  Polymarket judging cron (markets/auto/polymarket_daily.py) drops
  one .md file per market it scores into queue/pending/. As of
  2026-06-30 there are 173 files accumulated since 2026-05-11 — no
  consumer reads them, so the Brier audit can't score this stream
  against eventual outcomes. Each pending file already contains the
  judge's reasoning + sized position, so the consumer is the LAST
  HOP: parse → persist to JSONL → move to decided/.

Pipeline:
  queue/pending/*.md → parse markdown header → append to
  ~/.orallexa/markets/polymarket-decisions.jsonl
                    → move file to queue/decided/

Once persisted, a future `brier_resolve.py` can hit Polymarket's
gamma API to check `resolves`-date markets and score `our_p_yes`
against actual outcome. That's a separate ship — this script just
unblocks the data flow.

Schema (one row per market decision):
  {
    "ts_judged": "2026-06-25T19:11:12-04:00",     # file mtime
    "platform": "polymarket",
    "market_id": "will-bernie-sanders-...-879",
    "market_url": "https://polymarket.com/event/...",
    "market_p_yes": 0.007,
    "our_p_yes": 0.007,
    "edge": 0.000,
    "suggested_side": "BUY NO",                    # or "BUY YES" / "WAIT"
    "suggested_position_usd": 0.00,
    "resolves": "2028-11-07T00:00:00Z",
    "category": "other",
    "source_file": "queue/pending/2026-05-11-polymarket-will-bernie-..."
  }
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
QUEUE_DIR = HOME / ".orallexa" / "markets" / "queue"
PENDING_DIR = QUEUE_DIR / "pending"
DECIDED_DIR = QUEUE_DIR / "decided"
DECISIONS_JSONL = HOME / ".orallexa" / "markets" / "polymarket-decisions.jsonl"


def parse_md_header(text: str) -> dict | None:
    """Parse the markdown header table into a dict.

    Pending files have this shape (from polymarket_daily.py output):
      # <Market question>

      | Field | Value |
      |---|---|
      | Platform | `polymarket` |
      | Market | `<market-slug>` |
      | Category | <cat> |
      | Resolves | <ISO> |
      | Market YES price | **0.007** |
      | Our p_yes | **0.007** |
      | Edge | **+0.000** |
      | Suggested side | BUY NO |
      | Suggested position | $0.00 |
      | Trade URL | https://... |
    """
    # Extract each "| Field | Value |" row
    fields: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", line)
        if not m:
            continue
        key, val = m.group(1).strip(), m.group(2).strip()
        if key.lower() in ("field", "value", "---", "----"):
            continue
        if key.startswith("-"):
            continue
        # Strip backticks + bold markers
        val = val.replace("`", "").replace("**", "").strip()
        fields[key] = val

    if "Platform" not in fields or "Market" not in fields:
        return None

    # Float fields — be tolerant of "+0.045" / "$1.20" / "0.07"
    def _num(s: str) -> float | None:
        s = (s or "").replace("$", "").replace("+", "").replace(",", "").strip()
        if not s or s.lower() in ("none", "n/a", "—", "-"):
            return None
        try:
            return float(s)
        except ValueError:
            return None

    return {
        "platform": fields.get("Platform"),
        "market_id": fields.get("Market"),
        "category": fields.get("Category", "unknown"),
        "resolves": fields.get("Resolves"),
        "market_p_yes": _num(fields.get("Market YES price", "")),
        "our_p_yes": _num(fields.get("Our p_yes", "")),
        "edge": _num(fields.get("Edge", "")),
        "suggested_side": fields.get("Suggested side", "WAIT"),
        "suggested_position_usd": _num(fields.get("Suggested position", "")) or 0.0,
        "market_url": fields.get("Trade URL"),
    }


def file_ts_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def process_one(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"[queue-consumer] read failed {path.name}: {exc}", file=sys.stderr)
        return None
    parsed = parse_md_header(text)
    if not parsed:
        print(f"[queue-consumer] header parse failed: {path.name}", file=sys.stderr)
        return None
    parsed["ts_judged"] = file_ts_iso(path)
    parsed["source_file"] = f"queue/pending/{path.name}"
    return parsed


def main() -> int:
    if not PENDING_DIR.exists():
        print(f"[queue-consumer] no pending dir: {PENDING_DIR}", file=sys.stderr)
        return 0
    DECIDED_DIR.mkdir(parents=True, exist_ok=True)
    DECISIONS_JSONL.parent.mkdir(parents=True, exist_ok=True)

    pending = sorted(p for p in PENDING_DIR.glob("*.md") if not p.name.startswith("."))
    if not pending:
        print("[queue-consumer] queue empty", file=sys.stderr)
        return 0

    n_persisted = 0
    n_failed_parse = 0
    n_moved = 0
    summary_by_side: dict[str, int] = {}
    summary_by_category: dict[str, int] = {}
    edges_with_position: list[float] = []

    with DECISIONS_JSONL.open("a", encoding="utf-8") as out:
        for path in pending:
            decision = process_one(path)
            if decision is None:
                n_failed_parse += 1
                continue
            out.write(json.dumps(decision, ensure_ascii=False) + "\n")
            n_persisted += 1

            side = decision.get("suggested_side") or "UNKNOWN"
            summary_by_side[side] = summary_by_side.get(side, 0) + 1
            cat = decision.get("category") or "unknown"
            summary_by_category[cat] = summary_by_category.get(cat, 0) + 1
            pos = decision.get("suggested_position_usd") or 0.0
            edge = decision.get("edge")
            if pos > 0 and edge is not None:
                edges_with_position.append(edge)

            # Move file to decided/
            try:
                shutil.move(str(path), str(DECIDED_DIR / path.name))
                n_moved += 1
            except Exception as exc:
                print(f"[queue-consumer] move failed {path.name}: {exc}", file=sys.stderr)

    # Summary log to stderr (cron-friendly; jsonl is the data artifact)
    print(f"[queue-consumer] {n_persisted} persisted, {n_failed_parse} parse-fail, "
          f"{n_moved} moved → decided/", file=sys.stderr)
    if summary_by_side:
        print(f"[queue-consumer] by side: {summary_by_side}", file=sys.stderr)
    if summary_by_category:
        print(f"[queue-consumer] by category: {summary_by_category}", file=sys.stderr)
    if edges_with_position:
        avg = sum(edges_with_position) / len(edges_with_position)
        mx = max(edges_with_position)
        print(f"[queue-consumer] {len(edges_with_position)} entries had sized position; "
              f"mean edge {avg:+.3f}, max edge {mx:+.3f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
