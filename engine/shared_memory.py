"""
engine/shared_memory.py
──────────────────────────────────────────────────────────────────
CORAL-inspired shared persistent memory.

The CORAL paper (2026) showed that self-evolving multi-agent systems
with **shared** persistent memory outperform fixed-baseline agents
3-10× because each agent's predictions inform the others. We already
have two memory modules — engine/role_memory.py (per-role prediction
log + accuracy stats) and engine/layered_memory.py (recency-tiered
short/mid/long buckets). This wraps them under a unified read API.

Design:
    SharedMemory(role_mem=..., layered_mem=...)
        .summary_for(role, ticker)   → one-line context for prompt injection
        .full_context(role, ticker)  → richer dict for analytics
        .similar_situations(ticker)  → cross-role: what other roles thought
                                        about this ticker recently

The store-side stays in the existing modules — we don't move data.
This is purely a read aggregator so prompts can ask one question
("what should I know about NVDA before I predict?") and get fused
context from both stores.

Usage:
    from engine.shared_memory import SharedMemory
    mem = SharedMemory()
    line = mem.summary_for("Conservative Analyst", "NVDA")
    # → "Conservative Analyst on NVDA: 65% accuracy (12 records).
    #    Tier breakdown — short: 50% (4) | mid: 71% (7) | long: 80% (5).
    #    Other roles: Aggressive bullish (last 3, 67% acc); Quant bearish."
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SharedMemory:
    """Read aggregator over role_memory + layered_memory."""

    def __init__(self, role_mem=None, layered_mem=None):
        self._role_mem = role_mem
        self._layered_mem = layered_mem

    def _ensure_role_mem(self):
        if self._role_mem is None:
            try:
                from engine.role_memory import RoleMemory
                self._role_mem = RoleMemory()
            except Exception as e:
                logger.debug("RoleMemory unavailable: %s", e)
                self._role_mem = False  # negative cache
        return self._role_mem if self._role_mem is not False else None

    def _ensure_layered_mem(self):
        if self._layered_mem is None:
            try:
                from engine.layered_memory import LayeredMemory
                self._layered_mem = LayeredMemory()
            except Exception as e:
                logger.debug("LayeredMemory unavailable: %s", e)
                self._layered_mem = False
        return self._layered_mem if self._layered_mem is not False else None

    # ── One-line summary for prompt injection ────────────────────────────

    def summary_for(self, role: str, ticker: str) -> str:
        """
        Return a short multi-line summary for `role` on `ticker`. Empty
        string if neither memory has anything useful.
        """
        parts: list[str] = []

        rm = self._ensure_role_mem()
        if rm is not None:
            try:
                ctx = rm.get_role_context(role, ticker)
                if ctx and "Insufficient" not in ctx:
                    parts.append(ctx)
            except Exception:
                pass

        lm = self._ensure_layered_mem()
        if lm is not None:
            try:
                narr = lm.narrative(role, ticker)
                if narr and "Insufficient" not in narr:
                    parts.append(narr)
            except Exception:
                pass

        cross = self.cross_role_consensus(ticker, exclude_role=role)
        if cross:
            parts.append(cross)

        return "\n".join(parts)

    # ── Cross-role: what did OTHER roles say about this ticker? ──────────

    def cross_role_consensus(
        self,
        ticker: str,
        *,
        exclude_role: Optional[str] = None,
        window: int = 30,
    ) -> str:
        """
        Pull the last `window` predictions on this ticker from layered
        memory across ALL roles except the excluded one. Returns a
        terse summary like:
            "Other roles on NVDA (last 30 days): 8 BULLISH / 2 BEARISH;
             Aggressive: 75% accurate, Macro: 50%."
        """
        lm = self._ensure_layered_mem()
        if lm is None:
            return ""

        try:
            records = [
                r for r in getattr(lm, "_data", {}).get("records", [])
                if r.get("ticker", "").upper() == ticker.upper()
                and (exclude_role is None or r.get("role") != exclude_role)
            ]
        except Exception:
            return ""

        if not records:
            return ""

        # Tally bias counts
        tally = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
        per_role: dict[str, dict] = {}
        for r in records[-window:]:
            bias = str(r.get("bias", "")).upper()
            if bias in tally:
                tally[bias] += 1
            role = str(r.get("role", "unknown"))
            d = per_role.setdefault(role, {"n": 0, "correct": 0})
            d["n"] += 1
            if r.get("correct") is True:
                d["correct"] += 1

        # Per-role accuracy strings, only when we have ≥3 evaluated calls
        acc_parts = []
        for role, d in per_role.items():
            evaluated = d["n"]
            if evaluated >= 3 and d["correct"] > 0:
                acc = d["correct"] / evaluated
                acc_parts.append(f"{role}: {int(acc * 100)}% acc ({evaluated})")

        bias_part = (
            f"{tally['BULLISH']} BULLISH / {tally['BEARISH']} BEARISH "
            f"/ {tally['NEUTRAL']} NEUTRAL"
        )
        roles_part = "; ".join(acc_parts) if acc_parts else "no per-role accuracy yet"
        return (
            f"Other roles on {ticker} (last {window}): {bias_part}. {roles_part}."
        )

    # ── Full context dict for downstream analytics ───────────────────────

    def full_context(self, role: str, ticker: str) -> dict:
        """Structured dict with both role + layered + cross-role data."""
        out: dict = {"role": role, "ticker": ticker}
        rm = self._ensure_role_mem()
        if rm is not None:
            try:
                out["role_memory"] = rm.get_role_context(role, ticker)
            except Exception:
                pass
        lm = self._ensure_layered_mem()
        if lm is not None:
            try:
                out["layered_tiers"] = lm.get_tiered_context(role, ticker)
                out["layered_narrative"] = lm.narrative(role, ticker)
            except Exception:
                pass
        cross = self.cross_role_consensus(ticker, exclude_role=role)
        if cross:
            out["cross_role"] = cross
        return out
