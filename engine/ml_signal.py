"""
engine/ml_signal.py
────────────────────────────────────────────────────────────────────────────
Machine Learning signal generator for Orallexa.
Trains RandomForest / XGBoost on V2 technical indicators,
predicts next-N-day direction, returns trading signal.

For ML course presentation: this is the key differentiator vs rule-based strategies.

Usage:
    from engine.ml_signal import MLSignalGenerator
    gen = MLSignalGenerator(train_df, test_df)
    result = gen.run_all()
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional

from core.logger import get_logger

logger = get_logger("ml_signal")

# ── feature columns from TechnicalAnalysisSkillV2 ──
FEATURE_COLS = [
    "MA5", "MA10", "MA20", "MA50",
    "EMA12", "EMA26",
    "MACD", "MACD_Signal", "MACD_Hist",
    "RSI", "Stoch_K", "Stoch_D", "ROC",
    "BB_Pct", "BB_Width",
    "ATR_Pct", "HV20",
    "Volume_Ratio", "OBV",
    "ADX", "Plus_DI", "Minus_DI",
    "Above_MA20", "Above_MA50",
    "MACD_Cross_Up", "MACD_Cross_Down",
    "RSI_Oversold", "RSI_Overbought",
]


def _make_features_labels(df: pd.DataFrame, forward_days: int = 5) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Build feature matrix X and binary label y.
    y = 1 if price is higher in `forward_days` days, else 0.
    """
    available = [c for c in FEATURE_COLS if c in df.columns]
    X = df[available].copy()

    # Label: forward return > 0
    future_return = df["Close"].shift(-forward_days) / df["Close"] - 1
    y = (future_return > 0).astype(int)

    # Drop last N rows (no future label)
    X = X.iloc[:-forward_days]
    y = y.iloc[:-forward_days]

    # Drop early rows where indicators have NaN (MA50 needs ~50 rows)
    first_valid = X.dropna(how="any").index[0] if not X.dropna(how="any").empty else X.index[0]
    X = X.loc[first_valid:]
    y = y.loc[first_valid:]

    # Forward-fill then back-fill any remaining sparse NaN (safer than zero-fill)
    X = X.ffill().bfill().fillna(0)

    return X, y


def _empty_metrics() -> dict:
    """Return zeroed metrics dict for failed/skipped models."""
    return {"sharpe": 0, "total_return": 0, "max_drawdown": 0, "win_rate": 0, "n_trades": 0, "mkt_return": 0, "excess_return": 0}


# ── Model cache (in-memory, keyed by ticker + data hash) ──────────────────
_MODEL_CACHE: Dict[str, Dict] = {}
_CACHE_TTL = 3600  # 1 hour


def _cache_key(ticker: str, train_len: int) -> str:
    """Generate cache key from ticker and training data size."""
    return f"{ticker}:{train_len}"


def _get_cached(ticker: str, train_len: int) -> Optional[Dict]:
    """Return cached models if still valid."""
    import time
    key = _cache_key(ticker, train_len)
    entry = _MODEL_CACHE.get(key)
    if entry and time.time() - entry["ts"] < _CACHE_TTL:
        logger.info("ML cache hit: %s (%d models)", key, len(entry["models"]))
        return entry["models"]
    return None


def _set_cache(ticker: str, train_len: int, models: Dict) -> None:
    """Cache trained models with timestamp."""
    import time
    key = _cache_key(ticker, train_len)
    _MODEL_CACHE[key] = {"models": models, "ts": time.time()}
    # Evict old entries (keep max 5 tickers)
    if len(_MODEL_CACHE) > 5:
        oldest = min(_MODEL_CACHE, key=lambda k: _MODEL_CACHE[k]["ts"])
        del _MODEL_CACHE[oldest]


