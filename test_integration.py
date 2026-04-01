"""
INTEGRATION_GUIDE.md
════════════════════════════════════════════════════════════════════════════
How to integrate the new strategy engine into your existing Orallexa project.
Do this step by step — each step is independent and testable.

NEW FILES (copy these into your project):
  skills/technical_analysis_v2.py   → enhanced TA indicators
  engine/strategies.py              → 6 strategy library
  engine/multi_strategy.py          → parallel strategy runner
  engine/factor_engine.py           → alpha factor library

════════════════════════════════════════════════════════════════════════════
STEP 1 — Replace TechnicalAnalysisSkill with V2
════════════════════════════════════════════════════════════════════════════

In your existing files (core/brain.py, app_ui.py, etc.), replace:

    from skills.technical_analysis import TechnicalAnalysisSkill
    ta = TechnicalAnalysisSkill(data).add_indicators().dropna().copy()

With:

    from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2 as TechnicalAnalysisSkill
    ta = TechnicalAnalysisSkill(data).add_indicators().dropna().copy()

The V2 class has the SAME interface — it's a drop-in replacement.
It just adds ~20 more columns (MACD, BB, ATR, OBV, Stochastic, ADX, etc.)


════════════════════════════════════════════════════════════════════════════
STEP 2 — Add multi-strategy to StrategyLoop
════════════════════════════════════════════════════════════════════════════

In core/loop.py (your StrategyLoop), add this to the run() method:

    from engine.multi_strategy import run_multi_strategy_analysis

    # After your existing best_result is found, also run multi-strategy:
    multi_result = run_multi_strategy_analysis(
        train_df=train_df,
        test_df=test_df,
        ticker=ticker,
        transaction_cost=transaction_cost,
        slippage=slippage,
    )
    result["multi_strategy"] = multi_result


════════════════════════════════════════════════════════════════════════════
STEP 3 — Show multi-strategy results in Analysis page
════════════════════════════════════════════════════════════════════════════

In app_ui.py, inside the Analysis page per-ticker expander, add:

    from engine.multi_strategy import MultiStrategyRunner

    # After existing backtest results
    if "multi_strategy" in row.get("full_result", {}):
        ms = row["full_result"]["multi_strategy"]
        st.markdown("**Multi-Strategy Ranking**")
        st.dataframe(ms["summary_table"], use_container_width=True)

        st.markdown(f"**Best Strategy:** {ms['best_strategy']}")
        st.markdown(f"**Best Test Sharpe:** {ms['test_metrics'].get('sharpe', 0):.3f}")


════════════════════════════════════════════════════════════════════════════
STEP 4 — Add factor-based ranking to portfolio allocation
════════════════════════════════════════════════════════════════════════════

In portfolio/allocator.py, you can add alpha-factor ranking:

    from engine.factor_engine import rank_tickers_by_alpha

    def select_top_n_by_alpha(results, ticker_dfs, n=3):
        \"\"\"
        Rank tickers by composite alpha factor instead of just Sharpe.
        ticker_dfs: dict of {ticker: dataframe}
        \"\"\"
        ranking = rank_tickers_by_alpha(ticker_dfs)
        top_tickers = ranking.head(n)["ticker"].tolist()
        return [r for r in results if r["ticker"] in top_tickers]


════════════════════════════════════════════════════════════════════════════
STEP 5 — Quick test script
════════════════════════════════════════════════════════════════════════════

Run this to verify everything works before touching app_ui.py:

    # test_new_strategies.py
    import yfinance as yf
    from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2
    from engine.multi_strategy import run_multi_strategy_analysis
    from engine.factor_engine import FactorEngine

    # Get data
    data = yf.download("NVDA", period="2y")
    data.columns = [c[0] for c in data.columns]  # flatten MultiIndex

    # Run enhanced TA
    ta = TechnicalAnalysisSkillV2(data).add_indicators().dropna()
    df = ta.copy()
    print(f"Columns: {list(df.columns)}")
    print(f"Rows: {len(df)}")

    # Split
    split = int(len(df) * 0.7)
    train_df = df.iloc[:split]
    test_df  = df.iloc[split:]

    # Run all strategies
    result = run_multi_strategy_analysis(train_df, test_df, "NVDA")
    print(f"Best strategy: {result['best_strategy']}")
    print(result["summary_table"][["strategy","test_sharpe","test_return","test_maxdd"]])

    # Factor engine
    fe = FactorEngine(df)
    fe.compute_all()
    print(fe.factor_table().tail(5))


════════════════════════════════════════════════════════════════════════════
WHAT EACH FILE DOES
════════════════════════════════════════════════════════════════════════════

skills/technical_analysis_v2.py
  ├── MA5/10/20/50/200, EMA12/26
  ├── MACD + Signal + Histogram + cross flags
  ├── ADX + Plus_DI + Minus_DI (trend strength)
  ├── RSI, Stochastic %K/%D, ROC
  ├── Bollinger Bands (upper/lower/mid/%B/width/squeeze)
  ├── ATR + ATR_Pct (normalised volatility)
  ├── Historical Volatility (20-day annualised)
  ├── OBV (On-Balance Volume)
  ├── Volume MA + Volume Ratio + Volume Surge flag
  ├── VWAP (20-bar rolling)
  └── Composite signals: golden cross, death cross, RSI zones, BB squeeze

engine/strategies.py
  ├── double_ma           — classic dual MA crossover (ai_quant_trade)
  ├── macd_crossover      — MACD line cross with trend filter
  ├── bollinger_breakout  — price breaks BB after squeeze
  ├── rsi_reversal        — mean reversion with ADX filter
  ├── trend_momentum      — Orallexa enhanced (MA+MACD+RSI+Volume)
  └── alpha_combo         — 6-factor composite signal

engine/multi_strategy.py
  ├── MultiStrategyRunner   — runs all strategies in parallel
  ├── summary_table()       — comparison DataFrame
  ├── get_best()            — best strategy by any metric
  ├── get_strategy_ranking()— list ranked by test Sharpe
  └── ensemble_signal()     — majority-vote combination

engine/factor_engine.py
  ├── FactorEngine          — single ticker factor computer
  ├── momentum_factor()     — multi-horizon price momentum
  ├── volatility_factor()   — low-vol signal
  ├── volume_factor()       — OBV + volume pressure
  ├── trend_factor()        — MA alignment × ADX
  ├── reversal_factor()     — short-term mean reversion
  ├── composite_alpha()     — weighted combination
  └── rank_tickers_by_alpha()— cross-ticker ranking for portfolio
"""
