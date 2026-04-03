"""
api_server.py
──────────────────────────────────────────────────────────────────
FastAPI server exposing the Python trading engine to the React frontend.

Run:
    python api_server.py          (port 8002)
    uvicorn api_server:app --reload --port 8002

Endpoints:
    POST /api/analyze          → fast analysis (scalp/intraday/swing)
    POST /api/deep-analysis    → multi-agent deep analysis
    POST /api/chart-analysis   → screenshot chart analysis
    GET  /api/news/{ticker}    → live news + sentiment
    GET  /api/profile          → trader profile + behavior
    GET  /api/journal          → recent decisions from log
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

# Make project root importable
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env", override=True)

app = FastAPI(title="Orallexa Capital API")

DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("true", "1", "yes")


# ── Warm up heavy imports at startup (avoids 30s cold start on first request) ──
@app.on_event("startup")
async def _warmup():
    """Lazy warmup — don't block startup."""
    if DEMO_MODE:
        import logging
        logging.getLogger("api").info("🎭 DEMO MODE — all endpoints return mock data, no API keys needed")


_cors_origins = os.environ.get("CORS_ORIGINS", "").split(",") if os.environ.get("CORS_ORIGINS") else [
    "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001",
    "https://orallexa-ui.vercel.app",
    "https://orallexa-ui-*.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# ── API Key Authentication ────────────────────────────────────────────────────
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_API_KEY = os.environ.get("ORALLEXA_API_KEY", "")


def _require_api_key(key: str | None = Security(_API_KEY_HEADER)) -> None:
    """Protect sensitive endpoints. Skipped in demo mode or when no key is configured."""
    if DEMO_MODE or not _API_KEY:
        return
    if not key or key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Input Validation ─────────────────────────────────────────────────────────
MAX_CONTEXT_LEN = 500


def _sanitize_context(context: str) -> str:
    """Cap user context length to prevent prompt injection via volume."""
    if len(context) > MAX_CONTEXT_LEN:
        return context[:MAX_CONTEXT_LEN]
    return context


@app.get("/api/status")
async def status():
    """Health check + demo mode indicator."""
    return {"status": "ok", "demo": DEMO_MODE}


def _fast_claude_overlay(result, ticker: str, context: str = ""):
    """Single Haiku call to refine a technical-only decision. ~0.5s, ~$0.0005."""
    import json as _json
    from models.decision import DecisionOutput
    from models.confidence import scale_confidence, make_recommendation

    import llm.claude_client as cc
    from llm.claude_client import get_client, _extract_text
    from llm.call_logger import logged_create

    d = result.to_dict()
    prompt = f"""You are a fast trading signal reviewer for {ticker}.

Technical signal: {d['decision']} (confidence {d['confidence']:.0f}%, signal {d['signal_strength']:.0f}/100)
Probabilities: Up {d['probabilities']['up']*100:.0f}% | Neutral {d['probabilities']['neutral']*100:.0f}% | Down {d['probabilities']['down']*100:.0f}%
Reasoning: {'; '.join(d['reasoning'][-3:])}
{f"User context: {context}" if context else ""}

Review this signal. You may adjust confidence ±15 points and probabilities ±10% if warranted.

Output ONLY valid JSON:
{{"decision":"{d['decision']}","confidence":{d['confidence']:.0f},"risk_level":"{d['risk_level']}","up_probability":{d['probabilities']['up']:.2f},"neutral_probability":{d['probabilities']['neutral']:.2f},"down_probability":{d['probabilities']['down']:.2f},"refinement":"one sentence explaining any adjustment or confirming the signal"}}"""

    client = get_client()
    response, _ = logged_create(
        client, request_type="fast_claude_overlay",
        model=cc.FAST_MODEL, max_tokens=250, temperature=0,
        messages=[{"role": "user", "content": prompt}],
        ticker=ticker,
    )
    text = _extract_text(response).strip().replace("```json", "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    data = _json.loads(text)

    # Apply refined values (within guardrails)
    new_conf = float(data.get("confidence", d["confidence"]))
    new_conf = max(d["confidence"] - 15, min(d["confidence"] + 15, new_conf))
    scaled = scale_confidence(new_conf)

    up = float(data.get("up_probability", d["probabilities"]["up"]))
    neut = float(data.get("neutral_probability", d["probabilities"]["neutral"]))
    down = float(data.get("down_probability", d["probabilities"]["down"]))
    total = up + neut + down
    if total > 0 and abs(total - 1.0) > 0.05:
        up, neut, down = up / total, neut / total, down / total

    decision = str(data.get("decision", d["decision"])).upper()
    if decision not in ("BUY", "SELL", "WAIT"):
        decision = d["decision"]
    risk = str(data.get("risk_level", d["risk_level"])).upper()
    if risk not in ("LOW", "MEDIUM", "HIGH"):
        risk = d["risk_level"]

    refinement = str(data.get("refinement", ""))
    reasoning = list(d["reasoning"])
    if refinement:
        reasoning.append(f"Claude: {refinement}")

    return DecisionOutput(
        decision=decision,
        confidence=scaled,
        risk_level=risk,
        reasoning=reasoning,
        probabilities={"up": round(up, 3), "neutral": round(neut, 3), "down": round(down, 3)},
        source=f"{d['source']}+claude",
        signal_strength=d["signal_strength"],
        recommendation=make_recommendation(decision, scaled, risk),
    )


@app.post("/api/analyze")
async def analyze(
    ticker: str = Form("NVDA"),
    mode: str = Form("intraday"),
    timeframe: str = Form("15m"),
    use_debate: bool = Form(False),
    use_claude: bool = Form(False),
    context: str = Form(""),
):
    """Fast analysis — scalp / intraday / swing. Optional Claude overlay + debate."""
    context = _sanitize_context(context)
    if DEMO_MODE:
        from engine.demo_data import mock_analyze
        return mock_analyze(ticker, mode, timeframe, context)

    import asyncio

    def _run():
        from core.brain import OrallexaBrain
        from models.confidence import guard_decision
        brain = OrallexaBrain(ticker.upper())
        r = brain.run_for_mode(mode=mode, timeframe=timeframe, use_claude=False, use_debate=use_debate, rag_context=context)
        return guard_decision(r)

    result = await asyncio.to_thread(_run)

    # Lightweight Claude overlay — single Haiku call to refine signal
    if use_claude and result.decision != "WAIT":
        try:
            result = _fast_claude_overlay(result, ticker.upper(), context)
        except Exception as exc:
            from core.logger import get_logger
            get_logger("api").warning("Claude overlay failed: %s", exc)

    # Detect breaking signals BEFORE saving (compare against last log entry)
    breaking = None
    try:
        from engine.breaking_signals import detect_breaking
        breaking = detect_breaking(result, ticker.upper())
    except Exception as exc:
        from core.logger import get_logger
        get_logger("api").warning("Breaking signal detection failed: %s", exc)

    # Save to decision log
    try:
        from engine.decision_log import save_decision
        save_decision(decision=result, ticker=ticker.upper(), mode=mode, timeframe=timeframe)
    except Exception as exc:
        from core.logger import get_logger
        get_logger("api").warning("Failed to save decision log: %s", exc)

    out = result.to_dict()
    if breaking:
        out["breaking_signal"] = breaking
    return out


@app.post("/api/deep-analysis")
async def deep_analysis(
    ticker: str = Form("NVDA"),
):
    """
    Lightweight deep analysis: ML models + technical analysis + news sentiment
    + Bull/Bear debate.  ~15-30 seconds.
    """
    if DEMO_MODE:
        from engine.demo_data import mock_deep_analysis
        return mock_deep_analysis(ticker)

    from fastapi.responses import JSONResponse

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        load_dotenv(_ROOT / ".env", override=True)
        key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return JSONResponse(
            status_code=503,
            content={"detail": "ANTHROPIC_API_KEY is not set. Add it to .env or set it as an environment variable."},
        )

    import asyncio

    def _run_deep(tk: str):
        from core.brain import OrallexaBrain
        from engine.multi_agent_analysis import run_multi_agent_analysis
        brain = OrallexaBrain(tk)
        return run_multi_agent_analysis(ticker=tk, brain=brain)

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_deep, ticker.upper()),
            timeout=240,
        )
        dec = result.decision_output.to_dict()
        plan = result.investment_plan or {}

        breaking = None
        try:
            from engine.breaking_signals import detect_breaking
            breaking = detect_breaking(result.decision_output, ticker.upper())
        except Exception as _exc:
            from core.logger import get_logger; get_logger("api").debug("Non-critical: %s", _exc)

        try:
            from engine.decision_log import save_decision
            save_decision(decision=result.decision_output, ticker=ticker.upper(),
                          mode="deep", timeframe="1D")
        except Exception as _exc:
            from core.logger import get_logger; get_logger("api").debug("Non-critical: %s", _exc)

        out = {
            **dec,
            "reports": {
                "market": result.market_report,
                "fundamentals": result.fundamentals_report,
                "news": result.news_report,
            },
            "investment_plan": plan,
            "analysis_narrative": plan.get("analysis_narrative", ""),
            "ml_models": result.ml_models or [],
            "summary": result.summary or {},
        }
        if breaking:
            out["breaking_signal"] = breaking
        return out

    except asyncio.TimeoutError:
        return JSONResponse(status_code=504, content={"detail": "Deep analysis timed out after 4 minutes. Try again — cached data may speed up the next run."})
    except Exception as e:
        msg = str(e)
        if "credit balance" in msg:
            detail = "Anthropic API credit balance too low. Top up at console.anthropic.com"
        elif "authentication" in msg or "invalid x-api-key" in msg:
            detail = "Invalid Anthropic API key. Check ANTHROPIC_API_KEY in .env"
        elif "529" in msg or "overloaded" in msg.lower():
            detail = "Anthropic API is overloaded. Please try again in a few minutes."
        else:
            detail = msg[:200] if len(msg) > 200 else msg
        return JSONResponse(
            status_code=500,
            content={"detail": detail},
        )


