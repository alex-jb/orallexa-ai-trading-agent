"""
engine/multi_agent_analysis.py
──────────────────────────────────────────────────────────────────
Self-contained multi-agent analysis pipeline for Oralexxa.

Inspired by multi-agent trading frameworks, implemented entirely
with our own code:
  1. Market Analyst  — technical indicators → report  (local)
  2. News Analyst    — news sentiment → report        (local)
  3. ML Analyst      — RF/XGB/Chronos/MOIRAI → report (local)
  4. Bull/Bear Debate — adversarial LLM debate         (3 calls)
  5. Risk Manager    — final risk assessment           (1 call)

No external framework dependencies — pure Oralexxa.

Usage:
    from engine.multi_agent_analysis import run_multi_agent_analysis

    result = run_multi_agent_analysis("NVDA", date="2026-03-30")
    print(result.decision_output)    # DecisionOutput
    print(result.market_report)      # technical analysis text
"""
from __future__ import annotations

import logging
from datetime import date as _date
from typing import Optional
from dataclasses import dataclass

from models.decision import DecisionOutput

logger = logging.getLogger(__name__)


# ── Extended result dataclass ─────────────────────────────────────────────────

@dataclass
class MultiAgentResult:
    """Extends DecisionOutput with full multi-agent reports."""
    decision_output: DecisionOutput
    market_report:      str = ""
    news_report:        str = ""
    sentiment_report:   str = ""
    fundamentals_report: str = ""
    investment_plan:    dict = None       # structured risk manager output
    final_trade_decision: str = ""
    raw_signal:         str = ""
    ml_models:          list = None       # ML model comparison data
    summary:            dict = None       # technical indicator summary
    perspective_panel:  dict = None       # role-based multi-perspective analysis
    signal_fusion:      dict = None       # multi-source signal fusion result
    token_budget:       dict = None       # final budget snapshot (used/cap/exhausted)
    budget_skipped:     list = None       # names of steps skipped due to budget exhaustion


# ── Agent 1: Market Analyst (local, instant) ──────────────────────────────────

def _run_market_analyst(summary: dict, ticker: str) -> str:
    """Technical indicator analysis — no LLM needed."""
    close = summary.get("close")
    ma20 = summary.get("ma20")
    ma50 = summary.get("ma50")
    rsi = summary.get("rsi")
    macd_hist = summary.get("macd_hist")
    bb_pct = summary.get("bb_pct")
    adx = summary.get("adx")
    vol_ratio = summary.get("volume_ratio")

    lines = [f"## {ticker} Market Analysis\n"]

    # Trend structure
    if ma20 and ma50 and close:
        if close > ma20 > ma50:
            lines.append("**Trend:** Bullish — price > MA20 > MA50 (uptrend)")
        elif close < ma20 < ma50:
            lines.append("**Trend:** Bearish — price < MA20 < MA50 (downtrend)")
        elif close > ma50:
            lines.append("**Trend:** Mixed — above MA50 but below MA20 (consolidation)")
        else:
            lines.append("**Trend:** Weak — below both moving averages")

    # RSI
    if rsi:
        if rsi > 70:
            lines.append(f"**RSI:** {rsi:.1f} — Overbought, reversal risk")
        elif rsi < 30:
            lines.append(f"**RSI:** {rsi:.1f} — Oversold, potential bounce")
        elif rsi > 50:
            lines.append(f"**RSI:** {rsi:.1f} — Bullish momentum")
        else:
            lines.append(f"**RSI:** {rsi:.1f} — Bearish momentum")

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
            lines.append(f"**Volume:** {vol_ratio:.2f}x — Above average")
        elif vol_ratio < 0.7:
            lines.append(f"**Volume:** {vol_ratio:.2f}x — Below average")
        else:
            lines.append(f"**Volume:** {vol_ratio:.2f}x — Normal")

    # Support / Resistance (from Bollinger Bands + MA levels)
    bb_upper = summary.get("bb_upper")
    bb_lower = summary.get("bb_lower")
    if bb_lower and close:
        lines.append(f"\n**Support:** ${bb_lower:.2f} (BB lower) / ${ma20:.2f} (MA20)" if ma20 else f"\n**Support:** ${bb_lower:.2f} (BB lower)")
    if bb_upper and close:
        lines.append(f"**Resistance:** ${bb_upper:.2f} (BB upper) / ${ma50:.2f} (MA50)" if ma50 else f"**Resistance:** ${bb_upper:.2f} (BB upper)")

    # Trend Score (composite 0-100)
    score = 50
    if rsi:
        score += (rsi - 50) * 0.3
    if macd_hist:
        score += min(max(macd_hist * 100, -15), 15)
    if ma20 and ma50 and close:
        if close > ma20 > ma50:
            score += 15
        elif close < ma20 < ma50:
            score -= 15
    if adx and adx > 25:
        score += 5
    score = max(0, min(100, score))
    lines.append(f"\n**Trend Score:** {score:.0f}/100")

    return "\n".join(lines)


