"""
eval/report_generator.py
--------------------------------------------------------------------
Generate evaluation report: markdown + matplotlib charts + JSON export.

Academic style: white background, serif labels, clean lines.
Charts saved to docs/charts/{ticker}_{type}.png.
Report saved to docs/evaluation_report.md.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from eval.harness import HarnessResult, StrategyEvaluation

logger = logging.getLogger("eval.report")

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = _ROOT / "docs"
_CHARTS = _DOCS / "charts"


def _setup_academic_style():
    """Configure matplotlib for academic publication style."""
    if not HAS_MATPLOTLIB:
        return
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.grid": True,
        "axes.grid.which": "major",
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
        "font.family": "serif",
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.2,
    })


def _plot_walk_forward(evals: List[StrategyEvaluation], ticker: str) -> str | None:
    """Generate walk-forward equity curve chart. Returns relative path or None."""
    if not HAS_MATPLOTLIB:
        return None

    _setup_academic_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), height_ratios=[2, 1])

    has_data = False
    for ev in evals:
        wf = ev.walk_forward
        if not wf or not wf.windows:
            continue
        has_data = True
        sharpes = [w.sharpe for w in wf.windows]
        returns = [w.total_return * 100 for w in wf.windows]
        window_labels = [f"W{w.window_idx + 1}" for w in wf.windows]

        ax1.plot(window_labels, sharpes, marker="o", markersize=4,
                 label=ev.strategy_name, linewidth=1.5)
        ax2.bar(
            [f"{l}\n{ev.strategy_name[:6]}" for l in window_labels],
            returns, alpha=0.7, width=0.8 / len(evals),
        )

    if not has_data:
        plt.close(fig)
        return None

    ax1.set_ylabel("Out-of-Sample Sharpe Ratio")
    ax1.set_title(f"Walk-Forward Validation — {ticker}")
    ax1.axhline(y=0, color="red", linestyle="-", linewidth=0.8, alpha=0.5)
    ax1.legend(fontsize=8, ncol=2)

    ax2.set_ylabel("OOS Return (%)")
    ax2.axhline(y=0, color="red", linestyle="-", linewidth=0.8, alpha=0.5)

    plt.tight_layout()
    path = _CHARTS / f"{ticker}_walk_forward.png"
    fig.savefig(path)
    plt.close(fig)
    return f"charts/{ticker}_walk_forward.png"


def _plot_monte_carlo(evals: List[StrategyEvaluation], ticker: str) -> str | None:
    """Generate Monte Carlo fan chart. Returns relative path or None."""
    if not HAS_MATPLOTLIB:
        return None

    _setup_academic_style()

    # Find the strategy with the most equity curve samples
    best_ev = None
    max_curves = 0
    for ev in evals:
        mc = ev.monte_carlo
        if mc and len(mc.equity_curves_sample) > max_curves:
            max_curves = len(mc.equity_curves_sample)
            best_ev = ev

    if not best_ev or not best_ev.monte_carlo or max_curves == 0:
        return None

    mc = best_ev.monte_carlo
    fig, ax = plt.subplots(figsize=(10, 5))

    # Plot sampled equity curves in light gray
    for curve in mc.equity_curves_sample:
        ax.plot(curve, color="gray", alpha=0.15, linewidth=0.5)

    # Overlay percentile bands if we have enough curves
    if len(mc.equity_curves_sample) >= 5:
        max_len = max(len(c) for c in mc.equity_curves_sample)
        padded = np.full((len(mc.equity_curves_sample), max_len), np.nan)
        for i, c in enumerate(mc.equity_curves_sample):
            padded[i, :len(c)] = c

        p5 = np.nanpercentile(padded, 5, axis=0)
        p25 = np.nanpercentile(padded, 25, axis=0)
        p50 = np.nanpercentile(padded, 50, axis=0)
        p75 = np.nanpercentile(padded, 75, axis=0)
        p95 = np.nanpercentile(padded, 95, axis=0)

        x = range(max_len)
        ax.fill_between(x, p5, p95, alpha=0.15, color="steelblue", label="5th-95th pct")
        ax.fill_between(x, p25, p75, alpha=0.25, color="steelblue", label="25th-75th pct")
        ax.plot(p50, color="steelblue", linewidth=1.5, label="Median")

    ax.axhline(y=1.0, color="red", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_xlabel("Trading Days")
    ax.set_ylabel("Equity (starting at 1.0)")
    ax.set_title(f"Monte Carlo Simulation — {ticker} ({best_ev.strategy_name}, {mc.n_iterations} iterations)")
    ax.legend(fontsize=8)

    plt.tight_layout()
    path = _CHARTS / f"{ticker}_monte_carlo.png"
    fig.savefig(path)
    plt.close(fig)
    return f"charts/{ticker}_monte_carlo.png"


def _plot_strategy_comparison(result: HarnessResult) -> str | None:
    """Generate strategy comparison heatmap. Returns relative path or None."""
    if not HAS_MATPLOTLIB:
        return None

    _setup_academic_style()

    tickers = [t for t in result.tickers if t not in result.skipped_tickers]
    strategies = result.strategies

    if not tickers or not strategies:
        return None

    # Build Sharpe matrix
    sharpe_matrix = np.full((len(strategies), len(tickers)), np.nan)
    for ev in result.evaluations:
        if ev.walk_forward and ev.walk_forward.avg_oos_sharpe != 0:
            si = strategies.index(ev.strategy_name)
            ti = tickers.index(ev.ticker)
            sharpe_matrix[si, ti] = ev.walk_forward.avg_oos_sharpe

    fig, ax = plt.subplots(figsize=(max(6, len(tickers) * 2), max(4, len(strategies) * 0.8)))

    im = ax.imshow(sharpe_matrix, cmap="RdYlGn", aspect="auto", vmin=-1, vmax=2)
    ax.set_xticks(range(len(tickers)))
    ax.set_xticklabels(tickers)
    ax.set_yticks(range(len(strategies)))
    ax.set_yticklabels(strategies, fontsize=9)
    ax.set_title("Strategy Comparison — OOS Sharpe Ratio")

    # Annotate cells
    for i in range(len(strategies)):
        for j in range(len(tickers)):
            val = sharpe_matrix[i, j]
            if not np.isnan(val):
                color = "white" if abs(val) > 1 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=9, color=color, fontweight="bold")

    fig.colorbar(im, ax=ax, label="Sharpe Ratio", shrink=0.8)
    plt.tight_layout()
    path = _CHARTS / "strategy_comparison.png"
    fig.savefig(path)
    plt.close(fig)
    return "charts/strategy_comparison.png"


def _generate_badge_url(result: HarnessResult) -> str:
    """Generate shields.io badge URL for README."""
    # Find best OOS Sharpe across all evaluations
    best_sharpe = 0.0
    for ev in result.evaluations:
        if ev.walk_forward:
            best_sharpe = max(best_sharpe, ev.walk_forward.avg_oos_sharpe)

    color = "red" if best_sharpe <= 0 else "yellow" if best_sharpe < 0.5 else "green" if best_sharpe < 1.5 else "brightgreen"
    label = f"Walk--Forward Sharpe-{best_sharpe:.2f} (OOS)"
    return f"https://img.shields.io/badge/{label}-{color}?style=flat-square"


def _generate_ranking_table(result: HarnessResult) -> str:
    """Generate strategy ranking table for README."""
    rows = []
    for ev in result.evaluations:
        wf = ev.walk_forward
        mc = ev.monte_carlo
        st = ev.statistical

        sharpe = wf.avg_oos_sharpe if wf else 0.0
        ir = wf.avg_information_ratio if wf else 0.0
        mc_rank = mc.sharpe_percentile_rank if mc else 0.0
        p_val = st.p_value if st and st.sufficient_data else 1.0
        passed = "PASS" if ev.overall_pass else "FAIL"

        rows.append({
            "strategy": ev.strategy_name,
            "ticker": ev.ticker,
            "oos_sharpe": sharpe,
            "info_ratio": ir,
            "mc_percentile": mc_rank,
            "p_value": p_val,
            "verdict": passed,
        })

    rows.sort(key=lambda r: r["oos_sharpe"], reverse=True)

    lines = [
        "| Strategy | Ticker | OOS Sharpe | Info Ratio | MC Pct | p-value | Verdict |",
        "|----------|--------|-----------|------------|--------|---------|---------|",
    ]
    for r in rows:
        p_str = f"{r['p_value']:.4f}" if r["p_value"] < 1 else "N/A"
        lines.append(
            f"| {r['strategy']} | {r['ticker']} | {r['oos_sharpe']:.3f} | "
            f"{r['info_ratio']:.3f} | {r['mc_percentile']:.1f}% | "
            f"{p_str} | {r['verdict']} |"
        )

    return "\n".join(lines)


def generate_report(
    result: HarnessResult,
    output_path: str | Path | None = None,
) -> str:
    """
    Generate the full evaluation report.

    Args:
        result: HarnessResult from EvaluationHarness.run().
        output_path: Path for the markdown report. Defaults to docs/evaluation_report.md.

    Returns:
        The markdown report content as a string.
    """
    if not HAS_MATPLOTLIB:
        logger.warning("matplotlib not available. Report will have no charts. Install: pip install matplotlib")

    output_path = Path(output_path) if output_path else _DOCS / "evaluation_report.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _CHARTS.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    tickers_str = ", ".join(result.tickers)
    skipped_str = ", ".join(result.skipped_tickers) if result.skipped_tickers else "None"

    # Generate charts
    chart_paths = {}
    tickers_with_data = [t for t in result.tickers if t not in result.skipped_tickers]

    for ticker in tickers_with_data:
        ticker_evals = [e for e in result.evaluations if e.ticker == ticker]
        wf_chart = _plot_walk_forward(ticker_evals, ticker)
        if wf_chart:
            chart_paths[f"{ticker}_wf"] = wf_chart
        mc_chart = _plot_monte_carlo(ticker_evals, ticker)
        if mc_chart:
            chart_paths[f"{ticker}_mc"] = mc_chart

    comparison_chart = _plot_strategy_comparison(result)
    if comparison_chart:
        chart_paths["comparison"] = comparison_chart

    # Build report
    lines = []
    lines.append("# Orallexa Evaluation Report\n")
    lines.append(f"Generated: {now} | Tickers: {tickers_str} | "
                 f"Strategies: {result.num_strategies_tested} | "
                 f"Skipped: {skipped_str}\n")

    # Executive Summary
    lines.append("## Executive Summary\n")
    lines.append(f"**{result.total_passed}/{result.total_evaluated}** strategy-ticker "
                 f"pairs passed all evaluation gates.\n")
    lines.append(_generate_ranking_table(result))
    lines.append("")

    # Walk-Forward Validation
    lines.append("\n## Walk-Forward Validation\n")
    lines.append("Expanding-window walk-forward: each strategy is evaluated on sequential "
                 "out-of-sample windows. Indicators are computed per-window with a 50-bar "
                 "warmup buffer to prevent data leakage.\n")

    for ticker in tickers_with_data:
        key = f"{ticker}_wf"
        if key in chart_paths:
            lines.append(f"\n### {ticker}\n")
            lines.append(f"![Walk-Forward {ticker}]({chart_paths[key]})\n")

        ticker_evals = [e for e in result.evaluations if e.ticker == ticker]
        lines.append("| Strategy | Windows | Avg OOS Sharpe | % Positive | Avg Return | Pass |")
        lines.append("|----------|---------|---------------|------------|------------|------|")
        for ev in ticker_evals:
            wf = ev.walk_forward
            if wf:
                lines.append(
                    f"| {ev.strategy_name} | {wf.num_windows} | {wf.avg_oos_sharpe:.3f} | "
                    f"{wf.pct_positive_sharpe:.0%} | {wf.avg_oos_return:.2%} | "
                    f"{'PASS' if wf.passed else 'FAIL'} |"
                )
        lines.append("")

    # Monte Carlo Simulation
    lines.append("\n## Monte Carlo Simulation\n")
    lines.append("Trade returns are extracted from bars with active positions (non-zero signal), "
                 "shuffled, and used to reconstruct equity curves. This tests whether strategy "
                 "performance depends on the specific sequence of trades.\n")

    for ticker in tickers_with_data:
        key = f"{ticker}_mc"
        if key in chart_paths:
            lines.append(f"\n### {ticker}\n")
            lines.append(f"![Monte Carlo {ticker}]({chart_paths[key]})\n")

        ticker_evals = [e for e in result.evaluations if e.ticker == ticker]
        lines.append("| Strategy | Trades | Original Sharpe | MC 75th Pct | Percentile Rank | P(Ruin) | Pass |")
        lines.append("|----------|--------|-----------------|-------------|-----------------|---------|------|")
        for ev in ticker_evals:
            mc = ev.monte_carlo
            if mc:
                p75 = mc.sharpe_percentiles.get(75, 0)
                lines.append(
                    f"| {ev.strategy_name} | {mc.n_trade_returns} | {mc.original_sharpe:.3f} | "
                    f"{p75:.3f} | {mc.sharpe_percentile_rank:.1f}% | "
                    f"{mc.probability_of_ruin:.1f}% | {'PASS' if mc.passed else 'FAIL'} |"
                )
        lines.append("")

    # Statistical Significance
    lines.append("\n## Statistical Significance\n")
    lines.append("One-sided t-test on trade returns (H0: mean return = 0). "
                 "Bootstrap 95% CI on Sharpe ratio (5,000 resamples). "
                 "Deflated Sharpe Ratio corrects for multiple testing "
                 "(Bailey & Lopez de Prado 2014). "
                 f"Minimum {result.num_strategies_tested} strategies tested per run.\n")
    lines.append("Tests require a minimum of 20 trades. Strategies with fewer trades "
                 "are marked 'Insufficient data.'\n")

    for ticker in tickers_with_data:
        ticker_evals = [e for e in result.evaluations if e.ticker == ticker]
        lines.append(f"\n### {ticker}\n")
        lines.append("| Strategy | n | t-stat | p-value | Sharpe [95% CI] | DSR | Sig? |")
        lines.append("|----------|---|--------|---------|-----------------|-----|------|")
        for ev in ticker_evals:
            st = ev.statistical
            if st and st.sufficient_data:
                ci_str = f"{st.sharpe_point:.2f} [{st.sharpe_ci_lower:.2f}, {st.sharpe_ci_upper:.2f}]"
                sig = "Yes" if st.returns_significant else "No"
                lines.append(
                    f"| {ev.strategy_name} | {st.n_observations} | {st.t_statistic:.2f} | "
                    f"{st.p_value:.4f} | {ci_str} | {st.dsr:.3f} | {sig} |"
                )
            elif st:
                lines.append(
                    f"| {ev.strategy_name} | {st.n_observations} | — | — | — | — | Insufficient data |"
                )
        lines.append("")

    # Strategy Comparison
    if "comparison" in chart_paths:
        lines.append("\n## Strategy Comparison\n")
        lines.append(f"![Strategy Comparison]({chart_paths['comparison']})\n")

    # Methodology Notes
    lines.append("\n## Methodology Notes\n")
    lines.append("- **Walk-forward:** Expanding window, 252-day initial training, "
                 "63-day quarterly test windows, minimum 4 windows")
    lines.append("- **Indicators:** Computed per-window with 50-bar warmup buffer "
                 "(prevents lookahead bias from rolling indicators)")
    lines.append(f"- **Monte Carlo:** {result.evaluations[0].monte_carlo.n_iterations if result.evaluations and result.evaluations[0].monte_carlo else 1000} "
                 "iterations, shuffling non-zero trade returns only")
    lines.append("- **Statistical tests:** One-sided t-test (p < 0.05), "
                 "bootstrap 95% CI (5,000 resamples)")
    lines.append(f"- **DSR:** Deflated Sharpe Ratio with {result.num_strategies_tested} "
                 "strategies tested. DSR > 0.5 = pass. "
                 "Results are not comparable across separate invocations")
    lines.append("- **Minimum trades:** 20 required for statistical tests")
    lines.append("- **Pass/fail gates:** Walk-forward OOS Sharpe > 0 in >50% of windows; "
                 "Monte Carlo strategy Sharpe > 75th percentile; t-test p < 0.05")
    lines.append("")

    report_content = "\n".join(lines)

    # Write markdown report
    try:
        output_path.write_text(report_content, encoding="utf-8")
        logger.info("Report written to %s", output_path)
    except PermissionError:
        logger.error("Cannot write to %s. Check permissions.", output_path)
        raise

    # Write JSON export
    json_path = output_path.parent / "evaluation_results.json"
    try:
        json_data = _result_to_dict(result)
        json_path.write_text(json.dumps(json_data, indent=2, default=str), encoding="utf-8")
        logger.info("JSON results written to %s", json_path)
    except Exception as exc:
        logger.warning("Failed to write JSON: %s", exc)

    # Generate badge URL
    badge_url = _generate_badge_url(result)
    badge_path = output_path.parent / "eval_badge_url.txt"
    try:
        badge_path.write_text(badge_url, encoding="utf-8")
    except Exception:
        pass

    return report_content


def _result_to_dict(result: HarnessResult) -> dict:
    """Convert HarnessResult to a JSON-serializable dict."""
    evaluations = []
    for ev in result.evaluations:
        entry = {
            "strategy": ev.strategy_name,
            "ticker": ev.ticker,
            "overall_pass": ev.overall_pass,
        }
        if ev.walk_forward:
            wf = ev.walk_forward
            entry["walk_forward"] = {
                "num_windows": wf.num_windows,
                "avg_oos_sharpe": round(wf.avg_oos_sharpe, 4),
                "pct_positive_sharpe": round(wf.pct_positive_sharpe, 3),
                "avg_oos_return": round(wf.avg_oos_return, 4),
                "avg_information_ratio": round(wf.avg_information_ratio, 4),
                "passed": wf.passed,
            }
        if ev.monte_carlo:
            mc = ev.monte_carlo
            entry["monte_carlo"] = {
                "n_iterations": mc.n_iterations,
                "n_trade_returns": mc.n_trade_returns,
                "original_sharpe": round(mc.original_sharpe, 4),
                "sharpe_percentile_rank": round(mc.sharpe_percentile_rank, 1),
                "probability_of_ruin": round(mc.probability_of_ruin, 1),
                "passed": mc.passed,
            }
        if ev.statistical:
            st = ev.statistical
            entry["statistical"] = {
                "n_observations": st.n_observations,
                "sufficient_data": st.sufficient_data,
                "t_statistic": round(st.t_statistic, 4),
                "p_value": round(st.p_value, 4),
                "sharpe_point": round(st.sharpe_point, 4),
                "sharpe_ci": [round(st.sharpe_ci_lower, 4), round(st.sharpe_ci_upper, 4)],
                "dsr": round(st.dsr, 4),
                "returns_significant": st.returns_significant,
                "dsr_passed": st.dsr_passed,
            }
        evaluations.append(entry)

    return {
        "generated": datetime.now().isoformat(),
        "tickers": result.tickers,
        "strategies": result.strategies,
        "num_strategies_tested": result.num_strategies_tested,
        "skipped_tickers": result.skipped_tickers,
        "total_evaluated": result.total_evaluated,
        "total_passed": result.total_passed,
        "evaluations": evaluations,
    }
