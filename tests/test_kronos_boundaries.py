"""Daily date, forecast-vote and context regressions with no model/network calls."""
from __future__ import annotations

import ast
import asyncio
import importlib
import json
import sys
import time
import types
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from engine import kronos_signal as ks
from engine import multi_agent_analysis as ma
from engine.signal_fusion import _score_ml
from models.decision import DecisionOutput


def _bars(end="2026-10-02", n=100):
    sessions = xcals.get_calendar("XNYS", start="2023-01-01", end="2027-12-31")
    dates = sessions.sessions[sessions.sessions <= pd.Timestamp(end)][-n:]
    return pd.DataFrame({"open": 100., "high": 101., "low": 99.,
                         "close": 100., "volume": 1000.}, index=dates)


class RecordingPredictor:
    def __init__(self, closes=None):
        self.calls = []
        self.closes = closes

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        values = self.closes if self.closes is not None else [100.] * kwargs["pred_len"]
        return pd.DataFrame({"close": values})


@pytest.fixture
def predictor(monkeypatch):
    p = RecordingPredictor()
    monkeypatch.setattr(ks, "_ensure_kronos", lambda size: p)
    return p


@pytest.mark.parametrize("end,expected", [
    ("2026-10-02", ["2026-10-05", "2026-10-06", "2026-10-07"]),
    ("2026-04-02", ["2026-04-06", "2026-04-07", "2026-04-08"]),
    ("2026-06-18", ["2026-06-22", "2026-06-23", "2026-06-24"]),
    ("2026-07-02", ["2026-07-06", "2026-07-07", "2026-07-08"]),
    ("2026-09-04", ["2026-09-08", "2026-09-09", "2026-09-10"]),
    ("2026-11-25", ["2026-11-27", "2026-11-30", "2026-12-01"]),
])
def test_future_dates_skip_weekends_and_exchange_holidays(predictor, end, expected):
    out = ks.KronosSignal().predict(_bars(end), pred_len=3)
    assert out is not None
    assert predictor.calls[0]["y_timestamp"].dt.strftime("%Y-%m-%d").tolist() == expected
    assert out.attrs["orallexa_forecast"]["target_sessions"] == expected


@pytest.mark.parametrize("index_kind", ["range", "wrong_dates"])
def test_explicit_timestamps_override_index(predictor, index_kind):
    df = _bars()
    dates = df.index.copy()
    df["timestamps"] = dates
    df.index = (pd.RangeIndex(len(df)) if index_kind == "range"
                else dates - pd.DateOffset(years=3))
    assert ks.KronosSignal().predict(df) is not None
    pd.testing.assert_series_equal(predictor.calls[0]["x_timestamp"], pd.Series(dates[-64:]),
                                   check_names=False)
    assert len(predictor.calls[0]["df"]) == 64
    assert "timestamps" not in predictor.calls[0]["df"]


def test_timezone_aware_daily_session_labels(predictor):
    df = _bars()
    df.index = df.index.tz_localize("America/New_York")
    assert ks.KronosSignal().predict(df) is not None
    assert predictor.calls[0]["x_timestamp"].iloc[-1] == pd.Timestamp("2026-10-02")


@pytest.mark.parametrize("bad_dates", ["numeric_index", "numeric_column", "invalid_column",
                                       "missing_column", "duplicate", "out_of_order", "weekend"])
def test_invalid_dates_do_not_load_predictor(monkeypatch, bad_dates):
    calls = []
    monkeypatch.setattr(ks, "_ensure_kronos", lambda size: calls.append(size))
    df = _bars()
    if bad_dates == "numeric_index":
        df = df.reset_index(drop=True)
    elif bad_dates == "numeric_column":
        df["timestamps"] = np.arange(len(df))
    elif bad_dates == "invalid_column":
        df["timestamps"] = "not a date"
    elif bad_dates == "missing_column":
        df["timestamps"] = pd.NaT
    else:
        dates = df.index.to_list()
        if bad_dates == "duplicate":
            dates[-1] = dates[-2]
        elif bad_dates == "out_of_order":
            dates[-2], dates[-1] = dates[-1], dates[-2]
        else:
            dates[-1] = pd.Timestamp("2026-10-03")
        df.index = dates
    assert ks.KronosSignal().predict(df) is None
    assert calls == []


