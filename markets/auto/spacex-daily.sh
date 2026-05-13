#!/bin/bash
# scripts/spacex-daily.sh
# ─────────────────────────────────────────────────────────────
# Daily SpaceX-pure-play research run. Triggered by launchd at
# NY 14:00 EDT (post-market-open + intra-day RSI/MACD have data).
#
# 1. Run Orallexa pilot on 8-ticker watchlist (dry-run, no real trade)
# 2. Extract per-ticker reasoning from decision_log.json
# 3. Write Markdown brief to ~/Desktop/Interview-Prep/Projects/alex-brain/
#    research/spacex-daily/YYYY-MM-DD.md
# 4. Open the brief in default markdown viewer
#
# Failure mode: if Orallexa pilot fails, leave previous day's file
# untouched and log the failure to ~/.orallexa/markets/logs/spacex-daily.err
set -u

REPO="${REPO:-$HOME/Desktop/orallexa-ai-trading-agent}"
PY="${PY:-$HOME/.local/bin/python3.11}"
BRAIN="${BRAIN:-$HOME/Desktop/Interview-Prep/Projects/alex-brain}"
WATCHLIST="${WATCHLIST:-RKLB,ASTS,LUNR,BKSY,PL,RDW,LMT,LIN,TSLA,SYM,NVDA,AVGO,AVAV,KTOS}"
DATE=$(date +%F)
BRIEF_DIR="$BRAIN/research/spacex-daily"
BRIEF_FILE="$BRIEF_DIR/${DATE}.md"
LOG_DIR="$HOME/.orallexa/markets/logs"

mkdir -p "$BRIEF_DIR" "$LOG_DIR"

# Pull ANTHROPIC_API_KEY from ~/.zshrc (launchd context doesn't load zshrc)
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    export ANTHROPIC_API_KEY=$(grep "^export ANTHROPIC_API_KEY" "$HOME/.zshrc" | head -1 | cut -d= -f2)
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "[$(date -u +%FT%TZ)] FATAL: ANTHROPIC_API_KEY not set" >&2
    exit 1
fi

cd "$REPO" || { echo "FATAL: cannot cd to $REPO" >&2; exit 1; }

echo "[$(date -u +%FT%TZ)] SpaceX daily pilot starting — watchlist=$WATCHLIST"

# Run pilot
"$PY" scripts/run_daily_pilot.py \
    --tickers "$WATCHLIST" \
    --confidence 60 \
    --dry-run 2>&1 | tee /tmp/spacex-pilot-$DATE.log

RC=$?
if [ $RC -ne 0 ]; then
    echo "[$(date -u +%FT%TZ)] pilot FAILED rc=$RC — brief not written"
    exit $RC
fi

# Build brief markdown from decision log
"$PY" - <<PYEOF
import json
from pathlib import Path
from datetime import datetime

WATCHLIST = "$WATCHLIST".split(",")
DATE = "$DATE"
BRIEF = Path("$BRIEF_FILE")

with open("$REPO/memory_data/decision_log.json") as f:
    data = json.load(f)

# Find today's entries for each ticker (most recent first)
today_runs = {}
for d in reversed(data):
    if d.get("timestamp", "").startswith(DATE) and d.get("ticker") in WATCHLIST:
        today_runs.setdefault(d["ticker"], d)

if not today_runs:
    print("WARNING: no decisions found for today; using stale data")

# Rank by p(up) - p(down)
ranked = sorted(
    today_runs.values(),
    key=lambda d: d["probabilities"].get("up", 0) - d["probabilities"].get("down", 0),
    reverse=True,
)

