"""
engine/daily_intel.py
──────────────────────────────────────────────────────────────────
Daily Market Intelligence — social-grade morning brief generator.

Fetches top movers (including volume spike detection), sector heatmap,
news headlines, then uses Claude Sonnet for high-quality summary,
AI picks, and a ready-to-post Orallexa thread for social media.

Caches result per day to memory_data/daily_intel.json.

Usage:
    from engine.daily_intel import generate_daily_intel
    report = generate_daily_intel()           # cached if today already generated
    report = generate_daily_intel(force=True)  # force regenerate
"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).parent.parent / "memory_data" / "daily_intel.json"

# ── Watchlist (expanded) ─────────────────────────────────────────────────────

SCAN_TICKERS = [
    # Mega-cap tech
    "NVDA", "AAPL", "TSLA", "MSFT", "GOOG", "AMZN", "META", "AMD", "TSM", "NFLX",
    # Growth / AI / Semis
    "PLTR", "ARM", "AVGO", "CRM", "ORCL", "SNOW", "SQ", "COIN", "SMCI", "MRVL",
    # Finance / Energy / Health
    "JPM", "GS", "V", "XOM", "CVX", "UNH", "LLY", "MRNA",
    # Indices / ETFs
    "SPY", "QQQ", "IWM", "DIA", "SOXX", "GLD", "TLT",
    # Crypto
    "BTC-USD", "ETH-USD", "SOL-USD",
]

# Extra tickers to scan for volume spikes (broader net)
VOLUME_SCAN_EXTRA = [
    "RIVN", "LCID", "NIO", "BABA", "JD", "PDD", "SE",
    "ROKU", "SHOP", "DKNG", "MARA", "RIOT", "HOOD",
    "SOFI", "AFRM", "UPST", "PATH", "IONQ", "RGTI",
]

SECTOR_ETFS = [
    ("Technology", "XLK"), ("Financials", "XLF"), ("Energy", "XLE"),
    ("Healthcare", "XLV"), ("Industrials", "XLI"), ("Comm Services", "XLC"),
    ("Consumer Disc", "XLY"), ("Consumer Staples", "XLP"),
    ("Materials", "XLB"), ("Real Estate", "XLRE"), ("Utilities", "XLU"),
    ("Semiconductors", "SOXX"), ("Clean Energy", "ICLN"),
]


# ── Step 1: Top Movers + Volume Spike Detection ─────────────────────────────

def _fetch_price_with_volume(ticker: str) -> Optional[dict]:
    """Fetch price, change, volume, and avg volume for spike detection."""
    import yfinance as yf
    try:
        tk = yf.Ticker(ticker)
        info = tk.fast_info
        price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        prev = getattr(info, "previous_close", None)
        if not price or price <= 0:
            return None
        change_pct = round((price - prev) / prev * 100, 2) if prev and prev > 0 else 0.0
        volume = int(getattr(info, "last_volume", 0) or 0)

        # Get 20-day average volume for spike detection
        avg_volume = 0
        try:
            hist = tk.history(period="1mo", interval="1d")
            if hist is not None and len(hist) >= 5:
                avg_volume = int(hist["Volume"].tail(20).mean())
        except Exception:
            pass

        volume_ratio = round(volume / max(avg_volume, 1), 2) if avg_volume > 0 else 0.0

        return {
            "ticker": ticker,
            "price": round(float(price), 2),
            "change_pct": change_pct,
            "volume": volume,
            "avg_volume": avg_volume,
            "volume_ratio": volume_ratio,
            "volume_spike": volume_ratio >= 2.0,  # 2x average = spike
        }
    except Exception as e:
        logger.debug("Price fetch failed for %s: %s", ticker, e)
        return None


def _fetch_top_movers() -> tuple[list[dict], list[dict], list[dict]]:
    """Parallel fetch all tickers, return (gainers, losers, volume_spikes)."""
    all_tickers = list(set(SCAN_TICKERS + VOLUME_SCAN_EXTRA))
    results = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_price_with_volume, tk): tk for tk in all_tickers}
        for f in as_completed(futures):
            r = f.result()
            if r:
                results.append(r)

    # Gainers / Losers
    results.sort(key=lambda x: x["change_pct"], reverse=True)
    gainers = [r for r in results if r["change_pct"] > 0.5][:8]
    losers = [r for r in results if r["change_pct"] < -0.5]
    losers.sort(key=lambda x: x["change_pct"])
    losers = losers[:8]

    # Volume spikes (2x+ average, regardless of direction)
    spikes = [r for r in results if r.get("volume_spike")]
    spikes.sort(key=lambda x: x["volume_ratio"], reverse=True)
    spikes = spikes[:8]

    return gainers, losers, spikes


# ── Step 2: Sector Heatmap ───────────────────────────────────────────────────

def _fetch_sectors() -> list[dict]:
    """Fetch sector ETF performance."""
    sectors = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_price_with_volume, etf): (name, etf) for name, etf in SECTOR_ETFS}
        for f in as_completed(futures):
            name, etf = futures[f]
            r = f.result()
            if r:
                sectors.append({
                    "sector": name,
                    "etf": etf,
                    "change_pct": r["change_pct"],
                })
    sectors.sort(key=lambda x: x["change_pct"], reverse=True)
    return sectors


# ── Step 3: News Scan ────────────────────────────────────────────────────────

def _fetch_headlines(tickers: list[str]) -> list[dict]:
    """Fetch and score headlines with weighted ranking.

    Ranking formula: weighted_score = |sentiment| * recency_weight * provider_tier
    - Recency: exponential decay, newer articles score higher
    - Provider tier: premium sources (Bloomberg, Reuters) get 1.5x multiplier
    """
    from skills.news import NewsSkill
    from datetime import datetime, timezone

    try:
        from engine.sentiment import score_text
    except ImportError:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        _sia = SentimentIntensityAnalyzer()
        def score_text(text):
            sc = _sia.polarity_scores(text)
            return {"compound": sc["compound"], "label": "positive" if sc["compound"] > 0.1 else "negative" if sc["compound"] < -0.1 else "neutral"}

    # Provider credibility tiers
    _TIER1 = {"bloomberg", "reuters", "wsj", "wall street journal", "financial times",
              "cnbc", "barron's", "marketwatch", "the wall street journal"}
    _TIER2 = {"yahoo finance", "seeking alpha", "benzinga", "investopedia",
              "motley fool", "tipranks", "zacks", "thestreet"}

    def _provider_weight(provider: str) -> float:
        low = provider.lower()
        if any(t in low for t in _TIER1):
            return 1.5
        if any(t in low for t in _TIER2):
            return 1.2
        return 1.0

    def _recency_weight(pub_time: str) -> float:
        """Exponential decay: 1.0 for now, 0.5 for 12h ago, 0.25 for 24h ago."""
        try:
            if pub_time:
                from dateutil.parser import parse as dateparse
                dt = dateparse(pub_time)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                hours_ago = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                return max(0.2, 0.5 ** (hours_ago / 12))
        except Exception:
            pass
        return 0.7  # default if no timestamp

    # Opt-in: multi-platform RSS aggregation (Google News + Yahoo Finance)
    # alongside the existing yfinance-backed NewsSkill path. When enabled,
    # items are merged per-ticker and deduped before scoring.
    use_rss = os.environ.get("DAILY_INTEL_USE_RSS", "").lower() in ("1", "true", "yes")

    def _collect_per_ticker(tk: str) -> list[dict]:
        items: list[dict] = []
        try:
            ys = NewsSkill(tk).fetch_news(limit=4)
            for it in ys:
                items.append({
                    "title": it.get("title", ""),
                    "url": it.get("link", ""),
                    "provider": it.get("publisher", ""),
                    "published": it.get("published", "") or it.get("providerPublishTime", ""),
                    "source": "yfinance",
                })
        except Exception as e:
            logger.debug("yfinance news fetch failed for %s: %s", tk, e)
        if use_rss:
            try:
                from engine.news_aggregator import fetch_aggregated_news
                items.extend(fetch_aggregated_news(tk, limit=6))
            except Exception as e:
                logger.debug("RSS aggregator failed for %s: %s", tk, e)
        return items

    def _dedup_merge(items: list[dict]) -> list[dict]:
        if not use_rss:
            return items  # single-source path: simple title-set dedup handled below
        try:
            from engine.news_aggregator import _dedupe_and_rank
            return _dedupe_and_rank(items, limit=len(items))
        except Exception:
            return items

    all_headlines = []
    seen_titles = set()
    for tk in tickers:
        try:
            merged = _dedup_merge(_collect_per_ticker(tk))
            for item in merged:
                title = item.get("title", "")
                if not title or len(title) < 15 or title in seen_titles:
                    continue
                seen_titles.add(title)
                scored = score_text(title)
                compound = scored.get("compound", 0)
                sentiment = "bullish" if compound > 0.1 else "bearish" if compound < -0.1 else "neutral"
                provider = item.get("provider", "")
                pub_time = item.get("published", "")

                # Weighted ranking score
                recency = _recency_weight(pub_time)
                tier = _provider_weight(provider)
                weighted = abs(compound) * recency * tier

                all_headlines.append({
                    "title": title,
                    "ticker": tk,
                    "sentiment": sentiment,
                    "score": round(compound, 3),
                    "weighted_score": round(weighted, 4),
                    "url": item.get("url", ""),
                    "provider": provider,
                })
        except Exception as e:
            logger.debug("News fetch failed for %s: %s", tk, e)

    all_headlines.sort(key=lambda x: x.get("weighted_score", abs(x["score"])), reverse=True)
    return all_headlines[:20]


# ── Step 4: AI Summary (DEEP_MODEL — Sonnet) ────────────────────────────────

def _generate_summary(
    gainers: list[dict],
    losers: list[dict],
    spikes: list[dict],
    sectors: list[dict],
    headlines: list[dict],
) -> tuple[str, str]:
    """Generate high-quality morning brief via Sonnet. Returns (summary, mood)."""
    import llm.claude_client as cc
    from llm.claude_client import get_client, _extract_text
    from llm.call_logger import logged_create

    gainers_str = "\n".join(f"  {g['ticker']} +{g['change_pct']:.1f}% (${g['price']}, vol {g['volume_ratio']:.1f}x avg)" for g in gainers[:6])
    losers_str = "\n".join(f"  {l['ticker']} {l['change_pct']:.1f}% (${l['price']}, vol {l['volume_ratio']:.1f}x avg)" for l in losers[:6])
    spikes_str = "\n".join(f"  {s['ticker']} {s['change_pct']:+.1f}% — volume {s['volume_ratio']:.1f}x average" for s in spikes[:5])
    sectors_str = "\n".join(f"  {s['sector']}: {s['change_pct']:+.1f}%" for s in sectors)
    headlines_str = "\n".join(f"  [{h['sentiment'].upper()}] {h['ticker']}: {h['title']}" for h in headlines[:12])

    prompt = f"""You are a sharp, opinionated financial market analyst writing a daily morning brief that will be read by active traders and posted on social media.

