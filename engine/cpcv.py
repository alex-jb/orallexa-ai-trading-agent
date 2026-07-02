"""
engine/cpcv.py
──────────────────────────────────────────────────────────────────
Combinatorial Purged Cross-Validation for financial time-series.

Ships 2026-07-02 Tier-2 upgrade #14 from the deep-research roadmap.

Why upgrade walkforward.py
--------------------------
markets/auto/walkforward.py already does sliding-window OOS via
`slice_decisions`. But sliding-window CV underestimates true
generalization error on financial data for two reasons:

  1. **Label overlap.** When entry-time and exit-time span N days,
     any decision in the train set whose (entry_time..exit_time)
     window overlaps a test-set decision's (entry_time..exit_time)
     window has label leakage — the "same" market move drives both.

  2. **Post-test contamination.** Market microstructure means the
     N days AFTER a test window still carry information from that
     window. Training on those days injects future leakage.

López de Prado's "Advances in Financial Machine Learning" (2018)
ch. 12 gives the fix — Combinatorial Purged Cross-Validation:

  - Split data into N groups by time
  - Iterate ALL C(N, k) combinations of k groups as test set
    (not just N sliding windows)
  - **Purge** train samples whose label window overlaps test
  - **Embargo** train samples in a δ×n_samples window after test

Instead of 4 sliding windows → C(6, 2) = 15 CPCV splits. Much
higher statistical power for the same underlying data.

Contract
--------
Pure functions. Deterministic. No LLM. No network. Given a sorted
list of `(entry_idx, exit_idx)` label windows for n samples, plus
(n_groups, k_test, embargo_pct), yield tuples of (train_indices,
test_indices) with purging + embargo applied.

Consumers
---------
- markets/auto/walkforward.py: opt-in via `--cpcv` flag. Preserves
  existing sliding-window path for back-compat until CPCV proves
  itself over N runs.

Refs
----
López de Prado, M. (2018) "Advances in Financial Machine Learning"
Ch. 12 §12.4-12.5 (embargo, CPCV).

Bailey, D. et al. (2014) "The Probability of Backtest Overfitting"
— motivates the C(N, k) enumeration over the single-path split.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations


# ═══════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CPCVSplit:
    """One CPCV fold.

    train_idx : indices in the train fold, purged + embargoed
    test_idx  : indices in the test fold (union of k groups)
    n_purged  : how many train indices were removed by purging (audit)
    n_embargoed : how many train indices were removed by embargo
    """
    train_idx: list[int]
    test_idx: list[int]
    n_purged: int
    n_embargoed: int


# ═══════════════════════════════════════════════════════════════
# Purging + embargo
# ═══════════════════════════════════════════════════════════════

def _label_overlaps(entry_a: int, exit_a: int,
                    entry_b: int, exit_b: int) -> bool:
    """Two label windows [entry_a, exit_a] and [entry_b, exit_b] overlap
    if entry_a ≤ exit_b AND entry_b ≤ exit_a (standard interval
    overlap test)."""
    return entry_a <= exit_b and entry_b <= exit_a


def purge(train_candidates: list[int],
          test_idx: list[int],
          label_windows: list[tuple[int, int]]) -> list[int]:
    """Remove from train_candidates any index whose label window
    overlaps with any test index's label window.

    Parameters
    ----------
    train_candidates : indices being considered for the train set
    test_idx         : indices in the test set
    label_windows    : per-sample (entry_idx, exit_idx) — entry <= exit

    Returns
    -------
    Purged train indices, in original order.

    This is the López de Prado "Purge" step (§12.4). Prevents the
    train fold from containing labels whose outcome overlaps with
    outcomes we're going to test on.
    """
    if not train_candidates or not test_idx:
        return list(train_candidates)
    test_windows = [label_windows[i] for i in test_idx]
    out = []
    for i in train_candidates:
        entry_i, exit_i = label_windows[i]
        overlaps = False
        for entry_t, exit_t in test_windows:
            if _label_overlaps(entry_i, exit_i, entry_t, exit_t):
                overlaps = True
                break
        if not overlaps:
            out.append(i)
    return out


def embargo(train_candidates: list[int],
            test_idx: list[int],
            n_samples: int,
            embargo_pct: float) -> list[int]:
    """Remove from train_candidates any index whose sample position is
    within `embargo_pct × n_samples` samples AFTER the max test index.

    Parameters
    ----------
    train_candidates : indices being considered for the train set
                       (typically post-purge)
    test_idx         : indices in the test set
    n_samples        : total sample count (denominator for embargo)
    embargo_pct      : fraction ∈ [0, 1]. López de Prado recommends
                       0.01 (1%) — a small buffer, not a wall. Set 0
                       to disable.

    Returns
    -------
    Embargoed train indices.
    """
    if not train_candidates or not test_idx or embargo_pct <= 0:
        return list(train_candidates)
    embargo_len = max(1, int(round(embargo_pct * n_samples)))
    # We embargo samples in [max(test_idx) + 1, max(test_idx) + embargo_len].
    # (Test-adjacent labels contaminate via forward-looking market
    # microstructure — see López de Prado §12.5.)
    max_test = max(test_idx)
    embargo_start = max_test + 1
    embargo_end = max_test + embargo_len
    return [i for i in train_candidates
            if not (embargo_start <= i <= embargo_end)]


# ═══════════════════════════════════════════════════════════════
# CPCV split generator
# ═══════════════════════════════════════════════════════════════

def generate_cpcv_splits(
    n_samples: int,
    n_groups: int = 6,
    k_test: int = 2,
    label_windows: list[tuple[int, int]] | None = None,
    embargo_pct: float = 0.01,
) -> list[CPCVSplit]:
    """Yield all C(n_groups, k_test) combinatorial splits.

    Parameters
    ----------
    n_samples : total number of samples
    n_groups  : split n_samples into n_groups contiguous groups.
                López de Prado 2018 example uses 6.
    k_test    : number of groups per test fold. k_test=2 → 15 splits
                for n_groups=6. k_test=1 collapses to k-fold.
    label_windows : per-sample (entry_idx, exit_idx). If None, the
                    label window is just [i, i] — no overlap purging
                    needed but embargo still applies.
    embargo_pct : López de Prado default 0.01 (1% of samples).

    Returns
    -------
    List of CPCVSplit dataclasses.

    Raises
    ------
    ValueError if n_samples < n_groups OR k_test >= n_groups OR
    k_test < 1.
    """
    if n_samples < n_groups:
        raise ValueError(
            f"n_samples ({n_samples}) must be >= n_groups ({n_groups})"
        )
    if k_test < 1 or k_test >= n_groups:
        raise ValueError(
            f"k_test ({k_test}) must be in [1, n_groups - 1] = [1, {n_groups - 1}]"
        )
    if label_windows is None:
        label_windows = [(i, i) for i in range(n_samples)]
    if len(label_windows) != n_samples:
        raise ValueError(
            f"label_windows length ({len(label_windows)}) must equal "
            f"n_samples ({n_samples})"
        )

    # Assign each sample to a contiguous group.
    # Group boundaries: [0, g_size), [g_size, 2*g_size), ..., last
    # gets any remainder samples.
    g_size = n_samples // n_groups
    groups: list[list[int]] = []
    for g in range(n_groups):
        start = g * g_size
        end = (g + 1) * g_size if g < n_groups - 1 else n_samples
        groups.append(list(range(start, end)))

    splits: list[CPCVSplit] = []
    for test_group_combo in combinations(range(n_groups), k_test):
        test_idx: list[int] = []
        for g in test_group_combo:
            test_idx.extend(groups[g])

        train_candidates: list[int] = []
        for g in range(n_groups):
            if g not in test_group_combo:
                train_candidates.extend(groups[g])

        # Purge
        pre_purge_len = len(train_candidates)
        train_purged = purge(train_candidates, test_idx, label_windows)
        n_purged = pre_purge_len - len(train_purged)

        # Embargo
        train_embargoed = embargo(train_purged, test_idx, n_samples, embargo_pct)
        n_embargoed = len(train_purged) - len(train_embargoed)

        splits.append(CPCVSplit(
            train_idx=train_embargoed,
            test_idx=sorted(test_idx),
            n_purged=n_purged,
            n_embargoed=n_embargoed,
        ))

    return splits


# ═══════════════════════════════════════════════════════════════
# Convenience: build label_windows from lookahead
# ═══════════════════════════════════════════════════════════════

def label_windows_from_lookahead(n_samples: int, lookahead: int) -> list[tuple[int, int]]:
    """For a strategy where each decision's outcome resolves `lookahead`
    samples later, return per-sample (entry_idx, exit_idx) tuples.

    exit_idx is clipped to n_samples - 1 for the tail (partial windows).
    """
    if lookahead < 0:
        raise ValueError(f"lookahead must be >= 0, got {lookahead}")
    return [(i, min(i + lookahead, n_samples - 1)) for i in range(n_samples)]