# ── Agent 2: News Analyst (local, instant) ────────────────────────────────────

def _run_news_analyst(ticker: str) -> tuple[str, list]:
    """Fetch news via yfinance + FinBERT/VADER sentiment. Returns (report, items)."""
    news_items = []
    try:
        import yfinance as yf
        raw = yf.Ticker(ticker).news or []

        # Try FinBERT first, fall back to VADER
        scorer = None
        scorer_type = None
        try:
            from engine.sentiment import analyze_ticker_sentiment
            scorer_type = "finbert"
        except ImportError:
            pass

        if scorer_type != "finbert":
            try:
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
                scorer = SentimentIntensityAnalyzer()
                scorer_type = "vader"
            except ImportError:
                scorer_type = "none"

        for r in raw[:8]:
            content = r.get("content", {})
            title = content.get("title", "")
            if not title or len(title) < 10:
                continue

            if scorer_type == "vader" and scorer:
                sc = scorer.polarity_scores(title)["compound"]
            else:
                sc = 0.0

            sent = "bullish" if sc > 0.1 else "bearish" if sc < -0.1 else "neutral"
            provider = content.get("provider", {})
            provider_name = provider.get("displayName", "") if isinstance(provider, dict) else ""
            news_items.append({
                "title": title, "sentiment": sent,
                "score": sc, "provider": provider_name,
            })

    except Exception as e:
        logger.warning(f"News fetch failed for {ticker}: {e}")

    if not news_items:
        return f"No recent news available for {ticker}.", []

    lines = [f"## {ticker} News Sentiment\n"]
    scores = [item["score"] for item in news_items]
    avg_score = sum(scores) / len(scores) if scores else 0
    sentiment = "Bullish" if avg_score > 0.1 else "Bearish" if avg_score < -0.1 else "Neutral"
    lines.append(f"**Overall Sentiment:** {sentiment} (avg score: {avg_score:.3f})\n")

    for item in news_items[:6]:
        sent = item["sentiment"]
        score = item["score"]
        icon = "[+]" if sent == "bullish" else "[-]" if sent == "bearish" else "[=]"
        source = f" ({item['provider']})" if item["provider"] else ""
        lines.append(f"{icon} [{score:+.3f}] {item['title']}{source}")

    return "\n".join(lines), news_items


# ── Agent 3: ML Analyst (local, ~2-5s) ────────────────────────────────────────

def _add_kronos_to_ml(ml_result: dict, ticker: str, full_df) -> None:
    """Mutates ml_result in place: appends a 'kronos' entry if Kronos
    is installed. Silent no-op otherwise — Kronos is optional."""
    try:
        from engine.kronos_signal import KronosSignal
        sig = KronosSignal()
        entry = sig.for_ml_ensemble(full_df)
        if entry.get("status") == "ok":
            ml_result.setdefault("results", {})["kronos"] = entry
    except Exception as e:
        logger.debug("Kronos voter unavailable for %s: %s", ticker, e)


def _run_ml_analyst(train_df, test_df, ticker: str) -> tuple[str, Optional[dict]]:
    """Run ML models and generate report. Returns (report, raw_result)."""
    try:
        from engine.ml_signal import run_ml_analysis
        ml_result = run_ml_analysis(train_df=train_df, test_df=test_df, ticker=ticker)
        # Append Kronos's vote if installed (no-op otherwise). Uses the
        # full historical df rather than train/test split since Kronos
        # is autoregressive and wants recent context.
        if ml_result and not ml_result.get("error"):
            try:
                _add_kronos_to_ml(ml_result, ticker, train_df.tail(120) if hasattr(train_df, "tail") else train_df)
            except Exception:
                pass
        if ml_result and not ml_result.get("error"):
            lines = [f"## {ticker} ML Model Analysis\n"]
            results = ml_result.get("results", {})

            for model_name in ("random_forest", "xgboost", "logistic_regression",
                               "chronos2", "moirai2"):
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

            bh = results.get("buy_and_hold", {}).get("metrics", {})
            if bh:
                lines.append(
                    f"\n**Buy & Hold:** Return={bh.get('total_return', 0):.2%}, "
                    f"Sharpe={bh.get('sharpe', 0):.2f}"
                )

            best = ml_result.get("best_model")
            if best:
                bm = ml_result.get("best_metrics", {})
                lines.append(
                    f"\n**Best Model:** {best.replace('_', ' ').title()} "
                    f"(excess: {bm.get('excess_return', 0):.2%})"
                )

            return "\n".join(lines), ml_result
    except Exception as e:
        logger.warning(f"ML analysis failed for {ticker}: {e}")

    return f"ML analysis unavailable for {ticker}.", None