TODAY'S MARKET DATA ({datetime.now().strftime('%B %d, %Y')}):

TOP GAINERS:
{gainers_str or "  None notable"}

TOP LOSERS:
{losers_str or "  None notable"}

VOLUME SPIKES (unusual activity):
{spikes_str or "  None detected"}

SECTOR PERFORMANCE:
{sectors_str or "  No data"}

KEY HEADLINES:
{headlines_str or "  No headlines"}

Write a compelling morning brief (300-400 words):
1. Start with the market mood in one punchy sentence (is money flowing into risk or hiding in safety?)
2. Name the 2-3 stories that matter most today — be specific about WHY they're moving
3. Highlight any volume spikes as potential institutional activity or catalysts brewing
4. Identify the dominant sector rotation theme
5. Close with the #1 risk to watch and a concrete level/event that would change the picture

IMPORTANT: Start your first line with exactly one of: RISK-ON, RISK-OFF, or MIXED

Write with conviction. Use specific numbers. No generic filler like "markets are volatile" — say something only today's data supports."""

    try:
        client = get_client()
        response, _ = logged_create(
            client, request_type="daily_intel_summary",
            model=cc.DEEP_MODEL, max_tokens=800, temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(response)
        first_line = text.strip().split("\n")[0].upper()
        if "RISK-ON" in first_line:
            mood = "Risk-On"
        elif "RISK-OFF" in first_line:
            mood = "Risk-Off"
        else:
            mood = "Mixed"
        return text, mood
    except Exception as e:
        logger.warning("AI summary failed: %s", e)
        avg = sum(s["change_pct"] for s in sectors) / max(len(sectors), 1) if sectors else 0
        mood = "Risk-On" if avg > 0.3 else "Risk-Off" if avg < -0.3 else "Mixed"
        g_str = ", ".join(f"{g['ticker']} +{g['change_pct']:.1f}%" for g in gainers[:3])
        return f"AI summary unavailable. Mood: {mood}. Top: {g_str}.", mood


# ── Step 4b: Pre-Market Playbook (structured analysis) ───────────────────────

def _generate_playbook(
    summary: str,
    mood: str,
    gainers: list[dict],
    losers: list[dict],
    spikes: list[dict],
    sectors: list[dict],
    headlines: list[dict],
) -> dict:
    """Generate structured pre-market playbook (EN/ZH bilingual)."""
    import llm.claude_client as cc
    from llm.claude_client import get_client, _extract_text
    from llm.call_logger import logged_create

    top_sectors = ", ".join(f"{s['sector']} {s['change_pct']:+.1f}%" for s in sectors[:3])
    worst_sectors = ", ".join(f"{s['sector']} {s['change_pct']:+.1f}%" for s in sectors[-3:])
    top_movers = ", ".join(f"${g['ticker']} {g['change_pct']:+.1f}%" for g in (gainers[:3] + losers[:3]))
    spike_str = ", ".join(f"${s['ticker']} {s['volume_ratio']:.0f}x" for s in spikes[:3]) or "None"
    headlines_str = "\n".join(f"  {h['ticker']}: {h['title']} ({h['sentiment']})" for h in headlines[:6])

    prompt = f"""You are a senior trading strategist writing a structured pre-market playbook.
Output ONLY valid JSON (no markdown):

{{
  "tone_en": "One punchy sentence: today's dominant theme and direction (e.g. 'AI infrastructure rotation accelerates as Shenzhen policy catalyzes domestic supply chain plays')",
  "tone_zh": "Same in Chinese (一句话总定调)",
  "environment": {{
    "risk_level": "high|mid|low",
    "index_bias": "bullish|neutral|bearish (one sentence why)",
    "index_bias_zh": "Same in Chinese",
    "sentiment": "One sentence on market emotion/positioning",
    "sentiment_zh": "Same in Chinese",
    "position_advice": "One sentence: sizing/timing guidance (e.g. 'Scale in on confirmed breakouts, avoid chasing gaps')",
    "position_advice_zh": "Same in Chinese"
  }},
  "main_theme_en": "Today's #1 sector/narrative to focus on, with 2-3 specific tickers and why (50 words max)",
  "main_theme_zh": "Same in Chinese",
  "secondary_themes_en": ["Theme 2 with tickers", "Theme 3 with tickers"],
  "secondary_themes_zh": ["Same in Chinese", "Same in Chinese"],
  "biggest_risk_en": "The ONE thing that could blow up today's thesis (be specific: a level, an event, a reversal pattern)",
  "biggest_risk_zh": "Same in Chinese",
  "biggest_opportunity_en": "The ONE asymmetric setup worth watching (specific ticker, level, catalyst)",
  "biggest_opportunity_zh": "Same in Chinese"
}}

TODAY'S DATA:
Mood: {mood}
Top Sectors: {top_sectors}
Worst Sectors: {worst_sectors}
Key Movers: {top_movers}
Volume Spikes: {spike_str}
Headlines:
{headlines_str}
Morning Brief:
{summary[:400]}

Be opinionated and specific. Traders want alpha, not generic commentary."""

    try:
        client = get_client()
        response, _ = logged_create(
            client, request_type="daily_intel_playbook",
            model=cc.DEEP_MODEL, max_tokens=800, temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        return json.loads(text)
    except Exception as e:
        logger.warning("Playbook generation failed: %s", e)
        return {
            "tone_en": f"Market mood: {mood}. Key movers: {top_movers}.",
            "tone_zh": f"市场情绪: {mood}。主要变动: {top_movers}。",
            "environment": {
                "risk_level": "mid",
                "index_bias": "Neutral — insufficient data", "index_bias_zh": "中性 — 数据不足",
                "sentiment": "Mixed signals", "sentiment_zh": "信号混合",
                "position_advice": "Wait for confirmation", "position_advice_zh": "等待确认",
            },
            "main_theme_en": "Analysis unavailable", "main_theme_zh": "分析暂不可用",
            "secondary_themes_en": [], "secondary_themes_zh": [],
            "biggest_risk_en": "N/A", "biggest_risk_zh": "暂无",
            "biggest_opportunity_en": "N/A", "biggest_opportunity_zh": "暂无",
        }


# ── Step 5: AI Picks (DEEP_MODEL) ────────────────────────────────────────────

def _generate_picks(
    gainers: list[dict],
    losers: list[dict],
    spikes: list[dict],
    headlines: list[dict],
) -> list[dict]:
    """Generate 3-5 'worth watching' picks via Sonnet."""
    import llm.claude_client as cc
    from llm.claude_client import get_client, _extract_text
    from llm.call_logger import logged_create

    movers_str = "\n".join(
        f"  {m['ticker']} {m['change_pct']:+.1f}% (vol {m['volume_ratio']:.1f}x)"
        for m in (gainers[:5] + losers[:5])
    )
    spikes_str = "\n".join(f"  {s['ticker']} vol {s['volume_ratio']:.1f}x, {s['change_pct']:+.1f}%" for s in spikes[:5])
    headlines_str = "\n".join(f"  {h['ticker']}: {h['title']} ({h['sentiment']})" for h in headlines[:8])

    # Build price context for predictions
    price_context = "\n".join(
        f"  {m['ticker']} current: ${m['price']:.2f} ({m['change_pct']:+.1f}%)"
        for m in (gainers[:5] + losers[:5]) if m.get("price")
    )

    prompt = f"""You are a quantitative trading analyst selecting the top 3-5 stocks worth watching today.
Give DIRECT, OPINIONATED predictions with specific price targets.

Movers:
{movers_str}
Current Prices:
{price_context}
Volume Spikes:
{spikes_str or "  None"}
Headlines:
{headlines_str}

Output ONLY valid JSON array (no markdown):
[
  {{"ticker": "NVDA", "direction": "bullish", "reason": "compelling thesis", "catalyst": "specific event", "target_price": 150.0, "stop_loss": 140.0, "timeframe": "1-2 weeks", "conviction": "high"}}
]

Rules:
- direction: "bullish", "bearish", or "neutral"
- reason: max 30 words, be DIRECT and opinionated. Say "likely to break $150 resistance" not "shows momentum"
- catalyst: the ONE thing driving the move
- target_price: specific dollar price target based on technical levels (resistance/support)
- stop_loss: where you'd cut the position (support level or % below entry)
- timeframe: "today", "this week", "1-2 weeks", or "1 month"
- conviction: "high", "medium", or "low"
- Include at least 1 contrarian pick (loser bounce or overextended gainer)
- Volume spikes = institutional money moving, flag these prominently
- Be bold. Traders want alpha, not hedging language."""

    try:
        client = get_client()
        response, _ = logged_create(
            client, request_type="daily_intel_picks",
            model=cc.DEEP_MODEL, max_tokens=500, temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        return json.loads(text)[:5]
    except Exception as e:
        logger.warning("AI picks failed: %s", e)
        return [
            {"ticker": g["ticker"], "direction": "bullish",
             "reason": f"Up {g['change_pct']:.1f}% on {g['volume_ratio']:.1f}x volume", "catalyst": "Momentum"}
            for g in gainers[:3]
        ]


# ── Step 6: Orallexa Thread (DEEP_MODEL) ─────────────────────────────────────

def _generate_social_posts(
    summary: str,
    mood: str,
    gainers: list[dict],
    losers: list[dict],
    spikes: list[dict],
    picks: list[dict],
    sectors: list[dict],
    headlines: list[dict],
) -> dict:
    """
    Generate per-section social posts + a full thread.
    Each section gets its own ready-to-copy post for Twitter/X, LinkedIn, etc.

    Returns dict:
      "thread": [list of 6-7 posts]
      "movers_post": str   — top movers as a standalone post
      "sectors_post": str  — sector rotation post
      "picks_post": str    — AI picks post
      "brief_post": str    — morning brief condensed post
      "volume_post": str   — volume spike alert post
    """
    import llm.claude_client as cc
    from llm.claude_client import get_client, _extract_text
    from llm.call_logger import logged_create

    date_str = datetime.now().strftime("%B %d")
    gainers_str = ", ".join(f"${g['ticker']} +{g['change_pct']:.1f}%" for g in gainers[:4])
    losers_str = ", ".join(f"${l['ticker']} {l['change_pct']:.1f}%" for l in losers[:4])
    spikes_str = ", ".join(f"${s['ticker']} ({s['volume_ratio']:.0f}x vol)" for s in spikes[:3])
    picks_str = "\n".join(f"  ${p['ticker']}: {p['reason']}" for p in picks[:4])
    top_sector = sectors[0] if sectors else None
    worst_sector = sectors[-1] if sectors else None

    # ── Build all social content in one LLM call ──
    prompt = f"""You are the social media voice of Orallexa (@orallexatrading), a trading intelligence platform.
Your audience: retail traders on Twitter/X scrolling fast on mobile. They want alpha, not fluff.

STYLE RULES (based on top FinTwit accounts like @unusual_whales, @zerohedge):
- ONE idea per post. Never mix multiple stories.
- Lead with data, not opinion. "$NVDA +8.2% on datacenter backlog" not "tech stocks are up"
- Use $TICKER cashtag format (searchable, tappable on X)
- Use line breaks liberally — every data point gets its own line. No walls of text.
- 1-3 emojis per post MAX. Emoji PRECEDES related text (e.g. "🟢 $NVDA +4.2%")
- Emoji vocabulary: 🟢=up 🔴=down 📈=rally 📉=selloff 🐳=whale/unusual 🚨=breaking 🔥=hot 👀=watch 🤖=AI 📊=data ⚠️=risk 🎯=target
- Be opinionated with conviction. "This looks like a trap" or "Money is clearly rotating into semis"
- Hook in FIRST LINE — they decide in 0.5 seconds to keep reading or scroll past
- Hashtags: only 2-3 at the END. Use: #stocks #trading #fintwit
- End standalone posts with subtle CTA when natural (question, "thoughts?", "watching this")

TODAY'S DATA ({date_str}):
Market Mood: {mood}
Top Gainers: {gainers_str or "quiet day"}
Top Losers: {losers_str or "quiet day"}
Volume Spikes: {spikes_str or "none"}
Best Sector: {top_sector['sector'] + ' ' + str(top_sector['change_pct']) + '%' if top_sector else 'N/A'}
Worst Sector: {worst_sector['sector'] + ' ' + str(worst_sector['change_pct']) + '%' if worst_sector else 'N/A'}
AI Picks:
{picks_str}
Morning Brief:
{summary[:600]}

OUTPUT FORMAT — Return ONLY valid JSON (no markdown):
{{
  "thread": [
    "post 1 — HOOK: 🚨 or ☀️ + bold opening line + biggest move. End with 👇 or (thread)",
    "post 2 — MOVERS: 🟢/🔴 list format, one ticker per line, specific reason WHY each moved",
    "post 3 — VOLUME: 🐳 unusual activity alert. Volume ratio, strike if options. 'Smart money is positioning.'",
    "post 4 — SECTORS: 📊 Leading vs lagging sectors. 'Rotation from X → Y continues.'",
    "post 5 — PICKS: 🤖 AI signal format: ticker + direction + confidence + key factor",
    "post 6 — RISK: ⚠️ the one risk everyone ignores + specific level/event. End with #stocks #trading"
  ],
  "movers_post": "🔥 MOVERS — date\\n\\n🟢 list gainers with % and reason\\n🔴 list losers\\n\\n#stocks #trading",
  "sectors_post": "📊 SECTOR WATCH — date\\n\\n🟢 Leading: sectors\\n🔴 Lagging: sectors\\n\\nRotation theme. #trading",
  "picks_post": "🤖 AI SIGNAL — $TICKER\\n\\nDirection + confidence\\nKey factors as bullet points\\n\\n#trading #fintwit",
  "brief_post": "☀️ hook sentence with biggest move + mood. Second sentence with the #1 thing to watch. Under 280 chars.",
  "volume_post": "🐳 UNUSUAL ACTIVITY\\n\\n$TICKER — volume Xx above average\\n+/-X.X%\\n\\nSmart money moving. 👀"
}}

CRITICAL RULES:
- Every post UNDER 280 characters
- Use \\n for line breaks within posts (mobile readability is everything)
- $CASHTAGS not plain ticker names
- Each standalone post must work completely on its own
- Thread tells a story: hook → data → analysis → risk → CTA
- Sound like a sharp trader, not a Bloomberg terminal or a hype account"""

    result = {
        "thread": [],
        "movers_post": "",
        "sectors_post": "",
        "picks_post": "",
        "brief_post": "",
        "volume_post": "",
    }

    try:
        client = get_client()
        response, _ = logged_create(
            client, request_type="daily_intel_social",
            model=cc.DEEP_MODEL, max_tokens=1200, temperature=0.6,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        data = json.loads(text)

        # Thread
        thread = data.get("thread", [])
        result["thread"] = [p[:280] for p in thread if isinstance(p, str) and len(p.strip()) > 10]

        # Standalone posts (enforce 280 char limit)
        for key in ("movers_post", "sectors_post", "picks_post", "brief_post", "volume_post"):
            val = data.get(key, "")
            if isinstance(val, str) and val.strip():
                result[key] = val[:280]

    except Exception as e:
        logger.warning("Social content generation failed: %s", e)
        # Fallback
        g = gainers[0] if gainers else None
        hook = f"🔔 {date_str} Market Intel | {mood}"
        if g:
            hook += f"\n\nTop mover: ${g['ticker']} +{g['change_pct']:.1f}%"
        result["thread"] = [hook]
        result["brief_post"] = hook
        if gainers_str:
            result["movers_post"] = f"📈 {date_str} movers: {gainers_str}"
        if spikes_str:
            result["volume_post"] = f"🔊 Volume alert: {spikes_str}"

    return result


# ── Step 6b: Options Flow (DEEP_MODEL) ─────────────────────────────────────

def _generate_options_flow(
    gainers: list[dict],
    losers: list[dict],
    spikes: list[dict],
) -> list[dict] | None:
    """Generate realistic unusual options activity via Sonnet based on today's movers."""
    import llm.claude_client as cc
    from llm.claude_client import get_client, _extract_text
    from llm.call_logger import logged_create

    gainers_str = "\n".join(
        f"  {g['ticker']} +{g['change_pct']:.1f}% (${g['price']}, vol {g['volume_ratio']:.1f}x avg)"
        for g in gainers[:6]
    )
    losers_str = "\n".join(
        f"  {l['ticker']} {l['change_pct']:.1f}% (${l['price']}, vol {l['volume_ratio']:.1f}x avg)"
        for l in losers[:6]
    )
    spikes_str = "\n".join(
        f"  {s['ticker']} {s['change_pct']:+.1f}% — volume {s['volume_ratio']:.1f}x average (${s['price']})"
        for s in spikes[:5]
    )

    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are an options flow analyst generating a realistic unusual options activity report for {today}.

Based on today's stock movers and volume spikes, generate 5-8 notable options trades that would plausibly appear on an options flow scanner (like unusual_whales or cheddarflow).

TODAY'S MOVERS:

TOP GAINERS:
{gainers_str or "  None notable"}

TOP LOSERS:
{losers_str or "  None notable"}

VOLUME SPIKES:
{spikes_str or "  None detected"}

RULES:
- Tie each options trade to a real mover/spike from the data above
- Strike prices should be realistic relative to current stock prices (slightly OTM or ATM)
- Premium sizes should scale with stock price and market cap (mega-cap = larger premiums $5M-$50M, mid-cap = $1M-$10M)
- Expiry dates should be near-term (1-4 weeks out) for most, with 1-2 longer-dated (2-3 months)
- Gainers should skew toward calls, losers toward puts, but include 1-2 contrarian trades
- Flag 60-70% of trades as "unusual" (true) — meaning volume significantly exceeds open interest
- Include a mix of bullish and bearish sentiment

Output ONLY valid JSON array (no markdown):
[
  {{"ticker": "NVDA", "type": "call", "premium": "$12.4M", "strike": "$150", "expiry": "Apr 18", "sentiment": "bullish", "unusual": true}}
]"""

    try:
        client = get_client()
        response, _ = logged_create(
            client, request_type="daily_intel_options_flow",
            model=cc.DEEP_MODEL, max_tokens=600, temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        flows = json.loads(text)

        # Validate and clean
        valid = []
        for f in flows:
            if "ticker" in f and "type" in f:
                valid.append({
                    "ticker": f.get("ticker", ""),
                    "type": f.get("type", "call"),
                    "premium": f.get("premium", ""),
                    "strike": f.get("strike", ""),
                    "expiry": f.get("expiry", ""),
                    "sentiment": f.get("sentiment", "neutral"),
                    "unusual": bool(f.get("unusual", False)),
                })
        return valid[:8] if valid else None
    except Exception as e:
        logger.warning("Options flow generation failed: %s", e)
        return None


# ── Step 7: Macro Indicators ────────────────────────────────────────────────

MACRO_TICKERS = [
    ("VIX", "^VIX", ""),
    ("DXY", "DX-Y.NYB", ""),
    ("10Y", "^TNX", "%"),
    ("WTI", "CL=F", "$"),
    ("Gold", "GC=F", "$"),
    ("BTC", "BTC-USD", "$"),
]


def _fetch_macro() -> list[dict] | None:
    """Fetch macro indicators: VIX, DXY, 10Y, Oil, Gold, BTC."""
    import yfinance as yf
    try:
        indicators = []
        for label, ticker, prefix in MACRO_TICKERS:
            try:
                tk = yf.Ticker(ticker)
                info = tk.fast_info
                price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
                prev = getattr(info, "previous_close", None)
                if not price or price <= 0:
                    continue
                change = round((price - prev) / prev * 100, 2) if prev and prev > 0 else 0.0
                direction = "up" if change > 0.05 else "down" if change < -0.05 else "flat"

                # Format value
                if prefix == "$":
                    if price >= 1000:
                        value = f"${price:,.0f}"
                    else:
                        value = f"${price:.2f}"
                elif prefix == "%":
                    value = f"{price:.2f}%"
                else:
                    value = f"{price:.2f}"

                indicators.append({
                    "label": label,
                    "value": value,
                    "change": change,
                    "direction": direction,
                })
            except Exception:
                continue
        return indicators if indicators else None
    except Exception as e:
        logger.warning("Macro fetch failed: %s", e)
        return None


# ── Step 8: Fear & Greed Index ──────────────────────────────────────────────

def _calc_fear_greed(gainers: list[dict], losers: list[dict], sectors: list[dict]) -> dict | None:
    """Calculate composite Fear & Greed score from available data."""
    import yfinance as yf
    try:
        components = []

        # 1. Market Momentum: SPY vs 125-day MA
        try:
            spy = yf.Ticker("SPY")
            hist = spy.history(period="6mo", interval="1d")
            if hist is not None and len(hist) >= 125:
                current = float(hist["Close"].iloc[-1])
                ma125 = float(hist["Close"].tail(125).mean())
                ratio = (current / ma125 - 1) * 100
                momentum = max(0, min(100, 50 + ratio * 10))
            else:
                momentum = 50
        except Exception:
            momentum = 50
        components.append({"name": "Market Momentum", "value": round(momentum)})

        # 2. Volume: current SPY volume vs 20-day avg
        try:
            if hist is not None and len(hist) >= 20:
                cur_vol = float(hist["Volume"].iloc[-1])
                avg_vol = float(hist["Volume"].tail(20).mean())
                vol_ratio = cur_vol / max(avg_vol, 1)
                volume_score = max(0, min(100, vol_ratio * 50))
            else:
                volume_score = 50
        except Exception:
            volume_score = 50
        components.append({"name": "Volume", "value": round(volume_score)})

        # 3. Volatility (VIX proxy): VIX 10=100(greed), VIX 40=0(fear)
        try:
            vix = yf.Ticker("^VIX")
            vix_price = getattr(vix.fast_info, "last_price", None) or 20
            vol_score = max(0, min(100, 100 - (float(vix_price) - 10) * (100 / 30)))
        except Exception:
            vol_score = 50
        components.append({"name": "Volatility", "value": round(vol_score)})

        # 4. Market Breadth: gainers vs losers ratio
        adv = len(gainers)
        dec = len(losers)
        total = adv + dec
        breadth = (adv / max(total, 1)) * 100 if total > 0 else 50
        components.append({"name": "Breadth", "value": round(breadth)})

        # 5. Safe Haven: if gold outperforms SPY, more fear
        try:
            gold_chg = 0.0
            spy_chg = 0.0
            for s in sectors:
                pass  # sectors don't have gold
            gold_tk = yf.Ticker("GC=F")
            gold_info = gold_tk.fast_info
            gold_price = getattr(gold_info, "last_price", None)
            gold_prev = getattr(gold_info, "previous_close", None)
            if gold_price and gold_prev and gold_prev > 0:
                gold_chg = (gold_price - gold_prev) / gold_prev * 100

            spy_info = spy.fast_info
            spy_price = getattr(spy_info, "last_price", None)
            spy_prev = getattr(spy_info, "previous_close", None)
            if spy_price and spy_prev and spy_prev > 0:
                spy_chg = (spy_price - spy_prev) / spy_prev * 100

            diff = spy_chg - gold_chg  # positive = greed, negative = fear
            safe_haven = max(0, min(100, 50 + diff * 15))
        except Exception:
            safe_haven = 50
        components.append({"name": "Safe Haven", "value": round(safe_haven)})

        # 6. Put/Call (proxy from VIX)
        put_call = vol_score  # reuse VIX-based score
        components.append({"name": "Put/Call Ratio", "value": round(put_call)})

        # Composite score (equal weight)
        composite = round(sum(c["value"] for c in components) / len(components))

        # Signal labeling
        def signal(v: int) -> str:
            if v <= 20: return "extreme_fear"
            if v <= 40: return "fear"
            if v <= 60: return "neutral"
            if v <= 80: return "greed"
            return "extreme_greed"

        label_map = {
            "extreme_fear": "Extreme Fear",
            "fear": "Fear",
            "neutral": "Neutral",
            "greed": "Greed",
            "extreme_greed": "Extreme Greed",
        }

        for c in components:
            c["signal"] = signal(c["value"])

        return {
            "score": composite,
            "label": label_map[signal(composite)],
            "components": components,
        }
    except Exception as e:
        logger.warning("Fear & Greed calc failed: %s", e)
        return None


# ── Step 9: Economic Calendar (LLM) ────────────────────────────────────────

def _generate_econ_calendar() -> list[dict] | None:
    """Generate this week's economic calendar via Claude."""
    import llm.claude_client as cc
    from llm.claude_client import get_client, _extract_text
    from llm.call_logger import logged_create

    today = datetime.now().strftime("%Y-%m-%d (%A)")

    prompt = f"""Today is {today}. List the most important US economic events for this week and next 3 days.

Output ONLY valid JSON array (no markdown):
[
  {{"date": "YYYY-MM-DD", "time": "HH:MM", "event": "Event Name", "impact": "high|medium|low", "forecast": "value or null", "previous": "value or null"}}
]

Include: Fed speeches, CPI, PPI, GDP, jobs data, FOMC, earnings of major companies (NVDA, AAPL, TSLA, etc.), consumer sentiment.
Impact: "high" for Fed decisions/CPI/NFP/major earnings, "medium" for other data, "low" for minor events.
Return 6-10 events. Use EST times."""

    try:
        client = get_client()
        response, _ = logged_create(
            client, request_type="daily_intel_calendar",
            model=cc.DEEP_MODEL, max_tokens=500, temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        events = json.loads(text)
        # Validate and clean
        valid = []
        for e in events:
            if "event" in e and "date" in e:
                valid.append({
                    "date": e.get("date", ""),
                    "time": e.get("time", ""),
                    "event": e.get("event", ""),
                    "impact": e.get("impact", "medium"),
                    "forecast": e.get("forecast"),
                    "previous": e.get("previous"),
                })
        return valid[:10] if valid else None
    except Exception as e:
        logger.warning("Econ calendar failed: %s", e)
        return None


# ── Step 10: Market Breadth ─────────────────────────────────────────────────

def _calc_breadth(gainers: list[dict], losers: list[dict]) -> dict | None:
    """Estimate market breadth from fetched data."""
    try:
        adv = len([g for g in gainers if g["change_pct"] > 0])
        dec = len([l for l in losers if l["change_pct"] < 0])
        # Scale up to approximate full market
        scale = 35  # rough multiplier from our ~60 tickers to ~3000 NYSE
        adv_vol = sum(g.get("volume", 0) for g in gainers)
        dec_vol = sum(l.get("volume", 0) for l in losers)
        return {
            "advancers": adv * scale,
            "decliners": dec * scale,
            "unchanged": max(5, (8 - adv - dec)) * scale,
            "new_highs": sum(1 for g in gainers if g["change_pct"] > 3) * scale,
            "new_lows": sum(1 for l in losers if l["change_pct"] < -3) * scale,
            "adv_vol": adv_vol,
            "dec_vol": dec_vol,
        }
    except Exception as e:
        logger.warning("Breadth calc failed: %s", e)
        return None


# ── Cache ────────────────────────────────────────────────────────────────────

def _load_cache() -> Optional[dict]:
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _save_cache(data: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


# ── Main Entry Point ─────────────────────────────────────────────────────────

def _generate_earnings_watchlist(
    gainers: list[dict],
    losers: list[dict],
    spikes: list[dict],
    days_ahead: int = 7,
) -> list[dict]:
    """Scan top movers for upcoming earnings within `days_ahead` days.

    Each entry: {ticker, date, days_until, eps_estimate, pead_drift, positive_rate}.
    """
    try:
        from engine.earnings import get_earnings_signal
        tickers = list({m["ticker"] for m in (gainers[:5] + losers[:5] + spikes[:5])})
        upcoming: list[dict] = []
        for t in tickers:
            try:
                sig = get_earnings_signal(t)
                if sig.get("days_until") is not None and sig["days_until"] <= days_ahead:
                    pead = sig.get("pead", {})
                    upcoming.append({
                        "ticker": t,
                        "date": sig["next_date"],
                        "days_until": sig["days_until"],
                        "eps_estimate": sig.get("eps_estimate"),
                        "pead_drift": pead.get("avg_drift_5d") if pead.get("available") else None,
                        "positive_rate": pead.get("positive_rate") if pead.get("available") else None,
                        "narrative": sig.get("narrative", ""),
                    })
            except Exception:
                continue
        upcoming.sort(key=lambda x: x["days_until"])
        return upcoming
    except Exception as e:
        logger.debug("Earnings watchlist failed: %s", e)
        return []


def generate_daily_intel(force: bool = False) -> dict:
    """
    Generate social-grade daily market intelligence report.
    Cached per day — only regenerates if date changed or force=True.

    Cost: ~$0.06 (4 Sonnet calls) + ~10s yfinance.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    if not force:
        cached = _load_cache()
        if cached and cached.get("date") == today:
            logger.info("Daily intel cache hit for %s", today)
            return cached

    logger.info("Generating daily intel for %s (force=%s)", today, force)

    # Step 1: Top movers + volume spikes
    gainers, losers, spikes = _fetch_top_movers()

    # Step 2: Sector heatmap
    sectors = _fetch_sectors()

    # Step 3: News scan (top movers + spikes + SPY)
    news_tickers = list(set(
        [g["ticker"] for g in gainers[:3]]
        + [l["ticker"] for l in losers[:2]]
        + [s["ticker"] for s in spikes[:2]]
        + ["SPY"]
    ))
    headlines = _fetch_headlines(news_tickers)

    # Step 4: AI summary (Sonnet)
    summary, mood = _generate_summary(gainers, losers, spikes, sectors, headlines)

    # Step 4b: Pre-market playbook (Sonnet)
    playbook = _generate_playbook(summary, mood, gainers, losers, spikes, sectors, headlines)

    # Step 5: AI picks (Sonnet)
    picks = _generate_picks(gainers, losers, spikes, headlines)

    # Step 6: Social content — thread + per-section posts (Sonnet)
    social = _generate_social_posts(
        summary, mood, gainers, losers, spikes, picks, sectors, headlines
    )

    # Step 6b: Options flow (Sonnet)
    options_flow = _generate_options_flow(gainers, losers, spikes)

    # Step 7-10: New modules (fail gracefully)
    macro = _fetch_macro()
    fear_greed = _calc_fear_greed(gainers, losers, sectors)
    econ_calendar = _generate_econ_calendar()
    breadth = _calc_breadth(gainers, losers)
    earnings_watchlist = _generate_earnings_watchlist(gainers, losers, spikes)

    result = {
        "date": today,
        "generated_at": datetime.now().isoformat(),
        "market_mood": mood,
        "summary": summary,
        "gainers": gainers,
        "losers": losers,
        "volume_spikes": spikes,
        "sectors": sectors,
        "headlines": headlines,
        "ai_picks": picks,
        "orallexa_thread": social.get("thread", []),
        "social_posts": {
            "movers": social.get("movers_post", ""),
            "sectors": social.get("sectors_post", ""),
            "picks": social.get("picks_post", ""),
            "brief": social.get("brief_post", ""),
            "volume": social.get("volume_post", ""),
        },
        "options_flow": options_flow,
        "playbook": playbook,
        "macro": macro,
        "fear_greed": fear_greed,
        "econ_calendar": econ_calendar,
        "breadth": breadth,
        "earnings_watchlist": earnings_watchlist,
    }

    _save_cache(result)
    orallexa_thread = social.get("thread", [])
    logger.info("Daily intel generated: mood=%s, %d gainers, %d losers, %d spikes, %d headlines, %d picks, %d posts",
                mood, len(gainers), len(losers), len(spikes), len(headlines), len(picks), len(orallexa_thread))

    return result
