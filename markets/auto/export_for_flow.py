"""
markets/auto/export_for_flow.py
──────────────────────────────────────────────────────────────────
Orallexa → Flow Spatial Cognitive Platform CSV exporter.

Reads the daily SpaceX-IPO-tracker decisions + insider-signal
adjustments and emits a Flow-ingestable wide CSV. Flow's SCP
satellite demo ingested `data/active-satellites-positions.csv` —
the same shape works for tickers, with axes mapped to:

  X (date)        — temporal
  Y (p_up)        — probability up
  Z (var_5pct)    — risk (negative scale flips spatially)
  color (sector)  — categorical (🛰 / 🤖 / 🧠 / 🚁)
  size (volume)   — magnitude

Surfaced by the 2026-06-22 Jason Marsh call. The 7/31 Y.U. demo
content path is: this CSV → Flow's `create_auto_flow` API → 5-step
spatial narrative rendered for the dean + vice-provost.

Output columns (one row per ticker per day):
  date, ticker, sector_emoji, sector_label, signal_label, decision,
  conviction_pct, p_up, p_down, current_price, var_5pct,
  insider_p_up_delta, insider_events_n, insider_cluster,
  decision_id, brief_id, rationale_short

Notes:
- decision/brief IDs are stable per (date, ticker) so Flow can
  drill back to the source markdown.
- rationale_short is bounded ≤ 240 chars (Flow tooltip-safe).
- A separate companion JSON (--json-out) carries the per-ticker
  insider rationale bullets when wanted (Flow Dataset API allows
  joined sidecar metadata).

Usage:
    python -m markets.auto.export_for_flow \\
        --decisions-jsonl markets/polymarket_history.jsonl \\
        --briefs-dir ~/Desktop/Interview-Prep/Projects/alex-brain/research/spacex-daily \\
        --since 2026-06-01 \\
        --csv-out flow_export.csv \\
        --json-out flow_export.sidecar.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional


# ──────────────────────────────────────────────────────────────────
# Schema definition — version this so Flow side can verify
# ──────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "orallexa-flow-export-v1.0"

CSV_COLUMNS = [
    "date",
    "ticker",
    "sector_emoji",
    "sector_label",
    "signal_label",       # "BUY" / "SELL" / "WAIT" / "FLAT"
    "decision",           # alias of signal_label for Flow x-axis
    "conviction_pct",     # 0-100
    "p_up",               # 0-1
    "p_down",             # 0-1
    "current_price",
    "var_5pct",           # downside-tail risk (negative pct)
    "insider_p_up_delta", # signed [-0.15, 0.15]
    "insider_events_n",   # int
    "insider_cluster",    # bool 0/1
    "decision_id",        # ${date}-${ticker}
    "brief_id",           # filename or run-id
    "rationale_short",    # ≤240 chars
]

# Sector encoding mirrored from the SpaceX-tracker brief convention.
# Flow can color by sector_emoji directly + show label on hover.
SECTOR_LOOKUP: dict[str, tuple[str, str]] = {
    "RKLB": ("🛰", "Space"),
    "ASTS": ("🛰", "Space"),
    "LUNR": ("🛰", "Space"),
    "BKSY": ("🛰", "Space"),
    "PL":   ("🛰", "Space"),
    "RDW":  ("🛰", "Space"),
    "LMT":  ("🛰", "Space-defense"),
    "LIN":  ("🛰", "Industrial-gas"),
    "TSLA": ("🤖", "Physical-AI"),
    "SYM":  ("🤖", "Physical-AI"),
    "NVDA": ("🧠", "AI-infra"),
    "AVGO": ("🧠", "AI-infra"),
    "AVAV": ("🚁", "Drone"),
    "KTOS": ("🚁", "Drone"),
}


# ──────────────────────────────────────────────────────────────────
# Brief parsing — pulls structured rows out of the SpaceX-tracker
# markdown table that the daily cron auto-writes.
#
# Expected row shape in the brief (matches 2026-06-20 onward):
#   | Rank | Sector | Ticker | Decision | Conf | Δ probs | RSI |
#   |---|---|---|---|---|---|---|
#   | 1 | 🛰 | LIN | BUY | 49.2% | +0.38 | 61.0 |
# ──────────────────────────────────────────────────────────────────

BRIEF_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*"
    r"(?P<emoji>[^\s|]+)\s*\|\s*"
    r"(?P<ticker>[A-Z]+)\s*\|\s*"
    r"(?P<decision>BUY|SELL|WAIT|FLAT)\s*\|\s*"
    r"(?P<conv>[0-9]+(?:\.[0-9]+)?)\s*%\s*\|\s*"
    r"(?P<delta>[+-]?[0-9]+(?:\.[0-9]+)?)\s*\|\s*"
    r"(?P<rsi>[0-9]+(?:\.[0-9]+)?)\s*\|"
)


def parse_brief(path: Path) -> tuple[Optional[date], list[dict]]:
    """Return (brief date, list of per-ticker raw rows) from a single
    spacex-daily markdown file. Empty list if no parseable table."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    # Date from filename (2026-06-22.md) or YAML frontmatter date field
    name_match = re.match(r"(\d{4}-\d{2}-\d{2})", path.stem)
    brief_date: Optional[date] = None
    if name_match:
        try:
            brief_date = date.fromisoformat(name_match.group(1))
        except ValueError:
            brief_date = None

    rows: list[dict] = []
    for line in text.splitlines():
        m = BRIEF_ROW_RE.match(line)
        if not m:
            continue
        d = m.groupdict()
        rows.append({
            "ticker": d["ticker"].upper(),
            "decision": d["decision"],
            "conv_pct": float(d["conv"]),
            "delta_probs": float(d["delta"]),
            "rsi": float(d["rsi"]),
            "_brief_path": str(path),
        })
    return brief_date, rows


