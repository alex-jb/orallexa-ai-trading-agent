"""
engine/demo_data.py
──────────────────────────────────────────────────────────────────
Mock data for DEMO_MODE — lets the full UI run without API keys,
live market data, or any external dependencies.

Usage:
    DEMO_MODE=true python api_server.py
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timedelta

# ── Ticker universe ─────────────────────────────────────────────────────

DEMO_TICKERS = {
    "NVDA": {"name": "NVIDIA", "price": 142.50, "sector": "Technology"},
    "AAPL": {"name": "Apple", "price": 218.30, "sector": "Technology"},
    "TSLA": {"name": "Tesla", "price": 275.80, "sector": "Consumer Disc"},
    "MSFT": {"name": "Microsoft", "price": 432.15, "sector": "Technology"},
    "GOOG": {"name": "Alphabet", "price": 178.90, "sector": "Comm Services"},
    "AMZN": {"name": "Amazon", "price": 205.40, "sector": "Consumer Disc"},
    "META": {"name": "Meta", "price": 615.20, "sector": "Comm Services"},
    "AMD": {"name": "AMD", "price": 128.60, "sector": "Technology"},
    "PLTR": {"name": "Palantir", "price": 98.30, "sector": "Technology"},
    "COIN": {"name": "Coinbase", "price": 265.70, "sector": "Financials"},
    "SPY": {"name": "S&P 500 ETF", "price": 572.40, "sector": "Index"},
    "QQQ": {"name": "Nasdaq 100 ETF", "price": 498.10, "sector": "Index"},
}

_DEFAULT = {"name": "Unknown", "price": 100.0, "sector": "Other"}


def _ticker_info(ticker: str) -> dict:
    return DEMO_TICKERS.get(ticker.upper(), {**_DEFAULT, "name": ticker.upper()})


def _jitter(base: float, pct: float = 0.02) -> float:
    return round(base * (1 + random.uniform(-pct, pct)), 2)


# ── /api/analyze ────────────────────────────────────────────────────────

def mock_analyze(ticker: str, mode: str = "scalp", timeframe: str = "5m", context: str = "") -> dict:
    info = _ticker_info(ticker)
    decisions = ["BUY", "SELL", "WAIT"]
    weights = [0.4, 0.3, 0.3]
    decision = random.choices(decisions, weights)[0]

    confidence = round(random.uniform(62, 92), 1)
    signal_strength = round(random.uniform(55, 88), 1)
    risk_levels = {"BUY": "MEDIUM", "SELL": "HIGH", "WAIT": "LOW"}

    up = round(random.uniform(0.25, 0.65), 2)
    down = round(random.uniform(0.10, 0.40), 2)
    neutral = round(1 - up - down, 2)
    if decision == "BUY":
        up = max(up, 0.50)
        neutral = round(1 - up - down, 2)
    elif decision == "SELL":
        down = max(down, 0.40)
        neutral = round(1 - up - down, 2)

    reasoning = [
        f"RSI at {random.randint(28, 72)} — {'oversold bounce likely' if decision == 'BUY' else 'approaching resistance'}",
        f"Volume {random.uniform(1.2, 3.5):.1f}x average — institutional interest detected",
        f"MACD crossover {'bullish' if decision == 'BUY' else 'bearish'} on {timeframe} chart",
        f"Support at ${_jitter(info['price'] * 0.95)}, resistance at ${_jitter(info['price'] * 1.05)}",
        f"Sector momentum: {info['sector']} {'leading' if decision == 'BUY' else 'lagging'} today",
    ]

    rec_map = {
        "BUY": f"Enter {ticker} long near ${_jitter(info['price'])} with stop at ${_jitter(info['price'] * 0.97)}",
        "SELL": f"Consider short {ticker} below ${_jitter(info['price'] * 0.99)} — risk/reward favorable",
        "WAIT": f"No clear setup on {ticker} — wait for volume confirmation or key level test",
    }

    return {
        "decision": decision,
        "confidence": confidence,
        "risk_level": risk_levels[decision],
        "signal_strength": signal_strength,
        "probabilities": {"up": up, "neutral": neutral, "down": down},
        "reasoning": reasoning,
        "recommendation": rec_map[decision],
        "source": f"demo_{mode}",
    }


# ── /api/deep-analysis-stream (SSE steps) ──────────────────────────────

DEEP_STEPS = [
    ("Fetching market data", "获取市场数据"),
    ("Running technical analysis", "运行技术分析"),
    ("ML ensemble prediction", "ML 集成预测"),
    ("Multi-agent debate", "多智能体辩论"),
    ("Risk assessment", "风险评估"),
    ("Generating investment plan", "生成投资方案"),
    ("Compiling final report", "编译最终报告"),
]


def mock_deep_analysis(ticker: str) -> dict:
    """Returns the final 'done' payload for deep analysis."""
    info = _ticker_info(ticker)
    base = mock_analyze(ticker, mode="swing", timeframe="1d")
    price = info["price"]

    return {
        **base,
        "reports": {
            "market": f"{ticker} is trading at ${price:.2f}, up {random.uniform(-3, 5):.1f}% this week. "
                      f"The broader {info['sector']} sector shows {random.choice(['strength', 'rotation', 'consolidation'])}. "
                      f"Key support at ${_jitter(price * 0.93)}, resistance at ${_jitter(price * 1.08)}. "
                      f"52-week range: ${_jitter(price * 0.60)} – ${_jitter(price * 1.25)}.",
            "fundamentals": f"ML ensemble (RF + LR + XGB) signals {base['decision']} with {base['confidence']:.0f}% confidence. "
                           f"Feature importance: RSI (0.23), MACD (0.19), Volume ratio (0.17), BB width (0.14). "
                           f"Walk-forward Sharpe: {random.uniform(0.8, 2.1):.2f}. Win rate: {random.uniform(52, 68):.0f}%.",
            "news": f"Recent catalysts for {ticker}: {random.choice(['earnings beat expectations', 'new product launch', 'analyst upgrade', 'sector rotation inflow', 'institutional accumulation detected'])}. "
                    f"Sentiment score: {random.uniform(0.1, 0.8):.2f} (mostly {random.choice(['positive', 'mixed', 'cautiously optimistic'])}).",
        },
        "investment_plan": {
            "position_pct": round(random.uniform(3, 12), 1),
            "entry": round(price, 2),
            "stop_loss": round(price * random.uniform(0.94, 0.97), 2),
            "take_profit": round(price * random.uniform(1.05, 1.15), 2),
            "risk_reward": f"1:{random.uniform(1.5, 3.5):.1f}",
            "key_risks": [
                f"Sector rotation away from {info['sector']}",
                "Broader market correction (SPX below 5600)",
                f"Earnings miss or guidance cut for {ticker}",
            ],
            "plan_summary": f"{'Accumulate' if base['decision'] == 'BUY' else 'Reduce'} {ticker} with {round(random.uniform(3, 12), 1)}% portfolio allocation. "
                           f"Defined risk at ${_jitter(price * 0.95)} stop.",
        },
        "ml_models": [
            {"model": "RandomForest", "sharpe": round(random.uniform(0.9, 2.0), 2), "return": round(random.uniform(5, 25), 1), "win_rate": round(random.uniform(52, 68), 1), "trades": random.randint(40, 120)},
            {"model": "LogisticReg", "sharpe": round(random.uniform(0.7, 1.8), 2), "return": round(random.uniform(3, 20), 1), "win_rate": round(random.uniform(50, 65), 1), "trades": random.randint(30, 100)},
            {"model": "XGBoost", "sharpe": round(random.uniform(1.0, 2.5), 2), "return": round(random.uniform(8, 30), 1), "win_rate": round(random.uniform(55, 72), 1), "trades": random.randint(35, 110)},
        ],
        "summary": {
            "close": price,
            "change_pct": round(random.uniform(-3, 5), 2),
            "rsi": round(random.uniform(30, 70), 1),
            "volume_ratio": round(random.uniform(0.8, 2.5), 2),
        },
        "analysis_narrative": f"Our multi-agent analysis of {ticker} reveals a {base['decision'].lower()} bias with "
                             f"{base['confidence']:.0f}% confidence. The technical picture shows "
                             f"{'constructive momentum' if base['decision'] == 'BUY' else 'distribution pressure' if base['decision'] == 'SELL' else 'indecision'}. "
                             f"Three ML models converge on a {'positive' if base['decision'] == 'BUY' else 'cautious'} outlook. "
                             f"Key catalyst to watch: {random.choice(['upcoming earnings', 'Fed meeting impact', 'sector rotation dynamics', 'options expiration'])}.",
        "elapsed_seconds": round(random.uniform(8, 18), 1),
    }


# ── /api/news/{ticker} ─────────────────────────────────────────────────

_HEADLINES = [
    ("{ticker} Beats Q4 Estimates, Raises Full-Year Guidance", "bullish", 0.72),
    ("{ticker} CEO Announces $2B Buyback Program", "bullish", 0.55),
    ("Analysts Upgrade {ticker} to Overweight on AI Tailwinds", "bullish", 0.48),
    ("{ticker} Faces Regulatory Scrutiny Over Market Practices", "bearish", -0.45),
    ("{ticker} Revenue Misses Estimates Amid Slowing Demand", "bearish", -0.62),
    ("Options Market Signals Unusual Activity in {ticker}", "neutral", 0.05),
    ("{ticker} Expands Into New Market Segment", "bullish", 0.38),
    ("Institutional Holders Trim {ticker} Positions", "bearish", -0.33),
    ("{ticker} Partners With Major Cloud Provider", "bullish", 0.41),
    ("Short Interest in {ticker} Reaches 6-Month High", "bearish", -0.28),
]


def mock_news(ticker: str) -> dict:
    items = []
    selected = random.sample(_HEADLINES, min(6, len(_HEADLINES)))
    providers = ["Reuters", "Bloomberg", "CNBC", "MarketWatch", "Benzinga", "Yahoo Finance"]
    for headline_tpl, sentiment, score in selected:
        items.append({
            "title": headline_tpl.format(ticker=ticker),
            "sentiment": sentiment,
            "score": round(score + random.uniform(-0.1, 0.1), 3),
            "url": "",
            "summary": "",
            "provider": random.choice(providers),
        })
    return {"ticker": ticker, "items": items}


# ── /api/profile ────────────────────────────────────────────────────────

def mock_profile() -> dict:
    return {
        "style": random.choice(["Aggressive", "Balanced", "Conservative"]),
        "win_rate": f"{random.randint(55, 72)}%",
        "today": f"{random.randint(2, 8)} trades",
        "win_streak": random.randint(0, 5),
        "loss_streak": random.randint(0, 2),
        "patterns": [
            "Strongest on momentum breakouts",
            "Better performance in morning session",
            "Tends to overtrade during low-vol periods",
        ],
        "preferred_mode": "scalp",
    }


# ── /api/journal ────────────────────────────────────────────────────────

def mock_journal() -> dict:
    entries = []
    tickers = ["NVDA", "TSLA", "AAPL", "AMD", "META"]
    modes = ["scalp", "intraday", "swing"]
    decisions = ["BUY", "SELL", "WAIT"]
    now = datetime.now()
    for i in range(5):
        entries.append({
            "ticker": random.choice(tickers),
            "mode": random.choice(modes),
            "decision": random.choice(decisions),
            "timestamp": (now - timedelta(hours=random.randint(1, 48))).isoformat(),
        })
    return {"entries": entries}


# ── /api/breaking-signals ──────────────────────────────────────────────

def mock_breaking_signals() -> dict:
    signals = []
    types = [
        ("volume_spike", "Volume spike detected — {ratio:.0f}x average"),
        ("sentiment_shift", "Sentiment flipped from {prev} to {new}"),
        ("price_breakout", "Price broke {direction} key level ${level:.2f}"),
    ]
    tickers = ["NVDA", "TSLA", "PLTR", "COIN", "AMD"]
    now = datetime.now()

    for i in range(random.randint(2, 4)):
        sig_type, msg_tpl = random.choice(types)
        tk = random.choice(tickers)
        info = _ticker_info(tk)

        if sig_type == "volume_spike":
            msg = msg_tpl.format(ratio=random.uniform(2, 5))
        elif sig_type == "sentiment_shift":
            msg = msg_tpl.format(prev=random.choice(["bearish", "neutral"]), new=random.choice(["bullish", "neutral"]))
        else:
            msg = msg_tpl.format(direction=random.choice(["above", "below"]), level=_jitter(info["price"]))

        signals.append({
            "type": sig_type,
            "severity": random.choice(["high", "medium"]),
            "ticker": tk,
            "timestamp": (now - timedelta(minutes=random.randint(5, 180))).isoformat(),
            "message": msg,
            "direction": random.choice(["bullish", "bearish"]),
        })
    return {"signals": signals}


# ── /api/live/{ticker} ─────────────────────────────────────────────────

def mock_live(ticker: str) -> dict:
    info = _ticker_info(ticker)
    price = _jitter(info["price"])
    change_pct = round(random.uniform(-3, 4), 2)
    prev_close = round(price / (1 + change_pct / 100), 2)
    return {
        "ticker": ticker.upper(),
        "price": price,
        "change_pct": change_pct,
        "prev_close": prev_close,
        "high": round(price * random.uniform(1.005, 1.025), 2),
        "low": round(price * random.uniform(0.975, 0.995), 2),
        "volume": random.randint(5_000_000, 80_000_000),
        "last_signal": {
            "decision": random.choice(["BUY", "SELL", "WAIT"]),
            "confidence": round(random.uniform(60, 90), 1),
            "signal_strength": round(random.uniform(50, 85), 1),
            "risk_level": random.choice(["LOW", "MEDIUM", "HIGH"]),
            "timestamp": datetime.now().isoformat(),
        },
        "timestamp": datetime.now().isoformat(),
    }


# ── /api/chart-analysis ────────────────────────────────────────────────

def mock_chart_analysis(ticker: str, timeframe: str = "1h") -> dict:
    base = mock_analyze(ticker, mode="scalp", timeframe=timeframe)
    info = _ticker_info(ticker)
    price = info["price"]
    return {
        **base,
        "chart_insight": {
            "trend": random.choice(["Uptrend — higher highs and higher lows", "Downtrend — lower highs confirmed", "Range-bound between key levels"]),
            "setup": random.choice(["Bull flag forming on the 1H", "Double bottom at support", "Head & shoulders pattern developing", "Breakout above descending trendline"]),
            "levels": f"Support: ${_jitter(price * 0.95)} / ${_jitter(price * 0.90)} | Resistance: ${_jitter(price * 1.05)} / ${_jitter(price * 1.10)}",
            "summary": f"{ticker} showing {'constructive' if base['decision'] == 'BUY' else 'distribution'} pattern on {timeframe}. "
                       f"Volume {'confirms' if random.random() > 0.4 else 'does not confirm'} the move.",
        },
    }


# ── /api/watchlist-scan ─────────────────────────────────────────────────

def mock_watchlist_scan(tickers: list[str]) -> dict:
    results = []
    for tk in tickers[:10]:
        info = _ticker_info(tk)
        d = mock_analyze(tk)
        results.append({
            "ticker": tk.upper(),
            "price": _jitter(info["price"]),
            "change_pct": round(random.uniform(-4, 6), 2),
            "decision": d["decision"],
            "confidence": d["confidence"],
            "signal_strength": d["signal_strength"],
            "risk_level": d["risk_level"],
            "probabilities": d["probabilities"],
            "recommendation": d["recommendation"],
            "error": None,
        })
    results.sort(key=lambda x: x["signal_strength"], reverse=True)
    return {"tickers": results}


# ── /api/daily-intel ────────────────────────────────────────────────────

def mock_daily_intel() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()

    gainers = [
        {"ticker": "NVDA", "price": 142.50, "change_pct": 5.2, "volume": 68_000_000, "volume_ratio": 2.3},
        {"ticker": "PLTR", "price": 98.30, "change_pct": 4.1, "volume": 45_000_000, "volume_ratio": 1.8},
        {"ticker": "COIN", "price": 265.70, "change_pct": 3.8, "volume": 22_000_000, "volume_ratio": 2.1},
        {"ticker": "AMD", "price": 128.60, "change_pct": 2.9, "volume": 38_000_000, "volume_ratio": 1.5},
        {"ticker": "TSLA", "price": 275.80, "change_pct": 2.4, "volume": 55_000_000, "volume_ratio": 1.3},
    ]
    losers = [
        {"ticker": "META", "price": 615.20, "change_pct": -2.8, "volume": 30_000_000, "volume_ratio": 1.6},
        {"ticker": "GOOG", "price": 178.90, "change_pct": -1.9, "volume": 25_000_000, "volume_ratio": 1.2},
        {"ticker": "AMZN", "price": 205.40, "change_pct": -1.5, "volume": 28_000_000, "volume_ratio": 1.1},
        {"ticker": "MSFT", "price": 432.15, "change_pct": -0.8, "volume": 20_000_000, "volume_ratio": 0.9},
    ]
    spikes = [
        {"ticker": "NVDA", "price": 142.50, "change_pct": 5.2, "volume_ratio": 2.3},
        {"ticker": "COIN", "price": 265.70, "change_pct": 3.8, "volume_ratio": 2.1},
        {"ticker": "PLTR", "price": 98.30, "change_pct": 4.1, "volume_ratio": 1.8},
    ]
    sectors = [
        {"sector": "Semiconductors", "etf": "SOXX", "change_pct": 3.2},
        {"sector": "Technology", "etf": "XLK", "change_pct": 2.1},
        {"sector": "Comm Services", "etf": "XLC", "change_pct": 0.8},
        {"sector": "Financials", "etf": "XLF", "change_pct": 0.5},
        {"sector": "Energy", "etf": "XLE", "change_pct": 0.2},
        {"sector": "Industrials", "etf": "XLI", "change_pct": -0.1},
        {"sector": "Healthcare", "etf": "XLV", "change_pct": -0.4},
        {"sector": "Consumer Disc", "etf": "XLY", "change_pct": -0.6},
        {"sector": "Consumer Staples", "etf": "XLP", "change_pct": -0.9},
        {"sector": "Real Estate", "etf": "XLRE", "change_pct": -1.2},
        {"sector": "Utilities", "etf": "XLU", "change_pct": -1.5},
    ]
    headlines = [
        {"title": "NVIDIA Datacenter Revenue Surges 40% as AI Demand Accelerates", "ticker": "NVDA", "sentiment": "bullish", "score": 0.78, "url": "", "provider": "Reuters"},
        {"title": "Palantir Wins $500M Government Contract for AI Platform", "ticker": "PLTR", "sentiment": "bullish", "score": 0.65, "url": "", "provider": "Bloomberg"},
        {"title": "Bitcoin Breaks $90K as Institutional Inflows Hit Record", "ticker": "COIN", "sentiment": "bullish", "score": 0.58, "url": "", "provider": "CNBC"},
        {"title": "Meta Faces Antitrust Lawsuit Over Social Media Monopoly", "ticker": "META", "sentiment": "bearish", "score": -0.52, "url": "", "provider": "WSJ"},
        {"title": "Fed Officials Signal Patience on Rate Cuts Amid Sticky Inflation", "ticker": "SPY", "sentiment": "bearish", "score": -0.35, "url": "", "provider": "MarketWatch"},
        {"title": "AMD Launches Next-Gen AI Chips to Challenge NVIDIA Dominance", "ticker": "AMD", "sentiment": "bullish", "score": 0.42, "url": "", "provider": "TechCrunch"},
        {"title": "Tesla Deliveries Beat Estimates Despite Price War Concerns", "ticker": "TSLA", "sentiment": "bullish", "score": 0.38, "url": "", "provider": "Bloomberg"},
        {"title": "Options Market Signals Unusual Bullish Positioning in Semis", "ticker": "SOXX", "sentiment": "bullish", "score": 0.30, "url": "", "provider": "Benzinga"},
    ]
    ai_picks = [
        {"ticker": "NVDA", "direction": "bullish", "reason": "AI capex cycle accelerating — datacenter backlog through 2027", "catalyst": "Earnings report next week"},
        {"ticker": "PLTR", "direction": "bullish", "reason": "Government AI spending inflection + commercial momentum", "catalyst": "$500M contract confirmation"},
        {"ticker": "META", "direction": "bearish", "reason": "Antitrust overhang caps upside — rotation into pure AI plays", "catalyst": "Court hearing date announcement"},
        {"ticker": "COIN", "direction": "bullish", "reason": "BTC $90K breakout drives exchange volume surge", "catalyst": "ETF flow data release"},
    ]
    thread = [
        f"🚨 RISK-ON — {today}\n\n$NVDA ripping +5.2% on datacenter demand. Semis leading everything. Money pouring into AI. 👇",
        "🟢 $NVDA +5.2% — AI capex cycle is real\n🟢 $PLTR +4.1% — $500M gov contract\n🟢 $COIN +3.8% — BTC $90K breakout\n🔴 $META -2.8% — antitrust overhang",
        "🐳 UNUSUAL ACTIVITY\n\n$NVDA volume 2.3x average\n$COIN volume 2.1x average\n\nInstitutional money is moving into AI + crypto. Smart money positioning.",
        "📊 SECTOR WATCH\n\n🟢 Semis +3.2% — clear leader\n🟢 Tech +2.1%\n🔴 Utilities -1.5%\n🔴 Real Estate -1.2%\n\nClassic risk-on rotation. Growth over safety.",
        "🤖 AI PICKS\n\n$NVDA — datacenter backlog through 2027\n$PLTR — gov AI spend inflection\n$COIN — BTC breakout = volume surge\n\nContrarian: $META short on antitrust",
        f"⚠️ RISK: Fed patience on rate cuts. If CPI comes in hot, this rally reverses fast.\n\nWatch SPX 5700 support.\n\n#stocks #trading #fintwit",
    ]

    return {
        "date": today,
        "generated_at": now.isoformat(),
        "market_mood": "Risk-On",
        "summary": (
            "RISK-ON\n\n"
            "Money is flooding into semiconductors and AI plays today, with NVIDIA leading the charge at +5.2% "
            "on surging datacenter revenue. The AI capex cycle narrative just got another data point — and the "
            "market is buying it aggressively.\n\n"
            "Two stories dominate: First, NVDA's datacenter backlog is reportedly filled through 2027, which "
            "triggered a sector-wide rally with SOXX up 3.2%. Second, Bitcoin smashing through $90K has lit up "
            "the crypto ecosystem — COIN is riding 2.1x normal volume as institutional ETF flows hit records.\n\n"
            "The losers tell the story too: META is down 2.8% on fresh antitrust concerns, and the rotation out "
            "of defensive sectors (Utilities -1.5%, Real Estate -1.2%) confirms this is a genuine risk-on move, "
            "not just a tech squeeze.\n\n"
            "The #1 risk everyone's ignoring: the Fed. Officials signaled patience on cuts today amid sticky "
            "inflation. If next week's CPI prints hot, this entire rally reverses. Watch SPX 5700 as the floor."
        ),
        "gainers": gainers,
        "losers": losers,
        "volume_spikes": spikes,
        "sectors": sectors,
        "headlines": headlines,
        "ai_picks": ai_picks,
        "orallexa_thread": thread,
        "social_posts": {
            "movers": f"🔥 MOVERS — {today}\n\n🟢 $NVDA +5.2%\n🟢 $PLTR +4.1%\n🟢 $COIN +3.8%\n🔴 $META -2.8%\n🔴 $GOOG -1.9%\n\nSemis eating. #stocks #trading",
            "sectors": f"📊 SECTOR WATCH\n\n🟢 Semis +3.2%, Tech +2.1%\n🔴 Utilities -1.5%, REITs -1.2%\n\nClassic risk-on rotation. Growth > safety. #trading",
            "picks": "🤖 AI PICKS\n\n$NVDA — datacenter backlog through 2027\n$PLTR — gov AI inflection\n$COIN — BTC breakout volume\n\nContrarian: $META short 👀\n\n#fintwit",
            "brief": f"☀️ Risk-on day — $NVDA +5.2% leads as AI capex accelerates. Semis +3.2%. Watch the Fed — CPI miss kills this rally. #stocks #trading",
            "volume": "🐳 UNUSUAL ACTIVITY\n\n$NVDA — 2.3x avg volume\n$COIN — 2.1x avg volume\n$PLTR — 1.8x avg volume\n\nSmart money moving. 👀",
        },
        "earnings_watchlist": [
            {"ticker": "NVDA", "date": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
             "days_until": 3, "eps_estimate": 1.77, "pead_drift": 2.3,
             "positive_rate": 0.75, "narrative": "NVDA reports in 3 days. PEAD history (8 events): avg +2.3% 5d drift, 75% positive → bullish bias."},
            {"ticker": "PLTR", "date": (now + timedelta(days=6)).strftime("%Y-%m-%d"),
             "days_until": 6, "eps_estimate": 0.15, "pead_drift": -1.1,
             "positive_rate": 0.40, "narrative": "PLTR reports in 6 days. PEAD history (5 events): avg -1.1% 5d drift, 40% positive → bearish bias."},
            {"ticker": "AMD", "date": (now + timedelta(days=12)).strftime("%Y-%m-%d"),
             "days_until": 12, "eps_estimate": 0.92, "pead_drift": 0.4,
             "positive_rate": 0.55, "narrative": "AMD reports in 12 days. PEAD history (6 events): avg +0.4% 5d drift, 55% positive → neutral bias."},
        ],
    }
