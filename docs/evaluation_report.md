# Orallexa Evaluation Report

Generated: 2026-04-02 15:56 | Tickers: NVDA, AAPL, TSLA | Strategies: 6 | Skipped: None

## Executive Summary

**0/18** strategy-ticker pairs passed all evaluation gates.

| Strategy | Ticker | OOS Sharpe | Info Ratio | MC Pct | p-value | Verdict |
|----------|--------|-----------|------------|--------|---------|---------|
| alpha_combo | NVDA | 0.920 | -1.073 | 100.0% | 0.0163 | FAIL |
| macd_crossover | NVDA | 0.909 | -1.007 | 98.9% | 0.0025 | FAIL |
| trend_momentum | NVDA | 0.738 | -1.125 | 96.2% | 0.0046 | FAIL |
| macd_crossover | TSLA | 0.693 | -0.273 | 99.7% | 0.0205 | FAIL |
| double_ma | NVDA | 0.625 | -1.532 | 99.9% | 0.0175 | FAIL |
| double_ma | TSLA | 0.517 | -0.277 | 99.6% | 0.1873 | FAIL |
| bollinger_breakout | TSLA | 0.437 | -0.152 | 99.5% | 0.0549 | FAIL |
| bollinger_breakout | AAPL | 0.385 | -0.758 | 100.0% | 0.0834 | FAIL |
| rsi_reversal | TSLA | 0.283 | -0.392 | 99.9% | 0.6003 | FAIL |
| alpha_combo | TSLA | 0.249 | -0.437 | 88.1% | 0.1575 | FAIL |
| double_ma | AAPL | 0.235 | -0.822 | 99.8% | 0.2431 | FAIL |
| bollinger_breakout | NVDA | 0.201 | -1.326 | 100.0% | 0.1579 | FAIL |
| trend_momentum | TSLA | 0.144 | -0.396 | 98.6% | 0.0910 | FAIL |
| trend_momentum | AAPL | 0.124 | -0.571 | 88.4% | 0.0834 | FAIL |
| alpha_combo | AAPL | -0.057 | -1.163 | 100.0% | 0.1621 | FAIL |
| rsi_reversal | NVDA | -0.070 | -1.365 | 99.8% | 0.2523 | FAIL |
| rsi_reversal | AAPL | -0.294 | -0.845 | 20.0% | 0.3956 | FAIL |
| macd_crossover | AAPL | -0.378 | -1.048 | 100.0% | 0.2168 | FAIL |


## Walk-Forward Validation

Expanding-window walk-forward: each strategy is evaluated on sequential out-of-sample windows. Indicators are computed per-window with a 50-bar warmup buffer to prevent data leakage.


### NVDA

![Walk-Forward NVDA](charts/NVDA_walk_forward.png)

| Strategy | Windows | Avg OOS Sharpe | % Positive | Avg Return | Pass |
|----------|---------|---------------|------------|------------|------|
| double_ma | 15 | 0.625 | 47% | 9.21% | FAIL |
| macd_crossover | 15 | 0.909 | 60% | 10.14% | PASS |
| bollinger_breakout | 15 | 0.201 | 27% | 3.16% | FAIL |
| rsi_reversal | 15 | -0.070 | 7% | -0.35% | FAIL |
| trend_momentum | 15 | 0.738 | 53% | 8.44% | PASS |
| alpha_combo | 15 | 0.920 | 60% | 14.66% | PASS |


### AAPL

![Walk-Forward AAPL](charts/AAPL_walk_forward.png)

| Strategy | Windows | Avg OOS Sharpe | % Positive | Avg Return | Pass |
|----------|---------|---------------|------------|------------|------|
| double_ma | 15 | 0.235 | 47% | 1.58% | FAIL |
| macd_crossover | 15 | -0.378 | 40% | -0.11% | FAIL |
| bollinger_breakout | 15 | 0.385 | 40% | 1.56% | FAIL |
| rsi_reversal | 15 | -0.294 | 7% | -0.56% | FAIL |
| trend_momentum | 15 | 0.124 | 53% | 2.51% | PASS |
| alpha_combo | 15 | -0.057 | 53% | 0.15% | PASS |


