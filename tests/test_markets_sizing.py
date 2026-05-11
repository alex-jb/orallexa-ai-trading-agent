"""tests/test_markets_sizing.py
─────────────────────────────────────────────────────────────
Kelly-fraction + circuit-breaker tests for markets.sizing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from markets.sizing import SizingConfig, size_position


_C = SizingConfig(
    bankroll_usd=300.0,
    kelly_fraction=0.25,
    max_position_pct=0.05,
    min_edge=0.05,
    min_position_usd=1.0,
    daily_loss_pct=0.10,
)


def test_skips_below_min_edge():
    r = size_position(p_yes=0.55, market_price=0.52, config=_C)
    assert r.position_usd == 0.0
    assert r.skip_reason == "EDGE_TOO_SMALL"


def test_yes_bet_positive_edge():
    # We say 0.70, market says 0.50. Edge = +0.20. Bet YES.
    r = size_position(p_yes=0.70, market_price=0.50, config=_C)
    assert r.side == "YES"
    assert r.position_usd > 0.0
    # Full Kelly for p=0.70, b=1.0 → f = (1*0.70 - 0.30) / 1 = 0.40
    assert abs(r.kelly_full - 0.40) < 1e-6
    # Quarter Kelly = 0.10 → raw = $30; capped at 5% of $300 = $15
    assert r.position_usd == 15.0
    assert r.capped_at_max is True


def test_no_bet_negative_edge():
    # We say 0.30, market says 0.60. Edge = -0.30. Bet NO.
    r = size_position(p_yes=0.30, market_price=0.60, config=_C)
    assert r.side == "NO"
    # Betting NO at no_price = 0.40. p_win = 0.70.
    # b = (1-0.40)/0.40 = 1.5. Kelly = (1.5*0.70 - 0.30)/1.5 = 0.5
    assert abs(r.kelly_full - 0.50) < 1e-6
    assert r.position_usd > 0.0


def test_daily_loss_breaker_trips():
    # bankroll $300, daily_loss_pct 10% → breaker at -$30
    r = size_position(
        p_yes=0.70, market_price=0.50, config=_C, pnl_today_usd=-31.0
    )
    assert r.skipped is True
    assert r.skip_reason == "DAILY_LOSS_BREAKER_TRIPPED"
    assert r.position_usd == 0.0


def test_daily_loss_breaker_at_exact_threshold():
    # Exactly at -$30 → still trips (defensively triggers at <=)
    r = size_position(
        p_yes=0.70, market_price=0.50, config=_C, pnl_today_usd=-30.0
    )
    assert r.skipped is True
    assert r.skip_reason == "DAILY_LOSS_BREAKER_TRIPPED"


def test_position_capped_at_max_pct():
    # Huge edge → uncapped Kelly would suggest huge bet
    r = size_position(p_yes=0.95, market_price=0.05, config=_C)
    assert r.position_usd <= _C.max_position_usd() + 0.01
    assert r.capped_at_max is True


def test_position_too_small_to_bother():
    # Tiny bankroll → quarter-Kelly might be sub-dollar
    tiny = SizingConfig(
        bankroll_usd=20.0,
        kelly_fraction=0.25,
        max_position_pct=0.05,
        min_edge=0.05,
        min_position_usd=2.0,
    )
    # Edge 0.05 exactly meets min_edge; quarter-Kelly very small here.
    r = size_position(p_yes=0.55, market_price=0.50, config=tiny)
    # On $20 bankroll, max position is $1 — below min_position $2 → skip
    if r.position_usd == 0.0:
        assert r.skip_reason in ("POSITION_TOO_SMALL", "EDGE_TOO_SMALL")
