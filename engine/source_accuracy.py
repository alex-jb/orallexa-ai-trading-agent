"""
engine/source_accuracy.py
──────────────────────────────────────────────────────────────────
Per-source accuracy tracker for signal_fusion.

Records each source's score at decision time, then later (after a
forward window) checks whether that score's SIGN matched the actual
N-day return. This produces a rolling accuracy per source that the
fusion engine can use to dynamically reweight sources — sources that
have been right recently get more weight, sources that have been
wrong get less.

Why per-source: accuracy isn't uniform. Options-flow may be reliable
on big-cap tech but useless on small-caps; social_sentiment may help
during retail-mania weeks but hurt in quiet markets. Static weights
ignore this; dynamic weights track it.

Append-only JSONL store at memory_data/source_accuracy.jsonl.

Usage:
    from engine.source_accuracy import SourceAccuracy
    sa = SourceAccuracy()
    sa.record_scores("NVDA", {"technical": 40, "options_flow": 55, ...})
    # ... 5 trading days later ...
    sa.update_outcomes("NVDA", forward_return=0.03)
    accuracy = sa.get_rolling_accuracy(window=30)
    # {"technical": 0.62, "options_flow": 0.71, ...}
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PATH = _ROOT / "memory_data" / "source_accuracy.jsonl"
_NEUTRAL_THRESHOLD = 0.005  # |score| ≤ 5 or |return| ≤ 0.5% counts as neutral
_MAX_RECORDS = 10_000        # safety cap on the in-memory list


@dataclass
class _Record:
    timestamp: str
    ticker: str
    scores: dict[str, int]      # per-source score at decision time
    forward_return: Optional[float]  # filled later
    correct: Optional[dict[str, bool]]  # per-source hit/miss

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "ticker": self.ticker,
            "scores": self.scores,
            "forward_return": self.forward_return,
            "correct": self.correct,
        }


class SourceAccuracy:
    """Per-source accuracy ledger backed by JSONL on disk."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        self._records: list[dict] = self._load()

    # ── Persistence ───────────────────────────────────────────────────────

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            records: list[dict] = []
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            # Cap to most recent N to bound memory
            return records[-_MAX_RECORDS:]
        except OSError:
            return []

    def _append(self, record: dict) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Failed to append source accuracy: %s", e)

    def _rewrite_all(self) -> None:
        """Rewrite the file from in-memory state — used after outcome updates."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                tmp = self._path.with_suffix(".jsonl.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    for r in self._records:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                tmp.replace(self._path)
        except OSError as e:
            logger.warning("Failed to rewrite source accuracy: %s", e)

    # ── API ───────────────────────────────────────────────────────────────

    def record_scores(
        self,
        ticker: str,
        scores: dict[str, int],
        *,
        timestamp: Optional[str] = None,
    ) -> None:
        """Record the per-source scores at decision time. Outcome filled later."""
        rec = {
            "timestamp": timestamp or datetime.now().isoformat(),
            "ticker": ticker.upper(),
            "scores": {k: int(v) for k, v in scores.items() if isinstance(v, (int, float))},
            "forward_return": None,
            "correct": None,
        }
        self._records.append(rec)
        if len(self._records) > _MAX_RECORDS:
            self._records = self._records[-_MAX_RECORDS:]
        self._append(rec)

    def update_outcomes(
        self,
        ticker: str,
        forward_return: float,
        *,
        threshold: float = _NEUTRAL_THRESHOLD,
    ) -> int:
        """
        Fill in outcomes for ALL pending records of `ticker` using the same
        forward_return value. Returns the number of records updated.
        """
        updated = 0
        actual_dir = (
            1 if forward_return > threshold
            else -1 if forward_return < -threshold
            else 0
        )
        for r in self._records:
            if r["ticker"] != ticker.upper() or r["correct"] is not None:
                continue
            r["forward_return"] = round(float(forward_return), 4)
            r["correct"] = {}
            for src, score in r["scores"].items():
                src_dir = 1 if score > 5 else -1 if score < -5 else 0
                if actual_dir == 0:
                    r["correct"][src] = (src_dir == 0)
                else:
                    r["correct"][src] = (src_dir == actual_dir)
            updated += 1
        if updated:
            self._rewrite_all()
        return updated

    def get_rolling_accuracy(
        self,
        *,
        window: int = 50,
        min_samples: int = 5,
    ) -> dict[str, float]:
        """
        Per-source accuracy over the last `window` evaluated records.

        Returns {source: accuracy ∈ [0,1]} for sources with at least
        `min_samples` evaluated records. Sources below the threshold are
        omitted (caller should fall back to the default weight).
        """
        evaluated = [r for r in self._records if r.get("correct") is not None]
        recent = evaluated[-window:]
        if not recent:
            return {}

        per_source_correct: dict[str, int] = {}
        per_source_total: dict[str, int] = {}
        for r in recent:
            for src, ok in (r.get("correct") or {}).items():
                per_source_total[src] = per_source_total.get(src, 0) + 1
                if ok:
                    per_source_correct[src] = per_source_correct.get(src, 0) + 1

        out: dict[str, float] = {}
        for src, total in per_source_total.items():
            if total >= min_samples:
                out[src] = round(per_source_correct.get(src, 0) / total, 4)
        return out

    def stats_per_source(self, *, window: int = 50) -> dict[str, dict]:
        """Detailed per-source stats (n, correct, accuracy) over the window."""
        evaluated = [r for r in self._records if r.get("correct") is not None]
        recent = evaluated[-window:]
        out: dict[str, dict] = {}
        for r in recent:
            for src, ok in (r.get("correct") or {}).items():
                d = out.setdefault(src, {"n": 0, "correct": 0})
                d["n"] += 1
                if ok:
                    d["correct"] += 1
        for src, d in out.items():
            d["accuracy"] = round(d["correct"] / d["n"], 4) if d["n"] > 0 else None
        return out
