"""
markets/auto/insider_join.py
──────────────────────────────────────────────────────────────────
Wire the engine/insider_signal primitive into the SpaceX-tracker
daily decision pipeline.

Today (2026-06-22) the SpaceX daily cron renders a markdown table of
14 tickers with Decision / Conf / Δ probs / RSI columns. The
insider_signal primitive (commit c34de90 + 50ef054) is shipped but
NOT wired into the decision pipeline — the SEC EDGAR Form-4 data
loaded by news_morning.fetch_insider_transactions is rendered into
the daily brief but never feeds back into per-ticker probability.

This module is the bridge. It is intentionally a thin function-
oriented adapter so the existing spacex-daily script can stay
unchanged except for one import + one wrap call per ticker.

Usage from spacex-daily.sh-style scripts:
    from markets.auto.insider_join import enrich_decision_with_insider

    for ticker, decision_payload in zip(WATCHLIST, decisions):
        decision_payload = enrich_decision_with_insider(
            ticker=ticker,
            decision=decision_payload,
            insider_events=insider_by_ticker.get(ticker, []),
        )

The enriched payload gains:
    insider_p_up_delta : float   (signed; negative = insider sells)
    insider_events_n   : int
    insider_cluster    : bool
    insider_rationale  : list[str]  (1-3 short bullets)

The downstream markdown renderer can show this inline as e.g.
   "BUY 49.2% conv (insider Δp(up) -0.04 ← CFO sale)"

Optional: also writes a sidecar JSONL at
markets/insider_history.jsonl so Brier audit can score the insider-
adjusted decisions independently from the raw model output.

Pure-function, no LLM calls, deterministic. Mirrors the Shadow-side
flow-export wrapper pattern (Shadow uses traceability dict to expose
governance-layer attribution; here we expose decision-attribution
for the per-ticker p(up) delta).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# Late import so this module doesn't break a CI environment that
# can't import the full engine/ tree.
try:
    from engine.insider_signal import (
        compute_insider_signal,
        wrap_signal_with_insider,
    )
    _HAS_ENGINE = True
except ImportError:
    _HAS_ENGINE = False


def enrich_decision_with_insider(
    ticker: str,
    decision: dict,
    insider_events: Iterable[dict],
    *,
    window_days: int = 14,
    today: Optional[date] = None,
    apply_to_p_up: bool = True,
) -> dict:
    """Return a new dict (does not mutate) with insider fields added.

    If `apply_to_p_up=True` and the decision dict has `up_probability`
    + `down_probability`, mass is shifted up→down (or vice versa)
    preserving sum. The original p_up and p_down values are saved as
    `p_up_pre_insider` and `p_down_pre_insider` for transparency.

    If the engine isn't on the import path (e.g. CI dry-run), the
    function still returns a valid payload with zero-valued insider
    fields — callers don't need to gate on import success.
    """
    if not _HAS_ENGINE:
        return _zero_filled(decision, "engine.insider_signal not importable")

    today = today or datetime.now(timezone.utc).date()

    sig = compute_insider_signal(
        ticker=ticker,
        events=insider_events,
        window_days=window_days,
        today=today,
    )

    out = dict(decision)
    out["insider_p_up_delta"] = sig.p_up_delta
    out["insider_events_n"] = sig.events_considered
    out["insider_cluster"] = bool(sig.cluster_bonus_applied)
    out["insider_rationale"] = list(sig.rationale)

    # Optionally shift probability mass
    if apply_to_p_up and "up_probability" in out and "down_probability" in out:
        out["p_up_pre_insider"] = out["up_probability"]
        out["p_down_pre_insider"] = out["down_probability"]
        out = wrap_signal_with_insider(
            signal_dict=out,
            insider_events=insider_events,
            ticker=ticker,
            window_days=window_days,
            today=today,
        )
        # wrap_signal_with_insider already adjusted up_probability +
        # down_probability + added insider_adjustment metadata.

    return out


def _zero_filled(decision: dict, note: str) -> dict:
    """Fallback when the engine module isn't importable. Returns the
    original decision + zero-valued insider fields so downstream
    renderers don't crash."""
    out = dict(decision)
    out["insider_p_up_delta"] = 0.0
    out["insider_events_n"] = 0
    out["insider_cluster"] = False
    out["insider_rationale"] = [f"insider-join skipped: {note}"]
    return out


# ──────────────────────────────────────────────────────────────────
# Markdown rendering helpers — for the existing spacex-daily script
# to drop in unchanged
# ──────────────────────────────────────────────────────────────────

def render_insider_inline(decision: dict) -> str:
    """Inline string for the spacex-daily markdown table cell.

    Returns "" if no qualifying insider events for that ticker —
    caller can choose to omit the column or pad with em-dash.
    """
    n = int(decision.get("insider_events_n", 0))
    if n == 0:
        return ""
    delta = float(decision.get("insider_p_up_delta", 0.0))
    cluster = bool(decision.get("insider_cluster", False))
    sign = "+" if delta >= 0 else ""
    cluster_tag = " 🚨" if cluster else ""
    return f"Δp(up) {sign}{delta:.3f}{cluster_tag} (n={n})"


def render_insider_section(enriched_decisions: list[tuple[str, dict]]) -> str:
    """Detailed markdown section to append to the daily brief.

    Lists each ticker with material insider activity in the window,
    with the rationale bullets the engine.insider_signal primitive
    surfaced. Tickers with zero qualifying events are omitted.
    """
    flagged = [
        (t, d) for t, d in enriched_decisions
        if int(d.get("insider_events_n", 0)) > 0
    ]
    if not flagged:
        return ""

    lines = [
        "",
        "## 📋 Insider-trade signal adjustments (last 14d)",
        "",
        "Per-ticker p(up) delta from material C-suite / Director / "
        "10%-owner Form-4 transactions. Negative = insider selling "
        "discount; positive = insider buying premium. 🚨 = same-day "
        "C-suite cluster (×1.6 multiplier).",
        "",
        "| Ticker | Δp(up) | Events | Cluster | Notes |",
        "|---|---|---|---|---|",
    ]
    for ticker, d in flagged:
        delta = float(d.get("insider_p_up_delta", 0.0))
        n = int(d.get("insider_events_n", 0))
        cluster = "🚨" if d.get("insider_cluster", False) else ""
        # First rationale line, ≤80 chars
        rationale = d.get("insider_rationale") or []
        first = (rationale[0] if rationale else "")[:80]
        sign = "+" if delta >= 0 else ""
        lines.append(
            f"| {ticker} | {sign}{delta:.3f} | {n} | {cluster} | {first} |"
        )
    return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────────────────────────
# Sidecar JSONL — append-only per decision for Brier audit
# ──────────────────────────────────────────────────────────────────

def append_insider_history(
    path: Path,
    *,
    date_str: str,
    ticker: str,
    enriched_decision: dict,
) -> None:
    """Append a single row to markets/insider_history.jsonl so the
    Brier audit harness can score insider-adjusted decisions
    independently of raw-model decisions. Schema is the smallest
    superset needed for replay.
    """
    record = {
        "date": date_str,
        "ticker": ticker,
        "p_up_pre_insider": enriched_decision.get("p_up_pre_insider"),
        "p_up_post_insider": enriched_decision.get("up_probability"),
        "insider_p_up_delta": enriched_decision.get("insider_p_up_delta", 0.0),
        "insider_events_n": enriched_decision.get("insider_events_n", 0),
        "insider_cluster": enriched_decision.get("insider_cluster", False),
        "decision_id": f"{date_str}-{ticker}",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
