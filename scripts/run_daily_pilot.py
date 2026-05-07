#!/usr/bin/env python3
"""
scripts/run_daily_pilot.py
──────────────────────────────────────────────────────────────────
Daily Alpaca paper-trading pilot. Last-mile glue between the
OrallexaBrain prediction pipeline and the Alpaca executor.

For each ticker on the watchlist:
  1. Run a Claude-backed prediction (deep-analysis pipeline)
  2. Append the DecisionOutput to memory_data/decision_log.json
     so DSPy Phase B accumulates training data
  3. If confidence >= 60% AND decision is BUY/SELL, fire a paper
     trade through AlpacaExecutor

Designed to be invoked by ~/Library/LaunchAgents/com.alexji.orallexa-paper-daily.plist
at 9:35am ET (5 minutes after US market open).

Logs everything to logs/pilot.log so the launchd output is grep-able
for "DECISION", "TRADE", "SKIP".

Why exists: per docs/UNBLOCK_30_DAYS.md, both DSPy Phase B compile
and the multi-modal lift gate are blocked on memory_data/decision_log.json
having 100 eligible production debate rows. Running this daily on
7 tickers produces ~7 rows/day, clearing the gate in ~14 days at
~$38 marginal cost.

Usage:
    python scripts/run_daily_pilot.py
    python scripts/run_daily_pilot.py --tickers NVDA,AAPL --confidence 70
    python scripts/run_daily_pilot.py --dry-run     # no Alpaca calls
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Project root on path so imports work regardless of CWD.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("pilot")

DEFAULT_WATCHLIST = ["NVDA", "AAPL", "TSLA", "GOOG", "META", "INTC", "QQQ"]
DEFAULT_CONFIDENCE_GATE = 60.0
DEFAULT_POSITION_PCT = 5.0  # % of paper portfolio per trade


def run_for_ticker(ticker: str, dry_run: bool, confidence_gate: float) -> dict:
    """
    Run Claude-backed prediction + (optionally) paper trade for one ticker.
    Returns a summary dict suitable for JSON logging.
    """
    from core.brain import OrallexaBrain
    from engine.decision_log import save_decision

    t0 = time.time()
    try:
        brain = OrallexaBrain(ticker)
    except Exception as e:
        logger.error("BRAIN_INIT_FAIL %s: %s", ticker, e)
        return {"ticker": ticker, "status": "brain_init_failed", "error": str(e)}

    try:
        decision = brain.run_prediction(use_claude=True, mode="swing")
    except Exception as e:
        logger.error("PREDICT_FAIL %s: %s", ticker, e)
        return {"ticker": ticker, "status": "predict_failed", "error": str(e)}

    elapsed = time.time() - t0
    confidence_pct = float(decision.confidence) * 100 if decision.confidence <= 1 else float(decision.confidence)

    logger.info(
        "DECISION %s decision=%s confidence=%.1f%% risk=%s elapsed=%.1fs",
        ticker,
        decision.decision,
        confidence_pct,
        decision.risk_level,
        elapsed,
    )

    # Always log to decision_log.json — this is the DSPy training data
    # we're trying to accumulate. Even WAIT decisions count toward the
    # forward-return labelling pipeline if extra.debate populated.
    try:
        save_decision(
            decision=decision,
            ticker=ticker,
            mode="swing",
            timeframe="1D",
            entry_price=0.0,
            notes="run_daily_pilot",
        )
    except Exception as e:
        logger.error("LOG_FAIL %s: %s", ticker, e)

    # Trade gate
    if dry_run:
        return {
            "ticker": ticker,
            "status": "dry_run",
            "decision": decision.decision,
            "confidence": confidence_pct,
        }

    if decision.decision == "WAIT":
        logger.info("SKIP %s — WAIT signal", ticker)
        return {"ticker": ticker, "status": "skipped_wait", "decision": "WAIT"}

    if confidence_pct < confidence_gate:
        logger.info(
            "SKIP %s — confidence %.1f%% below gate %.1f%%",
            ticker, confidence_pct, confidence_gate,
        )
        return {
            "ticker": ticker,
            "status": "skipped_low_confidence",
            "confidence": confidence_pct,
        }

    # Fire paper trade
    try:
        from bot.alpaca_executor import AlpacaExecutor
        executor = AlpacaExecutor()
        result = executor.execute_signal(
            ticker=ticker,
            decision=decision.decision,
            confidence=confidence_pct,
            position_pct=DEFAULT_POSITION_PCT,
        )
        logger.info("TRADE %s decision=%s result=%s", ticker, decision.decision, result.get("status", "?"))
        return {
            "ticker": ticker,
            "status": "traded",
            "decision": decision.decision,
            "confidence": confidence_pct,
            "alpaca_result": result,
        }
    except Exception as e:
        logger.error("ALPACA_FAIL %s: %s", ticker, e)
        return {"ticker": ticker, "status": "alpaca_failed", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tickers",
        default=",".join(DEFAULT_WATCHLIST),
        help="Comma-separated list (default: %(default)s)",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=DEFAULT_CONFIDENCE_GATE,
        help="Min confidence percent to fire trade (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip Alpaca calls. Useful for backfilling decision_log without trading.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(_ROOT / "logs" / "pilot.log"),
        help="JSON-line summary file (default: %(default)s)",
    )
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    logger.info(
        "PILOT_START tickers=%s confidence_gate=%.1f%% dry_run=%s",
        tickers, args.confidence, args.dry_run,
    )

    results = []
    for ticker in tickers:
        results.append(run_for_ticker(ticker, args.dry_run, args.confidence))

    # Append summary as one JSON line per run.
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "tickers": tickers,
        "results": results,
        "trades": sum(1 for r in results if r.get("status") == "traded"),
        "decisions_logged": sum(1 for r in results if r.get("status") not in ("brain_init_failed", "predict_failed")),
    }
    with out_path.open("a") as f:
        f.write(json.dumps(summary) + "\n")

    logger.info(
        "PILOT_DONE trades=%d decisions=%d",
        summary["trades"], summary["decisions_logged"],
    )

    # Exit non-zero only if every ticker failed — partial failure shouldn't
    # break the launchd cron's restart logic.
    if not any(r.get("status") not in ("brain_init_failed", "predict_failed") for r in results):
        sys.exit(2)


if __name__ == "__main__":
    main()