@app.post("/api/deep-analysis-stream")
async def deep_analysis_stream(
    ticker: str = Form("NVDA"),
):
    """SSE streaming deep analysis — sends progress events then final result."""
    from fastapi.responses import StreamingResponse, JSONResponse
    import asyncio
    import time

    if DEMO_MODE:
        from engine.demo_data import mock_deep_analysis, DEEP_STEPS

        async def demo_stream():
            for i, (label_en, label_zh) in enumerate(DEEP_STEPS, 1):
                yield f"event: progress\ndata: {json.dumps({'step': i, 'total': len(DEEP_STEPS), 'label': label_en, 'label_zh': label_zh})}\n\n"
                await asyncio.sleep(0.8)
            result = mock_deep_analysis(ticker)
            result["elapsed_seconds"] = round(len(DEEP_STEPS) * 0.8, 1)
            yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"

        return StreamingResponse(demo_stream(), media_type="text/event-stream")

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        load_dotenv(_ROOT / ".env", override=True)
        key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return JSONResponse(
            status_code=503,
            content={"detail": "ANTHROPIC_API_KEY is not set."},
        )

    tk = ticker.upper()

    async def event_stream():
        def _send(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield _send("progress", {"step": 1, "total": 6, "label": "Loading market data...",
                                  "label_zh": "加载行情数据..."})
        t0 = time.time()

        try:
            from core.brain import OrallexaBrain
            brain = OrallexaBrain(tk)
            ta = brain._prepare_data()
            train_df, test_df = brain._single_split(ta)
            summary = brain._safe_summary_from_df(ta)
        except Exception as exc:
            yield _send("error", {"detail": f"Data load failed: {exc}"})
            return

        yield _send("progress", {"step": 2, "total": 6, "label": "Technical & news analysis...",
                                  "label_zh": "技术面 & 新闻分析..."})

        try:
            from engine.multi_agent_analysis import _run_market_analyst, _run_news_analyst, _run_ml_analyst
            market_report = _run_market_analyst(summary, tk)
            news_report, _ = await asyncio.to_thread(_run_news_analyst, tk)
            ml_report, ml_result = await asyncio.to_thread(_run_ml_analyst, train_df, test_df, tk)
        except Exception as exc:
            yield _send("error", {"detail": f"Analysis failed: {exc}"})
            return

        yield _send("progress", {"step": 3, "total": 6, "label": "Building initial signal...",
                                  "label_zh": "生成初始信号..."})

        from skills.prediction import PredictionSkill
        from models.decision import DecisionOutput
        try:
            initial_decision = PredictionSkill(tk).execute(use_claude=False)
        except Exception:
            from models.confidence import make_recommendation
            initial_decision = DecisionOutput(
                decision="WAIT", confidence=40.0, risk_level="MEDIUM",
                reasoning=["Technical analysis inconclusive"],
                probabilities={"up": 0.33, "neutral": 0.34, "down": 0.33},
                source="prediction", signal_strength=40.0,
                recommendation=make_recommendation("WAIT", 40.0, "MEDIUM"),
            )

        yield _send("progress", {"step": 4, "total": 6, "label": "Bull/Bear debate (3 LLM calls)...",
                                  "label_zh": "多空辩论（3次AI调用）..."})

        try:
            rag_context = f"{ml_report}\n\n{news_report}"
            from llm.debate import run_lightweight_debate
            debate_decision = await asyncio.to_thread(
                run_lightweight_debate,
                initial_decision=initial_decision, summary=summary,
                ticker=tk, rag_context=rag_context,
            )
        except Exception as exc:
            yield _send("error", {"detail": f"Debate failed: {exc}"})
            return

        yield _send("progress", {"step": 5, "total": 6, "label": "Risk assessment & deep report (parallel)...",
                                  "label_zh": "风险评估 & 深度报告（并行）..."})

        try:
            from llm.claude_client import get_client
            from engine.multi_agent_analysis import _run_risk_manager, _run_llm_market_report
            client = get_client()

            risk_future = asyncio.to_thread(
                _run_risk_manager, client, debate_decision,
                market_report, news_report, ml_report, tk, summary,
            )
            report_future = asyncio.to_thread(
                _run_llm_market_report, client,
                market_report, news_report, ml_report, tk, summary,
            )
            risk_data, deep_market_report = await asyncio.gather(risk_future, report_future)
        except Exception as exc:
            yield _send("error", {"detail": f"Risk/Report failed: {exc}"})
            return

        yield _send("progress", {"step": 6, "total": 6, "label": "Finalizing...",
                                  "label_zh": "生成最终结果..."})

        from models.confidence import guard_decision
        final_decision = guard_decision(debate_decision)
        plan_summary = risk_data.get("plan_summary", "")
        final_decision.reasoning.append(f"Risk Plan: {plan_summary[:200]}")

        # Build ML models list
        ml_models = []
        if ml_result:
            results = ml_result.get("results", {})
            for name in ("random_forest", "xgboost", "logistic_regression",
                         "chronos2", "moirai2", "emaformer", "diffusion", "gnn", "rl_ppo"):
                data = results.get(name)
                if data:
                    m = data["metrics"]
                    ml_models.append({
                        "model": name.replace("_", " ").title(),
                        "sharpe": round(m.get("sharpe", 0), 2),
                        "return": round(m.get("total_return", 0) * 100, 1),
                        "win_rate": round(m.get("win_rate", 0) * 100, 1),
                        "trades": m.get("n_trades", 0),
                    })
            bh = results.get("buy_and_hold", {}).get("metrics", {})
            if bh:
                ml_models.append({
                    "model": "Buy & Hold",
                    "sharpe": round(bh.get("sharpe", 0), 2),
                    "return": round(bh.get("total_return", 0) * 100, 1),
                    "win_rate": round(bh.get("win_rate", 0) * 100, 1),
                    "trades": bh.get("n_trades", 0),
                })

        breaking = None
        try:
            from engine.breaking_signals import detect_breaking
            breaking = detect_breaking(final_decision, tk)
        except Exception as _exc:
            from core.logger import get_logger; get_logger("api").debug("Non-critical: %s", _exc)

        try:
            from engine.decision_log import save_decision
            save_decision(decision=final_decision, ticker=tk, mode="deep", timeframe="1D")
        except Exception as _exc:
            from core.logger import get_logger; get_logger("api").debug("Non-critical: %s", _exc)

        dec = final_decision.to_dict()
        out = {
            **dec,
            "reports": {"market": deep_market_report, "fundamentals": ml_report, "news": news_report},
            "investment_plan": risk_data,
            "analysis_narrative": risk_data.get("analysis_narrative", ""),
            "ml_models": ml_models,
            "summary": summary,
        }
        if breaking:
            out["breaking_signal"] = breaking

        elapsed = round(time.time() - t0, 1)
        yield _send("done", {**out, "elapsed_seconds": elapsed})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/chart-analysis")
async def chart_analysis(
    file: UploadFile = File(...),
    ticker: str = Form("NVDA"),
    timeframe: str = Form("15m"),
):
    """Screenshot chart analysis via Claude Vision."""
    if DEMO_MODE:
        from engine.demo_data import mock_chart_analysis
        return mock_chart_analysis(ticker, timeframe)

    from skills.chart_analysis import ChartAnalysisSkill
    from models.confidence import guard_decision

    image_bytes = await file.read()
    media_type = file.content_type or "image/png"

    skill = ChartAnalysisSkill()
    result = skill.analyze(
        image_bytes=image_bytes,
        ticker=ticker.upper(),
        timeframe=timeframe,
        media_type=media_type,
    )
    result = guard_decision(result)
    out = result.to_dict()
    # Extract chart-specific fields from reasoning for frontend display
    out["chart_insight"] = _extract_chart_insight(result.reasoning)
    return out


def _extract_chart_insight(reasoning: list) -> dict:
    """Parse chart analysis reasoning to extract trend/setup/levels."""
    insight = {"trend": "", "setup": "", "levels": "", "summary": ""}
    for line in reasoning:
        line_lower = line.lower()
        if "trend:" in line_lower or "trend —" in line_lower:
            insight["trend"] = line.split(":", 1)[-1].strip() if ":" in line else line
        if "setup:" in line_lower or "setup —" in line_lower:
            insight["setup"] = line.split(":", 1)[-1].strip() if ":" in line else line
        if "s/r:" in line_lower or "support" in line_lower or "resistance" in line_lower:
            insight["levels"] = line.replace("S/R: ", "").strip()
    if reasoning:
        insight["summary"] = reasoning[-1] if len(reasoning) > 1 else reasoning[0]
    return insight



@app.get("/api/news/{ticker}")
async def news(ticker: str):
    """Live news headlines + VADER sentiment."""
    if DEMO_MODE:
        from engine.demo_data import mock_news
        return mock_news(ticker)

    import yfinance as yf
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    sia = SentimentIntensityAnalyzer()
    raw = yf.Ticker(ticker.upper()).news or []

    items = []
    for r in raw[:6]:
        content = r.get("content", {})
        title = content.get("title", "")
        if title and len(title) > 10:
            sc = sia.polarity_scores(title)["compound"]
            sent = "bullish" if sc > 0.1 else "bearish" if sc < -0.1 else "neutral"
            canonical = content.get("canonicalUrl", {})
            url = canonical.get("url", "") if isinstance(canonical, dict) else str(canonical)
            provider = content.get("provider", {})
            provider_name = provider.get("displayName", "") if isinstance(provider, dict) else ""
            items.append({
                "title": title,
                "sentiment": sent,
                "score": round(sc, 3),
                "url": url or None,
                "summary": (content.get("summary", "") or "")[:120] or None,
                "provider": provider_name or None,
            })

    return {"ticker": ticker.upper(), "items": items}


@app.get("/api/profile")
async def profile():
    """Trader profile + behavior insights."""
    if DEMO_MODE:
        from engine.demo_data import mock_profile
        return mock_profile()

    try:
        from bot.behavior import BehaviorMemory
        from bot.config import BotProfileManager
        mem = BehaviorMemory()
        insights = mem.get_behavior_insights()
        prof = BotProfileManager().load()
        agg = insights.get("aggressiveness", 0.5)
        return {
            "style": "Aggressive" if agg > 0.7 else "Conservative" if agg < 0.35 else "Balanced",
            "win_rate": f"{insights.get('win_rate_overall', 0):.0f}%",
            "today": f"{insights.get('trades_today', 0)} trades",
            "win_streak": insights.get("win_streak", 0),
            "loss_streak": insights.get("loss_streak", 0),
            "patterns": insights.get("patterns", []),
            "preferred_mode": prof.get("preferred_mode", "intraday"),
        }
    except Exception as exc:
        from core.logger import get_logger
        get_logger("api").warning("Failed to load profile: %s", exc)
        return {"style": "Balanced", "win_rate": "0%", "today": "0 trades",
                "win_streak": 0, "loss_streak": 0, "patterns": []}


@app.get("/api/journal")
async def journal():
    """Recent decisions from decision log."""
    if DEMO_MODE:
        from engine.demo_data import mock_journal
        return mock_journal()

    try:
        log_path = Path("memory_data/decision_log.json")
        if log_path.exists():
            with open(log_path, "r") as f:
                log = json.load(f)
            entries = []
            for e in reversed(log[-5:]):
                d = e.get("decision", {})
                dec = d.get("decision", "?") if isinstance(d, dict) else str(d)
                entries.append({
                    "ticker": e.get("ticker", "?"),
                    "mode": e.get("mode", "?"),
                    "decision": dec,
                    "timestamp": str(e.get("timestamp", ""))[:10],
                })
            return {"entries": entries}
    except Exception as exc:
        from core.logger import get_logger
        get_logger("api").warning("Failed to load journal: %s", exc)
    return {"entries": []}


@app.get("/api/daily-intel")
async def daily_intel(force: bool = False):
    """Daily market intelligence — top movers, sectors, news, AI summary, picks. Cached per day."""
    if DEMO_MODE:
        from engine.demo_data import mock_daily_intel
        return mock_daily_intel()

    import asyncio
    try:
        from engine.daily_intel import generate_daily_intel
        result = await asyncio.to_thread(generate_daily_intel, force=force)
        return result
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": str(e)[:200]})


@app.post("/api/daily-intel/refresh")
async def daily_intel_refresh():
    """Force regenerate daily intelligence report."""
    if DEMO_MODE:
        from engine.demo_data import mock_daily_intel
        return mock_daily_intel()

    import asyncio
    try:
        from engine.daily_intel import generate_daily_intel
        result = await asyncio.to_thread(generate_daily_intel, force=True)
        return result
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": str(e)[:200]})


@app.post("/api/watchlist-scan")
async def watchlist_scan(tickers: str = Form("NVDA,AAPL,TSLA")):
    """Fast parallel scan of multiple tickers — technical signals only, no LLM."""
    if DEMO_MODE:
        from engine.demo_data import mock_watchlist_scan
        ticker_list = [t.strip().upper() for t in tickers.replace("，", ",").split(",") if t.strip()]
        return mock_watchlist_scan(ticker_list)

    import concurrent.futures
    import yfinance as yf

    ticker_list = [t.strip().upper() for t in tickers.replace("，", ",").split(",") if t.strip()]
    ticker_list = ticker_list[:10]  # cap at 10

    def scan_one(tk: str) -> dict:
        out = {"ticker": tk, "price": None, "change_pct": None, "decision": "WAIT",
               "confidence": 0, "signal_strength": 0, "risk_level": "MEDIUM",
               "probabilities": {"up": 0.33, "neutral": 0.34, "down": 0.33},
               "recommendation": "", "error": None}
        try:
            # Price
            info = yf.Ticker(tk).fast_info
            price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
            prev = getattr(info, "previous_close", None)
            if price and price > 0:
                out["price"] = round(float(price), 2)
                if prev and prev > 0:
                    out["change_pct"] = round((price - prev) / prev * 100, 2)

            # Fast technical signal (no LLM)
            from core.brain import OrallexaBrain
            from models.confidence import guard_decision
            brain = OrallexaBrain(tk)
            result = brain.run_for_mode(mode="intraday", timeframe="15m", use_claude=False)
            result = guard_decision(result)
            d = result.to_dict()
            out.update({
                "decision": d["decision"],
                "confidence": d["confidence"],
                "signal_strength": d["signal_strength"],
                "risk_level": d["risk_level"],
                "probabilities": d["probabilities"],
                "recommendation": d["recommendation"],
            })
        except Exception as e:
            out["error"] = str(e)[:100]
        return out

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(scan_one, ticker_list))

    # Sort: strongest signals first (BUY/SELL with highest confidence)
    def sort_key(r: dict) -> float:
        if r.get("error"):
            return -999
        base = r.get("confidence", 0)
        if r.get("decision") == "WAIT":
            base -= 50
        return base

    results.sort(key=sort_key, reverse=True)
    return {"tickers": results}


