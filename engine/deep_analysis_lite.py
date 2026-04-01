"""
engine/deep_analysis_lite.py
──────────────────────────────────────────────────────────────────
Lightweight deep analysis replacing the heavy TradingAgents pipeline.

Combines:
  1. Technical indicators (local, instant)
  2. ML model predictions — RF, XGBoost, LR (local, ~2s)
  3. News sentiment via VADER (local, instant)
  4. Bull/Bear/Judge debate (3 LLM calls, ~10-20s)

Total: ~15-30 seconds vs 3-5 minutes for TradingAgents.

Returns the same shape as the old deep analysis endpoint:
  {
    "decision_output": DecisionOutput,
    "reports": {"market": str, "fundamentals": str, "news": str},
  }
"""
from __future__ import annotations

from models.decision import DecisionOutput


def _build_market_report(summary: dict, ticker: str) -> str:
    """Generate a market/technical report from indicator summary."""
    close = summary.get("close")
    ma20 = summary.get("ma20")
    ma50 = summary.get("ma50")
    rsi = summary.get("rsi")
    macd_hist = summary.get("macd_hist")
    bb_pct = summary.get("bb_pct")
    adx = summary.get("adx")
    vol_ratio = summary.get("volume_ratio")

    lines = [f"## {ticker} Technical Analysis\n"]

    # Trend
    if ma20 and ma50 and close:
        if close > ma20 > ma50:
            lines.append("**Trend:** Bullish — price above MA20 > MA50 (uptrend structure)")
        elif close < ma20 < ma50:
            lines.append("**Trend:** Bearish — price below MA20 < MA50 (downtrend structure)")
        elif close > ma50:
            lines.append("**Trend:** Mixed — price above MA50 but below MA20 (consolidation)")
        else:
            lines.append("**Trend:** Weak — price below both moving averages")

    # RSI
    if rsi:
        if rsi > 70:
            lines.append(f"**RSI:** {rsi:.1f} — Overbought territory, caution for reversal")
        elif rsi < 30:
            lines.append(f"**RSI:** {rsi:.1f} — Oversold territory, potential bounce")
        elif rsi > 50:
            lines.append(f"**RSI:** {rsi:.1f} — Bullish momentum zone")
        else:
            lines.append(f"**RSI:** {rsi:.1f} — Bearish momentum zone")

    # MACD
    if macd_hist:
        direction = "positive (bullish)" if macd_hist > 0 else "negative (bearish)"
        lines.append(f"**MACD Histogram:** {macd_hist:.4f} — {direction}")

    # Bollinger
    if bb_pct is not None:
        if bb_pct > 0.8:
            lines.append(f"**Bollinger %B:** {bb_pct:.2f} — Near upper band, extended")
        elif bb_pct < 0.2:
            lines.append(f"**Bollinger %B:** {bb_pct:.2f} — Near lower band, compressed")
        else:
            lines.append(f"**Bollinger %B:** {bb_pct:.2f} — Mid-range")

    # ADX
    if adx:
        strength = "strong" if adx > 25 else "weak/ranging"
        lines.append(f"**ADX:** {adx:.1f} — Trend {strength}")

    # Volume
    if vol_ratio:
        if vol_ratio > 1.5:
            lines.append(f"**Volume Ratio:** {vol_ratio:.2f} — Above average (interest)")
        elif vol_ratio < 0.7:
            lines.append(f"**Volume Ratio:** {vol_ratio:.2f} — Below average (quiet)")
        else:
            lines.append(f"**Volume Ratio:** {vol_ratio:.2f} — Normal")

    return "\n".join(lines)


