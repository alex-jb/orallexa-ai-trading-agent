# Orallexa — Project Instructions

## Overview
AI-powered trading research dashboard. Streamlit UI + Claude AI analysis + multi-strategy backtesting engine.

## Tech Stack
| Layer | Technology |
|-------|-----------|
| Language | Python 3 |
| UI | Next.js 16 (`orallexa-ui/`), Streamlit prototype (`app_ui.py`) |
| LLM | Anthropic Claude via `anthropic` SDK (`llm/claude_client.py`) |
| Market Data | yfinance |
| ML | scikit-learn (RF, LR) |
| Visualization | matplotlib |
| Data | pandas, numpy |

## Project Structure
```
app.py                  → Main Streamlit dashboard (3 modes: scalp/predict/research)
app_ui.py               → Alternative UI entry
models/
  decision.py           → DecisionOutput dataclass (shared output type)
core/
  brain.py              → OrallexaBrain — run_scalping(), run_prediction(), run_train(), etc.
  loop.py               → StrategyLoop — iterative param optimization (research mode)
engine/
  backtest.py           → simple_backtest() core function
  evaluation.py         → evaluate() — Sharpe, drawdown, return metrics
  strategies.py         → 7 rule-based strategies (double MA, MACD, BB, RSI, etc.)
  multi_strategy.py     → run_multi_strategy_analysis()
  ml_signal.py          → run_ml_analysis() — RF/LR models
  sentiment.py          → analyze_ticker_sentiment()
  factor_engine.py      → factor-based signals
llm/
  claude_client.py      → real_llm_analysis(), reflect_on_strategy(), generate_new_parameters()
  strategy_generator.py → LLM-based strategy generation
  ui_analysis.py        → ui_analysis_with_rag(), ui_probability_report(), prediction_decision_report()
skills/
  market_data.py        → MarketDataSkill — yfinance wrapper
  technical_analysis_v2.py → TechnicalAnalysisSkillV2 (preferred over v1)
  scalping.py           → ScalpingSkill — 5-min breakout/pullback/volume detection
  prediction.py         → PredictionSkill — technical + Claude probability forecast
  risk_management.py    → RiskManagementSkill — position sizing, stop-loss
  news.py               → NewsSkill — news fetching
portfolio/
  allocator.py          → portfolio allocation
  backtest_portfolio.py → portfolio-level backtesting
  correlation_filter.py → correlation-based filtering
bot/
  behavior.py           → BehaviorMemory — trade tracking + aggressiveness adaptation
  memory.json           → persistent trade state (wins/losses, streaks, aggressiveness)
rag/
  vector_store.py       → LocalRAGStore — JSON-based vector store
rag_data/               → market_notes.json (RAG knowledge base)
memory_data/            → session/voice/daily memory JSON files
results/                → saved backtest JSON output files
```

## Running the App
```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export ANTHROPIC_API_KEY=your_key_here

# Run dashboard
streamlit run app.py
```

## App Modes
- **scalp** — 5-minute scalping decision (default): breakout/pullback/volume detection → BUY/SELL/WAIT
- **predict** — Daily/swing probability forecast: technical scoring + Claude overlay
- **research** — Full backtest pipeline (original): multi-strategy + ML + walk-forward

## Key Conventions
- Use `TechnicalAnalysisSkillV2` (not v1) for indicator computation
- Strategies are pure functions: `strategy_fn(df, params) -> pd.Series` of signals {-1, 0, 1}
- All trade decisions return `DecisionOutput` (models/decision.py) — use `.to_dict()` to serialize
- LLM model in use: `claude-sonnet-4-6` (deep) + `claude-haiku-4-5-20251001` (fast), defined in `llm/claude_client.py`
- Backtest params: `rsi_min`, `rsi_max`, `stop_loss`, `take_profit`
- Transaction cost + slippage defaults: 0.001 each
- Results saved to `results/{prefix}_{ticker}.json`
- Bot trade state in `bot/memory.json` — never delete, update via `BehaviorMemory`

## Environment Variables
- `ANTHROPIC_API_KEY` — required for all LLM features

## Testing
```bash
# Unit/integration tests
python -m pytest tests/ -q

# Evaluation harness (walk-forward + Monte Carlo + statistical tests)
python eval/run_harness.py --tickers NVDA,AAPL
python eval/run_harness.py --tickers NVDA --seed 42 --mc-iterations 5000
```

## Adding a New Strategy
1. Add pure function to `engine/strategies.py` following the signal convention
2. Register it in `engine/multi_strategy.py`
3. Test via `engine/test_integration.py`

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
