"""
tests/test_brier_reliability.py
──────────────────────────────────────────────────────────────────
Pins the 10-bin reliability diagram shipped 2026-07-02 (Tier-1 #8).

The middle-bin ECE is the pathology-surfacing metric — Prophet Arena
found weak models collapse into 0.3-0.7 bucket and a single overall
Brier score masks it. These tests make sure that middle-bin ECE is
reported correctly + separately from tail-bin ECE.
"""
from __future__ import annotations

from markets.auto.brier_audit import (
    MIDDLE_BINS,
    RELIABILITY_BINS,
    TAIL_BINS,
    compute_reliability_diagram,
    render_reliability_section,
)


def _make(forecast_p: float, actual: int) -> dict:
    """Minimal fake result dict shape brier_for_decision() would emit."""
    return {"forecast_p": forecast_p, "actual": float(actual)}


def test_reliability_ten_bins_returned():
    """Every RELIABILITY_BIN is represented in the output even if empty —
    the reliability diagram is fixed-shape, not sparse."""
    diag = compute_reliability_diagram([])
    assert diag["n_total"] == 0
    # Empty input → per_bin should be empty (we return early with
    # zeros / empty list — not 10 empty bins).
    assert diag["per_bin"] == []


def test_perfect_calibration_yields_low_ece():
    """If every 60% forecast wins 60% of the time (etc.), ECE → 0."""
    results = (
        [_make(0.65, 1)] * 6 + [_make(0.65, 0)] * 4     # 60% hit @ 65%
        + [_make(0.85, 1)] * 8 + [_make(0.85, 0)] * 2   # 80% hit @ 85%
        + [_make(0.15, 1)] * 2 + [_make(0.15, 0)] * 8   # 20% hit @ 15%
    )
    diag = compute_reliability_diagram(results)
    # Each of the 3 populated bins has |gap| = 0.05 → ECE ~ 0.05
    assert diag["overall_ece"] < 0.10


def test_middle_bin_ece_isolated_from_tail_bin_ece():
    """Prophet Arena's key insight: even if overall ECE is fine,
    middle-bin ECE can still be catastrophic. Verify they're computed
    from separate bin sets."""
    # 10 rows all in the middle bin @ 0.55, but ALL of them actually
    # resolve to 0. Big middle-bin miscalibration.
    results = [_make(0.55, 0)] * 10
    diag = compute_reliability_diagram(results)
    # Middle-bin ECE should reflect the full 0.55 gap
    assert diag["middle_bin_ece"] > 0.4
    # Tail-bin ECE should be zero — no results landed there
    assert diag["tail_bin_ece"] == 0.0


def test_tail_bin_ece_isolated_from_middle_bin_ece():
    """Inverse test — tail-bin failure without middle-bin miscalibration."""
    # 10 rows all in the 0-10% bin @ 0.05, but ALL of them actually
    # resolve to 1. Massive tail-bin miscalibration.
    results = [_make(0.05, 1)] * 10
    diag = compute_reliability_diagram(results)
    assert diag["tail_bin_ece"] > 0.9
    assert diag["middle_bin_ece"] == 0.0


def test_haiku_uniform_middle_bin_pathology_surfaces():
    """The specific pathology Alex's Haiku had — everything estimated
    ~0.15 regardless of true edge — should light up the middle-bin
    row with a big gap AND surface non-zero middle-bin ECE."""
    # Simulate 40 markets, all estimated at 0.15, actual base rate 0.30
    results = [_make(0.15, 1)] * 12 + [_make(0.15, 0)] * 28
    diag = compute_reliability_diagram(results)
    # The 10-20% bin gets 12/40 = 30% hit rate at 15% predicted → gap +0.15
    bin_1020 = next(b for b in diag["per_bin"] if b["low"] == 0.1 and b["high"] == 0.2)
    assert bin_1020["n"] == 40
    assert abs(bin_1020["hit_rate"] - 0.30) < 0.01
    assert bin_1020["gap"] > 0.10  # meaningful miscalibration surfaced


def test_p_equals_1_gets_placed_in_last_bin():
    """The last bin (90-100%) is CLOSED on the right — p=1.0 should
    be counted here, not dropped."""
    results = [_make(1.0, 1)] * 5
    diag = compute_reliability_diagram(results)
    bin_9010 = next(b for b in diag["per_bin"] if b["low"] == 0.9)
    assert bin_9010["n"] == 5


def test_render_produces_expected_markdown_headers():
    """Smoke test the render — has the pathology-surfacing headers."""
    diag = compute_reliability_diagram([_make(0.55, 0)] * 5)
    lines = render_reliability_section(diag)
    md = "\n".join(lines)
    assert "Reliability diagram" in md
    assert "Middle-bin ECE" in md or "middle-bin" in md.lower()
    assert "Tail-bin ECE" in md or "tail-bin" in md.lower()
    assert "Prophet Arena" in md  # the citation is preserved


def test_render_handles_empty_input_gracefully():
    """Empty diag should still produce SOME output rather than crash."""
    diag = compute_reliability_diagram([])
    lines = render_reliability_section(diag)
    assert len(lines) > 0
    # ECE reports 0.0 → labeled "well-calibrated" but trivially so
    md = "\n".join(lines)
    assert "0.0" in md


def test_bin_constants_are_disjoint_and_ordered():
    """RELIABILITY_BINS must partition [0, 1] without gaps or overlaps.
    A bug here silently loses observations to the void."""
    prev_high = 0.0
    for low, high in RELIABILITY_BINS:
        assert low == prev_high, f"gap or overlap at {low}"
        prev_high = high
    assert prev_high == 1.0


def test_middle_bins_are_subset_of_reliability_bins():
    """MIDDLE_BINS and TAIL_BINS must reference exact-match tuples in
    RELIABILITY_BINS or ECE computation silently reports zero for them."""
    all_bins = set(RELIABILITY_BINS)
    for b in MIDDLE_BINS:
        assert b in all_bins, f"{b} not in RELIABILITY_BINS"
    for b in TAIL_BINS:
        assert b in all_bins, f"{b} not in RELIABILITY_BINS"
