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
from numbers import Integral
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
                 temperature: float = 1.0, top_p: float = 0.9,
                 calendar: str = "XNYS"):
        if isinstance(lookback, bool) or not isinstance(lookback, Integral) or lookback < 1:
            raise ValueError("lookback must be a positive integer")
        self.model_size = model_size
        self.lookback = min(lookback, 480)  # leave headroom under 512 max
        self.temperature = temperature
        self.top_p = top_p
        self.calendar = calendar

    def predict(self, df, *, pred_len: int = 5):
        """
        df:        daily OHLCV bars with session dates in a datetime-like
                   index or an explicit 'timestamps' column (takes priority).
                   The caller must supply only bars available at its cutoff.
                   Dates are provider-local session labels, not UTC instants.
        pred_len:  future sessions of the configured exchange to forecast.

        Returns the forecasted OHLCV DataFrame (Kronos's native shape) or
        None on failure.
        """
        if (isinstance(pred_len, bool) or not isinstance(pred_len, Integral)
                or not 1 <= pred_len <= 512):
            return None
        if df is None or len(df) < self.lookback:
            return None

        try:
            import numpy as np
            import pandas as pd
            import exchange_calendars as xcals

            # Normalize columns: Kronos wants lower-case OHLCV
            df_norm = df.copy()
            rename_map = {c: c.lower() for c in df_norm.columns
                          if isinstance(c, str) and c.lower() in (
                              "open", "high", "low", "close", "volume",
                              "amount", "timestamps")}
            df_norm = df_norm.rename(columns=rename_map)
            if not df_norm.columns.is_unique:
                return None

            required = ["open", "high", "low", "close"]
            for col in required:
                if col not in df_norm.columns:
                    return None

            cols = required + [c for c in ("volume", "amount")
                                if c in df_norm.columns]
            x_df = (df_norm.loc[:, cols].iloc[-self.lookback:]
                    .astype(float).reset_index(drop=True))
            if (not np.isfinite(x_df.to_numpy()).all()
                    or (x_df[required] <= 0).any().any()
                    or (x_df[[c for c in ("volume", "amount") if c in cols]] < 0)
                    .any().any()):
                return None

            source = (df_norm["timestamps"].iloc[-self.lookback:]
                      if "timestamps" in df_norm.columns
                      else df_norm.index[-self.lookback:])
            # Numeric indexes otherwise parse as nanoseconds in January 1970.
            if (pd.api.types.is_numeric_dtype(source)
                    or any(isinstance(v, (int, float, np.number)) for v in source)):
                return None
            dates = pd.DatetimeIndex(pd.to_datetime(source, errors="raise"))
            if dates.tz is not None:
                dates = dates.tz_localize(None)
            dates = dates.normalize()
            if dates.hasnans or not dates.is_unique or not dates.is_monotonic_increasing:
                return None

            last = dates[-1]
            end = last + pd.Timedelta(days=(int(pred_len) + 5) * 4)
            exchange = xcals.get_calendar(self.calendar, start=dates[0], end=end)
            if not dates.isin(exchange.sessions).all():
                return None
            # Calendar endpoints can themselves fall on holidays. Select
            # from actual session labels instead of querying beyond its bounds.
            future = exchange.sessions[exchange.sessions > last][:pred_len]
            if len(future) != pred_len:
                return None
            x_timestamp = pd.Series(dates)
            y_timestamp = pd.Series(future)

            # Do not load checkpoints until input dates and values are valid.
            predictor = _ensure_kronos(self.model_size)
            forecast = predictor.predict(
                df=x_df, x_timestamp=x_timestamp, y_timestamp=y_timestamp,
                pred_len=pred_len, T=self.temperature, top_p=self.top_p,
            )
            if not isinstance(forecast, pd.DataFrame) or len(forecast) != pred_len:
                return None
            forecast.attrs["orallexa_forecast"] = {
                "calendar": self.calendar,
                "calendar_version": xcals.__version__,
                "last_session": last.date().isoformat(),
                "target_sessions": future.strftime("%Y-%m-%d").tolist(),
                "forecast_kind": "point_path",
            }
            return forecast
        except Exception as e:
            logger.warning("Kronos predict failed: %s", e)
            return None

    def for_ml_ensemble(self, df, *, pred_len: int = 5) -> dict:
        """
        Return a result dict shaped for `engine.signal_fusion._score_ml`.
        Caller plugs into `ml_result["results"]["kronos"]` before calling
        fuse_signals.

        Forecast evidence is separate from realized backtest metrics.
        The fusion engine consumes directional_score directly. Empty metrics
        retains the container shape without inventing Sharpe or realized returns.
        """
        s = self.score_for_fusion(df, pred_len=pred_len)
        if not s.get("available"):
            return {"status": "error", "metrics": {}}
        return {
            "status": "ok",
            "signal_type": "price_forecast",
            "directional_score": s["score"],
            "metrics": {},
            "forecast": {
                **s.get("forecast_metadata", {}),
                "expected_return_pct": s["expected_return_pct"],
                "n_steps": s["n_steps"],
                "model_size": self.model_size,
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
            import numpy as np
            import pandas as pd
            df_norm = df.rename(columns={c: c.lower() for c in df.columns})
            current_close = float(df_norm["close"].iloc[-1])
            closes = forecast["close"].to_numpy(dtype=float)
            if (not np.isfinite(current_close) or current_close <= 0
                    or not np.isfinite(closes).all() or (closes <= 0).any()):
                return {"available": False, "score": 0}
            forecast_close = float(closes[-1])

            ret_pct = (forecast_close - current_close) / current_close * 100.0
            if not np.isfinite(ret_pct):
                return {"available": False, "score": 0}

            # Map expected return to -100..+100 score: ±5% return → ±100
            score = max(-100, min(100, int(ret_pct * 20)))

            # Descriptive path statistic only; ties are neutral, not bearish.
            changes = np.diff(closes)
            monotone_pct = (float(((changes > 0) + 0.5 * (changes == 0)).mean())
                            if len(changes) else 0.5)

            return {
                "available": True,
                "score": score,
                "expected_return_pct": round(ret_pct, 3),
                "n_steps": pred_len,
                "monotone_pct": round(monotone_pct, 3),
                "model_size": self.model_size,
                "forecast_metadata": forecast.attrs.get("orallexa_forecast", {}),
            }
        except Exception as e:
            logger.warning("Kronos score conversion failed: %s", e)
            return {"available": False, "score": 0}
