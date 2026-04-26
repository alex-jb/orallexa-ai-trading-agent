"""
llm/perspective_panel.py
──────────────────────────────────────────────────────────────────
Role-based multi-perspective analysis panel.

Inspired by MiroFish's heterogeneous agent simulation — instead of
homogeneous bull/bear debate, we run 4 distinct market personas in
parallel, each with different risk appetite, time horizon, and focus.

The panel produces a consensus score and per-role reasoning that
feeds into the judge and risk manager for richer decision-making.

Usage:
    from llm.perspective_panel import run_perspective_panel
    result = run_perspective_panel(summary, ticker, news_report, ml_report)
    print(result["consensus"])       # "BULLISH" / "BEARISH" / "NEUTRAL"
    print(result["perspectives"])    # list of per-role analyses
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass
from typing import Optional

import llm.claude_client as cc
from llm.claude_client import get_client, _extract_text
from llm.call_logger import logged_create

logger = logging.getLogger(__name__)

# ── Role Definitions ─────────────────────────────────────────────────────────

ROLES = [
    {
        "name": "Conservative Analyst",
        "icon": "🛡️",
        "system": (
            "You are a conservative institutional analyst managing pension fund assets. "
            "You prioritize capital preservation over returns. You are skeptical of momentum "
            "plays and always look for downside risks first. You prefer high-quality setups "
            "with clear support levels and favorable risk/reward ratios (>1:2)."
        ),
        "focus": "risk/reward, capital preservation, support levels, drawdown risk",
    },
    {
        "name": "Aggressive Trader",
        "icon": "⚡",
        "system": (
            "You are an aggressive swing trader with a 1-5 day horizon. "
            "You love momentum, breakouts, and volume surges. You tolerate higher risk "
            "for higher reward and use tight stops. You watch RSI divergences, MACD "
            "crossovers, and volume spikes as your primary signals."
        ),
        "focus": "momentum, breakout potential, volume, short-term catalysts",
    },
    {
        "name": "Macro Strategist",
        "icon": "🌍",
        "system": (
            "You are a macro strategist who views individual stocks through the lens of "
            "broader market conditions, sector rotation, interest rates, and geopolitical "
            "risk. You care less about a single stock's RSI and more about whether the "
            "macro environment supports the trade thesis."
        ),
        "focus": "sector trends, macro environment, correlation risk, regime",
    },
    {
        "name": "Quant Researcher",
        "icon": "📊",
        "system": (
            "You are a quantitative researcher who trusts data over narratives. "
            "You focus on statistical edge: Sharpe ratios, win rates, model agreement, "
            "and historical patterns. You are unemotional and only act when multiple "
            "independent signals align with statistical significance."
        ),
        "focus": "model consensus, statistical edge, signal alignment, backtest evidence",
    },
]


@dataclass
class PerspectiveResult:
    """Single role's analysis output."""
    role: str
    icon: str
    bias: str          # "BULLISH", "BEARISH", "NEUTRAL"
    score: int         # -100 (max bearish) to +100 (max bullish)
    conviction: int    # 0-100 confidence in their own view
    reasoning: str     # 2-3 sentence explanation
    key_factor: str    # single most important factor