class MLSignalGenerator:
    """
    Trains ML models on train_df, generates signals on test_df.
    Compares against buy-and-hold and rule-based baseline.
    """

    def __init__(
        self,
        train_df: pd.DataFrame,
        test_df:  pd.DataFrame,
        forward_days: int = 5,
        transaction_cost: float = 0.001,
        slippage: float = 0.001,
        ticker: str = "NVDA",
    ):
        self.train_df         = train_df
        self.test_df          = test_df
        self._ticker          = ticker
        self.forward_days     = forward_days
        self.tc               = transaction_cost + slippage
        self.results: Dict    = {}
        self.models: Dict     = {}

    # ──────────────────────────────────────────────────────────────────────
    # MODEL TRAINING
    # ──────────────────────────────────────────────────────────────────────

    def _train_random_forest(self, X_train, y_train):
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.preprocessing import StandardScaler
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_train)
            model = RandomForestClassifier(
                n_estimators=100, max_depth=5, min_samples_leaf=10,
                random_state=42, n_jobs=-1)
            model.fit(X_scaled, y_train)
            return model, scaler
        except ImportError:
            return None, None

    def _train_xgboost(self, X_train, y_train):
        try:
            from xgboost import XGBClassifier
            model = XGBClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                random_state=42, eval_metric="logloss",
                verbosity=0, use_label_encoder=False)
            model.fit(X_train, y_train)
            return model
        except ImportError:
            return None

    def _train_logistic(self, X_train, y_train):
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_train)
            model = LogisticRegression(C=0.1, max_iter=500, random_state=42)
            model.fit(X_scaled, y_train)
            return model, scaler
        except ImportError:
            return None, None

    # ──────────────────────────────────────────────────────────────────────
    # SIGNAL GENERATION
    # ──────────────────────────────────────────────────────────────────────

    def _signal_from_model(self, model, X_test, scaler=None) -> pd.Series:
        """Generate binary signal from model predictions."""
        X = X_test.fillna(0)
        if scaler is not None:
            X = scaler.transform(X)
        proba = model.predict_proba(X)[:, 1]  # probability of up
        # Enter when confidence > 55%
        signal = (proba > 0.55).astype(int)
        return pd.Series(signal, index=X_test.index)

    def _backtest_signal(self, df: pd.DataFrame, signal: pd.Series) -> Dict:
        """Lightweight backtest from signal series."""
        returns  = df["Close"].pct_change().fillna(0)
        position = signal.shift(1).fillna(0)
        trades   = position.diff().abs().fillna(0)

        gross = position * returns
        net   = gross - trades * self.tc
        mkt   = returns

        cum_net = (1 + net).cumprod()
        cum_mkt = (1 + mkt).cumprod()

        sharpe = float(net.mean() / net.std() * np.sqrt(252)) if net.std() > 1e-9 else 0.0
        total  = float(cum_net.iloc[-1] - 1)
        maxdd  = float(((cum_net - cum_net.cummax()) / cum_net.cummax()).min())
        winrate= float((net[position > 0] > 0).mean()) if (position > 0).any() else 0.0

        return {
            "sharpe":       round(sharpe, 4),
            "total_return": round(total,  4),
            "max_drawdown": round(maxdd,  4),
            "win_rate":     round(winrate,4),
            "n_trades":     int(trades[trades > 0].count()),
            "mkt_return":   round(float(cum_mkt.iloc[-1] - 1), 4),
            "excess_return":round(total - float(cum_mkt.iloc[-1] - 1), 4),
        }

    # ──────────────────────────────────────────────────────────────────────
    # FEATURE IMPORTANCE
    # ──────────────────────────────────────────────────────────────────────

    def _run_chronos(self, train_df: pd.DataFrame, test_df: pd.DataFrame) -> Optional[pd.Series]:
        """
        Run Chronos-2 pretrained time series model.
        Uses training Close prices as context, predicts forward for each test day.
        Returns a signal series: 1 (predicted up), 0 (predicted down/flat).
        """
        try:
            import torch
            from chronos import ChronosPipeline
        except ImportError:
            return None

        close_col = "Close" if "Close" in train_df.columns else "Adj Close"
        context = torch.tensor(train_df[close_col].values, dtype=torch.float32)

        # Use small model for speed (chronos-t5-small ~40MB)
        pipeline = ChronosPipeline.from_pretrained(
            "amazon/chronos-t5-small",
            device_map="cpu",
            dtype=torch.float32,
        )

        # Rolling prediction: for each test day, predict forward_days ahead
        signals = []
        full_close = pd.concat([train_df[close_col], test_df[close_col]])

        for i in range(len(test_df)):
            # Context: all data up to this test day
            ctx_end = len(train_df) + i
            ctx = torch.tensor(full_close.iloc[max(0, ctx_end - 200):ctx_end].values, dtype=torch.float32)

            # Predict next forward_days
            forecast = pipeline.predict(ctx.unsqueeze(0), self.forward_days)
            # forecast shape: (1, num_samples, forward_days) — take median
            median_forecast = forecast.median(dim=1).values[0]

            # Signal: 1 if predicted final price > current price
            current_price = float(full_close.iloc[ctx_end - 1])
            predicted_price = float(median_forecast[-1])
            signals.append(1 if predicted_price > current_price else 0)

        return pd.Series(signals, index=test_df.index)

    def _run_moirai2(self, train_df: pd.DataFrame, test_df: pd.DataFrame) -> Optional[pd.Series]:
        """
        Run MOIRAI-2 (Salesforce) pretrained time series foundation model.
        Zero-shot probabilistic forecasting via uni2ts — direct tensor API.
        Returns a signal series: 1 (predicted up), 0 (predicted down/flat).
        """
        try:
            import torch
            from uni2ts.model.moirai2 import Moirai2Forecast, Moirai2Module
        except ImportError:
            return None

        close_col = "Close" if "Close" in train_df.columns else "Adj Close"
        full_close = pd.concat([train_df[close_col], test_df[close_col]])

        # Context must be multiple of patch_size (16 for moirai-2.0-R-small)
        patch_size = 16
        ctx_len = (200 // patch_size) * patch_size  # 192

        module = Moirai2Module.from_pretrained("Salesforce/moirai-2.0-R-small")
        model = Moirai2Forecast(
            module=module,
            prediction_length=self.forward_days,
            context_length=ctx_len,
            target_dim=1,
            feat_dynamic_real_dim=0,
            past_feat_dynamic_real_dim=0,
        )
        model.eval()

        signals = []
        for i in range(len(test_df)):
            ctx_end = len(train_df) + i
            ctx_vals = full_close.iloc[max(0, ctx_end - ctx_len):ctx_end].values.astype(float)

            # Ensure exact ctx_len by padding or trimming
            if len(ctx_vals) < ctx_len:
                pad_len = ctx_len - len(ctx_vals)
                ctx_vals = np.concatenate([np.full(pad_len, ctx_vals[0]), ctx_vals])
                is_pad = np.concatenate([np.ones(pad_len), np.zeros(ctx_len - pad_len)])
            else:
                ctx_vals = ctx_vals[-ctx_len:]
                is_pad = np.zeros(ctx_len)

            # Shape: (batch=1, time=ctx_len, tgt=1)
            past_target = torch.tensor(ctx_vals, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
            past_observed = torch.ones_like(past_target, dtype=torch.bool)
            past_is_pad = torch.tensor(is_pad, dtype=torch.bool).unsqueeze(0)

            with torch.no_grad():
                # Output shape: (1, 9_quantiles, forward_days)
                quantiles = model(past_target, past_observed, past_is_pad)

            # Median quantile (index 4 of 9: [0.1,0.2,...,0.9])
            # Values are price-level predictions
            predicted_price = float(quantiles[0, 4, -1])
            current_price = float(ctx_vals[-1])
            signals.append(1 if predicted_price > current_price else 0)

        return pd.Series(signals, index=test_df.index)

    def get_feature_importance(self, model_name: str = "random_forest") -> pd.DataFrame:
        """Return feature importance from RF model."""
        if model_name not in self.models:
            return pd.DataFrame()
        model_data = self.models[model_name]
        model = model_data.get("model")
        if model is None or not hasattr(model, "feature_importances_"):
            return pd.DataFrame()
        feat_names = model_data.get("feature_names", [])
        imp = model.feature_importances_
        df = pd.DataFrame({"feature": feat_names, "importance": imp})
        return df.sort_values("importance", ascending=False).head(10)

    # ──────────────────────────────────────────────────────────────────────
    # RUN ALL
    # ──────────────────────────────────────────────────────────────────────

    def run_all(self) -> Dict:
        """Train all models, generate signals, backtest, return comparison.

        Uses in-memory cache (1h TTL) to avoid retraining on repeated calls.
        """
        X_train, y_train = _make_features_labels(self.train_df, self.forward_days)
        X_test,  _       = _make_features_labels(self.test_df,  self.forward_days)
        feat_names = list(X_train.columns)

        # Check cache
        cached = _get_cached(self._ticker, len(self.train_df))
        if cached:
            self.models = cached
            # Re-generate signals from cached models on current test data
            results = {}
            for name, model_data in cached.items():
                model = model_data.get("model")
                scaler = model_data.get("scaler")
                if model is not None:
                    try:
                        sig = self._signal_from_model(model, X_test, scaler)
                        full_sig = pd.Series(0, index=self.test_df.index)
                        full_sig.loc[sig.index] = sig
                        metrics = self._backtest_signal(self.test_df, full_sig)
                        results[name] = {"metrics": metrics, "signal": full_sig, "status": "ok"}
                    except Exception:
                        pass
            if results:
                # Still need to add buy_and_hold and advanced models
                # Fall through to add them below, but skip retraining core models
                self.results = results
                # Skip to advanced models section below
                # (core models already done from cache)

        results = getattr(self, "results", {})

        # ── Random Forest (skip if cached) ──
        rf_model, rf_scaler = None, None
        if "random_forest" not in results:
            rf_model, rf_scaler = self._train_random_forest(X_train, y_train)
        else:
            rf_model = self.models.get("random_forest", {}).get("model")
            rf_scaler = self.models.get("random_forest", {}).get("scaler")
        if rf_model is not None:
            sig = self._signal_from_model(rf_model, X_test, rf_scaler)
            # Align signal with test_df index
            full_sig = pd.Series(0, index=self.test_df.index)
            full_sig.loc[sig.index] = sig
            metrics = self._backtest_signal(self.test_df, full_sig)
            results["random_forest"] = {"metrics": metrics, "signal": full_sig}
            self.models["random_forest"] = {
                "model": rf_model, "scaler": rf_scaler, "feature_names": feat_names}

            # Train accuracy
            from sklearn.metrics import accuracy_score
            X_tr_scaled = rf_scaler.transform(X_train.fillna(0))
            train_acc = accuracy_score(y_train, rf_model.predict(X_tr_scaled))
            results["random_forest"]["train_accuracy"] = round(float(train_acc), 4)

        # ── XGBoost ──
        xgb_model = self._train_xgboost(X_train.fillna(0), y_train)
        if xgb_model is not None:
            sig = self._signal_from_model(xgb_model, X_test)
            full_sig = pd.Series(0, index=self.test_df.index)
            full_sig.loc[sig.index] = sig
            metrics = self._backtest_signal(self.test_df, full_sig)
            results["xgboost"] = {"metrics": metrics, "signal": full_sig}
            self.models["xgboost"] = {"model": xgb_model, "feature_names": feat_names}

        # ── Logistic Regression ──
        lr_model, lr_scaler = self._train_logistic(X_train, y_train)
        if lr_model is not None:
            sig = self._signal_from_model(lr_model, X_test, lr_scaler)
            full_sig = pd.Series(0, index=self.test_df.index)
            full_sig.loc[sig.index] = sig
            metrics = self._backtest_signal(self.test_df, full_sig)
            results["logistic_regression"] = {"metrics": metrics, "signal": full_sig}
            self.models["logistic_regression"] = {
                "model": lr_model, "scaler": lr_scaler, "feature_names": feat_names}

        # ── Chronos-2 (pretrained time series foundation model) ──
        try:
            chronos_sig = self._run_chronos(self.train_df, self.test_df)
            if chronos_sig is not None:
                metrics = self._backtest_signal(self.test_df, chronos_sig)
                results["chronos2"] = {"metrics": metrics, "signal": chronos_sig, "status": "ok"}
            else:
                results["chronos2"] = {"metrics": _empty_metrics(), "status": "skipped", "error": "No signal generated"}
        except Exception as exc:
            logger.warning("Chronos-2 failed: %s", exc)
            results["chronos2"] = {"metrics": _empty_metrics(), "status": "failed", "error": str(exc)[:80]}

        # ── MOIRAI-2 (Salesforce pretrained time series foundation model) ──
        try:
            moirai_sig = self._run_moirai2(self.train_df, self.test_df)
            if moirai_sig is not None:
                metrics = self._backtest_signal(self.test_df, moirai_sig)
                results["moirai2"] = {"metrics": metrics, "signal": moirai_sig, "status": "ok"}
            else:
                results["moirai2"] = {"metrics": _empty_metrics(), "status": "skipped", "error": "No signal generated"}
        except Exception as exc:
            logger.warning("MOIRAI-2 failed: %s", exc)
            results["moirai2"] = {"metrics": _empty_metrics(), "status": "failed", "error": str(exc)[:80]}

        # ── EMAformer (AAAI 2026 — Embedding Armor Transformer) ──
        try:
            from engine.emaformer import EMAformerPredictor
            ema = EMAformerPredictor(seq_len=60, pred_len=self.forward_days, epochs=30)
            ema.fit(self.train_df)
            ema_sig = ema.predict_with_context(self.train_df, self.test_df)
            if ema_sig is not None:
                metrics = self._backtest_signal(self.test_df, ema_sig)
                results["emaformer"] = {"metrics": metrics, "signal": ema_sig, "status": "ok"}
            else:
                results["emaformer"] = {"metrics": _empty_metrics(), "status": "skipped", "error": "No signal"}
        except Exception as exc:
            logger.warning("EMAformer failed: %s", exc)
            results["emaformer"] = {"metrics": _empty_metrics(), "status": "failed", "error": str(exc)[:80]}

        # ── Diffusion (DDPM probabilistic forecasting) ──
        try:
            from engine.diffusion_signal import DiffusionPredictor
            diff = DiffusionPredictor(context_len=60, pred_len=self.forward_days, epochs=30, n_samples=20)
            diff.fit(self.train_df)
            diff_sig = diff.predict_signal_series(self.train_df, self.test_df)
            if diff_sig is not None:
                metrics = self._backtest_signal(self.test_df, diff_sig)
                results["diffusion"] = {"metrics": metrics, "signal": diff_sig, "status": "ok"}
            else:
                results["diffusion"] = {"metrics": _empty_metrics(), "status": "skipped", "error": "No signal"}
        except Exception as exc:
            logger.warning("Diffusion failed: %s", exc)
            results["diffusion"] = {"metrics": _empty_metrics(), "status": "failed", "error": str(exc)[:80]}

        # ── GNN (Graph Neural Network inter-stock signals) ──
        try:
            from engine.gnn_signal import GNNSignalGenerator
            gnn = GNNSignalGenerator(target=getattr(self, '_ticker', 'NVDA'))
            gnn_result = gnn.run()
            gnn_sig = gnn_result.get("signal_series")
            if gnn_sig is not None and len(gnn_sig) > 0:
                aligned = pd.Series(0, index=self.test_df.index)
                common_idx = aligned.index.intersection(gnn_sig.index)
                aligned.loc[common_idx] = gnn_sig.loc[common_idx].astype(int)
                metrics = self._backtest_signal(self.test_df, aligned)
                results["gnn"] = {
                    "metrics": metrics, "signal": aligned, "status": "ok",
                    "graph_context": {
                        "consensus": gnn_result.get("consensus"),
                        "accuracy": gnn_result.get("accuracy"),
                        "neighbors": gnn_result.get("neighbor_signals"),
                    },
                }
            else:
                results["gnn"] = {"metrics": _empty_metrics(), "status": "skipped", "error": "No signal"}
        except Exception as exc:
            logger.warning("GNN failed: %s", exc)
            results["gnn"] = {"metrics": _empty_metrics(), "status": "failed", "error": str(exc)[:80]}

        # ── RL Agent (PPO reinforcement learning) ──
        try:
            from engine.rl_agent import RLTrader
            rl = RLTrader(total_timesteps=20000)
            if rl.train(self.train_df):
                rl_sig = rl.predict(self.test_df)
                if rl_sig is not None:
                    metrics = self._backtest_signal(self.test_df, rl_sig)
                    results["rl_ppo"] = {"metrics": metrics, "signal": rl_sig, "status": "ok"}
                else:
                    results["rl_ppo"] = {"metrics": _empty_metrics(), "status": "skipped", "error": "No signal"}
            else:
                results["rl_ppo"] = {"metrics": _empty_metrics(), "status": "failed", "error": "Training failed"}
        except Exception as exc:
            logger.warning("RL PPO failed: %s", exc)
            results["rl_ppo"] = {"metrics": _empty_metrics(), "status": "failed", "error": str(exc)[:80]}

        # ── Buy & Hold baseline ──
        bh_sig = pd.Series(1, index=self.test_df.index)
        results["buy_and_hold"] = {
            "metrics": self._backtest_signal(self.test_df, bh_sig),
            "signal": bh_sig}

        self.results = results

        # ── Summary table ──
        rows = []
        for name, data in results.items():
            m = data["metrics"]
            rows.append({
                "model":        name,
                "sharpe":       m["sharpe"],
                "total_return": m["total_return"],
                "max_drawdown": m["max_drawdown"],
                "win_rate":     m["win_rate"],
                "n_trades":     m["n_trades"],
                "excess_return":m["excess_return"],
                "train_acc":    data.get("train_accuracy", "-"),
            })
        summary = pd.DataFrame(rows).sort_values("sharpe", ascending=False)

        # Save trained models to cache
        if self.models:
            _set_cache(self._ticker, len(self.train_df), self.models)

        # Best ML model
        ml_only = {k: v for k, v in results.items()
                   if k != "buy_and_hold" and v.get("status", "ok") == "ok"}
        best_name = max(ml_only, key=lambda k: ml_only[k]["metrics"]["sharpe"]) if ml_only else None

        return {
            "results":      results,
            "summary":      summary,
            "best_model":   best_name,
            "best_metrics": results[best_name]["metrics"] if best_name else {},
            "feature_importance": self.get_feature_importance("random_forest"),
            "n_features":   len(feat_names),
            "forward_days": self.forward_days,
        }


# ── Convenience function called from brain.py ──
def run_ml_analysis(
    train_df: pd.DataFrame,
    test_df:  pd.DataFrame,
    ticker:   str,
    transaction_cost: float = 0.001,
    slippage: float = 0.001,
) -> Dict:
    try:
        gen = MLSignalGenerator(train_df, test_df,
                                transaction_cost=transaction_cost,
                                slippage=slippage,
                                ticker=ticker)
        result = gen.run_all()
        result["ticker"] = ticker
        result["error"]  = None
        return result
    except Exception as e:
        return {"ticker": ticker, "error": str(e),
                "results": {}, "summary": pd.DataFrame(),
                "best_model": None, "best_metrics": {}}