@pytest.mark.parametrize("bad", [0, -1, 513, 2.5, True])
def test_invalid_horizon_does_not_load_predictor(monkeypatch, bad):
    calls = []
    monkeypatch.setattr(ks, "_ensure_kronos", lambda size: calls.append(size))
    assert ks.KronosSignal().predict(_bars(), pred_len=bad) is None
    assert calls == []


@pytest.mark.parametrize("col,value", [("close", np.nan), ("open", np.inf),
                                        ("close", 0), ("volume", -1)])
def test_invalid_history_values_do_not_load_predictor(monkeypatch, col, value):
    calls = []
    monkeypatch.setattr(ks, "_ensure_kronos", lambda size: calls.append(size))
    df = _bars()
    df.loc[df.index[-1], col] = value
    assert ks.KronosSignal().predict(df) is None
    assert calls == []


def test_exact_lookback_is_sufficient(predictor):
    assert ks.KronosSignal().predict(_bars(n=64)) is not None


def test_flat_forecast_remains_neutral_through_fusion(predictor):
    sig = ks.KronosSignal()
    entry = sig.for_ml_ensemble(_bars())
    assert entry["status"] == "ok"
    assert entry["metrics"] == {}
    assert entry["forecast"]["expected_return_pct"] == 0
    assert entry["directional_score"] == 0
    vote = _score_ml({"results": {"kronos": entry}})
    assert vote == {"score": 0, "available": True, "agreement": 0, "n_models": 1}
    assert sig.score_for_fusion(_bars())["monotone_pct"] == .5


@pytest.mark.parametrize("path,expected", [([105, 104, 103, 102, 101], 20),
                                          ([90, 91, 92, 93, 94], -100)])
def test_direction_uses_return_from_current_price_not_path_slope(predictor, path, expected):
    predictor.closes = path
    entry = ks.KronosSignal().for_ml_ensemble(_bars())
    assert entry["directional_score"] == expected
    assert _score_ml({"results": {"kronos": entry}})["score"] == expected


@pytest.mark.parametrize("path", [[100, 100, np.nan, 100, 100],
                                  [100, 100, 100, 100, np.inf],
                                  [100, 100, 100, 100, 0], [100] * 6])
def test_invalid_forecast_is_unavailable(predictor, path):
    predictor.closes = path
    assert ks.KronosSignal().for_ml_ensemble(_bars())["status"] == "error"


@pytest.mark.parametrize("vote", [np.nan, np.inf, -np.inf, True, "20", 101, -101, None])
def test_malformed_forecast_vote_is_ignored(vote):
    result = _score_ml({"results": {"kronos": {
        "status": "ok", "signal_type": "price_forecast", "directional_score": vote}}})
    assert result["available"] is False
    assert result["score"] == 0


def test_legacy_kronos_metrics_ignored_and_other_voters_preserved():
    results = {"random_forest": {"metrics": {"sharpe": 1.5, "total_return": .1}},
               "xgboost": {"metrics": {"sharpe": .8, "total_return": .05}}}
    before = _score_ml({"results": results})
    assert before == {"score": 53, "available": True, "agreement": 100, "n_models": 2}
    results["kronos"] = {"status": "ok", "metrics": {"sharpe": -2, "total_return": 0}}
    assert _score_ml({"results": results}) == before


@pytest.fixture
def offline_ml(monkeypatch):
    def install(name, **attrs):
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)
        package, attribute = name.rsplit(".", 1)
        monkeypatch.setattr(importlib.import_module(package), attribute, module, raising=False)

    calls = []

    def fake_ml(**kwargs):
        calls.append(kwargs)
        return {"results": {"random_forest": {"status": "ok", "metrics": {}}}}

    install("engine.ml_signal", run_ml_analysis=fake_ml)
    return install, calls


