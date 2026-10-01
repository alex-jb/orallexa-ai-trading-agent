"""Offline contract and information-cutoff checks for the ICAIF adapter."""

import json
from datetime import date, timedelta

import pytest

from competition.icaif2026_sma import strategy, weights_from_bars


SYMBOLS = [f"X{number:02d}" for number in range(30)]


def _sessions(count=50, last=date(2026, 10, 7)):
    dates = []
    day = last
    while len(dates) < count:
        if day.weekday() < 5:
            dates.append(day)
        day -= timedelta(days=1)
    return list(reversed(dates))


def _bars(bulls=()):
    sessions = _sessions()
    return {
        symbol: [
            {"timestamp": f"{day.isoformat()}T16:00:00-04:00",
             "available_at": f"{day.isoformat()}T16:01:00-04:00",
             "close": (100 + index if symbol in bulls else 200 - index)}
            for index, day in enumerate(sessions)
        ]
        for symbol in SYMBOLS
    }


def _observation():
    return {
        "phase": "validation", "symbols": SYMBOLS,
        "as_of": "2026-10-08T09:09:00-04:00",
        "round": {"id": "validation-2026-10-08-r1", "status": "SCHEDULED",
                  "opens_at": "2026-10-07T19:40:00+00:00",
                  "deadline": "2026-10-08T13:10:00+00:00"},
        "portfolio": {"cash": 1_000_000}, "round_state": {},
    }


def _source():
    return {"url": "https://example.org/public-prices",
            "terms_url": "https://example.org/terms",
            "access": "public_free",
            "permission_basis": "Synthetic fixture permits offline test use.",
            "competition_use_confirmed": True,
            "verified_at": "2026-10-07T17:00:00-04:00"}


def test_complete_weights_obey_cap_and_cash_without_orders():
    expected = set(SYMBOLS[:3])
    result = weights_from_bars(_observation(), _bars(expected))
    assert set(result) == set(SYMBOLS)
    assert {name for name, weight in result.items() if weight} == expected
    assert all(result[name] == 0.30 for name in expected)
    assert sum(result.values()) == pytest.approx(0.90)
    assert max(result.values()) <= 0.30


def test_five_bullish_names_share_full_allocation():
    result = weights_from_bars(_observation(), _bars(SYMBOLS[:5]))
    assert list(result.values())[:5] == [0.20] * 5
    assert sum(result.values()) == pytest.approx(1.0)


def test_future_close_is_excluded_even_if_present_in_file():
    bars = _bars()
    bars[SYMBOLS[0]].append({
        "timestamp": "2026-10-08T16:00:00-04:00",
        "available_at": "2026-10-08T16:01:00-04:00", "close": 10_000,
    })
    result = weights_from_bars(_observation(), bars)
    assert all(weight == 0 for weight in result.values())


def test_large_valid_prices_do_not_overflow_into_false_cash_signal():
    bars = _bars()
    for index, record in enumerate(bars[SYMBOLS[0]]):
        record["close"] = 1e307 if index < 30 else 1e308
    assert weights_from_bars(_observation(), bars)[SYMBOLS[0]] == 0.30


def test_missing_or_insufficient_bars_refuse_decision_instead_of_liquidating():
    observation = _observation()
    bars = _bars(SYMBOLS[:1])
    del bars[SYMBOLS[-1]]
    with pytest.raises(ValueError, match="exactly the 30"):
        weights_from_bars(observation, bars)
    bars = _bars(SYMBOLS[:1])
    bars[SYMBOLS[-1]].pop()
    with pytest.raises(ValueError, match="fewer than 50"):
        weights_from_bars(observation, bars)


def test_stale_and_not_yet_published_closes_refuse_decision():
    bars = _bars()
    bars[SYMBOLS[0]][-1]["available_at"] = "2026-10-08T09:11:00-04:00"
    with pytest.raises(ValueError, match="fewer than 50"):
        weights_from_bars(_observation(), bars)
    bars = _bars()
    old_sessions = _sessions(last=date(2026, 9, 25))
    for record, day in zip(bars[SYMBOLS[0]], old_sessions):
        record["timestamp"] = f"{day.isoformat()}T16:00:00-04:00"
        record["available_at"] = f"{day.isoformat()}T16:01:00-04:00"
    with pytest.raises(ValueError, match="fewer than 50 current"):
        weights_from_bars(_observation(), bars)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1, "100", True])
def test_invalid_price_rejected(invalid):
    bars = _bars()
    bars[SYMBOLS[0]][0]["close"] = invalid
    with pytest.raises(ValueError, match="invalid close"):
        weights_from_bars(_observation(), bars)


@pytest.mark.parametrize("time_of_day", ["10:00:00", "13:00:00", "15:00:00"])
def test_partial_day_bar_rejected(time_of_day):
    bars = _bars()
    bars[SYMBOLS[0]][-1]["timestamp"] = f"2026-10-07T{time_of_day}-04:00"
    with pytest.raises(ValueError, match="16:00 ET completed"):
        weights_from_bars(_observation(), bars)


def test_duplicate_session_rejected():
    bars = _bars()
    bars[SYMBOLS[0]].append(bars[SYMBOLS[0]][-1].copy())
    with pytest.raises(ValueError, match="duplicate market session"):
        weights_from_bars(_observation(), bars)


def test_deadline_and_cancelled_round_rejected_before_reading_bars():
    observation = _observation()
    observation["as_of"] = "2026-10-08T09:10:00-04:00"
    with pytest.raises(ValueError, match="outside"):
        weights_from_bars(observation, _bars())
    observation = _observation()
    observation["round"]["status"] = "CANCELLED"
    with pytest.raises(ValueError, match="cancelled"):
        weights_from_bars(observation, _bars())


def test_strategy_reads_only_local_file_and_rejects_duplicate_json_keys(tmp_path, monkeypatch):
    file = tmp_path / "daily_closes.json"
    file.write_text(json.dumps({"bars": _bars(SYMBOLS[:1]), "source": _source()}), encoding="utf-8")
    monkeypatch.setenv("ORALLEXA_ICAIF_BARS_FILE", str(file))
    assert strategy(_observation())[SYMBOLS[0]] == 0.30
    file.write_text('{"bars":{},"bars":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        strategy(_observation())


def test_strategy_rejects_relative_private_data_path(monkeypatch):
    monkeypatch.setenv("ORALLEXA_ICAIF_BARS_FILE", "private/bars.json")
    with pytest.raises(ValueError, match="absolute path outside"):
        strategy(_observation())


def test_unverified_paid_or_future_source_refuses_strategy(tmp_path, monkeypatch):
    file = tmp_path / "daily_closes.json"
    monkeypatch.setenv("ORALLEXA_ICAIF_BARS_FILE", str(file))
    for source in (
        None,
        {**_source(), "access": "paid"},
        {**_source(), "terms_url": ""},
        {**_source(), "competition_use_confirmed": False},
        {**_source(), "verified_at": "2026-10-08T09:11:00-04:00"},
    ):
        file.write_text(json.dumps({"bars": _bars(), "source": source}), encoding="utf-8")
        with pytest.raises(ValueError, match="source"):
            strategy(_observation())
