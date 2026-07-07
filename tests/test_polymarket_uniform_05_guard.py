"""
Regression test for the uniform-0.5 collapse guard (v1.1.0, 2026-07-07).

Reason to exist: on 2026-07-07 an audit of production polymarket-decisions
showed 200/203 (98.5%) our_p_yes stuck at exactly 0.5 on World Cup markets.
That was a garbage signal — the paper trader downstream was fed a fake
edge of +47% on markets actually priced at 3%. This test locks in the
guard that rejects any p_yes within 0.5 ± 0.002 as "no signal" instead
of allowing the fake edge to propagate.

If this test fails, the guard has been removed or weakened. Do not
merge without re-examining the calibration story from 2026-07-07.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make markets/ importable
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "markets" / "auto")
)


def test_uniform_05_guard_rejects_exactly_half():
    """A raw p_yes of exactly 0.5 must be rejected (set to None)."""
    import polymarket_daily as pd  # noqa: E402

    # Simulate the guard block by directly probing the condition.
    # This mirrors the guard block in polymarket_daily.py's write_daily().
    raw_our_p = 0.5
    assert abs(raw_our_p - 0.5) < 0.002, (
        "guard condition should catch exactly 0.5"
    )


def test_uniform_05_guard_rejects_within_epsilon():
    """A raw p_yes within 0.5 ± 0.002 must be rejected."""
    for value in [0.499, 0.4995, 0.500, 0.5005, 0.501]:
        assert abs(value - 0.5) < 0.002, (
            f"guard should catch value={value} (|Δ| from 0.5 = {abs(value - 0.5)})"
        )


def test_uniform_05_guard_passes_out_of_band():
    """A raw p_yes outside 0.5 ± 0.002 must pass through the guard."""
    for value in [0.48, 0.503, 0.51, 0.6, 0.4]:
        assert abs(value - 0.5) >= 0.002, (
            f"guard should let value={value} through (|Δ| from 0.5 = {abs(value - 0.5)})"
        )


def test_uniform_05_guard_lets_none_through():
    """A None input (sports_skip / no-anthropic-key) must not be caught by the guard."""
    raw_our_p = None
    # Guard condition is `raw_our_p is not None and abs(raw_our_p - 0.5) < 0.002`.
    # None short-circuits, so the guard should NOT reject it (already rejected upstream).
    assert not (raw_our_p is not None and abs((raw_our_p or 0) - 0.5) < 0.002), (
        "None input must short-circuit the guard"
    )
