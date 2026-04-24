"""
engine/layered_memory.py
──────────────────────────────────────────────────────────────────
FinMem-inspired layered memory: bucket predictions by recency tier
(short / mid / long) with tier-specific retention + accuracy metrics.

Why layers? Accuracy is not uniform across time scales. A role might
be 45% accurate on ≤7-day calls but 72% on 30+ day calls. Mixing them
in one pool hides that signal. When generating a new prediction, we
surface per-tier accuracy so the role can weight toward its strengths.

Sits ALONGSIDE engine/role_memory.py — we read from its prediction
log, compute tiered views on demand, and cache to disk separately.

Usage:
    from engine.layered_memory import LayeredMemory
    lm = LayeredMemory()
    lm.record("Conservative Analyst", "NVDA", "BEARISH",
              score=-30, conviction=70)
    ctx = lm.get_tiered_context("Conservative Analyst", "NVDA")
    # {"short_term": {"accuracy": 0.45, "n": 4}, ...}
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_MEMORY_PATH = _ROOT / "memory_data" / "layered_memory.json"


@dataclass(frozen=True)
class Tier:
    name: str
    min_age_days: float
    max_age_days: float
    max_records: int


# Tier boundaries follow FinMem's three-scale decomposition.
# Note: the buckets partition time by record age; new records start in short.
TIERS: tuple[Tier, ...] = (
    Tier("short_term", min_age_days=0,  max_age_days=7,    max_records=100),
    Tier("mid_term",   min_age_days=7,  max_age_days=30,   max_records=200),
    Tier("long_term",  min_age_days=30, max_age_days=9999, max_records=500),
)


class LayeredMemory:
    """Recency-tiered persistent memory for role predictions."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or _MEMORY_PATH
        self._data = self._load()

    # ── Persistence ───────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"records": [], "updated_at": None}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._data["updated_at"] = datetime.now().isoformat()
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.warning("Failed to save layered memory: %s", e)

    # ── API ───────────────────────────────────────────────────────────────

    def record(
        self,
        role: str,
        ticker: str,
        bias: str,
        *,
        score: int = 0,
        conviction: int = 0,
        reasoning: str = "",
        timestamp: Optional[str] = None,
    ) -> None:
        """Append a new prediction. Records start in short_term automatically."""
        self._data["records"].append({
            "timestamp": timestamp or datetime.now().isoformat(),
            "role": role,
            "ticker": ticker,
            "bias": bias,
            "score": int(score),
            "conviction": int(conviction),
            "reasoning": reasoning[:200],
            "outcome": None,
            "correct": None,
            "forward_return": None,
        })
        self._prune()
        self._save()

    def update_outcome(
        self,
        role: str,
        ticker: str,
        forward_return: float,
        *,
        threshold: float = 0.02,
    ) -> int:
        """
        Fill in `outcome`/`correct`/`forward_return` for pending predictions
        matching (role, ticker). Returns the number of records updated.
        """
        updated = 0
        for r in self._data["records"]:
            if r["role"] != role or r["ticker"] != ticker:
                continue
            if r["correct"] is not None:
                continue
            outcome = (
                "BULLISH" if forward_return > threshold
                else "BEARISH" if forward_return < -threshold
                else "NEUTRAL"
            )
            r["outcome"] = outcome
            r["forward_return"] = round(float(forward_return), 4)
            r["correct"] = (r["bias"] == outcome)
            updated += 1
        if updated:
            self._save()
        return updated

    def get_tiered_context(
        self,
        role: str,
        ticker: Optional[str] = None,
        *,
        now: Optional[datetime] = None,
    ) -> dict:
        """
        Return per-tier accuracy stats for a role (optionally ticker-scoped).

        Each tier entry: {n, correct, pending, accuracy, avg_conviction}.
        """
        now = now or datetime.now()
        out: dict = {}

        role_records = [
            r for r in self._data["records"]
            if r["role"] == role and (ticker is None or r["ticker"] == ticker)
        ]

        for tier in TIERS:
            in_tier = [
                r for r in role_records
                if _age_days(r["timestamp"], now=now, default=0.0) >= tier.min_age_days
                and _age_days(r["timestamp"], now=now, default=0.0) < tier.max_age_days
            ]
            evaluated = [r for r in in_tier if r["correct"] is not None]
            correct = sum(1 for r in evaluated if r["correct"])
            n_eval = len(evaluated)
            pending = len(in_tier) - n_eval
            accuracy = correct / n_eval if n_eval > 0 else None
            avg_conv = (
                sum(r["conviction"] for r in in_tier) / len(in_tier)
                if in_tier else 0
            )
            out[tier.name] = {
                "n": len(in_tier),
                "correct": correct,
                "pending": pending,
                "accuracy": round(accuracy, 3) if accuracy is not None else None,
                "avg_conviction": round(avg_conv, 1),
            }
        return out

    def narrative(self, role: str, ticker: Optional[str] = None) -> str:
        """One-liner summary of tiered accuracy for injection into prompts."""
        ctx = self.get_tiered_context(role, ticker)
        parts = []
        for tier in TIERS:
            t = ctx[tier.name]
            if t["accuracy"] is not None and t["n"] >= 3:
                pct = int(t["accuracy"] * 100)
                parts.append(f"{tier.name}: {pct}% ({t['n']} records)")
        if not parts:
            return "Insufficient history for tier analysis."
        scope = f" on {ticker}" if ticker else ""
        return f"{role} accuracy{scope} — " + " | ".join(parts)

    # ── Internals ─────────────────────────────────────────────────────────

    def _prune(self) -> None:
        """Drop oldest records once each tier exceeds its cap."""
        now = datetime.now()
        records = self._data["records"]
        for tier in TIERS:
            in_tier = [
                i for i, r in enumerate(records)
                if _age_days(r["timestamp"], now=now, default=0.0) >= tier.min_age_days
                and _age_days(r["timestamp"], now=now, default=0.0) < tier.max_age_days
            ]
            if len(in_tier) > tier.max_records:
                # oldest first
                in_tier.sort(key=lambda i: records[i]["timestamp"])
                to_drop = set(in_tier[: len(in_tier) - tier.max_records])
                self._data["records"] = [
                    r for i, r in enumerate(records) if i not in to_drop
                ]
                records = self._data["records"]


def _age_days(ts: str, *, now: datetime, default: float = 0.0) -> float:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return (now - dt).total_seconds() / 86_400.0
    except Exception:
        return default