@app.get("/api/live/{ticker}")
async def live_price(ticker: str):
    """Lightweight live price + last signal status. No LLM calls — sub-second response."""
    if DEMO_MODE:
        from engine.demo_data import mock_live
        return mock_live(ticker)

    import yfinance as yf
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    t = ticker.upper()
    out: dict = {"ticker": t, "price": None, "change_pct": None, "prev_close": None,
                 "high": None, "low": None, "volume": None, "last_signal": None, "timestamp": None}

    # Live price via yfinance fast_info
    try:
        info = yf.Ticker(t).fast_info
        price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        prev = getattr(info, "previous_close", None) or getattr(info, "regularMarketPreviousClose", None)
        if price and price > 0:
            out["price"] = round(float(price), 2)
            out["timestamp"] = datetime.now().isoformat()
            if prev and prev > 0:
                out["prev_close"] = round(float(prev), 2)
                out["change_pct"] = round((price - prev) / prev * 100, 2)
            out["high"] = round(float(getattr(info, "day_high", 0) or 0), 2) or None
            out["low"] = round(float(getattr(info, "day_low", 0) or 0), 2) or None
            out["volume"] = int(getattr(info, "last_volume", 0) or 0) or None
    except Exception as _exc:
        from core.logger import get_logger; get_logger("api").debug("Non-critical: %s", _exc)

    # Last signal from decision log (no computation)
    try:
        from engine.decision_log import load_decisions
        for entry in load_decisions(20):
            if entry.get("ticker", "").upper() == t:
                out["last_signal"] = {
                    "decision": entry.get("decision", "WAIT"),
                    "confidence": entry.get("confidence", 0),
                    "signal_strength": entry.get("signal_strength", 0),
                    "risk_level": entry.get("risk_level", "MEDIUM"),
                    "timestamp": entry.get("timestamp", ""),
                }
                break
    except Exception as _exc:
        from core.logger import get_logger; get_logger("api").debug("Non-critical: %s", _exc)

    return out


