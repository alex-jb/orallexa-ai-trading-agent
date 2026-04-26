"""
engine/dynamic_weights.py
──────────────────────────────────────────────────────────────────
Compute fusion weights that scale with each source's recent accuracy.

The default DEFAULT_WEIGHTS in signal_fusion are static — they reflect
guesses about long-run informativeness. Once the system has accumulated
real per-source hit/miss history, dynamic weights can do better:

    adjusted_weight = base_weight × accuracy_factor(rolling_accuracy)

Where accuracy_factor maps:
    accuracy 0.50 (random)  → factor 1.0  (no change)
    accuracy 0.60          → factor ~1.5
    accuracy 0.70          → factor ~2.0
    accuracy 0.40          → factor ~0.5
    accuracy ≤ 0.30        → factor 0.1  (near-mute)

Sources with insufficient history keep their base weight unchanged.
Final weights are renormalized to sum to the original total so the
overall conviction scale is preserved.

Usage:
    from engine.signal_fusion import DEFAULT_WEIGHTS, fuse_signals
    from engine.source_accuracy import SourceAccuracy
    from engine.dynamic_weights import compute_dynamic_weights

    sa = SourceAccuracy()
    weights = compute_dynamic_weights(DEFAULT_WEIGHTS, sa.get_rolling_accuracy())
    result = fuse_signals("NVDA", summary=..., weights=weights)
"""
from __future__ import annotations

from typing import Optional


def _accuracy_factor(accuracy: float) -> float:
    """
    Map rolling accuracy ∈ [0, 1] to a multiplier.

    Calibration points:
        0.30 → 0.10   (down-weight bad sources hard)
        0.40 → 0.50
        0.50 → 1.00   (random — no change)
        0.60 → 1.50
        0.70 → 2.00
        0.80 → 2.50
        0.90+→ 3.00   (cap so a lucky streak can't dominate)
    """
    if accuracy <= 0.30:
        return 0.10
    if accuracy >= 0.90:
        return 3.00
    if accuracy < 0.50:
        # Linear from (0.30, 0.10) to (0.50, 1.00)
        return 0.10 + (accuracy - 0.30) * (0.90 / 0.20)
    # Linear from (0.50, 1.00) to (0.90, 3.00)
    return 1.00 + (accuracy - 0.50) * (2.00 / 0.40)


def compute_dynamic_weights(
    base_weights: dict[str, float],
    rolling_accuracy: dict[str, float],
    *,
    min_factor: float = 0.05,
    max_factor: float = 3.0,
    preserve_total: bool = True,
) -> dict[str, float]:
    """
    Build a new weights dict by scaling each base weight by its source's
    recent accuracy. Sources missing from `rolling_accuracy` keep their
    base weight (factor=1.0).

    Parameters
    ----------
    base_weights      : the starting policy (e.g. DEFAULT_WEIGHTS)
    rolling_accuracy  : {source: accuracy ∈ [0,1]} from SourceAccuracy
    min_factor        : floor on per-source multiplier (defensive)
    max_factor        : ceiling on per-source multiplier
    preserve_total    : if True, renormalize to keep the original sum
                        so overall conviction scale is comparable

    Returns
    -------
    new weights dict — same keys as base_weights
    """
    if not base_weights:
        return {}
    base_sum = sum(base_weights.values())

    adjusted: dict[str, float] = {}
    for src, base in base_weights.items():
        acc = rolling_accuracy.get(src)
        if acc is None or base <= 0:
            adjusted[src] = base
            continue
        factor = _accuracy_factor(acc)
        factor = max(min_factor, min(max_factor, factor))
        adjusted[src] = base * factor

    if not preserve_total:
        return adjusted

    new_sum = sum(adjusted.values())
    if new_sum <= 0:
        # Degenerate: every source bombed. Fall back to base.
        return dict(base_weights)
    scale = base_sum / new_sum
    # No per-value rounding here — that's a presentation concern. Rounding
    # each entry then summing accumulates float error (saw 1e-6 drift in CI
    # on a 4-source case). Display layers can format as needed.
    return {k: v * scale for k, v in adjusted.items()}


def explain_weight_adjustment(
    base_weights: dict[str, float],
    rolling_accuracy: dict[str, float],
) -> list[dict]:
    """
    Return a per-source explanation of how the adjustment moved the weight.

    Each entry: {source, base_weight, accuracy, factor, adjusted_weight, delta_pct}.
    Useful for UI/debug surfaces — answers "why is technical down-weighted?"
    """
    adjusted = compute_dynamic_weights(base_weights, rolling_accuracy)
    out: list[dict] = []
    for src, base in base_weights.items():
        acc = rolling_accuracy.get(src)
        adj = adjusted.get(src, base)
        delta_pct = ((adj - base) / base * 100) if base > 0 else 0
        out.append({
            "source": src,
            "base_weight": round(base, 4),
            "accuracy": acc,
            "factor": round(_accuracy_factor(acc), 3) if acc is not None else None,
            "adjusted_weight": round(adj, 4),
            "delta_pct": round(delta_pct, 2),
        })
    return out
