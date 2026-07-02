"""
tests/test_cpcv.py
──────────────────────────────────────────────────────────────────
Pins the CPCV contract shipped 2026-07-02 (Tier-2 #14).

Contract:
  - C(n_groups, k_test) splits produced (not just n_groups)
  - Every sample belongs to test in exactly C(n_groups - 1, k_test - 1)
    splits
  - Train and test are always disjoint
  - Purging removes labels overlapping test-window labels
  - Embargo removes N samples immediately after max test index
  - Degenerate inputs raise cleanly
"""
from __future__ import annotations

from math import comb

import pytest

from engine.cpcv import (
    CPCVSplit,
    embargo,
    generate_cpcv_splits,
    label_windows_from_lookahead,
    purge,
)


# ═══════════════════════════════════════════════════════════════
# Split enumeration
# ═══════════════════════════════════════════════════════════════

def test_number_of_splits_matches_c_n_k():
    """C(6, 2) = 15 splits."""
    splits = generate_cpcv_splits(n_samples=60, n_groups=6, k_test=2, embargo_pct=0)
    assert len(splits) == comb(6, 2)


def test_number_of_splits_kfold_equivalence():
    """k_test=1 collapses to k-fold — n_groups splits."""
    splits = generate_cpcv_splits(n_samples=50, n_groups=5, k_test=1, embargo_pct=0)
    assert len(splits) == 5


def test_train_and_test_disjoint():
    """No index should appear in both train and test of a single split."""
    splits = generate_cpcv_splits(n_samples=60, n_groups=6, k_test=2, embargo_pct=0)
    for split in splits:
        assert set(split.train_idx).isdisjoint(set(split.test_idx))


def test_every_sample_is_tested_c_n_minus_1_k_minus_1_times():
    """Combinatorial invariant: sample i appears in test in exactly
    C(n_groups - 1, k_test - 1) splits."""
    n_samples = 60
    n_groups = 6
    k_test = 2
    expected = comb(n_groups - 1, k_test - 1)  # C(5, 1) = 5
    splits = generate_cpcv_splits(n_samples=n_samples, n_groups=n_groups,
                                   k_test=k_test, embargo_pct=0)
    counts = {i: 0 for i in range(n_samples)}
    for s in splits:
        for i in s.test_idx:
            counts[i] += 1
    # Each sample should appear in test exactly `expected` times
    assert all(c == expected for c in counts.values()), (
        f"Coverage counts vary: min={min(counts.values())}, max={max(counts.values())}"
    )


def test_test_idx_is_sorted():
    """CPCVSplit.test_idx should be sorted for predictable downstream use."""
    splits = generate_cpcv_splits(n_samples=30, n_groups=5, k_test=2, embargo_pct=0)
    for s in splits:
        assert s.test_idx == sorted(s.test_idx)


# ═══════════════════════════════════════════════════════════════
# Guards
# ═══════════════════════════════════════════════════════════════

def test_n_samples_less_than_n_groups_raises():
    """5 samples in 6 groups → ValueError."""
    with pytest.raises(ValueError, match="n_samples"):
        generate_cpcv_splits(n_samples=5, n_groups=6, k_test=2)


def test_k_test_zero_raises():
    """k_test=0 → ValueError (no test fold)."""
    with pytest.raises(ValueError, match="k_test"):
        generate_cpcv_splits(n_samples=60, n_groups=6, k_test=0)


def test_k_test_equals_n_groups_raises():
    """k_test = n_groups → ValueError (no train fold left)."""
    with pytest.raises(ValueError, match="k_test"):
        generate_cpcv_splits(n_samples=60, n_groups=6, k_test=6)


def test_label_windows_length_mismatch_raises():
    """Wrong-length label_windows → ValueError."""
    with pytest.raises(ValueError, match="label_windows"):
        generate_cpcv_splits(n_samples=60, n_groups=6, k_test=2,
                             label_windows=[(0, 0)] * 30)


# ═══════════════════════════════════════════════════════════════
# Purging
# ═══════════════════════════════════════════════════════════════

def test_purge_removes_overlapping_labels():
    """Train sample whose label window overlaps a test label window
    should be removed."""
    # 10 samples, all with 3-day lookahead labels
    label_windows = label_windows_from_lookahead(10, lookahead=3)
    # Test on samples 4 (label [4, 7])
    train_candidates = list(range(10))
    train_candidates.remove(4)
    test_idx = [4]
    purged = purge(train_candidates, test_idx, label_windows)
    # Any train sample whose [entry, exit] overlaps [4, 7] should be gone.
    # Sample 2: label [2, 5] — overlaps [4, 7] → removed
    # Sample 6: label [6, 9] — overlaps [4, 7] → removed
    # Sample 8: label [8, 9] — doesn't overlap [4, 7] → kept
    assert 2 not in purged
    assert 3 not in purged
    assert 6 not in purged
    assert 7 not in purged
    assert 8 in purged


