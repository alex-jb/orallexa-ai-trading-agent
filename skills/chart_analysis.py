"""
skills/chart_analysis.py
──────────────────────────────────────────────────────────────────────────────
Chart screenshot analysis using Claude vision (multimodal).

User uploads a chart image (PNG/JPG). The skill encodes it and sends it to
Claude with a structured prompt. Claude returns JSON that maps directly to
DecisionOutput.

Output: DecisionOutput(source="chart_analysis")
"""

import base64
import json
from anthropic import Anthropic
from models.decision import DecisionOutput


_DEFAULT_OUTPUT = DecisionOutput(
    decision="WAIT",
    confidence=0.0,
    risk_level="HIGH",
    reasoning=["Chart analysis failed — unable to process image."],
    probabilities={"up": 0.33, "neutral": 0.34, "down": 0.33},
    source="chart_analysis",
    signal_strength=0.0,
    recommendation="Chart analysis unavailable — use technical analysis instead",
)

_PROMPT_TEMPLATE = """You are an expert technical analyst reviewing a trading chart.

Ticker: {ticker}
Timeframe: {timeframe}
User notes: {notes}

Analyze this chart carefully. Focus on:
1. Overall trend (uptrend / downtrend / sideways)
2. Market structure (higher highs/lows, lower highs/lows, consolidation)
3. Key setup type (breakout, pullback, reversal, none)
4. Support/resistance levels visible
5. Entry quality (strong / medium / weak)
6. Risk assessment

Return ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "trend": "uptrend|downtrend|sideways",
  "structure": "one sentence describing market structure",
  "setup_type": "breakout|pullback|reversal|consolidation|none",
  "support_resistance": "brief description of key levels",
  "entry_quality": "strong|medium|weak",
  "decision": "BUY|SELL|WAIT",
  "confidence": 65.0,
  "risk_level": "LOW|MEDIUM|HIGH",
  "reasoning": [
    "Step 1: Trend — ...",
    "Step 2: Structure — ...",
    "Step 3: Setup — ...",
    "Step 4: Risk — ...",
    "Step 5: Decision — ..."
  ],
  "probabilities": {{"up": 0.55, "neutral": 0.25, "down": 0.20}}
}}

Rules:
- decision must be "BUY", "SELL", or "WAIT"
- risk_level must be "LOW", "MEDIUM", or "HIGH"
- probabilities must sum to 1.0
- confidence is 0-100
- If image is unclear or not a chart, return decision="WAIT", confidence=0
"""


class ChartAnalysisSkill:
    """
    Analyze a chart screenshot using Claude vision API.

    Usage:
        with open("chart.png", "rb") as f:
            result = ChartAnalysisSkill().analyze(
                image_bytes=f.read(),
                ticker="NVDA",
                timeframe="15m",
                notes="Potential breakout above resistance",
            )
    """

    def __init__(self):
        self._client = None

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic()
        return self._client

    def analyze(
        self,
        image_bytes: bytes,
        ticker: str = "",
        timeframe: str = "",
        notes: str = "",
        media_type: str = "image/png",
    ) -> DecisionOutput:
        """
        Args:
            image_bytes: Raw image bytes (PNG or JPG)
            ticker:      Symbol being analyzed (e.g. "NVDA")
            timeframe:   Chart timeframe (e.g. "15m", "1h", "1D")
            notes:       Optional user notes about the setup
            media_type:  MIME type ("image/png" or "image/jpeg")

        Returns:
            DecisionOutput with source="chart_analysis"
        """
        try:
            image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        except Exception as e:
            out = _DEFAULT_OUTPUT
            out.reasoning = [f"Image encoding failed: {e}"]
            return out

        prompt = _PROMPT_TEMPLATE.format(
            ticker=ticker or "Unknown",
            timeframe=timeframe or "Unknown",
            notes=notes or "None provided",
        )

        try:
            client = self._get_client()
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type":       "base64",
                                    "media_type": media_type,
                                    "data":       image_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
            )
        except Exception as e:
            d = _DEFAULT_OUTPUT
            d.reasoning = [f"Claude API call failed: {e}"]
            return d

        raw = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                raw += block.text

        return self._parse(raw.strip(), ticker, timeframe)

    # ──────────────────────────────────────────────────────────────────────
    # Parse response
    # ──────────────────────────────────────────────────────────────────────

    def _parse(self, raw: str, ticker: str, timeframe: str) -> DecisionOutput:
        try:
            text = raw.replace("```json", "").replace("```", "").strip()
            start, end = text.find("{"), text.rfind("}")
            if start == -1 or end == -1:
                raise ValueError("No JSON object found in response")
            text = text[start:end + 1]
            data = json.loads(text)
        except Exception as e:
            return DecisionOutput(
                decision="WAIT",
                confidence=0.0,
                risk_level="HIGH",
                reasoning=[f"Failed to parse chart analysis: {e}", f"Raw: {raw[:200]}"],
                probabilities={"up": 0.33, "neutral": 0.34, "down": 0.33},
                source="chart_analysis",
                signal_strength=0.0,
                recommendation="Chart analysis failed — use technical analysis instead",
            )

        # Normalise probabilities
        probs = data.get("probabilities", {})
        up   = float(probs.get("up",      0.33))
        neut = float(probs.get("neutral", 0.34))
        down = float(probs.get("down",    0.33))
        total = up + neut + down
        if abs(total - 1.0) > 0.05 and total > 0:
            up, neut, down = up / total, neut / total, down / total

        # Build reasoning — prepend chart context
        reasoning = list(data.get("reasoning", []))
        if ticker or timeframe:
            context_line = f"Chart: {ticker} | {timeframe}"
            if data.get("trend"):
                context_line += f" | Trend: {data['trend']}"
            if data.get("setup_type"):
                context_line += f" | Setup: {data['setup_type']}"
            reasoning.insert(0, context_line)
        if data.get("support_resistance"):
            reasoning.append(f"S/R: {data['support_resistance']}")

        decision  = str(data.get("decision",   "WAIT")).upper()
        risk_level = str(data.get("risk_level", "HIGH")).upper()

        if decision not in ("BUY", "SELL", "WAIT"):
            decision = "WAIT"
        if risk_level not in ("LOW", "MEDIUM", "HIGH"):
            risk_level = "HIGH"

        from models.confidence import scale_confidence, score_to_risk, make_recommendation
        raw_conf   = float(data.get("confidence", 0.0))
        confidence = scale_confidence(raw_conf)
        # Use score_to_risk as primary; fall back to Claude's value only if it's stricter
        computed_risk = score_to_risk(raw_conf)
        _risk_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        risk_level = max(risk_level, computed_risk, key=lambda r: _risk_rank.get(r, 2))
        recommendation = make_recommendation(decision, confidence, risk_level)

        return DecisionOutput(
            decision=decision,
            confidence=confidence,
            risk_level=risk_level,
            reasoning=reasoning,
            probabilities={"up": round(up, 3), "neutral": round(neut, 3), "down": round(down, 3)},
            source="chart_analysis",
            signal_strength=round(raw_conf, 1),
            recommendation=recommendation,
        )
