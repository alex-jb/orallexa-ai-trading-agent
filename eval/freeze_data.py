"""Download a dated, auditable OHLCV snapshot for a predeclared evaluation.

This is a read-only market-data operation; it never accesses a broker.
The command fails without writing an incomplete cohort if any ticker fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import yfinance as yf


TICKERS = ("NVDA", "AAPL", "TSLA", "GOOG", "META", "INTC", "QQQ", "MSFT", "AMZN", "SPY")
START = "2021-01-01"
END_EXCLUSIVE = "2026-09-29"
COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="eval/snapshots/2026-09-29")
    args = parser.parse_args()
    data: dict[str, bytes] = {}
    for ticker in TICKERS:
        df = yf.download(ticker, start=START, end=END_EXCLUSIVE, auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if len(df) < 504 or not set(COLUMNS).issubset(df.columns):
            raise RuntimeError(f"No usable OHLCV snapshot for {ticker}; nothing written")
        df = df[COLUMNS].sort_index()
        df.index.name = "Date"
        data[ticker] = df.to_csv(float_format="%.10g").encode("utf-8")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": "yfinance download, auto_adjust=True",
        "yfinance_version": yf.__version__,
        "start": START,
        "end_exclusive": END_EXCLUSIVE,
        "tickers": list(TICKERS),
        "sha256": {},
    }
    for ticker, raw in data.items():
        (out / f"{ticker}.csv").write_bytes(raw)
        manifest["sha256"][ticker] = hashlib.sha256(raw).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(data)} snapshots to {out}")


if __name__ == "__main__":
    main()
