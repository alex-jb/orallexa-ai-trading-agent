#!/usr/bin/env python3
"""portfolio_paper.py — paper P&L simulator over decision_log.json.

Answers the question Alex actually wants: "if I had followed every BUY/SELL
the system recommended over the last N days, how much money would paper-me
have made (or lost)?"

Reads:
  ~/Desktop/orallexa-ai-trading-agent/memory_data/decision_log.json
    (BUY/SELL/WAIT decisions with entry_price + probabilities)

Writes:
  ~/Desktop/Interview-Prep/Projects/alex-brain/research/portfolio-paper/YYYY-MM-DD.md

Sizing follows trade_intel.py: 1.5% risk per trade on $10k account by default,
with same Setup-bucket notional scaling. Exit = configurable lookahead in
trading days (default 5).

This is the missing companion to brier_audit.py — Brier tells us if
probabilities are well-CALIBRATED; this tells us if calibration translated
into actual $$$.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time as _time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
DECISION_LOG = HOME / "Desktop" / "orallexa-ai-trading-agent" / "memory_data" / "decision_log.json"
OUT_DIR = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "portfolio-paper"


# Same yfinance throttle pattern as brier_audit.py — 60/min rate limit.
_YF_LAST_CALL = 0.0
YF_MIN_GAP = 1.5

def _yf_throttle():
    global _YF_LAST_CALL
    elapsed = _time.time() - _YF_LAST_CALL
    if elapsed < YF_MIN_GAP:
        _time.sleep(YF_MIN_GAP - elapsed)
    _YF_LAST_CALL = _time.time()


def _yf_retry(fn, attempts=3):
    for i in range(attempts):
        _yf_throttle()
        try:
            return fn()
        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "rate" in msg or "too many" in msg:
                _time.sleep((2 ** i) * 3)
                continue
            return None
    return None


def load_decisions(since_days: int) -> list[dict]:
    if not DECISION_LOG.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    try:
        data = json.loads(DECISION_LOG.read_text())
    except Exception as exc:
        print(f"[portfolio] load failed: {exc}", file=sys.stderr)
        return []
    out = []
    for d in data:
        ts = d.get("timestamp")
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if t < cutoff:
            continue
        out.append(d)
    return out


def fetch_ticker_history(ticker: str, days_back: int) -> "pd.DataFrame | None":
    try:
        import yfinance as yf
    except ImportError:
        return None
    period_days = days_back + 30  # buffer for weekends + lookahead
    df = _yf_retry(lambda: yf.Ticker(ticker).history(
        period=f"{period_days}d", auto_adjust=True))
    return df if df is not None and len(df) >= 2 else None


def price_on_or_after(df, target_date) -> float | None:
    """Return the close price on the first trading day >= target_date."""
    if df is None or df.empty:
        return None
    for ts, row in df.iterrows():
        try:
            d = ts.date() if hasattr(ts, "date") else ts
        except Exception:
            continue
        if d >= target_date:
            try:
                return float(row["Close"])
            except Exception:
                continue
    return None


# Phase B1 (2026-05-29): sector exposure cap.
# 5/27 portfolio_paper findings: 13/13 losing tickers were Space + AI infra.
# Fix is sector cap, not Brier-driven sizing.
TICKER_SECTORS = {
    "RKLB": "Space", "ASTS": "Space", "LUNR": "Space",
    "BKSY": "Space", "PL": "Space", "RDW": "Space",
    "LMT": "Defense", "KTOS": "Defense", "AVAV": "Defense",
    "NVDA": "AI_Infra", "AVGO": "AI_Infra", "TSLA": "AI_Infra",
    "SYM": "AI_Infra",
    "LIN": "Industrial",
    "BE": "Power", "CEG": "Power", "GEV": "Power", "CRWV": "Power",
}


def sector_of(ticker: str) -> str:
    return TICKER_SECTORS.get(ticker, "Other")


def size_position(decision: str, account: float, risk_pct: float = 0.015) -> tuple[float, float]:
    """Returns (notional_dollars, stop_distance_pct). Mirrors trade_intel.py
    bucketing but simplified for sim: treat any BUY = "Half" sizing,
    any SELL = "Short-half" sizing.

    Real production would map setup → bucket per trade_intel.compute_ticket.
    The decision log doesn't carry setup type, so we use uniform Half.
    """
    risk = account * risk_pct
    if decision == "BUY":
        return min(risk * 15, account * 0.10), 0.05  # Half: 10% notional, 5% stop
    if decision == "SELL":
        return min(risk * 12, account * 0.08), 0.04  # Short-half: 8% notional, 4% stop
    return 0.0, 0.0


def atr_14(df, lookback: int = 14) -> float | None:
    """14-day Average True Range. Standard Wilder formula.
    Returns ATR at the end of df, or None if not enough data."""
    try:
        import pandas as _pd  # noqa: F401 — verifies pandas import
    except ImportError:
        return None
    if df is None or len(df) < lookback + 1:
        return None
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = (high - low).combine((high - prev_close).abs(), max).combine(
        (low - prev_close).abs(), max)
    atr_series = tr.rolling(lookback).mean()
    val = atr_series.iloc[-1]
    try:
        return float(val) if val == val else None  # NaN check
    except Exception:
        return None


def atr_at_date(df, target_date, lookback: int = 14) -> float | None:
    """ATR computed over the last `lookback` bars ENDING at target_date.
    Backward-looking; no lookahead bias."""
    try:
        import pandas as _pd  # noqa: F401
    except ImportError:
        return None
    if df is None or df.empty:
        return None
    # Slice to bars at or before target_date
    mask = []
    for ts in df.index:
        try:
            d = ts.date() if hasattr(ts, "date") else ts
        except Exception:
            mask.append(False)
            continue
        mask.append(d <= target_date)
    sub = df[mask]
    return atr_14(sub, lookback)


def simulate(
    decisions: list[dict],
    lookahead_days: int,
    account: float,
    *,
    use_atr_stops: bool = True,   # 2026-07-02 upgrade #5: default → True
    atr_stop_mult: float = 1.5,
    sector_cap_pct: float | None = None,
) -> dict:
    """For each BUY/SELL decision, simulate a paper trade.

    Returns {
        'trades': [...],        # per-trade {ticker, entry_date, entry, exit, pnl_dollars, pnl_pct, win}
        'per_ticker': {...},    # {ticker: {n, pnl, win_rate}}
        'cumulative_pnl': float,
        'win_rate': float,
        'max_drawdown_pct': float,
        'sharpe_proxy': float,
    }
    """
    # Group decisions by ticker for batched yfinance fetches.
    # NOTE: decision_log's entry_price field is 0 across all 396 records (logger
    # doesn't fill it). We re-derive entry price from yfinance at timestamp,
    # same pattern brier_audit.py uses.
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for d in decisions:
        if d.get("decision") not in ("BUY", "SELL"):
            continue
        ticker = d.get("ticker")
        if not ticker:
            continue
        by_ticker[ticker].append(d)

    # Earliest decision date per ticker → fetch enough history.
    earliest_overall = None
    for ds in by_ticker.values():
        for d in ds:
            try:
                t = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).date()
            except Exception:
                continue
            if earliest_overall is None or t < earliest_overall:
                earliest_overall = t
    if earliest_overall is None:
        return {"trades": [], "per_ticker": {}, "cumulative_pnl": 0.0,
                "win_rate": 0.0, "max_drawdown_pct": 0.0, "sharpe_proxy": 0.0,
                "n_trades": 0, "n_stops": 0}

    days_back = (datetime.now(timezone.utc).date() - earliest_overall).days + lookahead_days + 5

    # Phase B1: chronological iteration across ALL ticker decisions for
    # sector-cap accounting. Pre-fetch all ticker histories, then walk a
    # merged timeline.
    histories: dict[str, "pd.DataFrame"] = {}
    for ticker in by_ticker:
        df = fetch_ticker_history(ticker, days_back)
        if df is not None:
            histories[ticker] = df

    # Flatten decisions to (entry_date, ticker, decision-dict)
    flat: list[tuple] = []
    for ticker, ds in by_ticker.items():
        if ticker not in histories:
            continue
        for d in ds:
            try:
                ed = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).date()
                flat.append((ed, ticker, d))
            except Exception:
                continue
    flat.sort(key=lambda x: x[0])

    # Track open positions for sector exposure
    open_positions: dict[str, dict] = {}  # ticker → {entry_date, exit_date_target, notional, sector}
    sector_blocked = 0

    trades: list[dict] = []
    for entry_date, ticker, d in flat:
        df = histories[ticker]
        exit_date_target = entry_date + timedelta(days=lookahead_days + 2)
        entry_price = price_on_or_after(df, entry_date)
        exit_price = price_on_or_after(df, exit_date_target)
        if entry_price is None or exit_price is None:
            continue
        notional, fixed_stop_pct = size_position(d["decision"], account)
        if notional <= 0:
            continue

        # Phase B1: ATR-based stop (overrides fixed if --use-atr-stops)
        if use_atr_stops:
            atr = atr_at_date(df, entry_date, lookback=14)
            if atr is not None and entry_price > 0:
                stop_pct = (atr * atr_stop_mult) / entry_price
                # Sanity: cap stop distance at 15% (don't let bad ATR blow up
                # position) and floor at 2% (don't let tight ATR over-tighten)
                stop_pct = max(0.02, min(0.15, stop_pct))
            else:
                stop_pct = fixed_stop_pct
        else:
            stop_pct = fixed_stop_pct

        shares = math.floor(notional / entry_price) if entry_price > 0 else 0
        if shares <= 0:
            continue

        # Phase B1: sector exposure cap (None = no cap)
        if sector_cap_pct is not None:
            sector = sector_of(ticker)
            # Cull positions whose exit_date has passed
            for tk in list(open_positions):
                if open_positions[tk]["exit_date_target"] < entry_date:
                    del open_positions[tk]
            sector_notional = sum(
                p["notional"] for p in open_positions.values()
                if p["sector"] == sector
            )
            new_total = sector_notional + (shares * entry_price)
            cap_dollars = account * sector_cap_pct
            if new_total > cap_dollars:
                sector_blocked += 1
                continue
            open_positions[ticker + "@" + str(entry_date)] = {
                "exit_date_target": exit_date_target,
                "notional": shares * entry_price,
                "sector": sector_of(ticker),
            }

        # Stop-loss check: if intraday Low/High within lookahead breaches stop,
        # exit at stop. Runs for ALL trades, not just sector-capped ones.
        if d["decision"] == "BUY":
            stop_price = entry_price * (1 - stop_pct)
            stopped = False
            for ts, row in df.iterrows():
                try:
                    rd = ts.date() if hasattr(ts, "date") else ts
                except Exception:
                    continue
                if rd <= entry_date:
                    continue
                if rd > exit_date_target:
                    break
                if float(row["Low"]) <= stop_price:
                    exit_price = stop_price
                    stopped = True
                    break
            pnl = (exit_price - entry_price) * shares
        else:  # SELL (short)
            stop_price = entry_price * (1 + stop_pct)
            stopped = False
            for ts, row in df.iterrows():
                try:
                    rd = ts.date() if hasattr(ts, "date") else ts
                except Exception:
                    continue
                if rd <= entry_date:
                    continue
                if rd > exit_date_target:
                    break
                if float(row["High"]) >= stop_price:
                    exit_price = stop_price
                    stopped = True
                    break
            pnl = (entry_price - exit_price) * shares

        pnl_pct = (pnl / (shares * entry_price)) * 100 if shares > 0 else 0
        win = pnl > 0
        trades.append({
            "ticker": ticker,
            "sector": sector_of(ticker),
            "decision": d["decision"],
            "entry_date": entry_date.isoformat(),
            "entry": round(entry_price, 2),
            "exit": round(exit_price, 2),
            "shares": shares,
            "notional": round(shares * entry_price, 2),
            "stop_pct": round(stop_pct * 100, 2),
            "pnl_dollars": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "stopped_out": stopped,
            "win": win,
        })

    # Aggregate
    per_ticker: dict[str, dict] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
    for t in trades:
        per_ticker[t["ticker"]]["n"] += 1
        per_ticker[t["ticker"]]["pnl"] += t["pnl_dollars"]
        per_ticker[t["ticker"]]["wins"] += 1 if t["win"] else 0
    for tk, stats in per_ticker.items():
        stats["pnl"] = round(stats["pnl"], 2)
        stats["win_rate"] = round(stats["wins"] / stats["n"], 3) if stats["n"] else 0.0

    cumulative_pnl = round(sum(t["pnl_dollars"] for t in trades), 2)
    win_rate = round(sum(1 for t in trades if t["win"]) / len(trades), 3) if trades else 0.0

    # Max drawdown: walk cumulative equity curve
    trades_sorted = sorted(trades, key=lambda t: t["entry_date"])
    equity = account
    peak = account
    max_dd = 0.0
    returns = []
    for t in trades_sorted:
        equity += t["pnl_dollars"]
        returns.append(t["pnl_dollars"] / account)
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    # Sharpe-proxy: per-trade returns mean/stddev × sqrt(252/avg_holding_days)
    sharpe = 0.0
    if len(returns) > 1:
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(var) if var > 0 else 0
        if std_r > 0:
            # Crude annualization assuming ~5-day holds
            sharpe = (mean_r / std_r) * math.sqrt(252 / lookahead_days)

    # Phase B1: per-sector P&L breakdown
    per_sector: dict[str, dict] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
    for t in trades:
        sec = t.get("sector", "Other")
        per_sector[sec]["n"] += 1
        per_sector[sec]["pnl"] += t["pnl_dollars"]
        per_sector[sec]["wins"] += 1 if t["win"] else 0
    for sec, stats in per_sector.items():
        stats["pnl"] = round(stats["pnl"], 2)
        stats["win_rate"] = round(stats["wins"] / stats["n"], 3) if stats["n"] else 0.0

    return {
        "trades": trades_sorted,
        "per_ticker": dict(per_ticker),
        "per_sector": dict(per_sector),
        "cumulative_pnl": cumulative_pnl,
        "win_rate": win_rate,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_proxy": round(sharpe, 2),
        "n_trades": len(trades),
        "n_stops": sum(1 for t in trades if t["stopped_out"]),
        "n_blocked_by_sector_cap": sector_blocked,
    }


def render_report(result: dict, since_days: int, lookahead_days: int, account: float,
                  flags: dict | None = None) -> str:
    now_utc = datetime.now(timezone.utc)
    lines = [f"# Portfolio paper P&L — {now_utc.date()}",
             "",
             f"_Window: last {since_days} days of decision_log. Lookahead: {lookahead_days} trading days. "
             f"Account: ${account:,.0f}. Sizing: trade_intel.py Half/Short-half buckets._",
             ""]

    # 2026-07-02 upgrade #5: enumerate flags at the top of every report.
    # Prod/backtest divergence hid a $6,823 signal for 3 weeks because
    # reports didn't mark the flags they were run under. Never again.
    if flags is not None:
        lines.append("## Flags enumerated")
        lines.append("| Flag | Value |")
        lines.append("|---|---|")
        for k, v in flags.items():
            lines.append(f"| `{k}` | `{v}` |")
        lines.append("")

    n = result["n_trades"]
    if n == 0:
        lines.append("**No tradable BUY/SELL decisions in window.** "
                     "(decision_log may have only WAIT entries, or entry_price=0.)")
        return "\n".join(lines)

    cum = result["cumulative_pnl"]
    pct = (cum / account) * 100
    lines.append(f"## Top-line")
    lines.append(f"- **Cumulative P&L: ${cum:,.2f}** ({pct:+.2f}% account)")
    lines.append(f"- Trades: **{n}** (BUY+SELL), stops hit: **{result['n_stops']}**")
    lines.append(f"- Win rate: **{result['win_rate']*100:.1f}%**")
    lines.append(f"- Max drawdown: **{result['max_drawdown_pct']:.2f}%**")
    lines.append(f"- Sharpe-proxy: **{result['sharpe_proxy']}** "
                 f"(crude, ~{lookahead_days}d holds annualized)")
    lines.append("")

    lines.append("## Per-ticker breakdown")
    lines.append("| Ticker | N | P&L $ | Win rate | Verdict |")
    lines.append("|---|---|---|---|---|")
    pt = result["per_ticker"]
    for tk in sorted(pt, key=lambda t: pt[t]["pnl"], reverse=True):
        s = pt[tk]
        verdict = "🟢" if s["pnl"] > 0 else ("🔴" if s["pnl"] < 0 else "⚪")
        lines.append(f"| **{tk}** | {s['n']} | ${s['pnl']:+,.2f} | {s['win_rate']*100:.0f}% | {verdict} |")
    lines.append("")

    lines.append("## Last 10 trades (chronological)")
    lines.append("| Date | Ticker | Dir | Entry | Exit | $ | % | Win | Stopped |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for t in result["trades"][-10:]:
        win = "✅" if t["win"] else "❌"
        st = "yes" if t["stopped_out"] else ""
        lines.append(
            f"| {t['entry_date']} | {t['ticker']} | {t['decision']} | "
            f"${t['entry']} | ${t['exit']} | ${t['pnl_dollars']:+.2f} | "
            f"{t['pnl_pct']:+.2f}% | {win} | {st} |"
        )
    lines.append("")

    # Calibration sanity check — what % of trades won, vs naive 50%
    lines.append("## Calibration sanity")
    edge_over_random = (result["win_rate"] - 0.5) * 100
    lines.append(f"- Edge over random (50% baseline): **{edge_over_random:+.1f}pp**")
    if result["win_rate"] > 0.6:
        lines.append("- **Verdict: real edge.** Win rate > 60% is statistically meaningful at N≥20.")
    elif result["win_rate"] > 0.52:
        lines.append("- **Verdict: marginal edge.** Possibly noise at low N; keep paper-trading.")
    else:
        lines.append("- **Verdict: NO edge.** System recommending trades that lose at random or worse. Don't enter real money.")

    return "\n".join(lines)


def _summary_line(r: dict, label: str) -> str:
    if r["n_trades"] == 0:
        return f"{label}: no trades"
    return (f"{label}: P&L ${r['cumulative_pnl']:+,.2f}  "
            f"win {r['win_rate']*100:.1f}%  "
            f"stops {r['n_stops']}/{r['n_trades']}  "
            f"maxDD {r['max_drawdown_pct']:.1f}%  "
            f"blocked {r['n_blocked_by_sector_cap']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--since-days", type=int, default=14,
                   help="Window of decision_log to evaluate")
    p.add_argument("--lookahead", type=int, default=5,
                   help="Trading days to hold each paper position before exit")
    p.add_argument("--account", type=float, default=10000.0)
    p.add_argument("--print", action="store_true",
                   help="Print report to stdout instead of writing file")
    # Phase B1 — entry-rule improvement flags
    # 2026-07-02 upgrade #5: ATR stops flipped to default TRUE.
    # Backtest 2026-05-29 (n=128) showed baseline -$873 vs +ATR +$5,950 —
    # a $6,823 swing that was hidden behind an opt-in flag for weeks
    # despite unambiguous statistical significance (p<0.005). The
    # audit finding was: "Prod vs backtest mismatch can hide 3 weeks."
    # Adding `--no-atr-stops` as escape hatch for backtest comparison
    # sweeps that WANT the baseline behavior.
    p.add_argument("--no-atr-stops", action="store_false", dest="use_atr_stops",
                   default=True,
                   help="Disable ATR stops (default is ON as of 2026-07-02). "
                        "Only pass this for backtest comparison sweeps.")
    p.add_argument("--atr-mult", type=float, default=1.5,
                   help="ATR multiplier for stop distance (default 1.5)")
    p.add_argument("--sector-cap", type=float, default=None,
                   help="Max sector exposure as account fraction (e.g. 0.30 for 30%%)")
    p.add_argument("--compare", action="store_true",
                   help="Run 4 scenarios (baseline / +ATR / +sector-cap / both) and print delta table")
    args = p.parse_args()

    # 2026-07-02 upgrade #5 part 2: every backtest report MUST enumerate
    # its flags. The audit finding was "backtest reports don't enumerate
    # the flags they ran under; prod/backtest mismatch can hide 3
    # weeks." Flags enumerated inline so any consumer of the report can
    # verify what scenario produced the numbers.
    flags_enumerated = {
        "use_atr_stops": args.use_atr_stops,
        "atr_stop_mult": args.atr_mult,
        "sector_cap_pct": args.sector_cap,
        "lookahead_days": args.lookahead,
        "since_days": args.since_days,
        "account": args.account,
    }
    print(f"[portfolio] flags_enumerated: {flags_enumerated}", file=sys.stderr)

    decisions = load_decisions(args.since_days)
    if not decisions:
        print(f"[portfolio] no decisions in last {args.since_days} days", file=sys.stderr)
        sys.exit(1)
    print(f"[portfolio] loaded {len(decisions)} decisions in window", file=sys.stderr)

    if args.compare:
        print(f"\n=== Phase B1 entry-rule backtest comparison ===")
        print(f"Window: {args.since_days} days. Lookahead: {args.lookahead}d. Account: ${args.account:,.0f}.\n")
        scenarios = [
            ("baseline (fixed stops, no cap)", False, None),
            ("+ATR stops only", True, None),
            ("+30% sector cap only", False, 0.30),
            ("+ATR + 30% sector cap", True, 0.30),
        ]
        for label, atr, cap in scenarios:
            r = simulate(decisions, args.lookahead, args.account,
                         use_atr_stops=atr, atr_stop_mult=args.atr_mult,
                         sector_cap_pct=cap)
            print(_summary_line(r, label))
        return

    result = simulate(decisions, args.lookahead, args.account,
                       use_atr_stops=args.use_atr_stops,
                       atr_stop_mult=args.atr_mult,
                       sector_cap_pct=args.sector_cap)
    report = render_report(result, args.since_days, args.lookahead, args.account,
                             flags=flags_enumerated)

    if args.print:
        print(report)
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).date().isoformat()
    out = OUT_DIR / f"{date_str}.md"
    out.write_text(report, encoding="utf-8")
    print(f"[portfolio] wrote {out}")


if __name__ == "__main__":
    main()
