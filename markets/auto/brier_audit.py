"""brier_audit.py — nightly calibration audit for Orallexa decisions.

For each decision in decision_log.json that's >= 1 trading day old AND
has a known outcome (close-vs-entry direction matched against the
decision), compute Brier score:

  B = (forecast_prob - actual_outcome)^2

where:
  forecast_prob = probabilities.up for BUY decisions
                  probabilities.down for SELL decisions
                  none-tracked for WAIT
  actual_outcome = 1 if price went the predicted direction within
                   the 1-day window, else 0

Aggregates by ticker and weekday. Writes:

  ~/Desktop/.../alex-brain/research/brier-audit/YYYY-MM-DD.md

This is the audit that tells us whether Orallexa's "BUY 59% confidence"
really means a 59% chance of moving up — or whether the system is
poorly calibrated (e.g., always saying 50-60% regardless of actual edge).

Honest calibration shows where the system is weak; fix the prompt
chain there, not the symptom.

Cost: ~5s, no Claude calls. Just yfinance + math.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
DECISION_LOG = HOME / "Desktop" / "orallexa-ai-trading-agent" / "memory_data" / "decision_log.json"
AUDIT_DIR = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "brier-audit"
MIN_DECISIONS_FOR_REPORT = 5


def load_decisions() -> list[dict]:
    if not DECISION_LOG.exists():
        return []
    try:
        with open(DECISION_LOG) as f:
            return json.load(f)
    except Exception as exc:
        print(f"[brier] load failed: {exc}", file=sys.stderr)
        return []


def fetch_close_after(ticker: str, after_date: str, lookahead_days: int = 5) -> tuple[float, float] | None:
    """Returns (entry_price, exit_price) where exit is the close
    `lookahead_days` after `after_date`. None if data unavailable."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    after = datetime.fromisoformat(after_date.replace("Z", "+00:00")).date()
    start = after.isoformat()
    end = (after + timedelta(days=lookahead_days + 4)).isoformat()  # buffer for weekends

    try:
        df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    except Exception:
        return None
    if df is None or len(df) < 2:
        return None

    entry = float(df["Close"].iloc[0])
    # Take the close at lookahead_days trading days out
    idx = min(lookahead_days, len(df) - 1)
    exit_ = float(df["Close"].iloc[idx])
    return entry, exit_


def brier_for_decision(d: dict, lookahead_days: int = 1) -> dict | None:
    """Compute Brier score for one decision. Returns dict or None
    (if outcome can't be determined yet)."""
    decision = d.get("decision", "")
    if decision not in ("BUY", "SELL"):
        return None  # skip WAIT — no directional claim

    probs = d.get("probabilities", {})
    if decision == "BUY":
        forecast_p = probs.get("up", 0.5)
        wanted_direction = "up"
    else:  # SELL
        forecast_p = probs.get("down", 0.5)
        wanted_direction = "down"

    ts = d.get("timestamp", "")
    if not ts:
        return None

    prices = fetch_close_after(d["ticker"], ts, lookahead_days)
    if not prices:
        return None
    entry, exit_ = prices

    moved_up = exit_ > entry
    actual = 1.0 if (
        (wanted_direction == "up" and moved_up)
        or (wanted_direction == "down" and not moved_up)
    ) else 0.0

    brier = (forecast_p - actual) ** 2
    return {
        "ticker": d["ticker"],
        "timestamp": ts,
        "decision": decision,
        "forecast_p": forecast_p,
        "actual": actual,
        "brier": brier,
        "entry": entry,
        "exit": exit_,
        "pct_move": (exit_ - entry) / entry * 100,
    }