def _conv_to_p_up(decision: str, conv_pct: float) -> float:
    """Translate decision + conviction into a p(up) scalar Flow can
    plot on Y axis. BUY tilts toward 1, SELL toward 0, WAIT 0.5 ± half
    of conviction."""
    c = max(0.0, min(100.0, conv_pct)) / 100.0
    if decision == "BUY":
        return round(0.5 + 0.5 * c, 4)
    if decision == "SELL":
        return round(0.5 - 0.5 * c, 4)
    # WAIT / FLAT — keep near neutral but lean slightly using conv as
    # confidence-of-no-move (so Flow can show a uniform cluster)
    return round(0.5 + (c - 0.5) * 0.1, 4)


# ──────────────────────────────────────────────────────────────────
# Insider-signal join — optional. If insider events JSONL is
# provided, fold the per-ticker p_up delta into each row.
# ──────────────────────────────────────────────────────────────────

def load_insider_events(path: Optional[Path]) -> dict[str, list[dict]]:
    """Group raw Form-4 events by ticker. Path is the JSONL file the
    news_morning cron writes to (typically a sibling of polymarket_
    history.jsonl). Returns {} if file missing — insider join is opt
    -in."""
    grouped: dict[str, list[dict]] = {}
    if not path or not path.exists():
        return grouped
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = (ev.get("ticker") or "").upper()
        if not t:
            continue
        grouped.setdefault(t, []).append(ev)
    return grouped


def _apply_insider(
    row: dict,
    brief_date: date,
    insider_by_ticker: dict[str, list[dict]],
) -> dict:
    """Mutates row to add insider_p_up_delta + insider_events_n +
    insider_cluster fields. Uses the engine.insider_signal primitive
    (commits c34de90 + 50ef054)."""
    ticker = row["ticker"]
    events = insider_by_ticker.get(ticker, [])
    if not events:
        row.update({
            "insider_p_up_delta": 0.0,
            "insider_events_n": 0,
            "insider_cluster": 0,
        })
        return row

    # Lazy-import so this script can run in environments without the
    # full engine/ tree on path (e.g. CI dry-runs).
    try:
        from engine.insider_signal import compute_insider_signal
        sig = compute_insider_signal(
            ticker=ticker,
            events=events,
            today=brief_date,
        )
        row["insider_p_up_delta"] = float(sig.p_up_delta)
        row["insider_events_n"] = int(sig.events_considered)
        row["insider_cluster"] = 1 if sig.cluster_bonus_applied else 0
    except ImportError:
        row["insider_p_up_delta"] = 0.0
        row["insider_events_n"] = 0
        row["insider_cluster"] = 0
    return row


# ──────────────────────────────────────────────────────────────────
# Pricing / VaR join (optional, gracefully skipped if absent)
# ──────────────────────────────────────────────────────────────────

def load_price_var_index(path: Optional[Path]) -> dict[str, dict]:
    """Optional companion JSONL with current_price + var_5pct per
    ticker per day. Schema:
      {ticker:"NVDA", date:"2026-06-22", current_price:172.40, var_5pct:-0.028}
    Returns dict keyed by (date, ticker).
    """
    index: dict[str, dict] = {}
    if not path or not path.exists():
        return index
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = rec.get("date") or rec.get("brief_date")
        t = (rec.get("ticker") or "").upper()
        if not d or not t:
            continue
        index[f"{d}|{t}"] = rec
    return index


