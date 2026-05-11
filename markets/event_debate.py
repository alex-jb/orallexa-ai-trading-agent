"""Binary-event Bull/Bear/Judge debate — outputs p_yes ∈ [0, 1].

Adapted from `llm/debate_graph.py` (which is stock-shaped: BUY/SELL/WAIT +
signal_strength). For binary YES/NO markets we want a direct probability,
not a trinary decision. We also don't need the LangGraph layer here — a
clean 3-call sequence is shorter and easier to reason about.

Cost per debate (2026-05 prices):
  Bull   — Haiku 4.5    ~$0.0008
  Bear   — Haiku 4.5    ~$0.0008
  Judge  — Sonnet 4.6   ~$0.005
  total              ≈  $0.007 / market

30 markets/day → ~$0.21/day → ~$6.30/month. Acceptable for the morning
queue. Cached system prompts (anthropic prompt caching) drop this 60-70%
once we stabilize the system text — not in v0.1.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional

from markets.market import BinaryMarket
from llm.claude_client import get_client, _extract_text, FAST_MODEL, DEEP_MODEL


# ────────────────────────────────────────────────────────────────────
# OUTPUT TYPES
# ────────────────────────────────────────────────────────────────────


@dataclass
class EventDebateOutput:
    """One debate's verdict on a binary market.

    p_yes is the LLM-debate output probability that YES resolves true.
    Compare against `market.yes_price` to get edge.
    """
    market_id: str
    platform: str
    question: str

    p_yes: float
    bull_argument: str
    bear_argument: str
    judge_reasoning: str
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)

    # Snapshot of market price at debate time (for edge calc + audit)
    market_price_at_debate: Optional[float] = None

    @property
    def edge(self) -> Optional[float]:
        """p_yes - market_price. Positive means we think YES is underpriced."""
        if self.market_price_at_debate is None:
            return None
        return self.p_yes - self.market_price_at_debate

    def to_dict(self) -> dict:
        return asdict(self)


# ────────────────────────────────────────────────────────────────────
# PROMPTS
# ────────────────────────────────────────────────────────────────────


_BULL_SYSTEM = """You are a Bull analyst on a binary prediction market. \
Your job is to make the strongest factual case that YES will resolve true \
by the resolution date. You must cite concrete evidence (events, base \
rates, statements, data) — not speculation or vibes. End with a \
one-sentence summary of your strongest single point. Maximum 350 words."""


_BEAR_SYSTEM = """You are a Bear analyst on a binary prediction market. \
Your job is to make the strongest factual case that YES will NOT resolve \
true by the resolution date (i.e. NO wins). You must cite concrete \
evidence (events, base rates, statements, data) — not speculation or \
vibes. End with a one-sentence summary of your strongest single point. \
Maximum 350 words."""


_JUDGE_SYSTEM = """You are the Judge in a binary-market debate. You will \
read a Bull argument and a Bear argument, then output your final \
probability that YES resolves true. You must:

1. Weigh which side cited stronger CONCRETE evidence (base rates, hard \
events, named sources). Ignore rhetoric and confidence assertions.
2. Consider that prediction markets are reasonably efficient at the \
aggregate; deviations from market price require strong evidence to justify.
3. Be calibrated: a 60% probability should resolve YES 6 times out of 10 \
historically. Don't say 80% just because you found one good Bull argument.
4. Output STRICT JSON. No prose outside the JSON block.

Required JSON shape:
{
  "p_yes": <float between 0 and 1>,
  "reasoning": "<1-2 paragraphs explaining the weighting>",
  "evidence_for": ["<bullet 1>", "<bullet 2>", "<bullet 3>"],
  "evidence_against": ["<bullet 1>", "<bullet 2>", "<bullet 3>"]
}"""


def _build_market_prompt(market: BinaryMarket, news_context: str) -> str:
    parts = [
        f"MARKET: {market.question}",
        f"PLATFORM: {market.platform}",
        f"CATEGORY: {market.category}",
    ]
    if market.close_time:
        parts.append(f"RESOLUTION DEADLINE: {market.close_time}")
    if market.yes_price is not None:
        parts.append(f"CURRENT MARKET YES PRICE: {market.yes_price:.3f}")
    if market.description:
        desc = market.description[:1500]
        parts.append(f"RESOLUTION RULES:\n{desc}")
    if news_context:
        ctx = news_context[:6000]
        parts.append(f"NEWS / CONTEXT (last 7 days):\n{ctx}")
    return "\n\n".join(parts)


# ────────────────────────────────────────────────────────────────────
# DEBATE ENGINE
# ────────────────────────────────────────────────────────────────────


def _call_haiku(system: str, user: str, max_tokens: int = 600) -> str:
    client = get_client()
    resp = client.messages.create(
        model=FAST_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return _extract_text(resp)


def _call_sonnet_json(system: str, user: str, max_tokens: int = 1200) -> dict:
    client = get_client()
    resp = client.messages.create(
        model=DEEP_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = _extract_text(resp)
    # Strip ```json fences if the model wraps them
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _coerce_probability(p) -> float:
    try:
        v = float(p)
    except (TypeError, ValueError):
        return 0.5
    # Clamp to (0.001, 0.999) — never return certainty; Brier punishes it.
    return max(0.001, min(0.999, v))


def run_event_debate(
    market: BinaryMarket,
    news_context: str = "",
) -> EventDebateOutput:
    """Run Bull/Bear/Judge on one market. Returns p_yes + reasoning.

    On any LLM failure, returns a neutral 0.5 with empty arguments so the
    caller's pipeline doesn't break — the queue.py writer marks this as
    LOW_CONFIDENCE so a human knows to skip it.
    """
    user_prompt = _build_market_prompt(market, news_context)

    try:
        bull = _call_haiku(_BULL_SYSTEM, user_prompt, max_tokens=500)
    except Exception as exc:  # noqa: BLE001
        bull = f"[bull call failed: {exc}]"

    try:
        bear = _call_haiku(_BEAR_SYSTEM, user_prompt, max_tokens=500)
    except Exception as exc:  # noqa: BLE001
        bear = f"[bear call failed: {exc}]"

    judge_input = (
        f"{user_prompt}\n\n"
        f"━━━━━ BULL ARGUMENT ━━━━━\n{bull}\n\n"
        f"━━━━━ BEAR ARGUMENT ━━━━━\n{bear}\n"
    )

    try:
        verdict = _call_sonnet_json(_JUDGE_SYSTEM, judge_input)
    except Exception as exc:  # noqa: BLE001
        verdict = {
            "p_yes": 0.5,
            "reasoning": f"[judge failed: {exc}]",
            "evidence_for": [],
            "evidence_against": [],
        }

    return EventDebateOutput(
        market_id=market.market_id,
        platform=market.platform,
        question=market.question,
        p_yes=_coerce_probability(verdict.get("p_yes")),
        bull_argument=bull,
        bear_argument=bear,
        judge_reasoning=verdict.get("reasoning", ""),
        evidence_for=list(verdict.get("evidence_for") or []),
        evidence_against=list(verdict.get("evidence_against") or []),
        market_price_at_debate=market.yes_price,
    )