### TSLA

![Walk-Forward TSLA](charts/TSLA_walk_forward.png)

| Strategy | Windows | Avg OOS Sharpe | % Positive | Avg Return | Pass |
|----------|---------|---------------|------------|------------|------|
| double_ma | 15 | 0.517 | 47% | 8.07% | FAIL |
| macd_crossover | 15 | 0.693 | 47% | 8.00% | FAIL |
| bollinger_breakout | 15 | 0.437 | 27% | 5.93% | FAIL |
| rsi_reversal | 15 | 0.283 | 20% | -1.07% | FAIL |
| trend_momentum | 15 | 0.144 | 40% | 6.27% | FAIL |
| alpha_combo | 15 | 0.249 | 47% | 5.97% | FAIL |


## Monte Carlo Simulation

Trade returns are extracted from bars with active positions (non-zero signal), shuffled, and used to reconstruct equity curves. This tests whether strategy performance depends on the specific sequence of trades.


### NVDA

![Monte Carlo NVDA](charts/NVDA_monte_carlo.png)

| Strategy | Trades | Original Sharpe | MC 75th Pct | Percentile Rank | P(Ruin) | Pass |
|----------|--------|-----------------|-------------|-----------------|---------|------|
| double_ma | 782 | 1.200 | 1.200 | 99.9% | 0.0% | FAIL |
| macd_crossover | 535 | 1.937 | 1.937 | 98.9% | 0.0% | FAIL |
| bollinger_breakout | 226 | 1.064 | 1.064 | 100.0% | 0.0% | FAIL |
| rsi_reversal | 38 | 1.759 | 1.759 | 99.8% | 0.0% | FAIL |
| trend_momentum | 545 | 1.778 | 1.778 | 96.2% | 0.0% | FAIL |
| alpha_combo | 920 | 1.121 | 1.121 | 100.0% | 0.0% | FAIL |


### AAPL

![Monte Carlo AAPL](charts/AAPL_monte_carlo.png)

| Strategy | Trades | Original Sharpe | MC 75th Pct | Percentile Rank | P(Ruin) | Pass |
|----------|--------|-----------------|-------------|-----------------|---------|------|
| double_ma | 709 | 0.416 | 0.416 | 99.8% | 0.0% | FAIL |
| macd_crossover | 487 | 0.564 | 0.564 | 100.0% | 0.0% | FAIL |
| bollinger_breakout | 329 | 1.214 | 1.214 | 100.0% | 0.0% | FAIL |
| rsi_reversal | 78 | 0.481 | 0.481 | 20.0% | 0.0% | FAIL |
| trend_momentum | 532 | 0.954 | 0.954 | 88.4% | 0.0% | FAIL |
| alpha_combo | 863 | 0.533 | 0.533 | 100.0% | 0.0% | FAIL |


### TSLA

![Monte Carlo TSLA](charts/TSLA_monte_carlo.png)

| Strategy | Trades | Original Sharpe | MC 75th Pct | Percentile Rank | P(Ruin) | Pass |
|----------|--------|-----------------|-------------|-----------------|---------|------|
| double_ma | 649 | 0.554 | 0.554 | 99.6% | 0.0% | FAIL |
| macd_crossover | 441 | 1.550 | 1.550 | 99.7% | 0.0% | FAIL |
| bollinger_breakout | 206 | 1.780 | 1.780 | 99.5% | 0.0% | PASS |
| rsi_reversal | 100 | -0.407 | -0.407 | 99.9% | 0.0% | FAIL |
| trend_momentum | 422 | 1.034 | 1.034 | 98.6% | 0.0% | FAIL |
| alpha_combo | 864 | 0.543 | 0.543 | 88.1% | 0.0% | FAIL |


## Statistical Significance