def _build_ml_report(ml_result: dict, ticker: str) -> str:
    """Generate a fundamentals/ML report from ML model results."""
    if not ml_result or ml_result.get("error"):
        return f"ML analysis unavailable for {ticker}."

    lines = [f"## {ticker} ML Model Analysis\n"]

    results = ml_result.get("results", {})
    for model_name in ("random_forest", "xgboost", "logistic_regression"):
        data = results.get(model_name)
        if data:
            m = data["metrics"]
            lines.append(
                f"**{model_name.replace('_', ' ').title()}:** "
                f"Sharpe={m.get('sharpe', 0):.2f}, "
                f"Return={m.get('total_return', 0):.2%}, "
                f"WinRate={m.get('win_rate', 0):.1%}, "
                f"Trades={m.get('n_trades', 0)}"
            )

    # Buy & hold comparison
    bh = results.get("buy_and_hold", {}).get("metrics", {})
    if bh:
        lines.append(
            f"\n**Buy & Hold Baseline:** "
            f"Return={bh.get('total_return', 0):.2%}, "
            f"Sharpe={bh.get('sharpe', 0):.2f}"
        )

    best = ml_result.get("best_model")
    if best:
        bm = ml_result.get("best_metrics", {})
        lines.append(
            f"\n**Best Model:** {best.replace('_', ' ').title()} — "
            f"excess return vs buy-and-hold: {bm.get('excess_return', 0):.2%}"
        )

    # Feature importance
    fi = ml_result.get("feature_importance")
    if fi is not None:
        try:
            import pandas as pd
            if isinstance(fi, pd.DataFrame) and not fi.empty:
                # DataFrame with columns like [feature, importance]
                fi_sorted = fi.head(5)
                lines.append("\n**Top 5 Features:**")
                for _, row in fi_sorted.iterrows():
                    lines.append(f"  - {row.iloc[0]}: {row.iloc[1]:.4f}")
            elif isinstance(fi, dict):
                top_features = sorted(fi.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
                lines.append("\n**Top 5 Features:**")
                for fname, fval in top_features:
                    lines.append(f"  - {fname}: {fval:.4f}")
        except Exception:
            pass

    return "\n".join(lines)


def _build_news_report(news_items: list, ticker: str) -> str:
    """Generate a news/sentiment report."""
    if not news_items:
        return f"No recent news available for {ticker}."

    lines = [f"## {ticker} News Sentiment\n"]

    scores = [item.get("score", 0) for item in news_items]
    avg_score = sum(scores) / len(scores) if scores else 0
    sentiment = "Bullish" if avg_score > 0.1 else "Bearish" if avg_score < -0.1 else "Neutral"
    lines.append(f"**Overall Sentiment:** {sentiment} (avg score: {avg_score:.3f})\n")

    for item in news_items[:6]:
        sent = item.get("sentiment", "neutral")
        score = item.get("score", 0)
        title = item.get("title", "")
        provider = item.get("provider", "")
        icon = "🟢" if sent == "bullish" else "🔴" if sent == "bearish" else "⚪"
        source = f" ({provider})" if provider else ""
        lines.append(f"{icon} [{score:+.3f}] {title}{source}")

    return "\n".join(lines)


def run_deep_analysis_lite(brain) -> dict:
    """
    Run lightweight deep analysis.

    Parameters
    ----------
    brain : OrallexaBrain instance (already initialized with ticker)

    Returns
    -------
    dict with "decision_output" (DecisionOutput) and "reports" (dict)
    """
    ticker = brain.ticker

    # ── Step 1: Technical analysis (instant) ──
    ta = brain._prepare_data()
    train_df, test_df = brain._single_split(ta)
    summary = brain._safe_summary_from_df(ta)
    market_report = _build_market_report(summary, ticker)

    # ── Step 2: ML models (local, ~2s) ──
    ml_report = ""
    ml_result = None
    try:
        from engine.ml_signal import run_ml_analysis
        ml_result = run_ml_analysis(train_df=train_df, test_df=test_df, ticker=ticker)
        ml_report = _build_ml_report(ml_result, ticker)
    except Exception as e:
        import logging
        logging.warning(f"ML analysis failed for {ticker}: {e}")
        ml_report = f"ML analysis unavailable for {ticker}."

    # ── Step 3: News sentiment (local via yfinance + VADER, instant) ──
    news_report = ""
    news_items = []
    try:
        import yfinance as yf
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        sia = SentimentIntensityAnalyzer()
        raw = yf.Ticker(ticker).news or []
        for r in raw[:6]:
            content = r.get("content", {})
            title = content.get("title", "")
            if title and len(title) > 10:
                sc = sia.polarity_scores(title)["compound"]
                sent = "bullish" if sc > 0.1 else "bearish" if sc < -0.1 else "neutral"
                provider = content.get("provider", {})
                provider_name = provider.get("displayName", "") if isinstance(provider, dict) else ""
                news_items.append({"title": title, "sentiment": sent, "score": sc, "provider": provider_name})
        news_report = _build_news_report(news_items, ticker)
    except Exception:
        news_report = f"News unavailable for {ticker}."

    # ── Step 4: Bull/Bear debate (3 LLM calls, ~10-20s) ──
    # First build initial decision from technical score
    from skills.prediction import PredictionSkill
    try:
        initial_decision = PredictionSkill(ticker).execute(use_claude=False)
    except Exception:
        from models.confidence import make_recommendation
        initial_decision = DecisionOutput(
            decision="WAIT", confidence=40.0, risk_level="MEDIUM",
            reasoning=["Technical analysis inconclusive"],
            probabilities={"up": 0.33, "neutral": 0.34, "down": 0.33},
            source="prediction", signal_strength=40.0,
            recommendation=make_recommendation("WAIT", 40.0, "MEDIUM"),
        )

    # Enrich RAG context with ML + news for the debate
    rag_context = f"{ml_report}\n\n{news_report}"

    from llm.debate import run_lightweight_debate
    final_decision = run_lightweight_debate(
        initial_decision=initial_decision,
        summary=summary,
        ticker=ticker,
        rag_context=rag_context,
    )

    return {
        "decision_output": final_decision,
        "reports": {
            "market": market_report,
            "fundamentals": ml_report,
            "news": news_report,
        },
    }