def main(lookahead_days: int = 1) -> int:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = AUDIT_DIR / f"{today_str}.md"

    decisions = load_decisions()
    print(f"[brier] loaded {len(decisions)} historical decisions")

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookahead_days)
    candidates = []
    for d in decisions:
        if d.get("decision") not in ("BUY", "SELL"):
            continue
        ts = d.get("timestamp", "")
        try:
            d_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if d_time.tzinfo is None:
                d_time = d_time.replace(tzinfo=timezone.utc)
            if d_time < cutoff:
                candidates.append(d)
        except Exception:
            continue
    print(f"[brier] {len(candidates)} candidates >= {lookahead_days}d old")

    if len(candidates) < MIN_DECISIONS_FOR_REPORT:
        body = (
            f"# Brier audit — {today_str}\n\n"
            f"Not enough mature decisions yet ({len(candidates)} found, "
            f"need >= {MIN_DECISIONS_FOR_REPORT}).\n\n"
            f"Wait for {MIN_DECISIONS_FOR_REPORT - len(candidates)} more days "
            f"of BUY/SELL signals to land.\n"
        )
        out_path.write_text(body, encoding="utf-8")
        print(f"[brier] wrote {out_path} (insufficient data placeholder)")
        return 0

    results = []
    for d in candidates:
        r = brier_for_decision(d, lookahead_days=lookahead_days)
        if r:
            results.append(r)

    if not results:
        body = f"# Brier audit — {today_str}\n\n⚠ No outcomes resolvable (yfinance fetch failures?). Try again tomorrow.\n"
        out_path.write_text(body, encoding="utf-8")
        return 0

    # Aggregate
    overall_brier = sum(r["brier"] for r in results) / len(results)
    by_ticker: dict[str, list[float]] = defaultdict(list)
    for r in results:
        by_ticker[r["ticker"]].append(r["brier"])

    # By bucket — confidence band
    bands = {"50-60%": [], "60-70%": [], "70-80%": [], "80%+": []}
    for r in results:
        p = r["forecast_p"]
        if p < 0.6: bands["50-60%"].append(r)
        elif p < 0.7: bands["60-70%"].append(r)
        elif p < 0.8: bands["70-80%"].append(r)
        else: bands["80%+"].append(r)

    body = [
        f"# Brier audit — {today_str}",
        "",
        f"**Sample size:** {len(results)} resolved BUY/SELL decisions",
        f"**Lookahead window:** {lookahead_days} trading day(s)",
        f"**Overall Brier score:** {overall_brier:.4f}",
        "",
        "## Calibration reference",
        "- 0.000 — perfect",
        "- 0.130 — FiveThirtyEight's election baseline (good)",
        "- **0.250 — \"50/50 coin\" baseline (uninformative)**",
        "- 0.500 — worse than random",
        "",
    ]

    verdict = "🔴 No edge yet — system needs more training/data" if overall_brier > 0.25 \
        else "🟡 Mild edge — directionally OK but not strong" if overall_brier > 0.20 \
        else "🟢 Real edge — calibration is working"
    body.append(f"**Verdict:** {verdict}")
    body.append("")

    body.append("## Per-ticker Brier (lower = better)\n")
    body.append("| Ticker | N | Avg Brier |")
    body.append("|---|---|---|")
    for t, scores in sorted(by_ticker.items(), key=lambda kv: sum(kv[1])/len(kv[1])):
        avg = sum(scores) / len(scores)
        body.append(f"| **{t}** | {len(scores)} | {avg:.4f} |")
    body.append("")

    body.append("## Confidence-band calibration\n")
    body.append("Does 'BUY 60% confidence' actually win ~60% of the time? (Hit rate in each band)\n")
    body.append("| Band | N | Hit rate | Avg forecast_p | Calibrated? |")
    body.append("|---|---|---|---|---|")
    for label, group in bands.items():
        if not group:
            body.append(f"| {label} | 0 | — | — | (no data) |")
            continue
        hits = sum(r["actual"] for r in group)
        hit_rate = hits / len(group)
        avg_p = sum(r["forecast_p"] for r in group) / len(group)
        gap = hit_rate - avg_p
        cal = "✅" if abs(gap) < 0.10 else "⚠" if abs(gap) < 0.20 else "🔴"
        body.append(f"| {label} | {len(group)} | {hit_rate:.1%} | {avg_p:.1%} | {cal} (gap {gap:+.1%}) |")
    body.append("")

    # Drift detection — compare last-7-days Brier to prior-7-days
    today = datetime.now(timezone.utc)
    recent_7 = [r for r in results if datetime.fromisoformat(r["timestamp"].replace("Z","+00:00")).replace(tzinfo=timezone.utc) >= today - timedelta(days=7)]
    prior_7 = [r for r in results if today - timedelta(days=14) <= datetime.fromisoformat(r["timestamp"].replace("Z","+00:00")).replace(tzinfo=timezone.utc) < today - timedelta(days=7)]
    body.append("## Drift detection — last-7d vs prior-7d Brier\n")
    if recent_7 and prior_7:
        recent_b = sum(r["brier"] for r in recent_7) / len(recent_7)
        prior_b = sum(r["brier"] for r in prior_7) / len(prior_7)
        drift = recent_b - prior_b
        drift_label = "🟢 stable" if abs(drift) < 0.03 else "🟡 minor drift" if abs(drift) < 0.05 else "🔴 DEGRADING" if drift > 0 else "🟢 IMPROVING"
        body.append(f"- Last 7 days: Brier = **{recent_b:.4f}** (n={len(recent_7)})")
        body.append(f"- Prior 7 days: Brier = **{prior_b:.4f}** (n={len(prior_7)})")
        body.append(f"- Delta: **{drift:+.4f}** → {drift_label}")
        if drift > 0.05:
            body.append("")
            body.append("> 🚨 **CALIBRATION DRIFT DETECTED.** Model is worse this week. "
                        "Likely causes: (a) prompt drift in extract.py, (b) regime change "
                        "(market behavior shifted), (c) data quality issue. "
                        "Action: surface this in tomorrow's news-morning brief and audit the "
                        "highest-Brier ticker's recent Claude reasoning.")
    else:
        body.append(f"_Not enough history yet — need both 7d windows populated (have last={len(recent_7)}, prior={len(prior_7)})._")
    body.append("")

    body.append("## Sample resolved decisions (latest 10)\n")
    body.append("| Date | Ticker | Decision | Forecast | Actual | Move | Brier |")
    body.append("|---|---|---|---|---|---|---|")
    for r in sorted(results, key=lambda x: x["timestamp"], reverse=True)[:10]:
        date = r["timestamp"][:10]
        actual_label = "✓" if r["actual"] == 1.0 else "✗"
        body.append(
            f"| {date} | **{r['ticker']}** | {r['decision']} | {r['forecast_p']:.1%} | "
            f"{actual_label} | {r['pct_move']:+.2f}% | {r['brier']:.3f} |"
        )

    out_path.write_text("\n".join(body), encoding="utf-8")
    print(f"[brier] wrote {out_path}")
    print(f"[brier] overall Brier: {overall_brier:.4f}, verdict: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
