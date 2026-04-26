"""
engine/kronos_signal.py
──────────────────────────────────────────────────────────────────
Kronos integration — first open-source foundation model for financial
candlesticks (NeoQuasar/Kronos series, MIT license).

Trained on 45+ global exchanges, predicts future OHLCV from past
OHLCV using hierarchical tokenization + autoregressive Transformer.
Four sizes: mini (4M), small (24M), base (102M), large (499M).

Why a 10th ML signal: our existing 9 models (RF, XGB, EMAformer, RL,
GNN, Diffusion, Chronos2, MOIRAI2, LR) are general time-series. Kronos
is finance-specific — it's pretrained on K-line patterns from real
exchanges. Worth adding as another vote in the ML ensemble.

Lazy-imports `kronos-ai` (or whatever the model package becomes once
PyPI'd; currently the project ships as a git clone). The integration
falls back gracefully if Kronos isn't installed — RuntimeError with
clear install hint, not silent zero.

Usage:
    from engine.kronos_signal import KronosSignal
    sig = KronosSignal()
    forecast = sig.predict(df, lookback=64, pred_len=5)
    score = sig.score_for_fusion(df)   # -100..+100 directional vote

Install:
    git clone https://github.com/shiyu-coder/Kronos
    cd Kronos && pip install -r requirements.txt
    # then add Kronos/ to sys.path or pip-install once they publish

Note: model checkpoints download from HuggingFace on first use
(NeoQuasar/Kronos-Tokenizer-base + NeoQuasar/Kronos-small ~50MB).
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Cache the loaded predictor so we don't re-download checkpoints per call.
_cached_predictor = None
_cached_size: Optional[str] = None


def _ensure_kronos(model_size: str = "small"):
    """Lazy import + load. Caches per process. Raises clear error on miss."""
    global _cached_predictor, _cached_size

    if _cached_predictor is not None and _cached_size == model_size:
        return _cached_predictor

    try:
        from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "Kronos not installed. Install with:\n"
            "  git clone https://github.com/shiyu-coder/Kronos\n"
            "  cd Kronos && pip install -r requirements.txt\n"
            "  # add Kronos/ to PYTHONPATH so 'from model import ...' resolves\n"
            "MIT license. Checkpoints from HuggingFace NeoQuasar/Kronos-*."
        ) from e

    valid_sizes = {"mini", "small", "base", "large"}
    if model_size not in valid_sizes:
        model_size = "small"

    try:
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model = Kronos.from_pretrained(f"NeoQuasar/Kronos-{model_size}")
        _cached_predictor = KronosPredictor(model, tokenizer, max_context=512)
        _cached_size = model_size
        return _cached_predictor
    except Exception as e:
        logger.warning("Kronos load failed: %s", e)
        raise RuntimeError(f"Kronos checkpoint load failed: {e}") from e


# ── Predictor wrapper ──────────────────────────────────────────────────────


class KronosSignal:
    """
    Wraps Kronos for use as a signal source. Stateless — re-uses the
    process-wide cached predictor.
    """

    def __init__(self, model_size: str = "small", lookback: int = 64,
                 temperature: float = 1.0, top_p: float = 0.9):
        self.model_size = model_size
        self.lookback = min(lookback, 480)  # leave headroom under 512 max
        self.temperature = temperature
        self.top_p = top_p

    def predict(self, df, *, pred_len: int = 5):
        """
        df:        pandas.DataFrame with at least open/high/low/close + a
                   datetime-like index OR a 'timestamps' column.
        pred_len:  trading days to forecast.

        Returns the forecasted OHLCV DataFrame (Kronos's native shape) or
        None on failure.
        """
        try:
            import pandas as pd
            predictor = _ensure_kronos(self.model_size)
        except Exception:
            return None

        if df is None or len(df) < self.lookback + 1:
            return None

        try:
            # Normalize columns: Kronos wants lower-case OHLCV
            df_norm = df.copy()
            rename_map = {c: c.lower() for c in df_norm.columns
                          if c.lower() in ("open", "high", "low", "close",
                                            "volume", "amount")}
            df_norm = df_norm.rename(columns=rename_map)

            required = ["open", "high", "low", "close"]
            for col in required:
                if col not in df_norm.columns:
                    return None

            cols = required + [c for c in ("volume", "amount")
                                if c in df_norm.columns]
            x_df = df_norm.loc[:, cols].iloc[-self.lookback:].reset_index(drop=True)

            # Build timestamps from the index, fall back to a sequential range
            try:
                idx = pd.to_datetime(df_norm.index[-self.lookback:])
                x_timestamp = pd.Series(idx)
            except Exception:
                x_timestamp = pd.Series(pd.date_range(end=pd.Timestamp.now(),
                                                       periods=self.lookback))

            future_start = x_timestamp.iloc[-1] + pd.Timedelta(days=1)
            y_timestamp = pd.Series(pd.date_range(start=future_start,
                                                    periods=pred_len))

            forecast = predictor.predict(
                df=x_df, x_timestamp=x_timestamp, y_timestamp=y_timestamp,
                pred_len=pred_len, T=self.temperature, top_p=self.top_p,
            )
            return forecast
        except Exception as e:
            logger.warning("Kronos predict failed: %s", e)
            return None

    def for_ml_ensemble(self, df, *, pred_len: int = 5) -> dict:
        """
        Return a result dict shaped for `engine.signal_fusion._score_ml`.
        Caller plugs into `ml_result["results"]["kronos"]` before calling
        fuse_signals.

        Shape: {status: 'ok'|'error', metrics: {sharpe, total_return}}.
        sharpe is synthesized from forecast monotonicity × magnitude;
        total_return mirrors expected_return_pct / 100. ml_ensemble
        consumes both via _score_ml's sign-magnitude logic.
        """
        s = self.score_for_fusion(df, pred_len=pred_len)
        if not s.get("available"):
            return {"status": "error", "metrics": {"sharpe": 0, "total_return": 0}}
        ret = s.get("expected_return_pct", 0) / 100.0
        # Synthesize a sharpe-equivalent: monotonicity (-0.5..+0.5)
        # scaled by 4 so a fully-monotone forecast contributes ±2.
        monotone = s.get("monotone_pct", 0.5)
        sharpe = (monotone - 0.5) * 4
        if ret < 0:
            sharpe = -abs(sharpe)
        return {
            "status": "ok",
            "metrics": {
                "sharpe": round(sharpe, 3),
                "total_return": round(ret, 4),
            },
        }

    def score_for_fusion(self, df, *, pred_len: int = 5) -> dict:
        """
        Run a forecast, convert it into a -100..+100 directional vote
        for the signal fusion engine.

        Returns {available, score, expected_return_pct, n_steps}.
        """
        forecast = self.predict(df, pred_len=pred_len)
        if forecast is None or len(forecast) < pred_len:
            return {"available": False, "score": 0}

        try:
            import pandas as pd
            df_norm = df.rename(columns={c: c.lower() for c in df.columns})
            current_close = float(df_norm["close"].iloc[-1])
            forecast_close = float(forecast["close"].iloc[-1])
            if current_close <= 0:
                return {"available": False, "score": 0}

            ret_pct = (forecast_close - current_close) / current_close * 100.0

            # Map expected return to -100..+100 score: ±5% return → ±100
            score = max(-100, min(100, int(ret_pct * 20)))

            # Confidence boost from how monotone the forecast is
            steps = forecast["close"].tolist()
            ups = sum(1 for i in range(1, len(steps)) if steps[i] > steps[i - 1])
            monotone_pct = ups / max(1, len(steps) - 1)
            if abs(monotone_pct - 0.5) > 0.3:
                score = int(score * 1.15)
                score = max(-100, min(100, score))

            return {
                "available": True,
                "score": score,
                "expected_return_pct": round(ret_pct, 3),
                "n_steps": pred_len,
                "monotone_pct": round(monotone_pct, 3),
                "model_size": self.model_size,
            }
        except Exception as e:
            logger.warning("Kronos score conversion failed: %s", e)
            return {"available": False, "score": 0}