# ─────────────────────────────────────────────────────────────
# FTD (Follow-Through Day) detector — William O'Neil / IBD signal
# that confirms a market bottom. When fired, all 'Trend' setups get
# upgraded sizing because the bigger-picture regime just turned.
#
# FTD criteria (any major index):
#   1. We're 4-7 trading days past a recent low (≤ 14d lookback)
#   2. Today's gain > 1.7% on the index
#   3. Today's volume > yesterday's (institutional confirmation)
#
# Reference: tradermonty/claude-trading-skills (2026-05-13 research scan)
# ─────────────────────────────────────────────────────────────
def detect_ftd():
    """Return (active: bool, summary: str). Caches yfinance fetch, fails open
    to active=False if data unavailable (safer than false-positive upgrade)."""
    try:
        import yfinance as yf
    except ImportError:
        return False, "yfinance not installed — FTD check skipped"

    results = []
    for index_symbol, name in (("^GSPC", "S&P 500"), ("^IXIC", "NASDAQ")):
        try:
            df = yf.Ticker(index_symbol).history(period="30d")
            if df is None or len(df) < 8:
                continue
            last_14 = df.tail(14)
            low_idx = last_14["Low"].idxmin()
            days_since = len(df.loc[low_idx:]) - 1  # trading days since low
            if not (4 <= days_since <= 7):
                results.append(f"{name}: not in FTD window (D+{days_since} since low)")
                continue
            today_close = float(df["Close"].iloc[-1])
            yest_close = float(df["Close"].iloc[-2])
            today_vol = float(df["Volume"].iloc[-1])
            yest_vol = float(df["Volume"].iloc[-2])
            gain_pct = (today_close - yest_close) / yest_close * 100
            vol_confirms = today_vol > yest_vol
            if gain_pct >= 1.7 and vol_confirms:
                results.append(f"✅ {name}: FTD CONFIRMED (D+{days_since}, +{gain_pct:.2f}%, vol up)")
                return True, " | ".join(results)
            else:
                results.append(f"{name}: D+{days_since}, +{gain_pct:.2f}% (need ≥1.7% + vol up)")
        except Exception as e:
            results.append(f"{name}: fetch error ({e!r})")
    return False, " | ".join(results) if results else "no index data"


_FTD_ACTIVE, _FTD_NOTE = detect_ftd()


# ─────────────────────────────────────────────────────────────
# VIX regime detector — complementary to FTD
#   VIX < 15  → calm regime, no adjustment
#   VIX 15-20 → mildly elevated, no adjustment
#   VIX 20-30 → elevated, downgrade Trend sizing one tier
#   VIX > 30  → panic regime, all setups go Pass except Tiny
# ─────────────────────────────────────────────────────────────
def detect_vix():
    """Return (vix_value: float, regime: str, downgrade_tiers: int)."""
    try:
        import yfinance as yf
        df = yf.Ticker("^VIX").history(period="5d")
        if df is None or len(df) == 0:
            return None, "unknown", 0
        vix = float(df["Close"].iloc[-1])
    except Exception:
        return None, "unknown", 0
    if vix > 30:
        return vix, "🔴 panic (Pass all but Tiny)", 99  # special: force Pass
    elif vix > 20:
        return vix, "🟡 elevated (downgrade Trend one tier)", 1
    elif vix > 15:
        return vix, "🟢 mildly elevated (no change)", 0
    else:
        return vix, "🟢 calm (no change)", 0


_VIX_VALUE, _VIX_REGIME, _VIX_DOWNGRADE = detect_vix()


# ─────────────────────────────────────────────────────────────
# Earnings calendar — yfinance gives upcoming earnings_dates per
# ticker. Anything within 5 trading days = high binary-event risk.
# When a ticker has earnings ≤ 3 days, force sizing to Tiny
# regardless of setup (don't take Trend exposure into a binary).
# ─────────────────────────────────────────────────────────────
_EARNINGS_BY_TICKER = {}

def fetch_earnings_calendar():
    """Build {ticker: days_until_earnings} for the 14 watchlist tickers."""
    try:
        import yfinance as yf
        from datetime import datetime, timezone
    except ImportError:
        return
    now = datetime.now(timezone.utc).date()
    for t in WATCHLIST:
        try:
            tk = yf.Ticker(t)
            df = tk.get_earnings_dates(limit=4) if hasattr(tk, "get_earnings_dates") else None
            if df is None or len(df) == 0:
                continue
            # Find next future date
            future_dates = [d.date() for d in df.index if d.date() >= now]
            if not future_dates:
                continue
            next_earn = min(future_dates)
            days = (next_earn - now).days
            if 0 <= days <= 14:
                _EARNINGS_BY_TICKER[t] = days
        except Exception:
            continue

fetch_earnings_calendar()


def earnings_warning(ticker: str) -> str:
    """Return '⚠ N d' string if earnings within 14 days, else '—'."""
    days = _EARNINGS_BY_TICKER.get(ticker)
    if days is None:
        return "—"
    if days <= 3:
        return f"🔴 {days}d"
    elif days <= 7:
        return f"🟡 {days}d"
    else:
        return f"🟢 {days}d"


