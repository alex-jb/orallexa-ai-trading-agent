"""Trade intel: per-ticker entry tickets + recent news.

Called inline from spacex-daily.sh after the main ranked-by-signal table.
Produces:
  §4. TRADE TICKETS — for each top-N row: entry price, stop $, shares,
       dollar risk, account-% sized. Pragmatic compute that doesn't
       require ATR re-fetch (uses % distance off price by setup type).
  §5. NEWS CATALYSTS — yfinance.news pull last 24h per ticker. yfinance
       returns Yahoo Finance news API rows; we filter to last 24h +
       cap at 3 per ticker so the brief stays scannable.

Account-size default: $10k (matches the "Sizing playbook" already in
the brief). Pass `--account` to override.
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone


# ─────────────────────────────────────────────────────────────────────
# Trade ticket compute
# ─────────────────────────────────────────────────────────────────────
def setup_to_sizing_notional(setup: str, sizing_label: str, account: float,
                             *,
                             kelly_p_win: float | None = None,
                             kelly_avg_win_pct: float | None = None,
                             kelly_avg_loss_pct: float | None = None,
                             kelly_current_drawdown_pct: float | None = None,
                             kelly_fraction: float = 0.5) -> tuple[float, str]:
    """Return (notional_dollars, side). Setup labels match classify_setup
    in spacex-daily.sh. side ∈ {'long', 'short', 'pass'}.

    Sizing paths
    ------------
    **Fixed-bucket (legacy, default):** Full = 25× risk_per_trade capped
    at 20% account, Half = 15× capped at 10%, Short-half = 12× capped
    at 8%. Doesn't adapt to edge magnitude — 2026-05-27 paper audit
    found this cost -$1015 on $10k account over 14 days.

    **Kelly (Tier-2 #11, wired 2026-07-02):** opt-in by passing
    kelly_p_win + kelly_avg_win_pct + kelly_avg_loss_pct together.
    Uses Half-Kelly by default (kelly_fraction=0.5, professional
    consensus). Drawdown-adjusted if kelly_current_drawdown_pct is
    passed. Capped at MAX_KELLY_FRACTION_CAP (25% account) as absolute
    safety regardless of edge.

    Both paths return (notional, side). Kelly path preserves the side
    logic (short/long/pass) from setup + sizing_label so downstream
    order-generation stays the same shape.
    """
    # ─── Kelly opt-in path ───────────────────────────────────────
    kelly_inputs_present = (
        kelly_p_win is not None
        and kelly_avg_win_pct is not None
        and kelly_avg_loss_pct is not None
    )
    if kelly_inputs_present:
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _sys.path.insert(0, str(_Path(__file__).parent.parent.parent))
            from engine.kelly_sizing import kelly_notional as _kelly_notional
            ticket = _kelly_notional(
                account, kelly_p_win, kelly_avg_win_pct, kelly_avg_loss_pct,
                fraction=kelly_fraction,
                current_drawdown_pct=kelly_current_drawdown_pct,
            )
            notional = ticket.notional_usd
            side = "pass"
            if notional > 0:
                side = "short" if ("Short" in sizing_label or "Breakdown" in setup) else "long"
            return notional, side
        except Exception:
            # Fail-safe: fixed-bucket fallback if kelly_sizing not
            # importable (broken sys.path in cron, etc.). Sizing must
            # never raise mid-trade.
            pass

    # ─── Fixed-bucket legacy path ────────────────────────────────
    # 1-2% risk rule → with ~5% stop distance, notional = 20-40x risk
    risk_per_trade = account * 0.015  # 1.5%
    if "Full" in sizing_label:
        notional = min(risk_per_trade * 25, account * 0.20)
    elif "Half" in sizing_label and "Short" not in sizing_label:
        notional = min(risk_per_trade * 15, account * 0.10)
    elif "Short-half" in sizing_label:
        notional = min(risk_per_trade * 12, account * 0.08)
    else:
        notional = 0  # tiny / pass

    side = "pass"
    if notional > 0:
        side = "short" if "Short" in sizing_label or "Breakdown" in setup else "long"
    return notional, side


def stop_distance_pct(setup: str) -> float:
    """How far from price to place the stop, as a fraction. Tighter for
    extended setups (Trend+chase), wider for MR-bounce.

    Legacy fixed-bucket fallback used when ATR is unavailable. 2026-05-29
    backtest showed this loses -$873 over 30 days on $10k account; ATR-based
    version wins +$5,950. See research/2026-05-29-phase-b1-atr-stops-validation.md.
    """
    if "Trend+chase" in setup:
        return 0.03   # tight — extended; if it breaks fast we want out fast
    if "MR-bounce" in setup:
        return 0.05   # wider — mean reversion needs room
    if "Trend" in setup:
        return 0.05   # standard 5% trailing
    if "Breakdown" in setup:
        return 0.04   # short, tighter
    return 0.05


def fetch_atr(ticker: str, lookback: int = 14) -> float | None:
    """Fetch 14-day ATR via yfinance. Returns dollar ATR or None on failure.
    Phase B1 (2026-05-29): replaces fixed-% stop_distance with ATR-based to
    avoid 1σ-stop-outs on high-volatility tickers."""
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period=f"{lookback + 10}d", auto_adjust=True)
    except Exception:
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


def stop_distance_pct_atr(price: float, atr: float | None, setup: str,
                          atr_mult: float = 1.5,
                          floor_pct: float = 0.02,
                          cap_pct: float = 0.15) -> float:
    """ATR-based stop distance. atr_mult × ATR / price.
    Floored at 2% (don't over-tighten on low-vol names), capped at 15%
    (don't blow up on data glitches). Falls back to fixed bucket if no ATR.
    """
    if atr is None or price <= 0 or atr <= 0:
        return stop_distance_pct(setup)
    pct = (atr * atr_mult) / price
    return max(floor_pct, min(cap_pct, pct))


def compute_ticket(price: float, setup: str, sizing: str, account: float,
                   ticker: str | None = None, use_atr: bool = True) -> dict | None:
    """Returns a dict with entry/stop/shares/risk, or None if 'pass'.

    2026-05-29 (Phase B1): when ticker is provided and use_atr=True, fetches
    ATR via yfinance and uses 1.5×ATR for stop distance (backtest: 60.9%
    win rate vs 22.7% on fixed stops). Falls back to fixed bucket on
    yfinance failure.
    """
    notional, side = setup_to_sizing_notional(setup, sizing, account)
    if notional <= 0 or side == "pass" or price <= 0:
        return None
    if use_atr and ticker:
        atr = fetch_atr(ticker)
        pct = stop_distance_pct_atr(price, atr, setup)
    else:
        pct = stop_distance_pct(setup)
    if side == "long":
        stop = price * (1 - pct)
    else:  # short
        stop = price * (1 + pct)
    shares = max(1, math.floor(notional / price))
    realised_notional = shares * price
    risk_dollars = abs(price - stop) * shares
    return {
        "side": side,
        "entry": round(price, 2),
        "stop": round(stop, 2),
        "shares": shares,
        "notional": round(realised_notional, 2),
        "risk_dollars": round(risk_dollars, 2),
        "risk_pct_account": round(risk_dollars / account * 100, 2),
    }


def render_tickets(rows: list[dict], account: float, top_n: int = 5) -> str:
    """rows: list of dicts with keys ticker, price (str), setup, sizing.
    Returns Markdown."""
    out = []
    out.append("## §4. TRADE TICKETS — concrete entries\n")
    out.append(f"_Account assumption: ${account:,.0f}. Risk-per-trade target: 1.5% (${account*0.015:,.0f})._\n")
    out.append("| Ticker | Side | Entry | Stop | Shares | Notional | Risk $ | Risk % |")
    out.append("|---|---|---|---|---|---|---|---|")
    written = 0
    for r in rows:
        if written >= top_n:
            break
        try:
            price = float(r.get("price") or 0)
        except Exception:
            price = 0
        if price <= 0:
            continue
        t = compute_ticket(price, r.get("setup", ""), r.get("sizing", ""),
                           account, ticker=r.get("ticker"), use_atr=True)
        if t is None:
            continue
        side_emoji = "🟢" if t["side"] == "long" else "🔴"
        out.append(
            f"| **{r['ticker']}** | {side_emoji} {t['side'].upper()} | ${t['entry']} | ${t['stop']} | "
            f"{t['shares']} | ${t['notional']:,.0f} | ${t['risk_dollars']:.0f} | {t['risk_pct_account']}% |"
        )
        written += 1
    if written == 0:
        out.append("| — | — | (no tradable setups today; all rows are 'pass' or price unavailable) | | | | | |")
    out.append("")
    out.append("**How to read:**")
    out.append("- Entry = limit order at this price (or market if -2%-of-MA20-pullback for Trend+chase). Valid until next session close.")
    out.append("- Stop = hard exit; risk_dollars = (entry - stop) × shares. Keep total open risk ≤ 5% account.")
    out.append("- Shares assumes whole-share broker (Robinhood/Fidelity). Adjust for fractional brokers (IBKR pro).")
    out.append("")
    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────
# News catalysts via yfinance
# ─────────────────────────────────────────────────────────────────────
def fetch_recent_news(tickers: list[str], hours: int = 36, per_ticker: int = 3) -> dict:
    """Returns {ticker: [{title, publisher, link, published_at}, ...]}.
    Filters to last `hours` hours."""
    try:
        import yfinance as yf
    except ImportError:
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    out: dict[str, list] = {}
    for t in tickers:
        try:
            raw = yf.Ticker(t).news or []
        except Exception:
            continue
        hits = []
        for n in raw:
            # yfinance returns either flat dict {title, providerPublishTime, ...}
            # or wrapped {content: {...}} depending on version. Handle both.
            content = n.get("content") if isinstance(n.get("content"), dict) else n
            title = content.get("title") or n.get("title")
            publisher = (
                content.get("provider", {}).get("displayName")
                if isinstance(content.get("provider"), dict)
                else content.get("publisher") or n.get("publisher")
            )
            ts = (
                content.get("pubDate")
                or content.get("displayTime")
                or n.get("providerPublishTime")
            )
            link = (
                content.get("canonicalUrl", {}).get("url")
                if isinstance(content.get("canonicalUrl"), dict)
                else content.get("link") or n.get("link")
            )
            if not title:
                continue
            published = None
            if isinstance(ts, (int, float)):
                published = datetime.fromtimestamp(ts, tz=timezone.utc)
            elif isinstance(ts, str):
                try:
                    published = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    published = None
            if published and published < cutoff:
                continue
            hits.append({
                "title": title.strip()[:140],
                "publisher": (publisher or "?")[:30],
                "link": link or "",
                "published_at": published.isoformat() if published else None,
            })
            if len(hits) >= per_ticker:
                break
        if hits:
            out[t] = hits
    return out


def render_news(news_by_ticker: dict) -> str:
    out = ["## §5. NEWS CATALYSTS — last 36h per ticker (yfinance)\n"]
    if not news_by_ticker:
        out.append("_No recent news fetched. (yfinance may be rate-limited; retry tomorrow.)_\n")
        return "\n".join(out)
    for ticker, items in news_by_ticker.items():
        out.append(f"### {ticker}")
        for it in items:
            ts = it["published_at"][:16].replace("T", " ") if it["published_at"] else "?"
            out.append(f"- [{ts}] **{it['title']}** — _{it['publisher']}_  ")
            if it["link"]:
                out.append(f"  → {it['link']}")
        out.append("")
    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────
# CLI entry — read ranked rows JSON via stdin, emit markdown
# ─────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--account", type=float, default=10000.0)
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--news-hours", type=int, default=36)
    args = p.parse_args()

    import json
    rows = json.load(sys.stdin)  # list of {ticker, price, setup, sizing}
    if not isinstance(rows, list):
        print("expected JSON list on stdin", file=sys.stderr)
        sys.exit(1)

    print(render_tickets(rows, args.account, args.top_n))
    print()
    tickers = [r["ticker"] for r in rows[: args.top_n]]
    print(render_news(fetch_recent_news(tickers, args.news_hours)))


if __name__ == "__main__":
    main()