One-sided t-test on trade returns (H0: mean return = 0). Bootstrap 95% CI on Sharpe ratio (5,000 resamples). Deflated Sharpe Ratio corrects for multiple testing (Bailey & Lopez de Prado 2014). Minimum 6 strategies tested per run.

Tests require a minimum of 20 trades. Strategies with fewer trades are marked 'Insufficient data.'


### NVDA

| Strategy | n | t-stat | p-value | Sharpe [95% CI] | DSR | Sig? |
|----------|---|--------|---------|-----------------|-----|------|
| double_ma | 782 | 2.11 | 0.0175 | 1.20 [0.09, 2.26] | 1.000 | Yes |
| macd_crossover | 535 | 2.82 | 0.0025 | 1.94 [0.64, 3.25] | 1.000 | Yes |
| bollinger_breakout | 226 | 1.01 | 0.1579 | 1.06 [-1.14, 2.87] | 0.076 | No |
| rsi_reversal | 38 | 0.67 | 0.2523 | 1.76 [-3.33, 7.29] | 0.000 | No |
| trend_momentum | 545 | 2.61 | 0.0046 | 1.78 [0.45, 3.02] | 1.000 | Yes |
| alpha_combo | 920 | 2.14 | 0.0163 | 1.12 [0.13, 2.16] | 1.000 | Yes |


### AAPL

| Strategy | n | t-stat | p-value | Sharpe [95% CI] | DSR | Sig? |
|----------|---|--------|---------|-----------------|-----|------|
| double_ma | 709 | 0.70 | 0.2431 | 0.42 [-0.83, 1.54] | 0.000 | No |
| macd_crossover | 487 | 0.78 | 0.2168 | 0.56 [-0.89, 1.97] | 0.000 | No |
| bollinger_breakout | 329 | 1.39 | 0.0834 | 1.21 [-0.54, 2.89] | 0.844 | No |
| rsi_reversal | 78 | 0.27 | 0.3956 | 0.48 [-3.10, 4.38] | 0.000 | No |
| trend_momentum | 532 | 1.38 | 0.0834 | 0.95 [-0.40, 2.33] | 0.809 | No |
| alpha_combo | 863 | 0.99 | 0.1621 | 0.53 [-0.51, 1.60] | 0.000 | No |


### TSLA

| Strategy | n | t-stat | p-value | Sharpe [95% CI] | DSR | Sig? |
|----------|---|--------|---------|-----------------|-----|------|
| double_ma | 649 | 0.89 | 0.1873 | 0.55 [-0.72, 1.78] | 0.000 | No |
| macd_crossover | 441 | 2.05 | 0.0205 | 1.55 [0.12, 3.03] | 1.000 | Yes |
| bollinger_breakout | 206 | 1.61 | 0.0549 | 1.78 [-0.40, 4.05] | 0.982 | No |
| rsi_reversal | 100 | -0.25 | 0.6003 | -0.41 [-3.52, 2.87] | 0.000 | No |
| trend_momentum | 422 | 1.34 | 0.0910 | 1.03 [-0.50, 2.51] | 0.657 | No |
| alpha_combo | 864 | 1.01 | 0.1575 | 0.54 [-0.54, 1.60] | 0.000 | No |


## Strategy Comparison

![Strategy Comparison](charts/strategy_comparison.png)


## Methodology Notes

- **Walk-forward:** Expanding window, 252-day initial training, 63-day quarterly test windows, minimum 4 windows
- **Indicators:** Computed per-window with 50-bar warmup buffer (prevents lookahead bias from rolling indicators)
- **Monte Carlo:** 1000 iterations, shuffling non-zero trade returns only
- **Statistical tests:** One-sided t-test (p < 0.05), bootstrap 95% CI (5,000 resamples)
- **DSR:** Deflated Sharpe Ratio with 6 strategies tested. DSR > 0.5 = pass. Results are not comparable across separate invocations
- **Minimum trades:** 20 required for statistical tests
- **Pass/fail gates:** Walk-forward OOS Sharpe > 0 in >50% of windows; Monte Carlo strategy Sharpe > 75th percentile; t-test p < 0.05
