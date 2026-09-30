#!/usr/bin/env python3
"""Record technical-only daily decisions; never call an LLM or submit orders.

This legacy script is not the fixed-rule Alpaca paper harness. For a paper
signal -> order -> fill -> log loop, use python -m bot.paper_harness
(see README). Its decisions do not qualify as debate rows for DSPy Phase B.

Usage:
    python scripts/run_daily_pilot.py
    python scripts/run_daily_pilot.py --tickers NVDA,AAPL --dry-run

--dry-run is retained for old launchd invocations; every invocation is
order-free and LLM-free. Market data may still be fetched from Yahoo Finance.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pilot")

DEFAULT_WATCHLIST = ["NVDA", "AAPL", "TSLA", "GOOG", "META", "INTC", "QQQ"]
MAX_TICKERS_PER_RUN = len(DEFAULT_WATCHLIST)
_TICKER = re.compile(r"[A-Z][A-Z0-9.]{0,9}\Z")


def _parse_tickers(raw: str) -> list[str]:
    tickers = [ticker.strip().upper() for ticker in raw.split(",")]
    if (not tickers or len(tickers) > MAX_TICKERS_PER_RUN
            or len(set(tickers)) != len(tickers)
            or any(not _TICKER.fullmatch(ticker) for ticker in tickers)):
        raise ValueError(f"Supply 1-{MAX_TICKERS_PER_RUN} distinct stock tickers")
    return tickers


def run_for_ticker(ticker: str) -> dict:
    """Fetch market data, produce a technical decision, and append its record."""
    from core.brain import OrallexaBrain
    from engine.decision_log import save_decision

    t0 = time.time()
    try:
        decision = OrallexaBrain(ticker).run_prediction(use_claude=False, mode="swing")
    except Exception as exc:
        logger.error("PREDICT_FAIL %s: %s", ticker, exc)
        return {"ticker": ticker, "status": "predict_failed", "error": str(exc)}

    # run_prediction converts failed data fetches into a WAIT sentinel. A
    # sentinel is not an observed decision and must not enter the log.
    if any(str(item).startswith("Prediction failed:") for item in decision.reasoning):
        logger.error("PREDICT_FAIL %s: data or indicator failure", ticker)
        return {"ticker": ticker, "status": "predict_failed"}

    confidence_pct = float(decision.confidence)
    logger.info("TECHNICAL_DECISION %s decision=%s confidence=%.1f%% elapsed=%.1fs",
                ticker, decision.decision, confidence_pct, time.time() - t0)

    try:
        saved = save_decision(
            decision=decision,
            ticker=ticker,
            mode="swing",
            timeframe="1D",
            entry_price=0.0,
            notes="run_daily_pilot:technical_only:no_debate",
        )
        if saved is False:
            raise OSError("Decision log write failed")
    except Exception as exc:
        logger.error("LOG_FAIL %s: %s", ticker, exc)
        return {"ticker": ticker, "status": "log_failed", "error": str(exc)}

    return {"ticker": ticker, "status": "logged_technical_only",
            "decision": decision.decision, "confidence": confidence_pct}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=",".join(DEFAULT_WATCHLIST),
                        help="Comma-separated stock symbols (max 7)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compatibility flag; all runs are order-free and LLM-free")
    parser.add_argument("--confidence", type=float, default=None,
                        help="Deprecated trade gate; not used for technical decision logs")
    parser.add_argument("--execute-paper", action="store_true",
                        help="Unavailable here; use python -m bot.paper_harness")
    parser.add_argument("--use-claude", action="store_true",
                        help="Unavailable here; paid LLM calls require a separate budgeted flow")
    parser.add_argument("--out", default=str(_ROOT / "logs" / "pilot.log"),
                        help="JSON-lines summary (default: %(default)s)")
    args = parser.parse_args(argv)

    # Reject unsafe requests before loading the brain, broker, or any keys.
    if args.execute_paper or args.use_claude:
        parser.error("This legacy entry point cannot place orders or call Claude; "
                     "use python -m bot.paper_harness for the fixed-rule paper loop")
    if args.confidence is not None:
        parser.error("--confidence only applied to the removed order path")
    try:
        tickers = _parse_tickers(args.tickers)
    except ValueError as exc:
        parser.error(str(exc))

    logger.info("PILOT_START technical_only=true tickers=%s llm_cost_usd=0", tickers)
    results = [run_for_ticker(ticker) for ticker in tickers]
    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "mode": "technical_only_no_debate",
        "tickers": tickers,
        "results": results,
        "decisions_logged": sum(r["status"] == "logged_technical_only" for r in results),
        "debate_rows": 0,
        "orders_submitted": 0,
        "llm_calls": 0,
        "llm_cost_usd": 0.0,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(summary) + "\n")
    logger.info("PILOT_DONE technical_decisions=%d debate_rows=0 orders=0 llm_cost_usd=0",
                summary["decisions_logged"])
    return 0 if summary["decisions_logged"] else 2


if __name__ == "__main__":
    sys.exit(main())