def test_forecast_context_is_independent_of_backtest_split(predictor, offline_ml):
    _, calls = offline_ml
    full = _bars()
    train, test = full.iloc[:70], full.iloc[70:]
    report, result = ma._run_ml_analyst(train, test, "TEST", forecast_df=full)
    assert calls[0]["train_df"] is train and calls[0]["test_df"] is test
    assert predictor.calls[0]["x_timestamp"].iloc[-1] == full.index[-1]
    assert predictor.calls[0]["x_timestamp"].iloc[-1] > train.index[-1]
    assert result["results"]["kronos"]["forecast"]["last_session"] == "2026-10-02"
    assert "Kronos price forecast" in report
    assert "not a backtest return" in report


def test_omitted_context_skips_kronos(predictor, offline_ml):
    full = _bars()
    _, result = ma._run_ml_analyst(full.iloc[:70], full.iloc[70:], "TEST")
    assert predictor.calls == []
    assert "kronos" not in result["results"]


def _brain(full):
    return types.SimpleNamespace(
        _prepare_data=lambda: full,
        _single_split=lambda df: (df.iloc[:70], df.iloc[70:]),
        _safe_summary_from_df=lambda df: {"close": 100.})


def test_main_pipeline_forwards_latest_context(monkeypatch, predictor, offline_ml):
    install, _ = offline_ml
    full = _bars()
    decision = DecisionOutput("WAIT", 40, "MEDIUM", [], {"up": .5, "down": .5}, "test")
    install("skills.prediction", PredictionSkill=lambda ticker: types.SimpleNamespace(
        execute=lambda **kwargs: decision))
    install("llm.debate", run_lightweight_debate=lambda **kwargs: decision)
    install("llm.perspective_panel", run_perspective_panel=lambda **kwargs: {})
    install("llm.claude_client", get_client=lambda: object())
    install("engine.strategies", _detect_regime=lambda df: pd.Series(["neutral"]))
    monkeypatch.setattr(ma, "_run_market_analyst", lambda *args: "Market")
    monkeypatch.setattr(ma, "_run_news_analyst", lambda ticker: ("News", []))
    monkeypatch.setattr(ma, "_run_risk_manager", lambda *args: {})
    monkeypatch.setattr(ma, "_run_llm_market_report", lambda *args: "Market")
    import engine.signal_fusion as fusion

    def local_fusion(**kwargs):
        ml = _score_ml(kwargs["ml_result"])
        return {"conviction": ml["score"], "direction": "NEUTRAL", "fusion_detail": ""}

    monkeypatch.setattr(fusion, "fuse_signals", local_fusion)
    result = ma.run_multi_agent_analysis("TEST", trade_date="2026-10-05", brain=_brain(full))
    assert predictor.calls[0]["x_timestamp"].iloc[-1] == full.index[-1]
    assert "after 2026-10-02" in result.fundamentals_report
    assert result.signal_fusion["conviction"] == 0


def test_stream_startup_forwards_latest_context(monkeypatch, predictor, offline_ml):
    """Execute the real SSE generator through step 3, before any LLM stage.

    Extracting the generator avoids importing the API server and its optional
    providers. This covers data/ML handoff, not HTTP auth or the remaining stream.
    """
    install, _ = offline_ml
    full = _bars()
    install("core.brain", OrallexaBrain=lambda ticker: _brain(full))
    monkeypatch.setattr(ma, "_run_market_analyst", lambda *args: "Market")
    monkeypatch.setattr(ma, "_run_news_analyst", lambda ticker: ("News", []))
    filename = Path(__file__).resolve().parents[1] / "api_server.py"
    tree = ast.parse(filename.read_text())
    generators = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                  and n.name == "event_stream"]
    assert len(generators) == 1
    code = compile(ast.Module(body=generators, type_ignores=[]), str(filename), "exec")
    namespace = {"tk": "TEST", "json": json, "time": time, "asyncio": asyncio}
    exec(code, namespace)

    async def startup():
        stream = namespace["event_stream"]()
        events = [await anext(stream) for _ in range(3)]
        await stream.aclose()
        return events

    events = asyncio.run(startup())
    assert '"step": 3' in events[-1]
    assert predictor.calls[0]["x_timestamp"].iloc[-1] == full.index[-1]
