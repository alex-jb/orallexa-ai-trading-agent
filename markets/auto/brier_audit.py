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

# ROOT for engine.platt_calibration import (added 2026-07-02 for #7a
# what-if Brier delta reporting).
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 2026-07-02 upgrade #8: reliability diagram per bin.
#
# Prophet Arena finding (arxiv 2510.17638): "strong models perform much
# better in the extreme bins (0-0.1 and 0.9-1.0), where it almost
# always predicts correctly. Weaker models compress toward middle-of-
# book." Direct symptom of Orallexa's Haiku middle-bin collapse.
#
# A single Brier score MASKS this pathology. The reliability diagram
# splits [0, 1] into 10 bins, reports per-bin hit rate, and separates
# middle-bin (0.3-0.7) ECE from tail-bin (0-0.1 + 0.9-1.0) ECE. The
# middle-bin ECE is the -$1015 paper-loss driver — this makes it
# inescapable.
RELIABILITY_BINS = [
    (0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5),
    (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0),
]
# Prophet Arena's "extreme bins" definition — these are where strong
# models earn their keep and weak models collapse into middle-bucket
# noise.
TAIL_BINS = [(0.0, 0.1), (0.9, 1.0)]
MIDDLE_BINS = [(0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7)]


def compute_reliability_diagram(results: list[dict]) -> dict:
    """Return per-bin hit rate + expected calibration error (ECE).

    Each result dict must have `forecast_p` (float in [0,1]) and
    `actual` (0 or 1). We accept the caller's forecast_p directly —
    no direction-normalization — so a symmetric distribution across
    [0,1] shows up as "some bins pull, others push" which is what we
    want to see.

    ECE = sum over bins of (n_in_bin / total_n) * |hit_rate - avg_p|.
    Lower is better. 0.03 or less is "well-calibrated" per the
    forecasting literature; > 0.10 is "meaningfully miscalibrated";
    > 0.20 is "system is telling you it doesn't know what it's doing."

    Returns:
      {
        "per_bin": [{low, high, n, hit_rate, avg_p, gap}, ...],
        "overall_ece": float,
        "middle_bin_ece": float,   # [0.3, 0.7] ECE — Prophet Arena's key
        "tail_bin_ece": float,     # [0, 0.1] + [0.9, 1.0] ECE
        "n_total": int,
      }
    """
    per_bin: list[dict] = []
    total = len(results)
    if total == 0:
        return {
            "per_bin": [],
            "overall_ece": 0.0,
            "middle_bin_ece": 0.0,
            "tail_bin_ece": 0.0,
            "n_total": 0,
        }

    for low, high in RELIABILITY_BINS:
        # Right-open interval [low, high) except the very last bin,
        # which is inclusive of 1.0 so p=1.0 forecasts get a home.
        is_last = high == 1.0
        in_bin = [r for r in results
                  if r["forecast_p"] >= low
                  and (r["forecast_p"] < high or (is_last and r["forecast_p"] <= 1.0))]
        n = len(in_bin)
        if n == 0:
            per_bin.append({
                "low": low, "high": high, "n": 0,
                "hit_rate": None, "avg_p": None, "gap": None,
            })
            continue
        hit_rate = sum(r["actual"] for r in in_bin) / n
        avg_p = sum(r["forecast_p"] for r in in_bin) / n
        gap = hit_rate - avg_p
        per_bin.append({
            "low": low, "high": high, "n": n,
            "hit_rate": hit_rate, "avg_p": avg_p, "gap": gap,
        })

    def ece_for(bin_set: list[tuple[float, float]]) -> float:
        total_contribution = 0.0
        for b in per_bin:
            if b["n"] == 0:
                continue
            in_set = any(b["low"] == lo and b["high"] == hi for lo, hi in bin_set)
            if in_set:
                total_contribution += (b["n"] / total) * abs(b["gap"])
        return total_contribution

    overall_ece = ece_for(RELIABILITY_BINS)
    middle_ece = ece_for(MIDDLE_BINS)
    tail_ece = ece_for(TAIL_BINS)

    return {
        "per_bin": per_bin,
        "overall_ece": overall_ece,
        "middle_bin_ece": middle_ece,
        "tail_bin_ece": tail_ece,
        "n_total": total,
    }