def _call_perspective(
    client,
    role: dict,
    context: str,
    ticker: str,
    role_memory_context: str = "",
) -> PerspectiveResult:
    """Run a single role's analysis. Returns PerspectiveResult."""
    memory_block = f"\n{role_memory_context}\n" if role_memory_context else ""
    prompt = f"""{role['system']}

Analyze {ticker} from your perspective. Focus on: {role['focus']}
{memory_block}
MARKET DATA:
{context}

Output ONLY valid JSON (no markdown):
{{
  "bias": "BULLISH",
  "score": 40,
  "conviction": 65,
  "reasoning": "2-3 sentences explaining your view with specific data points",
  "key_factor": "single most important factor driving your view"
}}

Rules:
- bias: "BULLISH", "BEARISH", or "NEUTRAL"
- score: -100 (max bearish) to +100 (max bullish)
- conviction: 0-100 (how confident in your view)
- reasoning: reference specific indicator values from the data
- key_factor: one concise phrase"""

    try:
        response, _ = logged_create(
            client, request_type=f"perspective_{role['name'].lower().replace(' ', '_')}",
            model=cc.FAST_MODEL, max_tokens=300, temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        data = json.loads(text)

        bias = str(data.get("bias", "NEUTRAL")).upper()
        if bias not in ("BULLISH", "BEARISH", "NEUTRAL"):
            bias = "NEUTRAL"

        return PerspectiveResult(
            role=role["name"],
            icon=role["icon"],
            bias=bias,
            score=max(-100, min(100, int(data.get("score", 0)))),
            conviction=max(0, min(100, int(data.get("conviction", 50)))),
            reasoning=str(data.get("reasoning", "")),
            key_factor=str(data.get("key_factor", "")),
        )
    except Exception as e:
        logger.warning("Perspective %s failed: %s", role["name"], e)
        return PerspectiveResult(
            role=role["name"], icon=role["icon"],
            bias="NEUTRAL", score=0, conviction=0,
            reasoning="Analysis unavailable.", key_factor="N/A",
        )


def _build_panel_context(
    summary: dict,
    ticker: str,
    news_report: str,
    ml_report: str,
) -> str:
    """Build compact context string for all roles."""
    lines = [
        f"Ticker: {ticker}",
        f"Close: ${summary.get('close', 0):.2f}  "
        f"MA20: {summary.get('ma20')}  MA50: {summary.get('ma50')}",
        f"RSI: {summary.get('rsi')}  MACD Hist: {summary.get('macd_hist')}",
        f"BB%: {summary.get('bb_pct')}  ADX: {summary.get('adx')}  "
        f"Vol Ratio: {summary.get('volume_ratio')}",
    ]
    if news_report:
        lines.append(f"\nNEWS:\n{news_report[:400]}")
    if ml_report:
        lines.append(f"\nML MODELS:\n{ml_report[:400]}")
    return "\n".join(lines)


def select_roles_for_context(
    summary: dict,
    *,
    regime: Optional[str] = None,
    min_roles: int = 2,
) -> list[dict]:
    """
    DyTopo-inspired dynamic role selection.

    Instead of always running all 4 perspectives, pick the 2-3 whose
    expertise matches the current market context. Saves ~50% of LLM
    calls on routine analysis while keeping all 4 voices available
    when the context is genuinely uncertain.

    Heuristic:
        trending market → Aggressive + Quant (momentum + signal)
        ranging market  → Conservative + Quant (caution + statistical edge)
        volatile market → all 4 (high-stakes — get all opinions)
        neutral / unknown → Conservative + Macro + Quant (default-prudent)

    Override the static list by passing roles= explicitly to
    run_perspective_panel.
    """
    by_name = {r["name"]: r for r in ROLES}
    regime_l = (regime or "").lower()

    if "volatile" in regime_l:
        return list(ROLES)  # full panel — uncertainty deserves diversity
    if "trend" in regime_l:
        picked = ["Aggressive Trader", "Quant Researcher"]
    elif "rang" in regime_l or "mean_revert" in regime_l:
        picked = ["Conservative Analyst", "Quant Researcher"]
    else:
        # Default-prudent triple
        picked = ["Conservative Analyst", "Macro Strategist", "Quant Researcher"]

    # Honor min_roles by topping up with the missing one if needed
    while len(picked) < min_roles:
        for r in ROLES:
            if r["name"] not in picked:
                picked.append(r["name"])
                break
        else:
            break

    return [by_name[n] for n in picked if n in by_name]


def run_perspective_panel(
    summary: dict,
    ticker: str,
    news_report: str = "",
    ml_report: str = "",
    roles: Optional[list[dict]] = None,
    regime: Optional[str] = None,
    dynamic: bool = False,
) -> dict:
    """
    Run role-based perspectives in parallel and aggregate consensus.

    Parameters
    ----------
    roles    : explicit role list — overrides everything else.
    regime   : "trending" / "ranging" / "volatile" / "neutral" — used by
               dynamic role selection when `dynamic=True`.
    dynamic  : when True, pick a subset of ROLES based on regime via
               select_roles_for_context. Default False to preserve the
               existing 4-role behavior.

    Returns
    -------
    dict with keys:
        consensus      : "BULLISH" / "BEARISH" / "NEUTRAL"
        avg_score      : -100 to +100
        agreement      : 0-100% (how much roles agree)
        perspectives   : list of PerspectiveResult as dicts
        panel_summary  : formatted text summary for LLM context
        roles_selected : names of roles actually run (debug)
    """
    if roles is None:
        if dynamic:
            roles = select_roles_for_context(summary, regime=regime)
        else:
            roles = ROLES

    client = get_client()
    context = _build_panel_context(summary, ticker, news_report, ml_report)

    # Load role memory for context injection
    role_mem = None
    try:
        from engine.role_memory import RoleMemory
        role_mem = RoleMemory()
    except Exception:
        pass

    # Layered (short/mid/long) memory — enriches role_memory with tier-aware
    # accuracy so prompts can weight toward the role's strongest horizon.
    layered_mem = None
    try:
        from engine.layered_memory import LayeredMemory
        layered_mem = LayeredMemory()
    except Exception:
        pass

    # Run all 4 roles in parallel (4 FAST_MODEL calls)
    results: list[PerspectiveResult] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for role in roles:
            mem_ctx = ""
            if role_mem:
                try:
                    mem_ctx = role_mem.get_role_context(role["name"], ticker)
                except Exception:
                    pass
            if layered_mem:
                try:
                    narrative = layered_mem.narrative(role["name"], ticker)
                    if narrative and "Insufficient" not in narrative:
                        mem_ctx = (mem_ctx + "\n" if mem_ctx else "") + narrative
                except Exception:
                    pass
            futures[pool.submit(
                _call_perspective, client, role, context, ticker, mem_ctx
            )] = role

        for future in futures:
            try:
                results.append(future.result(timeout=30))
            except (FuturesTimeout, Exception) as e:
                role = futures[future]
                logger.warning("Perspective %s timed out: %s", role["name"], e)
                results.append(PerspectiveResult(
                    role=role["name"], icon=role["icon"],
                    bias="NEUTRAL", score=0, conviction=0,
                    reasoning="Timed out.", key_factor="N/A",
                ))

    # Record predictions to role memory (single-pool + layered-tier stores)
    if role_mem:
        for r in results:
            if r.conviction > 0:
                try:
                    role_mem.record_prediction(
                        role=r.role, ticker=ticker, bias=r.bias,
                        score=r.score, conviction=r.conviction,
                        reasoning=r.reasoning, key_factor=r.key_factor,
                    )
                except Exception:
                    pass
    if layered_mem:
        for r in results:
            if r.conviction > 0:
                try:
                    layered_mem.record(
                        role=r.role, ticker=ticker, bias=r.bias,
                        score=r.score, conviction=r.conviction,
                        reasoning=r.reasoning,
                    )
                except Exception:
                    pass

    # Aggregate consensus
    valid = [r for r in results if r.conviction > 0]
    if valid:
        # Conviction-weighted average score
        total_weight = sum(r.conviction for r in valid)
        avg_score = sum(r.score * r.conviction for r in valid) / total_weight
        # Agreement: how similar are the biases?
        bias_counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
        for r in valid:
            bias_counts[r.bias] += 1
        max_agreement = max(bias_counts.values())
        agreement = int(max_agreement / len(valid) * 100)
    else:
        avg_score = 0.0
        agreement = 0

    if avg_score > 15:
        consensus = "BULLISH"
    elif avg_score < -15:
        consensus = "BEARISH"
    else:
        consensus = "NEUTRAL"

    # Build text summary for feeding into judge/risk manager
    panel_lines = [f"## Perspective Panel — {ticker}\n"]
    panel_lines.append(f"**Consensus: {consensus}** (score: {avg_score:+.0f}, agreement: {agreement}%)\n")
    for r in results:
        panel_lines.append(
            f"{r.icon} **{r.role}** — {r.bias} (score: {r.score:+d}, "
            f"conviction: {r.conviction}%)"
        )
        panel_lines.append(f"   {r.reasoning}")
        panel_lines.append(f"   Key: {r.key_factor}\n")

    return {
        "consensus": consensus,
        "avg_score": round(avg_score, 1),
        "agreement": agreement,
        "perspectives": [
            {
                "role": r.role, "icon": r.icon, "bias": r.bias,
                "score": r.score, "conviction": r.conviction,
                "reasoning": r.reasoning, "key_factor": r.key_factor,
            }
            for r in results
        ],
        "panel_summary": "\n".join(panel_lines),
        "roles_selected": [r["name"] for r in roles],
    }
