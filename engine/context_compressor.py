"""
engine/context_compressor.py
──────────────────────────────────────────────────────────────────
Compress prior agent outputs before feeding them into the next agent.

Pattern source: 2026 'context engineering' literature (Anthropic +
Weaviate + arxiv 2510.04618). Multi-agent chains accumulate text
faster than the value of any single token. Compressing intermediate
outputs to extractive or LLM-generated summaries keeps the final
agent (Judge, Risk Manager) inside its useful attention window.

Two strategies:

  extractive_summary(text, max_chars=600)
    Pure-Python, deterministic, no LLM. Keeps the first/last
    sentences plus any sentences containing numbers (prices, %s,
    dates) or directional keywords (bullish/bearish/breakout).
    Fast (<1ms), zero-cost. Loses nuance but preserves the spine
    of the analysis.

  llm_summary(text, ticker, max_tokens=200)
    Single FAST_MODEL call asking for a 2-3 sentence digest. ~$0.0005
    per call. Use for high-value reports (deep market analysis,
    investment narrative) where extractive summary loses too much.

  compress(text, mode="auto", ...)
    Auto picks extractive when text < 1500 chars (already short
    enough), else LLM. Override with mode="extractive" / "llm" / "off".

Usage:
    from engine.context_compressor import compress
    short = compress(market_report, mode="extractive", max_chars=500)
    short = compress(deep_analysis, mode="llm", ticker="NVDA")
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


_DIRECTIONAL_KEYWORDS = (
    "bullish", "bearish", "breakout", "breakdown", "rally", "selloff",
    "support", "resistance", "uptrend", "downtrend", "reversal",
    "buy", "sell", "long", "short",
    "beat", "miss", "exceed", "outperform", "underperform",
    "stop loss", "take profit", "target", "entry",
    "high conviction", "low conviction",
    "warning", "risk", "caution",
)
_NUMBER_RE = re.compile(r"\d")
_AUTO_LLM_THRESHOLD = 1500   # chars — below this, extractive is enough


def extractive_summary(text: str, max_chars: int = 600) -> str:
    """
    Deterministic extractive compression. Keeps the first sentence,
    last sentence, and any sentences with numbers or directional
    keywords up to `max_chars` budget. No LLM calls.
    """
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text

    # Sentence split — simple and good enough for English/finance text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) <= 2:
        return text[:max_chars].rstrip() + "…"

    keep_idx: set[int] = {0, len(sentences) - 1}
    for i, s in enumerate(sentences[1:-1], start=1):
        s_lower = s.lower()
        if _NUMBER_RE.search(s) or any(kw in s_lower for kw in _DIRECTIONAL_KEYWORDS):
            keep_idx.add(i)

    selected = [sentences[i] for i in sorted(keep_idx)]
    out = " ".join(selected)

    if len(out) <= max_chars:
        return out
    # Still too long — drop middle items by prioritizing first/last/numerics
    while len(out) > max_chars and len(selected) > 2:
        # Drop the middle-most non-numeric sentence
        mid = len(selected) // 2
        for offset in range(0, len(selected) // 2):
            for cand in (mid + offset, mid - offset):
                if 0 < cand < len(selected) - 1:
                    if not _NUMBER_RE.search(selected[cand]):
                        selected.pop(cand)
                        out = " ".join(selected)
                        break
            if len(out) <= max_chars:
                break
        else:
            # Couldn't find a non-numeric to drop — just truncate
            return out[:max_chars].rstrip() + "…"

    return out if len(out) <= max_chars else out[:max_chars].rstrip() + "…"


def llm_summary(
    text: str,
    *,
    ticker: Optional[str] = None,
    max_tokens: int = 200,
) -> str:
    """
    LLM-based compression via FAST_MODEL. Returns the original text
    on any failure so the caller never silently loses information.
    """
    if not text or len(text) < 200:
        return text

    try:
        from llm.claude_client import FAST_MODEL, get_client
        from llm.call_logger import logged_create

        ctx_line = f" about {ticker}" if ticker else ""
        prompt = (
            f"Summarize this trading analysis{ctx_line} in 2-3 sentences. "
            f"Keep numbers, directional verdict, and any explicit risk flags. "
            f"Drop hedging prose. No preamble.\n\n---\n{text}\n---"
        )
        client = get_client()
        response, _ = logged_create(
            client,
            request_type="context_compression",
            model=FAST_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            ticker=ticker,
        )
        out = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                out += block.text
        out = out.strip()
        # Sanity: never return empty, never return more than ~3x the requested cap
        if not out or len(out) > max_tokens * 6:
            return text
        return out
    except Exception as e:
        logger.debug("LLM compression failed, returning original: %s", e)
        return text


def compress(
    text: str,
    *,
    mode: str = "auto",
    max_chars: int = 600,
    ticker: Optional[str] = None,
) -> str:
    """
    Compress `text` according to `mode`:
        "extractive"  — pure-Python, fast, deterministic
        "llm"         — FAST_MODEL summary (costs ~$0.0005)
        "auto"        — extractive if text < 1500 chars, else llm
        "off"         — return unchanged
    """
    if mode == "off" or not text:
        return text or ""
    if mode == "extractive":
        return extractive_summary(text, max_chars=max_chars)
    if mode == "llm":
        return llm_summary(text, ticker=ticker, max_tokens=max_chars // 3)
    if mode == "auto":
        if len(text) < _AUTO_LLM_THRESHOLD:
            return extractive_summary(text, max_chars=max_chars)
        return llm_summary(text, ticker=ticker, max_tokens=max_chars // 3)
    raise ValueError(f"Unknown compression mode: {mode}")


def compression_ratio(original: str, compressed: str) -> float:
    """Helper: chars compressed / chars original. 1.0 = no shrinkage."""
    if not original:
        return 1.0
    return round(len(compressed) / len(original), 3)
