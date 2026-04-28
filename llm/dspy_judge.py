"""
llm/dspy_judge.py
──────────────────────────────────────────────────────────────────
DSPy Phase A bootstrap + Phase B artifact loader.

Phase A scope (per docs/DSPY_MIGRATION.md):
  - Define ONE Signature (`JudgeSignature`)
  - Wrap in `dspy.Predict` with no compilation / no optimizer
  - Provide a side-by-side comparison helper to A/B against the
    hand-tuned `_call_judge` from llm/debate.py

Phase B additions:
  - `load_compiled_judge(path)` — load a compiled artifact from disk
    and return a callable matching `judge_dspy`'s signature. Powered
    by `scripts/compile_judge_dspy.py` running MIPROv2 over the eval
    set produced by `scripts/build_dspy_eval_set.py`.

What's NOT in Phase B yet:
  - No production hot path swap. The compiled artifact ships when
    holdout improvement is ≥5% absolute (see DSPY_MIGRATION.md gate).

dspy is intentionally lazy-imported. The project doesn't take dspy-ai
as a hard dep — install it manually when you actually want to run
this. Calling `judge_dspy(...)` without dspy installed raises a clear
error pointing at the install command.

Usage (after `pip install dspy-ai`):
    from llm.dspy_judge import judge_dspy, compare_judges
    decision = judge_dspy(bull_text, bear_text, ticker="NVDA")
    diff = compare_judges(bull_text, bear_text, ticker="NVDA")
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Cache the configured dspy module so we don't re-init the LM client every
# call. dspy.LM is stateful and cheap to keep around.
_dspy_configured = False
_predict_cls = None


def _ensure_dspy():
    """Lazy-import dspy and configure it once. Raises clear error on miss."""
    global _dspy_configured, _predict_cls
    try:
        import dspy
    except ImportError as e:
        raise RuntimeError(
            "dspy-ai not installed. Phase A is opt-in — run "
            "`pip install dspy-ai>=2.5` to enable judge_dspy(). "
            "See docs/DSPY_MIGRATION.md for the full migration plan."
        ) from e

    if not _dspy_configured:
        # Configure dspy to use the same Anthropic Sonnet 4.6 our hand-tuned
        # judge currently uses. dspy.LM uses litellm under the hood, which
        # accepts 'anthropic/<model-id>' route strings.
        from llm.claude_client import DEEP_MODEL
        try:
            lm = dspy.LM(
                f"anthropic/{DEEP_MODEL}",
                max_tokens=600,
                temperature=0.0,
            )
            dspy.configure(lm=lm)
        except Exception as e:
            logger.debug("dspy.configure failed: %s", e)
            raise

        # Build the predict class once. Defining it inside the function so
        # the dspy.Signature subclass only exists when dspy is importable —
        # no module-level dspy reference at import time.
        class JudgeSignature(dspy.Signature):
            """Synthesize Bull and Bear arguments into a final trading verdict.

            Read the bull case and bear case carefully, weigh the evidence,
            and return a final decision (BUY / SELL / WAIT), a confidence
            score from 0 to 100, a risk_level (LOW / MEDIUM / HIGH), and a
            2-3 sentence reasoning_detail explaining the synthesis.
            """
            ticker:        str = dspy.InputField(desc="stock symbol, e.g. NVDA")
            bull_argument: str = dspy.InputField(desc="bull case 200-400 words")
            bear_argument: str = dspy.InputField(desc="bear case 200-400 words")
            decision:    str = dspy.OutputField(desc="BUY, SELL, or WAIT")
            confidence:  int = dspy.OutputField(desc="0-100")
            risk_level:  str = dspy.OutputField(desc="LOW, MEDIUM, or HIGH")
            reasoning_detail: str = dspy.OutputField(
                desc="2-3 sentences explaining the synthesis"
            )

        _predict_cls = dspy.Predict(JudgeSignature)
        _dspy_configured = True

    return _predict_cls


def judge_dspy(
    bull: str,
    bear: str,
    *,
    ticker: str = "UNKNOWN",
) -> dict:
    """
    Phase A drop-in: get a Judge verdict from the DSPy-wrapped Signature.
    Returns {decision, confidence, risk_level, reasoning_detail}.

    Falls back to None on any error (caller decides whether to use the
    hand-tuned judge instead). Never raises during normal use.
    """
    try:
        predictor = _ensure_dspy()
        out = predictor(ticker=ticker, bull_argument=bull, bear_argument=bear)
        # dspy returns a Prediction object — fields are attributes
        decision = str(getattr(out, "decision", "WAIT")).upper().strip()
        if decision not in ("BUY", "SELL", "WAIT"):
            decision = "WAIT"
        try:
            confidence = int(float(getattr(out, "confidence", 50)))
        except (ValueError, TypeError):
            confidence = 50
        confidence = max(0, min(100, confidence))
        risk_level = str(getattr(out, "risk_level", "MEDIUM")).upper().strip()
        if risk_level not in ("LOW", "MEDIUM", "HIGH"):
            risk_level = "MEDIUM"
        reasoning_detail = str(getattr(out, "reasoning_detail", ""))[:600]
        return {
            "decision":         decision,
            "confidence":       confidence,
            "risk_level":       risk_level,
            "reasoning_detail": reasoning_detail,
            "source":           "dspy",
        }
    except RuntimeError:
        # dspy not installed — re-raise so caller sees the install hint
        raise
    except Exception as e:
        logger.warning("judge_dspy failed for %s: %s", ticker, e)
        return None


def load_compiled_judge(path: str | "Path"):
    """
    Phase B: load a compiled MIPROv2 artifact and return a callable matching
    `judge_dspy(bull, bear, *, ticker)` — i.e. produces a dict with decision,
    confidence, risk_level, reasoning_detail, source.

    Returns None when:
      - the file doesn't exist (so callers can fall back to the hand-tuned path)
      - dspy isn't installed (RuntimeError surfaces with the install hint)

    Loaded programs are cached per-path so the dspy.LM client isn't rebuilt
    on every call.
    """
    from pathlib import Path as _Path

    path = _Path(path)
    if not path.exists():
        return None

    cache = _compiled_cache_get(str(path))
    if cache is not None:
        return cache

    base_predict_cls = _ensure_dspy()
    JudgeSignature = base_predict_cls.signature

    import dspy

    program = dspy.Predict(JudgeSignature)
    try:
        program.load(str(path))
    except Exception as e:
        logger.warning("Failed to load compiled judge from %s: %s", path, e)
        return None

    def predict(bull: str, bear: str, *, ticker: str = "UNKNOWN") -> Optional[dict]:
        try:
            out = program(ticker=ticker, bull_argument=bull, bear_argument=bear)
            decision = str(getattr(out, "decision", "WAIT")).upper().strip()
            if decision not in ("BUY", "SELL", "WAIT"):
                decision = "WAIT"
            try:
                confidence = max(0, min(100, int(float(getattr(out, "confidence", 50)))))
            except (TypeError, ValueError):
                confidence = 50
            risk_level = str(getattr(out, "risk_level", "MEDIUM")).upper().strip()
            if risk_level not in ("LOW", "MEDIUM", "HIGH"):
                risk_level = "MEDIUM"
            reasoning_detail = str(getattr(out, "reasoning_detail", ""))[:600]
            return {
                "decision":         decision,
                "confidence":       confidence,
                "risk_level":       risk_level,
                "reasoning_detail": reasoning_detail,
                "source":           "dspy_compiled",
            }
        except Exception as e:
            logger.warning("compiled judge failed for %s: %s", ticker, e)
            return None

    _compiled_cache_set(str(path), predict)
    return predict


# Per-path cache so reloads are cheap. Keyed on absolute path string.
_compiled_cache: dict[str, callable] = {}


def _compiled_cache_get(key: str):
    return _compiled_cache.get(key)


def _compiled_cache_set(key: str, value) -> None:
    _compiled_cache[key] = value


def reset_compiled_cache() -> None:
    """Test helper: drop the per-path compiled-program cache."""
    _compiled_cache.clear()


def compare_judges(
    bull: str,
    bear: str,
    *,
    ticker: str = "UNKNOWN",
) -> dict:
    """
    Run both judges (hand-tuned + DSPy) on the same inputs and report
    the diff. Useful for the Phase A head-to-head described in
    docs/DSPY_MIGRATION.md.

    Returns:
        {
            "hand_tuned": {...} or None,
            "dspy":       {...} or None,
            "agree":      bool (decision match),
            "conf_delta": int  (dspy.confidence - hand.confidence),
        }
    """
    hand_result = None
    try:
        # Hand-tuned _call_judge is private but we can call it directly
        # given we're inside the same package
        from unittest.mock import MagicMock
        from llm.debate import _call_judge
        from llm.claude_client import get_client
        initial = MagicMock()
        initial.decision = "WAIT"
        initial.confidence = 50.0
        initial.risk_level = "MEDIUM"
        initial.reasoning = []
        initial.probabilities = {"up": 0.33, "neutral": 0.34, "down": 0.33}
        initial.source = "compare"
        initial.signal_strength = 50.0
        out = _call_judge(get_client(), initial, bull, bear, ticker, {})
        hand_result = {
            "decision":   out.decision,
            "confidence": int(out.confidence),
            "risk_level": out.risk_level,
            "source":     "hand_tuned",
        }
    except Exception as e:
        logger.warning("Hand-tuned judge failed in compare: %s", e)

    dspy_result = judge_dspy(bull, bear, ticker=ticker)

    agree = (
        hand_result is not None
        and dspy_result is not None
        and hand_result["decision"] == dspy_result["decision"]
    )
    conf_delta = (
        dspy_result["confidence"] - hand_result["confidence"]
        if (hand_result and dspy_result) else None
    )
    return {
        "hand_tuned": hand_result,
        "dspy":       dspy_result,
        "agree":      agree,
        "conf_delta": conf_delta,
    }
