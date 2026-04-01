"""
bot/config.py
──────────────────────────────────────────────────────────────────────────────
Bot profile manager — persistent user preferences and skill weights.

The profile stores:
  - preferred trading mode / timeframe
  - aggressiveness (0.0–1.0)
  - risk tolerance (low / medium / high)
  - skill weights per mode
  - confidence adjustments per mode
  - common mistakes / preferred setups (updated by behavior learning)
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_PROFILE: dict = {
    "preferred_mode":      "intraday",
    "preferred_timeframe": "15m",
    "aggressiveness":      0.5,
    "risk_tolerance":      "medium",    # low / medium / high
    "common_mistakes":     [],
    "preferred_setups":    [],
    "skill_weights": {
        "scalp": {
            "structure":    0.35,
            "volume":       0.30,
            "risk_filter":  0.35,
        },
        "intraday": {
            "trend":        0.35,
            "momentum":     0.35,
            "session":      0.30,
        },
        "swing": {
            "trend":        0.30,
            "news":         0.35,
            "macro":        0.35,
        },
    },
    "warning_sensitivity":    "medium",  # low / medium / high
    "confidence_adjustments": {},        # {"scalp": 5.0, "intraday": -3.0}
}


class BotProfileManager:
    """
    Load, save, and update the user's bot profile.

    Usage:
        mgr = BotProfileManager()
        profile = mgr.load()
        weights = mgr.get_skill_weights("intraday")
        adjusted = mgr.get_adjusted_confidence(72.0, "scalp")
        mgr.save(profile)
    """

    def __init__(self, path: str = CONFIG_PATH):
        self.path = path

    # ──────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────

    def load(self) -> dict:
        """Load profile from disk. Returns DEFAULT_PROFILE if file missing/corrupt."""
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Backfill missing keys from default
                for k, v in DEFAULT_PROFILE.items():
                    data.setdefault(k, v)
                return data
            except (json.JSONDecodeError, OSError):
                pass
        return dict(DEFAULT_PROFILE)

    def save(self, profile: dict) -> None:
        """Write profile to disk."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)

    def reset(self) -> dict:
        """Reset to default and save."""
        self.save(dict(DEFAULT_PROFILE))
        return dict(DEFAULT_PROFILE)

    # ──────────────────────────────────────────────────────────────────────
    # Profile queries
    # ──────────────────────────────────────────────────────────────────────

    def get_skill_weights(self, mode: str) -> dict:
        """Return skill weights for the given mode."""
        profile = self.load()
        return profile.get("skill_weights", {}).get(mode, {})

    def get_adjusted_confidence(self, raw_confidence: float, mode: str) -> float:
        """
        Apply a per-mode confidence adjustment stored in the profile.
        Example: {"scalp": +5} raises scalp confidence by 5 points.
        """
        profile = self.load()
        adj = float(profile.get("confidence_adjustments", {}).get(mode, 0.0))
        return float(max(0.0, min(100.0, raw_confidence + adj)))

    def get_aggressiveness(self) -> float:
        return float(self.load().get("aggressiveness", 0.5))

    def get_risk_tolerance(self) -> str:
        return str(self.load().get("risk_tolerance", "medium"))

    def get_warning_sensitivity(self) -> str:
        return str(self.load().get("warning_sensitivity", "medium"))

    # ──────────────────────────────────────────────────────────────────────
    # Adaptive updates
    # ──────────────────────────────────────────────────────────────────────

    def update_from_behavior(self, behavior_summary: dict) -> None:
        """
        Sync profile aggressiveness with BehaviorMemory.get_summary().
        Also flags common mistakes if streaks are severe.
        """
        profile = self.load()

        beh_agg = float(behavior_summary.get("aggressiveness", 0.5))
        # Blend: 70% existing profile, 30% from behavior (slow adaptation)
        blended = round(profile["aggressiveness"] * 0.7 + beh_agg * 0.3, 3)
        profile["aggressiveness"] = blended

        # Detect and log common mistakes
        mistakes = list(profile.get("common_mistakes", []))
        loss_streak = int(behavior_summary.get("loss_streak", 0))
        trades_today = int(behavior_summary.get("trades_today", 0))

        if loss_streak >= 3 and "Consecutive losses" not in mistakes:
            mistakes.append("Consecutive losses")
        if trades_today >= 7 and "Overtrading" not in mistakes:
            mistakes.append("Overtrading")

        # Keep only last 10 unique mistakes
        profile["common_mistakes"] = list(dict.fromkeys(mistakes))[-10:]

        self.save(profile)

    def update_preference(self, mode: str = None, timeframe: str = None) -> None:
        """Update preferred mode / timeframe when user changes selection."""
        profile = self.load()
        if mode:
            profile["preferred_mode"] = mode
        if timeframe:
            profile["preferred_timeframe"] = timeframe
        self.save(profile)

    def update_confidence_adjustment(self, mode: str, delta: float) -> None:
        """
        Nudge confidence adjustment for a mode.
        E.g. after many false scalp signals: update_confidence_adjustment("scalp", -5)
        """
        profile = self.load()
        adj = profile.get("confidence_adjustments", {})
        current = float(adj.get(mode, 0.0))
        # Cap adjustment at ±20
        adj[mode] = round(max(-20.0, min(20.0, current + delta)), 1)
        profile["confidence_adjustments"] = adj
        self.save(profile)
