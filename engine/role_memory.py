"""
engine/role_memory.py
──────────────────────────────────────────────────────────────────
Persistent Role Memory for Perspective Panel agents.

Each role (Conservative Analyst, Aggressive Trader, etc.) develops
memory of past predictions and their outcomes. Over time, roles
learn which tickers/conditions they're good or bad at predicting.

Inspired by MiroFish's Zep Cloud agent memory — simplified to
local JSON persistence with per-role accuracy tracking.

Usage:
    from engine.role_memory import RoleMemory
    mem = RoleMemory()
    mem.record_prediction("Conservative Analyst", "NVDA", "BEARISH", -30, 70)
    mem.update_outcomes("NVDA", actual_return=0.05)   # 5 days later
    context = mem.get_role_context("Conservative Analyst", "NVDA")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_MEMORY_PATH = _ROOT / "memory_data" / "role_memory.json"
_MAX_RECORDS_PER_ROLE = 200


class RoleMemory:
    """Persistent memory store for perspective panel roles."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or _MEMORY_PATH
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"roles": {}, "updated_at": None}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._data["updated_at"] = datetime.now().isoformat()
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.warning("Failed to save role memory: %s", e)

    def _ensure_role(self, role: str) -> dict:
        if role not in self._data["roles"]:
            self._data["roles"][role] = {
                "predictions": [],
                "stats": {
                    "total": 0, "correct": 0,
                    "by_ticker": {},
                    "by_bias": {"BULLISH": {"total": 0, "correct": 0},
                                "BEARISH": {"total": 0, "correct": 0},
                                "NEUTRAL": {"total": 0, "correct": 0}},
                    "avg_conviction": 0,
                    "calibration_error": 0,
                },
            }
        return self._data["roles"][role]

    # ── Record a new prediction ──────────────────────────────────────────

    def record_prediction(
        self,
        role: str,
        ticker: str,
        bias: str,
        score: int,
        conviction: int,
        reasoning: str = "",
        key_factor: str = "",
    ) -> None:
        """Record a role's prediction for later evaluation."""
        role_data = self._ensure_role(role)
        role_data["predictions"].append({
            "timestamp": datetime.now().isoformat(),
            "ticker": ticker,
            "bias": bias,
            "score": score,
            "conviction": conviction,
            "reasoning": reasoning[:200],
            "key_factor": key_factor[:100],
            "outcome": None,       # filled later
            "correct": None,       # filled later
            "forward_return": None, # filled later
        })
        # Cap history
        role_data["predictions"] = role_data["predictions"][-_MAX_RECORDS_PER_ROLE:]
        self._save()

    # ── Update outcomes ──────────────────────────────────────────────────

    def update_outcomes(
        self,
        ticker: str,
        actual_return: float,
        lookback_days: int = 7,
    ) -> int:
        """
        Update unresolved predictions for a ticker with actual returns.
        Returns count of predictions updated.
        """
        cutoff = datetime.now() - timedelta(days=lookback_days)
        updated = 0

        for role_name, role_data in self._data.get("roles", {}).items():
            for pred in role_data.get("predictions", []):
                if pred["ticker"] != ticker:
                    continue
                if pred["outcome"] is not None:
                    continue
                try:
                    ts = datetime.fromisoformat(pred["timestamp"])
                    if ts < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue

                # Determine if prediction was correct
                bias = pred["bias"]
                correct = (
                    (bias == "BULLISH" and actual_return > 0.005) or
                    (bias == "BEARISH" and actual_return < -0.005) or
                    (bias == "NEUTRAL" and abs(actual_return) < 0.02)
                )

                pred["outcome"] = "correct" if correct else "wrong"
                pred["correct"] = correct
                pred["forward_return"] = round(actual_return, 4)
                updated += 1

                # Update stats
                stats = role_data["stats"]
                stats["total"] += 1
                if correct:
                    stats["correct"] += 1

                # By ticker
                if ticker not in stats["by_ticker"]:
                    stats["by_ticker"][ticker] = {"total": 0, "correct": 0, "avg_return": 0}
                tk_stats = stats["by_ticker"][ticker]
                tk_stats["total"] += 1
                if correct:
                    tk_stats["correct"] += 1
                n = tk_stats["total"]
                tk_stats["avg_return"] = round(
                    ((n - 1) * tk_stats["avg_return"] + actual_return) / n, 4
                )

                # By bias direction
                if bias in stats["by_bias"]:
                    stats["by_bias"][bias]["total"] += 1
                    if correct:
                        stats["by_bias"][bias]["correct"] += 1

        if updated > 0:
            self._save()
        return updated

    def update_outcomes_batch(self, forward_days: int = 5) -> int:
        """Auto-update all pending predictions using yfinance."""
        pending: dict[str, list] = {}
        cutoff = datetime.now() - timedelta(days=forward_days + 2)

        for role_data in self._data.get("roles", {}).values():
            for pred in role_data.get("predictions", []):
                if pred["outcome"] is not None:
                    continue
                try:
                    ts = datetime.fromisoformat(pred["timestamp"])
                    if ts > cutoff:
                        continue  # too recent
                except (ValueError, TypeError):
                    continue
                tk = pred["ticker"]
                if tk not in pending:
                    pending[tk] = []
                pending[tk].append(pred["timestamp"])

        if not pending:
            return 0

        total_updated = 0
        try:
            import yfinance as yf
            for ticker, timestamps in pending.items():
                try:
                    sorted_ts = sorted(timestamps)
                    start = sorted_ts[0][:10]
                    end_dt = datetime.strptime(sorted_ts[-1][:10], "%Y-%m-%d") + timedelta(days=forward_days + 10)
                    df = yf.download(ticker, start=start, end=str(end_dt.date()), progress=False)
                    if df is None or len(df) < 2:
                        continue

                    close_col = "Close" if "Close" in df.columns else "Adj Close"

                    for ts_str in timestamps:
                        try:
                            target = datetime.fromisoformat(ts_str).date()
                            mask = df.index.date >= target
                            if not mask.any():
                                continue
                            entry_idx = df.index[mask][0]
                            entry_pos = df.index.get_loc(entry_idx)
                            exit_pos = min(entry_pos + forward_days, len(df) - 1)
                            if exit_pos <= entry_pos:
                                continue

                            entry_price = float(df[close_col].iloc[entry_pos])
                            exit_price = float(df[close_col].iloc[exit_pos])
                            if hasattr(entry_price, '__len__'):
                                entry_price = float(entry_price[0])
                            if hasattr(exit_price, '__len__'):
                                exit_price = float(exit_price[0])

                            ret = (exit_price - entry_price) / entry_price
                            total_updated += self.update_outcomes(ticker, ret, lookback_days=forward_days + 5)
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug("Batch update failed for %s: %s", ticker, e)
        except ImportError:
            pass

        return total_updated

    # ── Get role context for LLM injection ───────────────────────────────

    def get_role_context(self, role: str, ticker: str) -> str:
        """
        Generate a compact memory context string for a role's prompt.
        Injected so the role can self-correct based on past performance.
        """
        if role not in self._data.get("roles", {}):
            return ""

        role_data = self._data["roles"][role]
        stats = role_data.get("stats", {})

        if stats.get("total", 0) < 3:
            return ""

        lines = [f"YOUR TRACK RECORD ({role}):"]

        # Overall accuracy
        total = stats["total"]
        correct = stats["correct"]
        acc = correct / total if total > 0 else 0
        lines.append(f"Overall: {acc:.0%} accuracy ({correct}/{total} correct)")

        # Ticker-specific
        tk_stats = stats.get("by_ticker", {}).get(ticker)
        if tk_stats and tk_stats["total"] >= 2:
            tk_acc = tk_stats["correct"] / tk_stats["total"]
            lines.append(
                f"{ticker}: {tk_acc:.0%} accuracy ({tk_stats['correct']}/{tk_stats['total']}), "
                f"avg return: {tk_stats['avg_return']:+.2%}"
            )
            if tk_acc < 0.4:
                lines.append(f"⚠ You have been WRONG more often than right on {ticker} — adjust your confidence down")
            elif tk_acc > 0.7:
                lines.append(f"✓ Strong track record on {ticker} — your edge is validated")

        # By bias direction
        by_bias = stats.get("by_bias", {})
        for direction in ("BULLISH", "BEARISH"):
            b = by_bias.get(direction, {})
            if b.get("total", 0) >= 3:
                b_acc = b["correct"] / b["total"]
                if b_acc < 0.4:
                    lines.append(f"⚠ Your {direction} calls are weak ({b_acc:.0%}) — be more cautious on {direction}")

        # Recent track record (last 5 resolved for this ticker)
        recent = [
            p for p in role_data.get("predictions", [])
            if p["ticker"] == ticker and p["outcome"] is not None
        ][-5:]
        if recent:
            streak = " → ".join(
                f"{'✓' if p['correct'] else '✗'}{p['bias'][0]}"
                for p in recent
            )
            lines.append(f"Recent {ticker}: {streak}")

        return "\n".join(lines)

    # ── Get summary for all roles ────────────────────────────────────────

    def get_all_role_stats(self) -> dict:
        """Return summary stats for all roles (for frontend display)."""
        result = {}
        for role_name, role_data in self._data.get("roles", {}).items():
            stats = role_data.get("stats", {})
            total = stats.get("total", 0)
            correct = stats.get("correct", 0)

            # Best/worst tickers
            by_ticker = stats.get("by_ticker", {})
            best_ticker = None
            worst_ticker = None
            if by_ticker:
                sorted_tickers = sorted(
                    [(tk, s) for tk, s in by_ticker.items() if s["total"] >= 2],
                    key=lambda x: x[1]["correct"] / x[1]["total"] if x[1]["total"] > 0 else 0,
                )
                if sorted_tickers:
                    worst_ticker = {
                        "ticker": sorted_tickers[0][0],
                        "accuracy": round(sorted_tickers[0][1]["correct"] / sorted_tickers[0][1]["total"], 3),
                    }
                    best_ticker = {
                        "ticker": sorted_tickers[-1][0],
                        "accuracy": round(sorted_tickers[-1][1]["correct"] / sorted_tickers[-1][1]["total"], 3),
                    }

            result[role_name] = {
                "total": total,
                "correct": correct,
                "accuracy": round(correct / total, 3) if total > 0 else 0,
                "by_bias": stats.get("by_bias", {}),
                "best_ticker": best_ticker,
                "worst_ticker": worst_ticker,
            }
        return result
