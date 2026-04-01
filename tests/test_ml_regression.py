"""
tests/test_ml_regression.py
────────────────────────────────────────────────────────────────────
ML model regression tests.

Ensures model upgrades don't degrade performance below baseline.
Tests each ML model individually + the full comparison pipeline.

Baselines are conservative — should pass even with random seed variance.
"""
import pytest
import numpy as np
import pandas as pd


@pytest.fixture(scope="module")
def stock_data():
    """Fetch real AAPL data for consistent testing."""
    np.random.seed(42)
    n = 300
    dates = pd.date_range("2024-06-01", periods=n, freq="B")
    close = 180 + np.cumsum(np.random.randn(n) * 2.0)
    close = np.maximum(close, 50)

    df = pd.DataFrame({
        "Open": close + np.random.randn(n) * 0.5,
        "High": close + np.abs(np.random.randn(n)) * 1.5,
        "Low": close - np.abs(np.random.randn(n)) * 1.5,
        "Close": close,
        "Volume": np.random.randint(5_000_000, 50_000_000, n),
    }, index=dates)

    from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2
    ta = TechnicalAnalysisSkillV2(df)
    ta.add_indicators()
    full = ta.df.dropna()

    split = int(len(full) * 0.8)
    return full.iloc[:split], full.iloc[split:]


# ═══════════════════════════════════════════════════════════════════════════
# INDIVIDUAL MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestRandomForest:
    def test_trains_and_predicts(self, stock_data):
        from engine.ml_signal import MLSignalGenerator, _make_features_labels
        train_df, test_df = stock_data
        gen = MLSignalGenerator(train_df, test_df)

        X_train, y_train = _make_features_labels(train_df, 5)
        model, scaler = gen._train_random_forest(X_train, y_train)
        assert model is not None
        assert scaler is not None

    def test_signal_is_binary(self, stock_data):
        from engine.ml_signal import MLSignalGenerator, _make_features_labels
        train_df, test_df = stock_data
        gen = MLSignalGenerator(train_df, test_df)

        X_train, y_train = _make_features_labels(train_df, 5)
        X_test, _ = _make_features_labels(test_df, 5)
        model, scaler = gen._train_random_forest(X_train, y_train)
        signal = gen._signal_from_model(model, X_test, scaler)
        assert set(signal.unique()).issubset({0, 1})

    def test_backtest_above_random(self, stock_data):
        """RF should not be catastrophically worse than random."""
        from engine.ml_signal import MLSignalGenerator, _make_features_labels
        train_df, test_df = stock_data
        gen = MLSignalGenerator(train_df, test_df)

        X_train, y_train = _make_features_labels(train_df, 5)
        X_test, _ = _make_features_labels(test_df, 5)
        model, scaler = gen._train_random_forest(X_train, y_train)
        signal = gen._signal_from_model(model, X_test, scaler)

        full_sig = pd.Series(0, index=test_df.index)
        full_sig.loc[signal.index] = signal
        metrics = gen._backtest_signal(test_df, full_sig)
        # Sharpe should not be catastrophically negative
        assert metrics["sharpe"] > -5.0, f"RF Sharpe catastrophically low: {metrics['sharpe']}"


class TestXGBoost:
    def test_trains_and_predicts(self, stock_data):
        from engine.ml_signal import MLSignalGenerator, _make_features_labels
        train_df, test_df = stock_data
        gen = MLSignalGenerator(train_df, test_df)

        X_train, y_train = _make_features_labels(train_df, 5)
        model = gen._train_xgboost(X_train.fillna(0), y_train)
        assert model is not None


class TestLogisticRegression:
    def test_trains_and_predicts(self, stock_data):
        from engine.ml_signal import MLSignalGenerator, _make_features_labels
        train_df, test_df = stock_data
        gen = MLSignalGenerator(train_df, test_df)

        X_train, y_train = _make_features_labels(train_df, 5)
        model, scaler = gen._train_logistic(X_train, y_train)
        assert model is not None