# ──────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────

def build_rows(
    briefs_dir: Path,
    since: Optional[date],
    insider_jsonl: Optional[Path],
    price_jsonl: Optional[Path],
) -> Iterable[dict]:
    insider_by_ticker = load_insider_events(insider_jsonl)
    price_index = load_price_var_index(price_jsonl)

    # Walk every brief .md file in date order
    paths = sorted(p for p in briefs_dir.glob("*.md") if not p.name.startswith("_"))
    for path in paths:
        brief_date, raw_rows = parse_brief(path)
        if brief_date is None or (since and brief_date < since):
            continue
        for raw in raw_rows:
            ticker = raw["ticker"]
            emoji, label = SECTOR_LOOKUP.get(ticker, ("❓", "Unknown"))
            p_up = _conv_to_p_up(raw["decision"], raw["conv_pct"])
            row = {
                "date": brief_date.isoformat(),
                "ticker": ticker,
                "sector_emoji": emoji,
                "sector_label": label,
                "signal_label": raw["decision"],
                "decision": raw["decision"],
                "conviction_pct": raw["conv_pct"],
                "p_up": p_up,
                "p_down": round(1.0 - p_up, 4),
                "decision_id": f"{brief_date.isoformat()}-{ticker}",
                "brief_id": Path(raw["_brief_path"]).name,
                "rationale_short": (
                    f"{raw['decision']} {raw['conv_pct']:.1f}% conv · "
                    f"Δprobs {raw['delta_probs']:+.2f} · RSI {raw['rsi']:.1f}"
                )[:240],
            }
            # Price + VaR join
            price_key = f"{brief_date.isoformat()}|{ticker}"
            price_rec = price_index.get(price_key, {})
            row["current_price"] = price_rec.get("current_price", "")
            row["var_5pct"] = price_rec.get("var_5pct", "")
            # Insider join
            _apply_insider(row, brief_date, insider_by_ticker)
            yield row


def write_csv(rows: Iterable[dict], path: Path) -> int:
    n = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})
            n += 1
    return n


def write_sidecar_json(rows: list[dict], path: Path) -> None:
    """Sidecar JSON carries the same rows + metadata (schema version
    + Flow render hints). Flow's Dataset API can join CSV + JSON sidecar
    on decision_id."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "render_hints": {
            "x_axis": "date",
            "y_axis": "p_up",
            "z_axis": "var_5pct",
            "color_by": "sector_emoji",
            "size_by": "conviction_pct",
            "label_field": "ticker",
            "tooltip_fields": [
                "decision", "conviction_pct", "p_up",
                "insider_p_up_delta", "insider_events_n",
                "rationale_short",
            ],
        },
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")


# ──────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Orallexa → Flow SCP exporter — emit a Flow-ingestable CSV "
                    "from spacex-daily briefs + insider events.",
    )
    ap.add_argument("--briefs-dir", required=True, type=Path,
                    help="Directory containing spacex-daily/*.md files")
    ap.add_argument("--insider-jsonl", type=Path, default=None,
                    help="Optional path to insider events JSONL (per-row "
                         "ticker/date/position/direction/value)")
    ap.add_argument("--price-jsonl", type=Path, default=None,
                    help="Optional path to price+var JSONL "
                         "(ticker/date/current_price/var_5pct)")
    ap.add_argument("--since", type=lambda s: date.fromisoformat(s), default=None,
                    help="Only include briefs from this date onward (YYYY-MM-DD)")
    ap.add_argument("--csv-out", required=True, type=Path,
                    help="Output CSV path (Flow ingests this directly)")
    ap.add_argument("--json-out", type=Path, default=None,
                    help="Optional sidecar JSON with schema_version + "
                         "render_hints + rows")
    return ap.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    if not args.briefs_dir.exists():
        print(f"[export-for-flow] briefs dir not found: {args.briefs_dir}",
              file=sys.stderr)
        return 1
    rows = list(build_rows(
        briefs_dir=args.briefs_dir,
        since=args.since,
        insider_jsonl=args.insider_jsonl,
        price_jsonl=args.price_jsonl,
    ))
    n = write_csv(rows, args.csv_out)
    print(f"[export-for-flow] wrote {n} rows → {args.csv_out}",
          file=sys.stderr)
    if args.json_out:
        write_sidecar_json(rows, args.json_out)
        print(f"[export-for-flow] wrote sidecar JSON → {args.json_out}",
              file=sys.stderr)
    print(f"[export-for-flow] schema_version={SCHEMA_VERSION}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
