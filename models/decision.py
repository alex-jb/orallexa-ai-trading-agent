from dataclasses import dataclass, field
from typing import Literal

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
DecisionLabel = Literal["BUY", "SELL", "WAIT"]


@dataclass
class DecisionOutput:
    decision: DecisionLabel
    confidence: float          # 0.0–82.0  (always capped — see models/confidence.py)
    risk_level: RiskLevel
    reasoning: list            # step-by-step strings
    probabilities: dict        # {"up": float, "neutral": float, "down": float}
    source: str                # e.g. "scalping", "intraday", "prediction", "multi_agent"

    # ── Extended fields (default-empty so existing callers are unaffected) ──
    signal_strength: float = 0.0   # raw 0-100 composite score (before confidence scaling)
    recommendation: str = ""       # plain-English action sentence

    def to_dict(self) -> dict:
        return {
            "decision":        self.decision,
            "confidence":      round(self.confidence, 1),
            "risk_level":      self.risk_level,
            "reasoning":       self.reasoning,
            "probabilities":   self.probabilities,
            "source":          self.source,
            "signal_strength": round(self.signal_strength, 1),
            "recommendation":  self.recommendation,
        }