@app.get("/api/breaking-signals")
async def breaking_signals(hours: int = 24, limit: int = 10):
    """Recent breaking signals — probability shifts, decision flips, confidence changes."""
    if DEMO_MODE:
        from engine.demo_data import mock_breaking_signals
        return mock_breaking_signals()

    try:
        from engine.breaking_signals import get_recent_breaking
        signals = get_recent_breaking(hours=hours, limit=limit)
        return {"signals": signals}
    except Exception as exc:
        from core.logger import get_logger
        get_logger("api").warning("Failed to load breaking signals: %s", exc)
        return {"signals": []}


@app.post("/api/evolve-strategies")
async def evolve_strategies(
    ticker: str = Form("NVDA"),
    generations: int = Form(3),
    population: int = Form(4),
):
    """Run LLM-driven strategy evolution. Returns leaderboard."""
    from fastapi.responses import JSONResponse
    try:
        from core.brain import OrallexaBrain
        from engine.strategy_evolver import StrategyEvolver

        brain = OrallexaBrain(ticker.upper())
        ta = brain._prepare_data()
        train_df, test_df = brain._single_split(ta)

        evolver = StrategyEvolver(ticker=ticker.upper())
        result = evolver.run(train_df, test_df, generations=generations, population=population)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)[:200]})


# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET — LIVE PRICE + SIGNAL STREAM
# ═══════════════════════════════════════════════════════════════════════════

_ws_clients: set[WebSocket] = set()


async def _broadcast(event: str, data: dict) -> None:
    """Send event to all connected WebSocket clients."""
    msg = json.dumps({"event": event, **data}, ensure_ascii=False)
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """
    WebSocket endpoint for live data streaming.

    Client sends: {"type": "subscribe", "tickers": ["NVDA", "AAPL"]}
    Server pushes: price updates every 5s, signal alerts on change

    Also accepts: {"type": "ping"} → responds with pong
    """
    await websocket.accept()
    _ws_clients.add(websocket)

    import asyncio

    tickers: list[str] = ["NVDA"]
    last_prices: dict[str, float] = {}
    last_signals: dict[str, str] = {}

    async def _price_loop():
        """Push price updates every 5 seconds."""
        import yfinance as yf
        while True:
            try:
                for tk in tickers:
                    try:
                        t = yf.Ticker(tk)
                        hist = t.history(period="1d", interval="1m")
                        if not hist.empty:
                            price = float(hist["Close"].iloc[-1])
                            change = 0.0
                            if len(hist) > 1:
                                prev = float(hist["Close"].iloc[-2])
                                change = (price / prev - 1) * 100

                            # Only push if price changed
                            if abs(price - last_prices.get(tk, 0)) > 0.01:
                                last_prices[tk] = price
                                await websocket.send_text(json.dumps({
                                    "event": "price",
                                    "ticker": tk,
                                    "price": round(price, 2),
                                    "change_pct": round(change, 2),
                                }))
                    except Exception as _exc:
                        from core.logger import get_logger; get_logger("api").debug("Non-critical: %s", _exc)
                await asyncio.sleep(5)
            except Exception:
                break

    price_task = asyncio.create_task(_price_loop())

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                if msg_type == "subscribe":
                    new_tickers = msg.get("tickers", [])
                    if isinstance(new_tickers, list):
                        tickers.clear()
                        tickers.extend([t.upper() for t in new_tickers[:10]])
                        await websocket.send_text(json.dumps({
                            "event": "subscribed",
                            "tickers": tickers,
                        }))

                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))

                elif msg_type == "analyze":
                    # Run quick analysis and push result
                    tk = msg.get("ticker", tickers[0] if tickers else "NVDA").upper()
                    await websocket.send_text(json.dumps({
                        "event": "analyzing", "ticker": tk,
                    }))

                    def _run_analysis(ticker: str) -> dict:
                        from core.brain import OrallexaBrain
                        from models.confidence import guard_decision
                        brain = OrallexaBrain(ticker)
                        result = brain.run_for_mode(mode="intraday", timeframe="15m", use_claude=False)
                        result = guard_decision(result)
                        return result.to_dict()

                    result = await asyncio.to_thread(_run_analysis, tk)
                    new_signal = result.get("decision", "WAIT")

                    # Detect signal change
                    changed = new_signal != last_signals.get(tk)
                    last_signals[tk] = new_signal

                    await websocket.send_text(json.dumps({
                        "event": "signal",
                        "ticker": tk,
                        "changed": changed,
                        **result,
                    }))

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        price_task.cancel()
        _ws_clients.discard(websocket)


# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST API
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/backtest/{ticker}")
async def run_backtest(ticker: str, period: str = "2y"):
    """Run multi-strategy backtest and return summary."""
    try:
        from engine.multi_strategy import run_multi_strategy_analysis
        from skills.market_data import MarketDataSkill

        mds = MarketDataSkill(ticker)
        df = mds.execute(period=period)
        if df is None or df.empty:
            return {"error": f"No data for {ticker}"}

        # Split into 70% train / 30% test for walk-forward
        split_idx = int(len(df) * 0.7)
        train_df = df.iloc[:split_idx]
        test_df = df.iloc[split_idx:]
        analysis = run_multi_strategy_analysis(train_df, test_df, ticker)

        # Build strategy results from all_results
        strategy_results = []
        for name, entry in analysis.get("all_results", {}).items():
            tm = entry.get("test_metrics", {})
            strategy_results.append({
                "strategy": name,
                "total_return": round(tm.get("total_return", 0) * 100, 2),
                "sharpe": round(tm.get("sharpe", 0), 2),
                "max_drawdown": round(abs(tm.get("max_drawdown", 0)) * 100, 2),
                "win_rate": round(tm.get("win_rate", 0) * 100, 1),
                "trades": tm.get("n_trades", 0),
            })
        strategy_results.sort(key=lambda x: x["sharpe"], reverse=True)

        start = df.index[0].strftime("%Y-%m-%d") if hasattr(df.index[0], "strftime") else str(df.index[0])
        end = df.index[-1].strftime("%Y-%m-%d") if hasattr(df.index[-1], "strftime") else str(df.index[-1])

        return {
            "ticker": ticker.upper(),
            "period": f"{start} to {end}",
            "results": strategy_results,
            "best_strategy": analysis.get("best_strategy", ""),
        }
    except Exception as exc:
        from core.logger import get_logger
        get_logger("api").warning("Backtest failed for %s: %s", ticker, exc)
        return {"error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════
# ALPACA PAPER TRADING
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/alpaca/account", dependencies=[Depends(_require_api_key)])
async def alpaca_account():
    """Get Alpaca paper trading account info."""
    from bot.alpaca_executor import AlpacaExecutor
    executor = AlpacaExecutor()
    if not executor.connected:
        return {"error": "Alpaca not connected. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env"}
    return executor.get_account()


@app.get("/api/alpaca/positions", dependencies=[Depends(_require_api_key)])
async def alpaca_positions():
    """Get all open Alpaca positions."""
    from bot.alpaca_executor import AlpacaExecutor
    return AlpacaExecutor().get_positions()


@app.get("/api/alpaca/orders", dependencies=[Depends(_require_api_key)])
async def alpaca_orders(limit: int = 10):
    """Get recent Alpaca orders."""
    from bot.alpaca_executor import AlpacaExecutor
    return AlpacaExecutor().get_recent_orders(limit)


@app.post("/api/alpaca/execute", dependencies=[Depends(_require_api_key)])
async def alpaca_execute(
    ticker: str = Form("NVDA"),
    decision: str = Form("BUY"),
    confidence: float = Form(50.0),
    entry_price: float = Form(0.0),
    stop_loss: float = Form(0.0),
    take_profit: float = Form(0.0),
    position_pct: float = Form(5.0),
):
    """Execute a signal as an Alpaca paper order."""
    from bot.alpaca_executor import AlpacaExecutor
    executor = AlpacaExecutor()
    return executor.execute_signal(
        ticker=ticker.upper(),
        decision=decision.upper(),
        confidence=confidence,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        position_pct=position_pct,
    )


@app.post("/api/alpaca/close/{ticker}", dependencies=[Depends(_require_api_key)])
async def alpaca_close(ticker: str):
    """Close an open position."""
    from bot.alpaca_executor import AlpacaExecutor
    return AlpacaExecutor().close_position(ticker.upper())


@app.post("/api/alpaca/close-all", dependencies=[Depends(_require_api_key)])
async def alpaca_close_all():
    """Close all open positions."""
    from bot.alpaca_executor import AlpacaExecutor
    return AlpacaExecutor().close_all()


# ── X/Twitter Publishing ─────────────────────────────────────────────────

@app.get("/api/x/status")
async def x_status():
    """Check if X API credentials are configured and valid."""
    try:
        from bot.x_publisher import XPublisher
        pub = XPublisher()
        info = pub.verify_credentials()
        return {"connected": True, **info}
    except ValueError as exc:
        return {"connected": False, "error": str(exc)}
    except Exception as exc:
        return {"connected": False, "error": str(exc)[:200]}


@app.post("/api/x/tweet", dependencies=[Depends(_require_api_key)])
async def x_post_tweet(text: str = Form(...)):
    """Post a single tweet to X."""
    from bot.x_publisher import XPublisher
    pub = XPublisher()
    result = pub.post_tweet(text)
    if result.success:
        return {"success": True, "tweet_id": result.tweet_ids[0]}
    return {"success": False, "errors": result.errors}


@app.post("/api/x/thread", dependencies=[Depends(_require_api_key)])
async def x_post_thread(tweets: str = Form(...)):
    """Post a thread to X. Tweets separated by ||| delimiter."""
    import asyncio
    from bot.x_publisher import XPublisher

    tweet_list = [t.strip() for t in tweets.split("|||") if t.strip()]
    if not tweet_list:
        return {"success": False, "errors": ["No tweets provided"]}

    pub = XPublisher()
    result = await asyncio.to_thread(pub.post_thread, tweet_list)
    return {
        "success": result.success,
        "tweet_ids": result.tweet_ids,
        "posted": len(result.tweet_ids),
        "total": len(tweet_list),
        "errors": result.errors,
    }


@app.post("/api/x/post-signal", dependencies=[Depends(_require_api_key)])
async def x_post_signal(
    ticker: str = Form("NVDA"),
    decision: str = Form("BUY"),
    confidence: float = Form(70.0),
    reasoning: str = Form(""),
):
    """Post a trading signal alert to X."""
    from bot.x_publisher import XPublisher
    pub = XPublisher()
    result = pub.post_signal_alert(ticker, decision, confidence, reasoning)
    if result.success:
        return {"success": True, "tweet_id": result.tweet_ids[0]}
    return {"success": False, "errors": result.errors}


@app.post("/api/x/post-daily-intel", dependencies=[Depends(_require_api_key)])
async def x_post_daily_intel():
    """Post today's daily intel morning brief to X."""
    import asyncio
    from bot.x_publisher import XPublisher
    from engine.daily_intel import get_daily_intel

    intel = await asyncio.to_thread(get_daily_intel)
    if not intel:
        return {"success": False, "errors": ["No daily intel available"]}

    pub = XPublisher()
    result = pub.post_daily_intel(intel)
    if result.success:
        return {"success": True, "tweet_id": result.tweet_ids[0]}
    return {"success": False, "errors": result.errors}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
