# Orallexa Evaluation Report

Generated: 2026-04-04 00:08 | Tickers: NVDA | Strategies: 9 | Skipped: None

## Executive Summary

9 strategy-ticker pairs evaluated across 1 tickers and 9 rule-based strategies. Each pair is tested against three independent statistical gates.

**Results by gate:**
- **Walk-forward (OOS Sharpe > 0 in >50% windows):** 5/9 passed
- **Statistical significance (p < 0.05):** 6/9 passed
- **Monte Carlo (beat 75th percentile):** 9/9 passed

**Tiered verdicts:**
- **STRONG PASS** (all 3 gates): 5
- **PASS** (2 gates + Sharpe > 0.5): 1
- **MARGINAL** (1+ gate + Sharpe > 0): 1
- **FAIL** (0 gates or Sharpe <= 0): 2

> Rule-based strategies serve as feature generators for the 9-model ML ensemble and Claude AI synthesis layer. The value is in the composite system, not individual strategies.

| Strategy | Ticker | OOS Sharpe | Info Ratio | MC Pct | p-value | Verdict |
|----------|--------|-----------|------------|--------|---------|---------|
| double_ma | NVDA | 0.953 | -1.139 | 97.0% | 0.0042 | STRONG PASS |
| dual_thrust | NVDA | 0.609 | -1.045 | 100.0% | 0.0019 | STRONG PASS |
| macd_crossover | NVDA | 0.572 | -1.146 | 100.0% | 0.0490 | STRONG PASS |
| alpha_combo | NVDA | 0.515 | -1.413 | 66.1% | 0.0483 | STRONG PASS |
| trend_momentum | NVDA | 0.447 | -1.200 | 99.2% | 0.0419 | STRONG PASS |
| ensemble_vote | NVDA | 0.424 | -1.070 | 99.9% | 0.0160 | PASS |
| rsi_reversal | NVDA | 0.173 | -1.170 | 100.0% | 0.2712 | MARGINAL |
| regime_ensemble | NVDA | -0.012 | -1.432 | 99.4% | 0.0579 | FAIL |
| bollinger_breakout | NVDA | -0.071 | -1.399 | 94.6% | 0.1770 | FAIL |


## Walk-Forward Validation

Expanding-window walk-forward: each strategy is evaluated on sequential out-of-sample windows. Indicators are computed per-window with a 50-bar warmup buffer to prevent data leakage.


### NVDA

![Walk-Forward NVDA](charts/NVDA_walk_forward.png)

| Strategy | Windows | Avg OOS Sharpe | % Positive | Avg Return | Pass |
|----------|---------|---------------|------------|------------|------|
| double_ma | 7 | 0.953 | 43% | 9.57% | PASS |
| macd_crossover | 7 | 0.572 | 57% | 3.94% | PASS |
| bollinger_breakout | 7 | -0.071 | 14% | -0.44% | FAIL |
| rsi_reversal | 7 | 0.173 | 14% | 0.77% | FAIL |
| trend_momentum | 7 | 0.447 | 57% | 2.17% | PASS |
| alpha_combo | 7 | 0.515 | 57% | 4.94% | PASS |
| dual_thrust | 7 | 0.609 | 43% | 9.92% | PASS |
| ensemble_vote | 7 | 0.424 | 29% | 6.72% | FAIL |
| regime_ensemble | 7 | -0.012 | 29% | 3.80% | FAIL |


## Monte Carlo Simulation

Trade returns are extracted from bars with active positions (non-zero signal), shuffled, and used to reconstruct equity curves. This tests whether strategy performance depends on the specific sequence of trades.


### NVDA

![Monte Carlo NVDA](charts/NVDA_monte_carlo.png)

| Strategy | Trades | Original Sharpe | MC 75th Pct | Percentile Rank | P(Ruin) | Pass |
|----------|--------|-----------------|-------------|-----------------|---------|------|
| double_ma | 484 | 1.914 | 1.914 | 97.0% | 0.0% | PASS |
| macd_crossover | 348 | 1.414 | 1.414 | 100.0% | 0.0% | PASS |
| bollinger_breakout | 125 | 1.327 | 1.327 | 94.6% | 0.0% | PASS |
| rsi_reversal | 21 | 2.200 | 2.200 | 100.0% | 0.0% | PASS |
| trend_momentum | 347 | 1.479 | 1.479 | 99.2% | 0.0% | PASS |
| alpha_combo | 573 | 1.105 | 1.105 | 66.1% | 0.0% | PASS |
| dual_thrust | 354 | 2.457 | 2.457 | 100.0% | 0.0% | PASS |
| ensemble_vote | 340 | 1.857 | 1.857 | 99.9% | 0.0% | PASS |
| regime_ensemble | 347 | 1.346 | 1.346 | 99.4% | 0.0% | PASS |


## Statistical Significance

One-sided t-test on trade returns (H0: mean return = 0). Bootstrap 95% CI on Sharpe ratio (5,000 resamples). Deflated Sharpe Ratio corrects for multiple testing (Bailey & Lopez de Prado 2014). Minimum 9 strategies tested per run.

Tests require a minimum of 20 trades. Strategies with fewer trades are marked 'Insufficient data.'


### NVDA

| Strategy | n | t-stat | p-value | Sharpe [95% CI] | DSR | Sig? |
|----------|---|--------|---------|-----------------|-----|------|
| double_ma | 484 | 2.65 | 0.0042 | 1.91 [0.56, 3.17] | 1.000 | Yes |
| macd_crossover | 348 | 1.66 | 0.0490 | 1.41 [-0.24, 3.03] | 0.837 | Yes |
| bollinger_breakout | 125 | 0.93 | 0.1770 | 1.33 [-1.49, 4.36] | 0.000 | No |
| rsi_reversal | 21 | 0.62 | 0.2712 | 2.20 [-4.82, 10.68] | 0.000 | No |
| trend_momentum | 347 | 1.73 | 0.0419 | 1.48 [-0.15, 3.14] | 0.907 | Yes |
| alpha_combo | 573 | 1.66 | 0.0483 | 1.10 [-0.16, 2.38] | 0.910 | Yes |
| dual_thrust | 354 | 2.91 | 0.0019 | 2.46 [0.91, 3.86] | 1.000 | Yes |
| ensemble_vote | 340 | 2.15 | 0.0160 | 1.86 [0.22, 3.36] | 0.999 | Yes |
| regime_ensemble | 347 | 1.58 | 0.0579 | 1.35 [-0.31, 2.85] | 0.783 | No |


## Strategy Comparison

![Strategy Comparison](charts/strategy_comparison.png)


## Methodology Notes

- **Walk-forward:** Expanding window, 252-day initial training, 63-day quarterly test windows, minimum 4 windows
- **Indicators:** Computed per-window with 50-bar warmup buffer (prevents lookahead bias from rolling indicators)
- **Monte Carlo:** 1000 iterations, shuffling non-zero trade returns only
- **Statistical tests:** One-sided t-test (p < 0.05), bootstrap 95% CI (5,000 resamples)
- **DSR:** Deflated Sharpe Ratio with 9 strategies tested. DSR > 0.5 = pass. Results are not comparable across separate invocations
- **Minimum trades:** 20 required for statistical tests
- **Pass/fail gates:** Walk-forward OOS Sharpe > 0 in >50% of windows; Monte Carlo strategy Sharpe > 75th percentile; t-test p < 0.05
