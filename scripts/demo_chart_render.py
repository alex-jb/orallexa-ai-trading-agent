"""
scripts/demo_chart_render.py
──────────────────────────────────────────────────────────────────
Day 1-2 spike demo — render a K-line chart for one ticker so we can
eyeball whether the image is good enough for a vision model to reason
about (candles legible, MA overlay visible, volume bars distinct).

Outputs to assets/demo_kline_<TICKER>.png by default.

Usage:
    python scripts/demo_chart_render.py                  # NVDA, 3mo
    python scripts/demo_chart_render.py AAPL --period 6mo
    python scripts/demo_chart_render.py NVDA --output /tmp/nvda.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", nargs="?", default="NVDA")
    parser.add_argument("--period", default="3mo",
                        choices=["1mo", "3mo", "6mo", "1y", "2y"])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    out_path = args.output or (_ROOT / "assets" / f"demo_kline_{args.ticker.upper()}.png")

    from engine.chart_render import save_kline_to

    ok = save_kline_to(str(out_path), args.ticker, period=args.period)
    if not ok:
        print(f"Failed to render {args.ticker}: data fetch returned empty.")
        return 1

    size_kb = out_path.stat().st_size / 1024
    print(f"Rendered {args.ticker} ({args.period}) -> {out_path} ({size_kb:.1f} KB)")
    print("Eyeball check: open the PNG, verify candles legible + 20MA visible + volume distinct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