# ─────────────────────────────────────────────────────────────
# Correlation matrix — 30-day rolling pairwise correlation across
# the 14 watchlist tickers. Flags "diversification illusion": when
# two Trend setups are >70% correlated, sizing them both Full is
# actually 1.4x leverage on a single bet, not a hedged position.
# ─────────────────────────────────────────────────────────────
def compute_correlations(period_days: int = 30):
    """Return (correlation_dict, high_corr_pairs).
    correlation_dict[(a, b)] = pearson corr coefficient.
    high_corr_pairs = [(a, b, corr), ...] sorted desc, where corr > 0.7.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {}, []

    # Batch download for efficiency
    try:
        df = yf.download(
            tickers=" ".join(WATCHLIST),
            period=f"{period_days + 10}d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        # df has MultiIndex columns: (price, ticker)
        if "Close" in df.columns.get_level_values(0):
            closes = df["Close"]
        else:
            return {}, []
    except Exception:
        return {}, []

    # Daily returns
    returns = closes.pct_change().dropna()
    if len(returns) < 10:
        return {}, []

    corr_matrix = returns.corr()
    corr_dict = {}
    high_pairs = []
    tickers_in_df = list(corr_matrix.columns)
    for i, a in enumerate(tickers_in_df):
        for b in tickers_in_df[i + 1:]:
            try:
                c = float(corr_matrix.loc[a, b])
                if __import__("math").isnan(c):
                    continue
            except Exception:
                continue
            corr_dict[(a, b)] = c
            if c > 0.7:
                high_pairs.append((a, b, c))
    high_pairs.sort(key=lambda x: x[2], reverse=True)
    return corr_dict, high_pairs


_CORR_DICT, _HIGH_CORR_PAIRS = compute_correlations()


# ─────────────────────────────────────────────────────────────
# Technical setup classifier — parses reasoning[] lines from Orallexa
# decision log and adds 3 enrichment fields the brief renders:
#
#   setup    : "Trend" / "MR-bounce" / "Trend+chase⚠" / "Breakdown" / "—"
#   sizing   : "Full" / "Half" / "Tiny" / "Pass" (paper-trade tier)
#   stop     : verbal stop-loss hint based on RSI/BB% context
#
# This implements the 3-framework entry timing playbook from the 2026-05-13
# session — trend-following, mean-reversion, breakout — applied
# automatically to each ranked ticker so the brief is actionable, not just
# descriptive. See alex-brain/research/2026-05-13-buzzplay-study.md and
# the daily-brief curriculum Day 2+ for the full rationale.
# ─────────────────────────────────────────────────────────────
def classify_setup(d):
    """Return (setup, sizing, stop_hint) for a decision_log entry."""
    reasoning = d.get("reasoning", [])
    decision = d.get("decision", "")
    confidence = d.get("confidence", 0) or 0
    earnings_days = _EARNINGS_BY_TICKER.get(d.get("ticker"))

    def parse_rsi():
        for r in reasoning:
            if "RSI" in r and "—" in r:
                try:
                    return float(r.split("RSI")[1].split("—")[0].strip())
                except Exception:
                    pass
        return None

    def parse_bb_pct():
        for r in reasoning:
            if "BB%" in r:
                try:
                    return float(r.split("BB%:")[1].split("—")[0].strip())
                except Exception:
                    pass
        return None

    rsi = parse_rsi()
    bb_pct = parse_bb_pct()
    has_bullish_stack = any("bullish stack" in r for r in reasoning)
    macd_bullish = any("MACD histogram positive" in r for r in reasoning)
    rsi_oversold = rsi is not None and rsi < 30
    rsi_overbought = rsi is not None and rsi > 70
    rsi_clean = rsi is not None and 40 <= rsi <= 65

    # Setup classification
    if decision == "BUY" and has_bullish_stack and macd_bullish and rsi_clean:
        setup = "Trend"
    elif decision == "BUY" and has_bullish_stack and rsi_overbought:
        setup = "Trend+chase⚠"  # bullish but extended; wait for pullback
    elif rsi_oversold:
        setup = "MR-bounce"  # mean-reversion candidate even if Orallexa says WAIT/SELL
    elif decision == "SELL" and not rsi_oversold:
        setup = "Breakdown"
    else:
        setup = "—"

    # Position sizing — paper-trade tier per 1-2% risk rule
    # FTD active = regime-confirming day → upgrade Trend setups by one tier
    # VIX > 30 = panic → force everything below Short-half to Pass
    # VIX 20-30 = elevated → downgrade Trend one tier
    if _VIX_DOWNGRADE >= 99:
        # Panic — only allow Tiny BUY (no Full/Half exposure)
        if decision == "BUY":
            sizing = "Tiny"
        elif setup == "Breakdown" and confidence >= 50:
            sizing = "Short-half"
        else:
            sizing = "Pass"
    elif setup == "Trend" and (confidence >= 65 or _FTD_ACTIVE):
        sizing = "Full" + ("🔥" if _FTD_ACTIVE else "")
        if _VIX_DOWNGRADE == 1:
            sizing = "Half⚠"  # VIX elevated → downgrade
    elif setup in ("Trend", "MR-bounce") and confidence >= 50:
        sizing = "Half" + ("🔥" if _FTD_ACTIVE and setup == "MR-bounce" else "")
        if _VIX_DOWNGRADE == 1:
            sizing = "Tiny⚠"
    elif decision == "BUY":
        sizing = "Tiny"
    elif setup == "Breakdown" and confidence >= 50:
        sizing = "Short-half"
    else:
        sizing = "Pass"

    # Earnings override — within 3 trading days, force down to Tiny (or Pass for SELL)
    # to avoid taking Trend exposure into a binary event
    if earnings_days is not None and earnings_days <= 3:
        if decision == "BUY" and sizing not in ("Pass", "Tiny"):
            sizing = "Tiny📅"  # 📅 = earnings within 3 days, sizing overridden
        elif decision == "SELL" and "half" in sizing.lower():
            sizing = "Pass📅"

    # Stop-loss hint based on BB% + setup
    if setup == "Trend" and bb_pct is not None:
        stop = "MA20 -1.5%" if bb_pct < 0.7 else "MA20 -1%"
    elif setup == "Trend+chase⚠":
        stop = "wait MA20 pullback"
    elif setup == "MR-bounce":
        stop = "swing low -1.5%"
    elif setup == "Breakdown":
        stop = "above swing high"
    else:
        stop = "-1.5 ATR"

    return setup, sizing, stop


# Sector tags (per Sun Yuchen 2026 thesis: 太空 / 物理AI / 智能 / 无人机)
SECTOR_EMOJI = {
    # 🛰 Space (SpaceX pure-play, original)
    "RKLB": "🛰", "ASTS": "🛰", "LUNR": "🛰", "BKSY": "🛰",
    "PL": "🛰", "RDW": "🛰", "LMT": "🛰", "LIN": "🛰",
    # 🤖 Physical AI / robotics
    "TSLA": "🤖", "SYM": "🤖",
    # 🧠 AI infra
    "NVDA": "🧠", "AVGO": "🧠",
    # 🚁 Drones
    "AVAV": "🚁", "KTOS": "🚁",
}
SECTOR_NAME = {"🛰": "Space", "🤖": "Physical AI", "🧠": "AI Infra", "🚁": "Drones"}

def tag(ticker):
    """Prefix ticker with sector emoji."""
    return f"{SECTOR_EMOJI.get(ticker, '·')} {ticker}"

# Build brief
lines = []
lines.append(f"# SpaceX Pure-Play Daily Brief — {DATE}\n")
lines.append(f"**Run time (UTC)**: {datetime.utcnow().isoformat()}Z\n")
lines.append(f"**Watchlist (14 tickers, 4 sectors)**: 🛰 Space · 🤖 Physical AI · 🧠 AI Infra · 🚁 Drones\n")
lines.append(f"{', '.join(tag(t) for t in WATCHLIST)}\n")
lines.append("")
lines.append(f"**Regime — FTD (Follow-Through Day):** {'🔥 ACTIVE — Trend setups upgraded one tier' if _FTD_ACTIVE else 'inactive'}")
lines.append(f"_{_FTD_NOTE}_\n")
vix_str = f"{_VIX_VALUE:.2f}" if _VIX_VALUE else "n/a"
lines.append(f"**Regime — VIX:** {vix_str} — {_VIX_REGIME}")
lines.append("")
lines.append("## Ranked by signal direction (p_up - p_down)\n")
lines.append("| Rank | Sector | Ticker | Decision | Conf | Setup | Sizing | Earn | Price | RSI | Stop | Δ probs |")
lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")

for i, d in enumerate(ranked, 1):
    rsi_line = [r for r in d.get("reasoning", []) if "RSI" in r]
    rsi = rsi_line[0].split("RSI")[1].strip().split()[0] if rsi_line else "?"
    price_line = [r for r in d.get("reasoning", []) if "Price (" in r]
    price = price_line[0].split("Price (")[1].split(")")[0] if price_line else "?"
    p_up = d["probabilities"].get("up", 0)
    p_down = d["probabilities"].get("down", 0)
    delta = p_up - p_down
    delta_str = f"{delta:+.2f}"
    emoji = SECTOR_EMOJI.get(d['ticker'], '·')
    setup, sizing, stop = classify_setup(d)
    earn = earnings_warning(d['ticker'])
    lines.append(
        f"| {i} | {emoji} | **{d['ticker']}** | {d['decision']} | {d['confidence']}% | "
        f"{setup} | {sizing} | {earn} | \${price} | {rsi} | {stop} | {delta_str} |"
    )

# Setup legend + position sizing playbook (so the brief is self-documenting)
lines.append("")
lines.append("**Setup legend:**")
lines.append("- **Trend** — Price > MA20 > MA50 + MACD bullish + RSI 40-65 (clean trend-follow entry)")
lines.append("- **Trend+chase⚠** — bullish stack BUT RSI > 70 (extended; wait for MA20 pullback before entering)")
lines.append("- **MR-bounce** — RSI < 30 (mean-reversion candidate; counter the Orallexa SELL with tight stop)")
lines.append("- **Breakdown** — Orallexa SELL + RSI not yet oversold (short candidate or pass)")
lines.append("- **—** — no clean setup; pass or paper only")
lines.append("")
lines.append("**Sizing playbook** (1-2% risk rule, \$10k account → \$100-200 max loss per trade):")
lines.append("- **Full** (\$1k-2k notional) — only Trend + conf ≥ 65%")
lines.append("- **Half** (\$500-1k) — Trend or MR-bounce + conf ≥ 50%")
lines.append("- **Short-half** — Breakdown + conf ≥ 50%, only with stop above swing high")
lines.append("- **Tiny / Pass** — paper trade or skip")
lines.append("")


# ─────────────────────────────────────────────────────────────
# Sector rotation tracker — aggregate Δ probs (p_up - p_down) by
# sector. Tells us which of the 4 sectors leads/lags today.
# ─────────────────────────────────────────────────────────────
sector_totals = {"🛰 Space": [], "🤖 Physical AI": [], "🧠 AI Infra": [], "🚁 Drones": []}
for d in ranked:
    emoji = SECTOR_EMOJI.get(d['ticker'], '·')
    name = SECTOR_NAME.get(emoji, "Other")
    full_label = f"{emoji} {name}"
    if full_label in sector_totals:
        p_up = d["probabilities"].get("up", 0)
        p_down = d["probabilities"].get("down", 0)
        sector_totals[full_label].append(p_up - p_down)

lines.append("\n## Sector rotation — aggregate Δ probs (p_up - p_down) by sector\n")
lines.append("| Sector | N | Avg Δ probs | Verdict |")
lines.append("|---|---|---|---|")
sector_avg = []
for label, deltas in sector_totals.items():
    if deltas:
        avg = sum(deltas) / len(deltas)
        sector_avg.append((label, len(deltas), avg))
sector_avg.sort(key=lambda x: x[2], reverse=True)
for label, n, avg in sector_avg:
    verdict = "🟢 leading" if avg > 0.20 else "🟡 neutral" if avg > -0.10 else "🔴 lagging"
    lines.append(f"| {label} | {n} | {avg:+.3f} | {verdict} |")
lines.append("")
if sector_avg:
    top = sector_avg[0]
    bot = sector_avg[-1]
    spread = top[2] - bot[2]
    lines.append(f"**Rotation read:** {top[0]} (Δ {top[2]:+.2f}) leading {bot[0]} (Δ {bot[2]:+.2f}) by **{spread:.2f}** today. "
                  + ("Strong rotation signal — concentrate position adds on leading sector." if spread > 0.40 else
                     "Mild rotation — single-day noise vs trend not yet separable." if spread > 0.20 else
                     "No clear rotation — sectors moving together."))
lines.append("")


# ─────────────────────────────────────────────────────────────
# Diversification audit — find Trend setups whose tickers are
# heavily correlated. If both rated 'Half', combining them is closer
# to 1.4x leverage than 2× hedged diversification.
# ─────────────────────────────────────────────────────────────
ticker_to_setup = {}
for d in ranked:
    setup, sizing, stop = classify_setup(d)
    ticker_to_setup[d['ticker']] = (setup, sizing, d['decision'])

trend_pairs_warning = []
for a, b, c in _HIGH_CORR_PAIRS:
    sa = ticker_to_setup.get(a)
    sb = ticker_to_setup.get(b)
    if not sa or not sb:
        continue
    setup_a, sizing_a, dec_a = sa
    setup_b, sizing_b, dec_b = sb
    if "Trend" in setup_a and "Trend" in setup_b and "Pass" not in sizing_a and "Pass" not in sizing_b:
        trend_pairs_warning.append((a, b, c, sizing_a, sizing_b))

lines.append("\n## Diversification audit — 30d rolling correlation\n")
if not _CORR_DICT:
    lines.append("_yfinance batch download failed — correlation skipped._\n")
else:
    lines.append("**Top 5 highest-correlation pairs in watchlist:**\n")
    lines.append("| Pair | Corr | Setup A | Setup B | Risk note |")
    lines.append("|---|---|---|---|---|")
    for a, b, c in _HIGH_CORR_PAIRS[:5]:
        sa = ticker_to_setup.get(a, ("—", "—", "—"))
        sb = ticker_to_setup.get(b, ("—", "—", "—"))
        risk = "⚠ both Trend — sizing both = leverage" if ("Trend" in sa[0] and "Trend" in sb[0]) else "—"
        lines.append(f"| **{a}** ↔ **{b}** | {c:.2f} | {sa[0]}/{sa[1]} | {sb[0]}/{sb[1]} | {risk} |")
    lines.append("")
    if trend_pairs_warning:
        lines.append("**🚨 Diversification illusion alert:**")
        for a, b, c, sza, szb in trend_pairs_warning[:3]:
            lines.append(f"- **{a}** ({sza}) + **{b}** ({szb}) are **{c:.2f} correlated**. "
                          f"Combined exposure ≈ 1+{c:.2f} = **{1+c:.2f}× leverage** on the same factor, "
                          f"not hedged diversification. Either downsize one to Tiny, or accept the leverage knowingly.")
        lines.append("")
    else:
        lines.append("_No Trend-Trend pairs with corr > 0.7 — current sizing is genuinely diversified._\n")

lines.append("\n## Per-ticker Claude reasoning\n")
for d in ranked:
    emoji = SECTOR_EMOJI.get(d['ticker'], '·')
    sector_name = SECTOR_NAME.get(emoji, "Other")
    setup, sizing, stop = classify_setup(d)
    lines.append(f"### {emoji} {d['ticker']} ({sector_name}) — {d['decision']} {d['confidence']}% ({d['risk_level']})")
    lines.append(f"**Setup:** {setup} · **Sizing:** {sizing} · **Stop:** {stop}")
    for r in d.get("reasoning", []):
        if "Claude reasoning:" in r:
            claude = r.split("Claude reasoning:", 1)[1].strip()
            lines.append(f"> {claude}")
            break
    lines.append("")

# Compare to yesterday — extract previous day's ranked decisions if available
prev_date = (datetime.strptime(DATE, "%Y-%m-%d").toordinal() - 1)
prev_date_str = datetime.fromordinal(prev_date).strftime("%Y-%m-%d")
prev_brief = BRIEF.parent / f"{prev_date_str}.md"
prev_runs = {}
for d in data:
    if d.get("timestamp", "").startswith(prev_date_str) and d.get("ticker") in WATCHLIST:
        prev_runs.setdefault(d["ticker"], d)

if prev_runs:
    lines.append(f"\n## Delta vs {prev_date_str} (yesterday)\n")
    lines.append("| Ticker | Yesterday | Today | Decision Δ | Δ p(up) | Δ conf |")
    lines.append("|---|---|---|---|---|---|")
    for t in WATCHLIST:
        if t not in today_runs:
            continue
        td = today_runs[t]
        if t not in prev_runs:
            lines.append(f"| **{t}** | (new) | {td['decision']} {td['confidence']}% | — | — | — |")
            continue
        pd = prev_runs[t]
        decision_change = "→" if pd["decision"] != td["decision"] else "="
        d_pup = td["probabilities"].get("up", 0) - pd["probabilities"].get("up", 0)
        d_conf = td["confidence"] - pd["confidence"]
        lines.append(
            f"| **{t}** | {pd['decision']} {pd['confidence']}% | "
            f"{td['decision']} {td['confidence']}% | "
            f"{pd['decision']} {decision_change} {td['decision']} | "
            f"{d_pup:+.3f} | {d_conf:+.1f}% |"
        )
    # Highlight notable changes
    lines.append("")
    notable = []
    for t in WATCHLIST:
        if t in today_runs and t in prev_runs:
            td, pd_ = today_runs[t], prev_runs[t]
            if td["decision"] != pd_["decision"]:
                notable.append(f"🔄 **{t}**: {pd_['decision']} → {td['decision']}")
            d_conf = td["confidence"] - pd_["confidence"]
            if abs(d_conf) >= 10:
                notable.append(f"📊 **{t}**: confidence {'+' if d_conf > 0 else ''}{d_conf:.1f}% in 1 day")
            d_pup = td["probabilities"].get("up", 0) - pd_["probabilities"].get("up", 0)
            if abs(d_pup) >= 0.15:
                notable.append(f"🎯 **{t}**: p(up) shifted {d_pup:+.2f} ({pd_['probabilities'].get('up', 0):.2f} → {td['probabilities'].get('up', 0):.2f})")
    if notable:
        lines.append("### Notable changes (≥10% conf or ≥0.15 prob shift)")
        for n in notable:
            lines.append(f"- {n}")
    else:
        lines.append("*No notable changes — signal stability day.*")
elif prev_brief.exists():
    lines.append(f"\n## Delta vs yesterday\n")
    lines.append(f"Previous brief: `{prev_brief.relative_to(Path.home())}` (no decision log overlap; full re-run needed)")

BRIEF.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote brief to {BRIEF}")
PYEOF

# Weekday investor-master lens — appends §3.7 to the brief BEFORE public mirror
# so the public repo gets the enriched version.
# Weekday rotation: Mon=Buffett · Tue=Druckenmiller · Wed=Lynch · Thu=Soros · Fri=Burry
"$PY" "$HOME/.orallexa/markets/scripts/master-lens.py" 2>&1 | tail -5 || true

# Open in default viewer
open "$BRIEF_FILE"

echo "[$(date -u +%FT%TZ)] SpaceX daily brief written: $BRIEF_FILE"

# ─────────────────────────────────────────────────────────────────────
# Mirror brief to public repo + auto-commit
# (alex-jb/spacex-ipo-tracker — public daily research feed)
# ─────────────────────────────────────────────────────────────────────
PUBLIC_REPO="${PUBLIC_REPO:-$HOME/Desktop/spacex-ipo-tracker}"
if [ -d "$PUBLIC_REPO" ]; then
    cd "$PUBLIC_REPO" || exit 0
    # Pull BEFORE any local changes to avoid dirty-tree rebase noise
    git pull --rebase origin main --quiet 2>/dev/null || true
    cp "$BRIEF_FILE" "$PUBLIC_REPO/briefs/${DATE}.md"
    git add "briefs/${DATE}.md"
    if git diff --staged --quiet; then
        echo "[$(date -u +%FT%TZ)] no diff in public repo (already committed)"
    else
        git commit -m "brief: ${DATE} daily SpaceX-pure-play research" --quiet
        git push origin main --quiet 2>&1 | tail -1
        echo "[$(date -u +%FT%TZ)] published to alex-jb/spacex-ipo-tracker"
    fi
else
    echo "[$(date -u +%FT%TZ)] public repo not found at $PUBLIC_REPO — skipping mirror"
fi

exit 0