def test_purge_no_overlap_keeps_everything():
    """When label windows are disjoint, nothing purged."""
    label_windows = [(i, i) for i in range(20)]  # single-sample labels
    train_candidates = list(range(15))
    test_idx = [17, 18, 19]
    purged = purge(train_candidates, test_idx, label_windows)
    assert set(purged) == set(train_candidates)


def test_purge_empty_test_keeps_train():
    """Empty test set → nothing to overlap with → keep all train."""
    label_windows = [(i, i + 2) for i in range(10)]
    train_candidates = list(range(10))
    assert purge(train_candidates, [], label_windows) == train_candidates


def test_purge_preserves_order():
    """Purged output preserves input order."""
    label_windows = label_windows_from_lookahead(20, lookahead=2)
    train_candidates = [0, 5, 10, 15]
    test_idx = [8]  # label [8, 10]
    purged = purge(train_candidates, test_idx, label_windows)
    assert purged == sorted(purged)  # 0, 5, 15 (10 removed for overlap)


# ═══════════════════════════════════════════════════════════════
# Embargo
# ═══════════════════════════════════════════════════════════════

def test_embargo_removes_samples_after_test():
    """Samples in [max_test + 1, max_test + embargo_len] should be dropped.
    Embargo does NOT touch samples inside test_idx or before it — that's
    what purge() is for."""
    # 100 samples, 1% embargo → embargo_len = 1
    train_candidates = list(range(100))
    test_idx = [50]
    embargoed = embargo(train_candidates, test_idx, n_samples=100, embargo_pct=0.01)
    assert 51 not in embargoed
    assert 52 in embargoed  # 1% of 100 = 1, so only 51 removed
    # 50 is in test_idx AND train_candidates — embargo doesn't purge it
    # (that's purge()'s job). This lets purge + embargo compose cleanly.
    assert 50 in embargoed
    assert 49 in embargoed  # before test — untouched by embargo


def test_embargo_scales_with_pct():
    """5% embargo on 100 samples → 5 samples removed after test."""
    train_candidates = list(range(100))
    test_idx = [50]
    embargoed = embargo(train_candidates, test_idx, n_samples=100, embargo_pct=0.05)
    # embargo_len = 5, so samples 51..55 removed
    for i in range(51, 56):
        assert i not in embargoed
    assert 56 in embargoed
    assert 40 in embargoed  # before test — unaffected


def test_embargo_zero_pct_is_noop():
    """embargo_pct=0 → nothing removed."""
    train_candidates = list(range(50))
    test_idx = [20]
    embargoed = embargo(train_candidates, test_idx, n_samples=50, embargo_pct=0)
    assert embargoed == train_candidates


def test_embargo_empty_test_is_noop():
    """Empty test → nothing to embargo after → keep all."""
    train_candidates = list(range(30))
    embargoed = embargo(train_candidates, [], n_samples=30, embargo_pct=0.1)
    assert embargoed == train_candidates


# ═══════════════════════════════════════════════════════════════
# label_windows_from_lookahead helper
# ═══════════════════════════════════════════════════════════════

def test_label_windows_from_lookahead_basic():
    """5 samples, lookahead=2 → [(0,2), (1,3), (2,4), (3,4), (4,4)]."""
    windows = label_windows_from_lookahead(5, lookahead=2)
    assert windows == [(0, 2), (1, 3), (2, 4), (3, 4), (4, 4)]


def test_label_windows_from_lookahead_clips_tail():
    """Tail windows should be clipped to n_samples - 1."""
    windows = label_windows_from_lookahead(3, lookahead=10)
    assert all(exit_idx <= 2 for _, exit_idx in windows)


def test_label_windows_from_lookahead_zero_lookahead():
    """lookahead=0 → each sample labels itself."""
    windows = label_windows_from_lookahead(4, lookahead=0)
    assert windows == [(0, 0), (1, 1), (2, 2), (3, 3)]


def test_label_windows_from_lookahead_negative_raises():
    """Negative lookahead → ValueError."""
    with pytest.raises(ValueError, match="lookahead"):
        label_windows_from_lookahead(5, lookahead=-1)


# ═══════════════════════════════════════════════════════════════
# End-to-end audit — purging + embargo integration
# ═══════════════════════════════════════════════════════════════

def test_cpcv_split_records_audit_counts():
    """Each CPCVSplit records how many indices were purged + embargoed
    so downstream reports can grade the aggressive-ness of the split."""
    label_windows = label_windows_from_lookahead(60, lookahead=3)
    splits = generate_cpcv_splits(
        n_samples=60, n_groups=6, k_test=2,
        label_windows=label_windows, embargo_pct=0.05,
    )
    assert all(s.n_purged >= 0 for s in splits)
    assert all(s.n_embargoed >= 0 for s in splits)
    # At least one split should have non-zero purging (overlap is common)
    assert any(s.n_purged > 0 for s in splits)


def test_cpcv_no_label_windows_defaults_to_singletons():
    """If no label_windows, each sample is its own single-point window
    → no purging needed but embargo still applies."""
    splits = generate_cpcv_splits(
        n_samples=60, n_groups=6, k_test=2,
        label_windows=None, embargo_pct=0.0,
    )
    for s in splits:
        assert s.n_purged == 0
