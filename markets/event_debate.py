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
class CriticOutput:
    """Critic agent's audit of the Bull/Bear/Judge chain.

    Inspired by yorkeccak/Polyseer (2026-05): a 5th "Critic" agent that
    reads ALL 3 prior outputs (bull / bear / judge) and flags structural
    failures the Judge missed:

      - same-source bias (both Bull and Bear cite the same news article)
      - missing base-rate anchor (Judge gave a probability without
        citing what comparable historical events resolved at)
      - unverifiable claims (specific dollar/date claims that no public
        source could confirm in the debate window)
      - confirmation drift (Judge p_yes leans the way of the more
        verbose argument rather than the better-evidenced one)

    The Critic does NOT replace the Judge's probability. It either:
      1. confirms the probability is well-supported  (verdict="OK"), or
      2. recommends adding a caveat to the queue card (verdict="CAVEAT"), or
      3. recommends rejecting the debate entirely    (verdict="REJECT")

    The queue writer surfaces critic output regardless — humans read the
    caveats and decide. The Critic never silently mutates p_yes.
    """
    verdict: str                          # "OK" / "CAVEAT" / "REJECT"
    failure_modes: list[str] = field(default_factory=list)
    same_source_overlap: bool = False
    missing_base_rate: bool = False
    unverifiable_claims: list[str] = field(default_factory=list)
    confirmation_drift: bool = False
    summary: str = ""                     # 1-3 sentence final note for the queue card

    def to_dict(self) -> dict:
        return asdict(self)


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

    # Critic verdict (added 2026-05-11 — Polyseer 5th-agent pattern)
    critic: Optional[CriticOutput] = None

    @property
    def edge(self) -> Optional[float]:
        """p_yes - market_price. Positive means we think YES is underpriced."""
        if self.market_price_at_debate is None:
            return None
        return self.p_yes - self.market_price_at_debate

    @property
    def has_critic_concerns(self) -> bool:
        """True if Critic flagged anything worth surfacing to HITL queue."""
        return self.critic is not None and self.critic.verdict != "OK"

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


_CRITIC_SYSTEM = """You are the Critic — the 5th voice in a binary-market \
debate. You read the original market question, the Bull argument, the \
Bear argument, and the Judge's probability + reasoning. You do NOT \
output a new probability. Your job is to AUDIT the debate for structural \
failures the Judge may have missed:

1. **Same-source bias**: do Bull and Bear cite the same news article / \
event / source? If both arguments rest on the same single source, the \
probability is unreliable — there's no actual disagreement, just two \
framings of one input.

2. **Missing base-rate anchor**: did the Judge cite a historical base \
rate for similar events (e.g. "in the last 30 years, peace deals signed \
within 7 days of an announcement = 0 of 12")? If the probability has no \
base-rate anchor, it's a vibe-check.

3. **Unverifiable claims**: list any specific dollar / date / quote \
claims in Bull or Bear that no public source could confirm within the \
debate window. These deserve a caveat in the queue card.

4. **Confirmation drift**: did the Judge probability lean toward the \
more verbose / confident argument rather than the better-evidenced one? \
Word count and certainty are NOT evidence.

5. **Outside-knowledge gap**: did either side cite knowledge the Judge \
could not verify? (E.g. "as everyone knows...", "industry sources say...")

Output STRICT JSON only. No prose outside the JSON block.

Required JSON shape:
{
  "verdict": "OK" | "CAVEAT" | "REJECT",
  "failure_modes": ["<short bullet>", ...],
  "same_source_overlap": true|false,
  "missing_base_rate": true|false,
  "unverifiable_claims": ["<claim>", ...],
  "confirmation_drift": true|false,
  "summary": "<1-3 sentences for the HITL queue card>"
}

Use "OK" if the debate is well-grounded.
Use "CAVEAT" if there are minor issues — the queue card should surface them but the probability is still informative.
Use "REJECT" only if the debate is structurally broken (e.g. both sides cited the same single source AND there's no base rate AND no verifiable claim). Reject means "do not act on this signal; the system should re-run with a different news_context or skip the market"."""


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


def _call_haiku_json(system: str, user: str, max_tokens: int = 1000) -> dict:
    """Same as _call_sonnet_json but uses Haiku (cheap, fine for audit task).

    Critic uses Haiku because the audit is mechanical pattern-matching
    against a checklist — doesn't need Sonnet-level reasoning. Saves
    ~$0.004/debate.
    """
    client = get_client()
    resp = client.messages.create(
        model=FAST_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = _extract_text(resp)
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _parse_critic(raw: dict) -> CriticOutput:
    """Coerce raw Critic JSON into a CriticOutput. Defensive against
    missing/wrong-typed fields.
    """
    verdict_raw = str(raw.get("verdict") or "OK").upper()
    if verdict_raw not in ("OK", "CAVEAT", "REJECT"):
        verdict_raw = "OK"

    def _str_list(x) -> list[str]:
        if not isinstance(x, list):
            return []
        return [str(s) for s in x if s]

    return CriticOutput(
        verdict=verdict_raw,
        failure_modes=_str_list(raw.get("failure_modes")),
        same_source_overlap=bool(raw.get("same_source_overlap")),
        missing_base_rate=bool(raw.get("missing_base_rate")),
        unverifiable_claims=_str_list(raw.get("unverifiable_claims")),
        confirmation_drift=bool(raw.get("confirmation_drift")),
        summary=str(raw.get("summary") or ""),
    )


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

    # 5th voice: Critic audits the entire chain. Reads Bull + Bear + Judge
    # output and flags structural failures (same-source bias, missing base
    # rate, unverifiable claims). Never mutates p_yes — only surfaces
    # caveats for the HITL queue card.
    critic_input = (
        f"{user_prompt}\n\n"
        f"━━━━━ BULL ARGUMENT ━━━━━\n{bull}\n\n"
        f"━━━━━ BEAR ARGUMENT ━━━━━\n{bear}\n\n"
        f"━━━━━ JUDGE VERDICT ━━━━━\n"
        f"p_yes = {verdict.get('p_yes')}\n"
        f"reasoning: {verdict.get('reasoning', '')}\n"
        f"evidence_for: {verdict.get('evidence_for') or []}\n"
        f"evidence_against: {verdict.get('evidence_against') or []}\n"
    )

    try:
        critic_raw = _call_haiku_json(_CRITIC_SYSTEM, critic_input)
        critic = _parse_critic(critic_raw)
    except Exception as exc:  # noqa: BLE001
        critic = CriticOutput(
            verdict="OK",
            summary=f"[critic call failed: {exc} — no audit available]",
        )

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
        critic=critic,
    )
