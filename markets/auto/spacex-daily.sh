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
    if setup == "Trend" and (confidence >= 65 or _FTD_ACTIVE):
        sizing = "Full" + ("🔥" if _FTD_ACTIVE else "")
    elif setup in ("Trend", "MR-bounce") and confidence >= 50:
        sizing = "Half" + ("🔥" if _FTD_ACTIVE and setup == "MR-bounce" else "")
    elif decision == "BUY":
        sizing = "Tiny"
    elif setup == "Breakdown" and confidence >= 50:
        sizing = "Short-half"
    else:
        sizing = "Pass"

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
lines.append("")
lines.append("## Ranked by signal direction (p_up - p_down)\n")
lines.append("| Rank | Sector | Ticker | Decision | Conf | Setup | Sizing | Price | RSI | Stop | Δ probs |")
lines.append("|---|---|---|---|---|---|---|---|---|---|---|")

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
    lines.append(
        f"| {i} | {emoji} | **{d['ticker']}** | {d['decision']} | {d['confidence']}% | "
        f"{setup} | {sizing} | \${price} | {rsi} | {stop} | {delta_str} |"
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