# ── Agent 4: Risk Manager (1 LLM call) ───────────────────────────────────────

def _run_risk_manager(
    client,
    debate_decision: DecisionOutput,
    market_report: str,
    news_report: str,
    ml_report: str,
    ticker: str,
    summary: dict = None,
) -> dict:
    """Final risk assessment and investment plan. Returns structured dict."""
    import json
    import llm.claude_client as cc
    from llm.claude_client import _extract_text
    from llm.call_logger import logged_create

    close = summary.get("close", 0) if summary else 0

    prompt = f"""You are a Risk Manager reviewing a trading decision for {ticker}.
Current price: ${close:.2f}

Decision: {debate_decision.decision} (confidence: {debate_decision.confidence:.0f}%)
Risk Level: {debate_decision.risk_level}

MARKET ANALYSIS:
{market_report[:600]}

NEWS:
{news_report[:400]}

ML MODELS:
{ml_report[:400]}

DEBATE REASONING:
{'; '.join(debate_decision.reasoning[-3:])}

Output ONLY valid JSON (no markdown):
{{
  "position_pct": 5,
  "entry": {close:.2f},
  "stop_loss": 0.0,
  "take_profit": 0.0,
  "risk_reward": "1:2.0",
  "key_risks": ["risk 1", "risk 2", "risk 3"],
  "plan_summary": "2-3 paragraph investment plan (150-200 words) covering: 1) the thesis and why this setup is actionable, 2) specific entry/exit criteria and position management rules, 3) what would invalidate this trade and trigger a full exit",
  "analysis_narrative": "3-4 paragraph investment thesis (200-300 words) providing deeper context: market regime assessment, how this trade fits within portfolio strategy, key catalysts to monitor over next 1-2 weeks, and specific conditions for adding to or reducing the position"
}}

Rules:
- position_pct: 1-10 (% of portfolio)
- stop_loss / take_profit: actual dollar prices based on support/resistance
- key_risks: exactly 3 concise risk factors
- plan_summary: 150-200 words, actionable and specific
- analysis_narrative: 200-300 words, deeper strategic context"""

    try:
        response, _ = logged_create(
            client, request_type="risk_manager",
            model=cc.DEEP_MODEL, max_tokens=800, temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Risk manager call failed: {e}")
        return {
            "position_pct": 3, "entry": close, "stop_loss": close * 0.97,
            "take_profit": close * 1.05, "risk_reward": "1:1.7",
            "key_risks": ["Analysis unavailable"], "plan_summary": "Risk assessment unavailable.",
        }


# ── Agent 6: LLM Deep Market Report (1 LLM call) ────────────────────────────

def _run_llm_market_report(
    client,
    local_market_report: str,
    news_report: str,
    ml_report: str,
    ticker: str,
    summary: dict = None,
) -> str:
    """Generate a structured deep market report using LLM. Returns markdown text."""
    import llm.claude_client as cc
    from llm.claude_client import _extract_text
    from llm.call_logger import logged_create

    close = summary.get("close", 0) if summary else 0

    prompt = f"""You are a senior market analyst writing a comprehensive research brief for {ticker} (current price: ${close:.2f}).

TECHNICAL DATA:
{local_market_report[:800]}

NEWS & SENTIMENT:
{news_report[:600]}

ML MODEL RESULTS:
{ml_report[:600]}

Write a structured deep analysis with these sections. Use plain text with section headers (no markdown symbols like ** or ##):

MARKET STRUCTURE
Analyze trend direction, momentum quality, and volatility regime. Reference specific indicator values (RSI, MACD, ADX, MA alignment). Is this a trending or ranging environment?

CATALYST ASSESSMENT
What are the key catalysts? Evaluate news impact, potential earnings effects, sector rotation dynamics. How does sentiment align with price action?

ML MODEL CONSENSUS
Summarize what the ML models agree and disagree on. Which model's signal is most reliable given current conditions? Any divergence between technical and ML signals?

RISK FACTORS
List 3-5 specific risk factors with severity (High/Medium/Low). Include both technical risks (support breaks, exhaustion) and fundamental risks (news, macro).

ACTIONABLE LEVELS
Provide specific price levels: entry zone, stop loss, first target, second target. Explain the rationale for each level based on support/resistance, Bollinger Bands, or MA levels.

Write 500-700 words total. Be specific, data-driven, and actionable. No generic filler."""

    try:
        response, _ = logged_create(
            client, request_type="llm_deep_market_report",
            model=cc.DEEP_MODEL, max_tokens=1500, temperature=0,
            messages=[{"role": "user", "content": prompt}],
            ticker=ticker,
        )
        return _extract_text(response)
    except Exception as e:
        logger.warning(f"LLM market report failed for {ticker}: {e}")
        return local_market_report


# ── Main entry point ──────────────────────────────────────────────────────────

def run_multi_agent_analysis(
    ticker: str,
    trade_date: Optional[str] = None,
    analysts: list[str] = None,
    ml_evidence: Optional[dict] = None,
    backtest_evidence: Optional[dict] = None,
    brain=None,
    token_budget=None,
    compress_context: str = "off",
    *,
    multimodal: bool = False,
    multimodal_roles: Optional[list[str]] = None,
) -> MultiAgentResult:
    """
    Run self-contained multi-agent pipeline.

    Parameters
    ----------
    ticker       : e.g. "NVDA"
    trade_date   : ISO date string (defaults to today)
    analysts     : unused, kept for API compatibility
    ml_evidence  : unused, kept for API compatibility
    backtest_evidence : unused, kept for API compatibility
    brain        : optional OrallexaBrain instance (avoids re-init)
    token_budget : optional engine.token_budget.TokenBudget — when
                   exhausted, downstream LLM-heavy steps (debate, market
                   report, scenario sim) are SKIPPED and the result
                   carries the partial output it has so far. The final
                   budget snapshot is attached as result.token_budget.
    compress_context : how to compress chained agent text before Risk
                   Manager / Deep Market Report. One of:
                       "off"        — pass full text (default, safe)
                       "extractive" — pure-Python summary (zero cost)
                       "llm"        — FAST_MODEL summary (~$0.0005/call)
                       "auto"       — extractive < 1.5k chars else llm
                   Run scripts/eval_context_compression.py to verify
                   decision agreement before enabling in production.

    Returns
    -------
    MultiAgentResult with .decision_output + full reports
    """
    if trade_date is None:
        trade_date = _date.today().isoformat()

    # ── Initialize brain if not provided ──
    if brain is None:
        from core.brain import OrallexaBrain
        brain = OrallexaBrain(ticker)

    # ── Agent 1: Market Analyst ──
    ta = brain._prepare_data()
    train_df, test_df = brain._single_split(ta)
    summary = brain._safe_summary_from_df(ta)
    market_report = _run_market_analyst(summary, ticker)

    # ── Agent 2: News Analyst ──
    news_report, news_items = _run_news_analyst(ticker)

    # ── Agent 3: ML Analyst ──
    ml_report, ml_result = _run_ml_analyst(train_df, test_df, ticker)

    # ── Build initial decision from technicals ──
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

    # ── Track which LLM-heavy steps were skipped due to token-budget exhaustion
    skipped: list[str] = []

    # ── Agent 4: Debate + Panel + Signal Fusion (parallel) ──
    rag_context = f"{ml_report}\n\n{news_report}"
    from llm.debate import run_lightweight_debate
    from llm.perspective_panel import run_perspective_panel
    from engine.signal_fusion import fuse_signals
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    # Budget-gated debate: only run if there's headroom. fuse_signals doesn't
    # call the LLM so it always runs. Perspective panel makes 4 fast calls,
    # so it's cheap enough to run unless budget already exhausted.
    skip_debate = bool(token_budget) and not token_budget.allow()
    skip_panel = bool(token_budget) and not token_budget.allow()

    with ThreadPoolExecutor(max_workers=3) as pool:
        debate_future = None
        if not skip_debate:
            debate_future = pool.submit(
                run_lightweight_debate,
                initial_decision=initial_decision,
                summary=summary,
                ticker=ticker,
                rag_context=rag_context,
            )
        # Detect current regime so DyTopo can pick role subset. Cheap —
        # _detect_regime is pure-pandas. Falls back to None on failure
        # (which leaves run_perspective_panel in static 4-role mode).
        detected_regime = None
        try:
            from engine.strategies import _detect_regime
            r_series = _detect_regime(ta)
            if len(r_series) > 0:
                detected_regime = str(r_series.iloc[-1])
        except Exception as e:
            logger.debug("Regime detection failed for %s: %s", ticker, e)

        panel_future = None
        if not skip_panel:
            panel_future = pool.submit(
                run_perspective_panel,
                summary=summary,
                ticker=ticker,
                news_report=news_report,
                ml_report=ml_report,
                regime=detected_regime,
                dynamic=True,
                multimodal=multimodal,
                multimodal_roles=multimodal_roles,
            )
        fusion_future = pool.submit(
            fuse_signals,
            ticker=ticker,
            summary=summary,
            ml_result=ml_result,
            news_items=news_items,
        )

        if debate_future is not None:
            try:
                debate_decision = debate_future.result(timeout=90)
            except (FuturesTimeout, Exception) as e:
                logger.warning("Debate timed out: %s", e)
                debate_decision = initial_decision
        else:
            debate_decision = initial_decision
            skipped.append("debate")
            logger.info("Skipped debate due to token budget exhaustion")

        if panel_future is not None:
            try:
                panel_result = panel_future.result(timeout=45)
            except (FuturesTimeout, Exception) as e:
                logger.warning("Perspective panel timed out: %s", e)
                panel_result = {
                    "consensus": "NEUTRAL", "avg_score": 0, "agreement": 0,
                    "perspectives": [], "panel_summary": "",
                }
        else:
            panel_result = {
                "consensus": "NEUTRAL", "avg_score": 0, "agreement": 0,
                "perspectives": [], "panel_summary": "(skipped: budget)",
            }
            skipped.append("perspective_panel")

        try:
            fusion_result = fusion_future.result(timeout=30)
        except (FuturesTimeout, Exception) as e:
            logger.warning("Signal fusion timed out: %s", e)
            fusion_result = {
                "conviction": 0, "direction": "NEUTRAL", "confidence": 0,
                "n_sources": 0, "sources": {}, "fusion_detail": "",
            }

    # ── Agent 5 + 6: Risk Manager & Deep Market Report (parallel, 2 LLM calls) ──
    from llm.claude_client import get_client
    client = get_client()

    # Enrich context with panel consensus + fusion for risk manager
    panel_summary = panel_result.get("panel_summary", "")
    fusion_summary = fusion_result.get("fusion_detail", "")

    # Optional context compression on chained reports before Risk Manager
    # consumes them. Default "off" to avoid silently changing decisions —
    # see scripts/eval_context_compression.py for verification workflow.
    if compress_context and compress_context != "off":
        try:
            from engine.context_compressor import compress
            market_report = compress(market_report, mode=compress_context,
                                       ticker=ticker)
            news_report = compress(news_report, mode=compress_context,
                                    ticker=ticker)
            ml_report = compress(ml_report, mode=compress_context, ticker=ticker)
        except Exception as e:
            logger.debug("Context compression failed for %s: %s", ticker, e)

    LLM_TIMEOUT = 60  # seconds — fail gracefully instead of hanging

    skip_risk = bool(token_budget) and not token_budget.allow()
    skip_report = bool(token_budget) and not token_budget.allow()

    with ThreadPoolExecutor(max_workers=2) as pool:
        risk_future = pool.submit(
            _run_risk_manager, client, debate_decision,
            market_report, news_report,
            f"{ml_report}\n\n{panel_summary}\n\nSignal Fusion: {fusion_summary}",
            ticker, summary,
        ) if not skip_risk else None
        report_future = pool.submit(
            _run_llm_market_report, client,
            market_report, news_report, ml_report, ticker, summary,
        ) if not skip_report else None

        close = summary.get("close", 0) if summary else 0
        if risk_future is not None:
            try:
                risk_data = risk_future.result(timeout=LLM_TIMEOUT)
            except (FuturesTimeout, Exception) as e:
                logger.warning("Risk manager timed out or failed: %s", e)
                risk_data = {
                    "position_pct": 3, "entry": close, "stop_loss": close * 0.97,
                    "take_profit": close * 1.05, "risk_reward": "1:1.7",
                    "key_risks": ["Risk assessment timed out"],
                    "plan_summary": "Risk assessment unavailable due to timeout.",
                }
        else:
            risk_data = {
                "position_pct": 3, "entry": close, "stop_loss": close * 0.97,
                "take_profit": close * 1.05, "risk_reward": "1:1.7",
                "key_risks": ["Skipped — token budget exhausted"],
                "plan_summary": "Risk plan skipped (token budget exhausted).",
            }
            skipped.append("risk_manager")

        if report_future is not None:
            try:
                deep_market_report = report_future.result(timeout=LLM_TIMEOUT)
            except (FuturesTimeout, Exception) as e:
                logger.warning("Deep market report timed out or failed: %s", e)
                deep_market_report = market_report  # fallback to local analysis
        else:
            deep_market_report = market_report
            skipped.append("deep_market_report")

    # ── Apply edge guards ──
    from models.confidence import guard_decision
    final_decision = guard_decision(debate_decision)

    # Add panel consensus, signal fusion, and risk manager reasoning
    panel_consensus = panel_result.get("consensus", "NEUTRAL")
    panel_agreement = panel_result.get("agreement", 0)
    panel_score = panel_result.get("avg_score", 0)
    final_decision.reasoning.append(
        f"Panel: {panel_consensus} (score: {panel_score:+.0f}, agreement: {panel_agreement}%)"
    )
    fusion_conv = fusion_result.get("conviction", 0)
    fusion_dir = fusion_result.get("direction", "NEUTRAL")
    fusion_detail = fusion_result.get("fusion_detail", "")
    final_decision.reasoning.append(
        f"Fusion: {fusion_dir} (conviction: {fusion_conv:+d}) — {fusion_detail}"
    )
    plan_summary = risk_data.get("plan_summary", "")
    final_decision.reasoning.append(f"Risk Plan: {plan_summary[:200]}")

    # Stash multimodal_diff on .extra so the eval-set extractor can rebuild
    # (text_decision, vision_decision, ground_truth) tuples without rerunning
    # the LLM pipeline. Same pattern as decision.extra["debate"] for DSPy.
    # No-op when multimodal=False or when the panel ran with no vision pairs.
    mm_diff = panel_result.get("multimodal_diff")
    if mm_diff and mm_diff.get("n_pairs", 0) > 0:
        final_decision.extra["multimodal_diff"] = mm_diff

    # Build ML model summary for frontend
    ml_models = []
    if ml_result:
        results = ml_result.get("results", {})
        for name in ("random_forest", "xgboost", "logistic_regression",
                     "chronos2", "moirai2", "emaformer", "diffusion", "gnn", "rl_ppo"):
            data = results.get(name)
            if data:
                m = data["metrics"]
                status = data.get("status", "ok")
                _PURPOSE = {
                    "random_forest": "Core stock selection",
                    "xgboost": "Gradient boosting",
                    "logistic_regression": "Baseline model",
                    "emaformer": "Time series forecast",
                    "chronos2": "Foundation model",
                    "moirai2": "Zero-shot forecast",
                    "diffusion": "Probability paths",
                    "gnn": "Inter-stock signals",
                    "rl_ppo": "Position optimization",
                }
                entry = {
                    "model": name.replace("_", " ").title(),
                    "sharpe": round(m.get("sharpe", 0), 2),
                    "return": round(m.get("total_return", 0) * 100, 1),
                    "win_rate": round(m.get("win_rate", 0) * 100, 1),
                    "trades": m.get("n_trades", 0),
                    "status": status,
                    "purpose": _PURPOSE.get(name, "Analysis"),
                }
                if status != "ok":
                    entry["error"] = data.get("error", "Unknown error")
                ml_models.append(entry)
        bh = results.get("buy_and_hold", {}).get("metrics", {})
        if bh:
            ml_models.append({
                "model": "Buy & Hold",
                "sharpe": round(bh.get("sharpe", 0), 2),
                "return": round(bh.get("total_return", 0) * 100, 1),
                "win_rate": round(bh.get("win_rate", 0) * 100, 1),
                "trades": bh.get("n_trades", 0),
            })

    return MultiAgentResult(
        decision_output=final_decision,
        market_report=deep_market_report,
        news_report=news_report,
        sentiment_report=news_report,
        fundamentals_report=ml_report,
        investment_plan=risk_data,
        final_trade_decision=f"{final_decision.decision} "
                             f"(conf: {final_decision.confidence:.0f}%)",
        raw_signal=final_decision.decision,
        ml_models=ml_models,
        summary=summary,
        perspective_panel=panel_result,
        signal_fusion=fusion_result,
        token_budget=token_budget.report() if token_budget else None,
        budget_skipped=skipped if skipped else None,
    )
