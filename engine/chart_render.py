"""
engine/chart_render.py
──────────────────────────────────────────────────────────────────
Pure rendering layer for the multi-modal debate spike.

Takes OHLCV data → produces a PNG image suitable for sending to a
vision-capable LLM (Claude Vision, GPT-4V, Gemini). The image is
deterministic given the same inputs, so two debate runs on the same
ticker compare apples-to-apples.

What's in this module:
  - render_kline(df) → bytes        : OHLCV DataFrame to PNG bytes
  - render_kline_for(ticker, …)     : convenience wrapper that fetches
                                       OHLCV via the historical cache
  - save_kline_to(path, …)          : helper used by the demo script

What's NOT here yet (Phase 2):
  - Actually feeding the image to a perspective panel — that's a
    separate wiring change in `llm/perspective_panel.py`. Day 1-2
    spike is pure rendering, no LLM integration.

mplfinance + matplotlib are required at runtime. Keep imports lazy so
projects that never call this code path don't pay the import cost.

Usage:
    from engine.chart_render import render_kline_for
    png = render_kline_for("NVDA", period="3mo")
    open("nvda.png", "wb").write(png)
"""
from __future__ import annotations

import io
import logging
from typing import Optional

# Force a headless backend BEFORE matplotlib gets imported through mplfinance.
# Without this, calling render_kline from a non-GUI context (CI, server,
# subprocess) crashes with `TclError: Can't find init.tcl` on Windows.
import matplotlib
matplotlib.use("Agg")

logger = logging.getLogger(__name__)


# ── Defaults --------------------------------------------------------------
# Chosen so a vision model gets enough resolution to read candles + volume
# without the payload exploding past Anthropic's 5MB image limit. Empirically
# 1100×800 PNG ≈ 80-150KB for 60 candles + volume + 20MA overlay.

DEFAULT_FIGSIZE = (11.0, 8.0)
DEFAULT_DPI = 100
DEFAULT_STYLE = "yahoo"
DEFAULT_MA = (20,)


def render_kline(
    df,
    *,
    ticker: str = "",
    figsize: tuple[float, float] = DEFAULT_FIGSIZE,
    dpi: int = DEFAULT_DPI,
    style: str = DEFAULT_STYLE,
    mavs: tuple[int, ...] = DEFAULT_MA,
    show_volume: bool = True,
) -> bytes:
    """
    Render a candlestick chart from an OHLCV DataFrame and return PNG bytes.

    The DataFrame must have a DatetimeIndex and Open/High/Low/Close/Volume
    columns — this is the standard yfinance shape. Extra columns are
    ignored (so cached frames with indicators added still work).

    `mavs` controls moving-average overlays. Default is (20,) — pass an
    empty tuple to disable.

    Raises ValueError on missing required columns. Returns PNG bytes
    suitable for `base64.b64encode(...)` into a vision-API payload.
    """
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"render_kline: missing required OHLCV columns: {sorted(missing)}"
        )
    if df.empty:
        raise ValueError("render_kline: empty DataFrame")

    import mplfinance as mpf

    buf = io.BytesIO()
    title = f"{ticker} — {len(df)} bars" if ticker else f"{len(df)} bars"

    plot_kwargs = dict(
        type="candle",
        style=style,
        title=title,
        ylabel="Price",
        ylabel_lower="Volume",
        volume=show_volume,
        figsize=figsize,
        savefig=dict(fname=buf, dpi=dpi, format="png", bbox_inches="tight"),
        warn_too_much_data=10_000,
    )
    # mplfinance.plot rejects `mav=None`; only pass the kwarg when non-empty.
    if mavs:
        plot_kwargs["mav"] = mavs

    mpf.plot(df, **plot_kwargs)
    buf.seek(0)
    return buf.getvalue()


def render_kline_for(
    ticker: str,
    *,
    period: str = "3mo",
    use_cache: Optional[bool] = None,
    **render_kwargs,
) -> Optional[bytes]:
    """
    Fetch OHLCV via the historical cache (or yfinance fallback) and render.

    `use_cache` overrides the `ORALLEXA_USE_CACHE` env-var default. None
    means "let cache_enabled() decide." Returns None if the data fetch
    fails — callers should fall back to text-only debate in that case.
    """
    df = None

    try:
        from engine.historical_cache import get_default_cache, cache_enabled
        do_cache = cache_enabled() if use_cache is None else use_cache
        if do_cache:
            df = get_default_cache().get_prices_by_period(ticker, period=period)
    except Exception as e:
        logger.debug("Chart cache lookup failed for %s: %s", ticker, e)

    if df is None or df.empty:
        try:
            import yfinance as yf
            df = yf.Ticker(ticker).history(period=period, interval="1d")
        except Exception as e:
            logger.warning("Chart yfinance fetch failed for %s: %s", ticker, e)
            return None

    if df is None or df.empty:
        return None

    return render_kline(df, ticker=ticker, **render_kwargs)


def save_kline_to(path: str, ticker: str, **kwargs) -> bool:
    """Convenience for the demo script. Writes PNG to `path`, True on success."""
    png = render_kline_for(ticker, **kwargs)
    if png is None:
        return False
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(png)
    return True