def render_reliability_section(diag: dict) -> list[str]:
    """Turn a compute_reliability_diagram result into markdown lines."""
    lines: list[str] = []
    lines.append("## Reliability diagram (10 bins across [0, 1])")
    lines.append("")
    lines.append("Prophet Arena 2026 finding: strong models excel in "
                 "**extreme bins** (0-10%, 90-100%). Weak models "
                 "**collapse into middle bins** (30-70%), where a single "
                 "overall Brier score masks the pathology.")
    lines.append("")
    lines.append(f"- **Overall ECE**: {diag['overall_ece']:.4f}")
    lines.append(f"- **Middle-bin ECE (30-70%)**: {diag['middle_bin_ece']:.4f} "
                 f"— {_ece_label(diag['middle_bin_ece'])}")
    lines.append(f"- **Tail-bin ECE (0-10% + 90-100%)**: {diag['tail_bin_ece']:.4f} "
                 f"— {_ece_label(diag['tail_bin_ece'])}")
    lines.append("")
    lines.append("| Bin | N | Avg forecast_p | Hit rate | Gap |")
    lines.append("|---|---|---|---|---|")
    for b in diag["per_bin"]:
        label = f"{b['low']*100:.0f}-{b['high']*100:.0f}%"
        if b["n"] == 0:
            lines.append(f"| {label} | 0 | — | — | — |")
            continue
        gap = b["gap"]
        gap_str = f"{gap:+.3f}"
        marker = "✅" if abs(gap) < 0.05 else "🟡" if abs(gap) < 0.15 else "🔴"
        lines.append(
            f"| {label} | {b['n']} | {b['avg_p']:.3f} | "
            f"{b['hit_rate']:.3f} | {gap_str} {marker} |"
        )
    lines.append("")
    return lines


def _ece_label(ece: float) -> str:
    if ece < 0.03:
        return "well-calibrated"
    if ece < 0.10:
        return "mildly miscalibrated"
    if ece < 0.20:
        return "🟠 meaningfully miscalibrated"
    return "🔴 severely miscalibrated"


HOME = Path.home()
DECISION_LOG = HOME / "Desktop" / "orallexa-ai-trading-agent" / "memory_data" / "decision_log.json"
AUDIT_DIR = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "brier-audit"
MIN_DECISIONS_FOR_REPORT = 5


def render_platt_whatif_section(results: list[dict]) -> list[str]:
    """Fit Platt scaling on `results` in-memory and report what the
    Brier score WOULD have been under calibration. What-if only —
    does not persist a calibrator and does not change any decisions.

    Purpose: give Alex empirical evidence before flipping the live
    wire-up flag on polymarket_daily.py / stock decision path. If
    Platt drops Brier by ≥ 5% here, the wire-up is worth shipping.

    Refs
    ----
    - engine/platt_calibration.py (shipped 2026-07-02, Tier-2 #7a)
    - AIA Forecaster (Bridgewater 2025-09, arxiv 2511.07678) supervisor
      pass — Platt is the deterministic post-hoc step of that framework.
    """
    lines: list[str] = ["", "## Platt what-if calibration",
                        "*What would Brier have been if we applied Platt "
                        "post-hoc calibration to the exact same forecasts?*",
                        ""]
    try:
        from engine.platt_calibration import fit as _platt_fit
    except ImportError:
        lines.append("_platt_calibration module not importable — skipping._")
        return lines

    if not results:
        lines.append("_No resolved decisions — nothing to calibrate._")
        return lines

    history = [{"forecast_p": r["forecast_p"], "actual": r["actual"]}
               for r in results]

    try:
        cal = _platt_fit(history, min_observations=30)
    except ValueError as exc:
        lines.append(f"_Skipped: {exc}_")
        return lines

    improvement = cal.improvement_pct()
    delta = cal.train_brier_raw - cal.train_brier_calibrated
    verdict = (
        "🟢 **Ship the wire-up** — Platt materially improves calibration."
        if improvement >= 0.05 else
        "🟡 Marginal — Platt helps but < 5% Brier drop. Wait for more data."
        if improvement > 0 else
        "🔴 **Do NOT ship** — Platt makes it worse. Forecasts already "
        "well-calibrated or fit overfit on this sample."
    )
    lines.extend([
        f"- Raw Brier         : {cal.train_brier_raw:.4f}",
        f"- Calibrated Brier  : {cal.train_brier_calibrated:.4f}",
        f"- Δ Brier           : {delta:+.4f}  ({improvement * 100:+.1f}%)",
        f"- Fit params        : A={cal.A:+.3f}, B={cal.B:+.3f}, "
        f"n_train={cal.n_train}",
        "",
        f"**Verdict:** {verdict}",
        "",
    ])
    return lines


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

    # 2026-07-02 upgrade #8: 10-bin reliability diagram. Comes BEFORE
    # the existing 4-band confidence-band section — the middle-bin ECE
    # is the pathology-surfacing number Prophet Arena's finding says
    # will save Alex from -$1015 paper losses, so put it up top.
    diag = compute_reliability_diagram(results)
    body.extend(render_reliability_section(diag))

    # 2026-07-02 upgrade #7a (wire-up): Platt what-if. Reports the
    # empirical Brier delta if we had applied post-hoc calibration
    # to the same forecasts. Does NOT change any live decision — it's
    # the go/no-go signal for whether to wire Platt into estimate_p_yes.
    body.extend(render_platt_whatif_section(results))

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