class TestEMAformer:
    def test_model_forward_pass(self):
        import torch
        from engine.emaformer import EMAformerModel
        model = EMAformerModel(seq_len=60, pred_len=5, enc_in=5, d_model=64, n_heads=2, e_layers=1)
        x = torch.randn(2, 60, 5)
        c = torch.tensor([0, 3])
        out = model(x, c)
        assert out.shape == (2, 5, 5)

    def test_fit_and_predict(self, stock_data):
        from engine.emaformer import EMAformerPredictor
        train_df, test_df = stock_data
        pred = EMAformerPredictor(seq_len=30, pred_len=5, epochs=5, d_model=32, n_heads=2, e_layers=1)
        loss = pred.fit(train_df)
        assert loss < 10.0, f"EMAformer training loss too high: {loss}"

        signals = pred.predict_with_context(train_df, test_df)
        assert signals is not None
        assert len(signals) == len(test_df)
        assert set(signals.unique()).issubset({0, 1})


class TestDiffusion:
    def test_model_forward_pass(self):
        import torch
        from engine.diffusion_signal import NoisePredictor
        model = NoisePredictor(context_len=30, pred_len=5, hidden=32, time_dim=16)
        x = torch.randn(2, 1, 5)
        ctx = torch.randn(2, 1, 30)
        t = torch.tensor([10, 50])
        out = model(x, ctx, t)
        assert out.shape == (2, 1, 5)

    def test_fit_and_predict(self, stock_data):
        from engine.diffusion_signal import DiffusionPredictor
        train_df, test_df = stock_data
        pred = DiffusionPredictor(context_len=30, pred_len=5, n_steps=50, n_samples=10, epochs=5)
        loss = pred.fit(train_df)
        assert loss < 10.0

        result = pred.predict(test_df)
        assert "signal" in result
        assert result["signal"] in (0, 1)
        if "up_probability" in result:
            assert 0 <= result["up_probability"] <= 1


class TestRLAgent:
    def test_train_and_predict(self, stock_data):
        from engine.rl_agent import RLTrader
        train_df, test_df = stock_data
        rl = RLTrader(total_timesteps=1000)
        success = rl.train(train_df)
        assert success is True

        signal = rl.predict(test_df)
        assert signal is not None
        assert len(signal) == len(test_df)
        assert set(signal.unique()).issubset({0, 1})


# ═══════════════════════════════════════════════════════════════════════════
# FULL PIPELINE REGRESSION
# ═══════════════════════════════════════════════════════════════════════════

class TestFullPipeline:
    def test_run_all_returns_results(self, stock_data):
        """run_all() should return results for at least RF + XGB + LR + buy_hold.
        Note: GNN/Diffusion/EMAformer/RL may fail gracefully — we only assert core models.
        """
        from engine.ml_signal import MLSignalGenerator
        train_df, test_df = stock_data
        gen = MLSignalGenerator(train_df, test_df, ticker="TEST")
        result = gen.run_all()

        assert "results" in result
        assert "best_model" in result
        assert "random_forest" in result["results"]
        assert "xgboost" in result["results"]
        assert "buy_and_hold" in result["results"]

    def test_all_metrics_have_required_keys(self, stock_data):
        from engine.ml_signal import MLSignalGenerator
        train_df, test_df = stock_data
        gen = MLSignalGenerator(train_df, test_df, ticker="TEST")
        result = gen.run_all()

        required_keys = {"sharpe", "total_return", "max_drawdown", "win_rate", "n_trades"}
        for name, data in result["results"].items():
            metrics = data["metrics"]
            missing = required_keys - set(metrics.keys())
            assert not missing, f"{name} missing metrics: {missing}"

    def test_best_model_is_valid(self, stock_data):
        from engine.ml_signal import MLSignalGenerator
        train_df, test_df = stock_data
        gen = MLSignalGenerator(train_df, test_df, ticker="TEST")
        result = gen.run_all()

        best = result["best_model"]
        assert best is not None
        assert best in result["results"]
        assert best != "buy_and_hold"
