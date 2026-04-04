# Contributing to Orallexa

Thanks for your interest! Here's how to get started.

## Quick Start

```bash
git clone https://github.com/alex-jb/orallexa-ai-trading-agent.git
cd orallexa-ai-trading-agent
pip install -r requirements.txt
cp .env.example .env  # add your API keys

# Run tests
python -m pytest tests/ -q
cd orallexa-ui && npm ci && npm test
```

## Development

| Component | Command |
|-----------|---------|
| API server | `python api_server.py` |
| Next.js UI | `cd orallexa-ui && npm run dev` |
| Desktop agent | `python desktop_agent/main.py` |
| Run all tests | `python -m pytest tests/ -v` |
| UI tests | `cd orallexa-ui && npm test` |
| E2E tests | `cd orallexa-ui && npx playwright test` |

## Adding a New Strategy

1. Add a pure function to `engine/strategies.py` following `strategy_fn(df, params) -> pd.Series`
2. Register in `STRATEGY_REGISTRY` and `STRATEGY_DEFAULT_PARAMS`
3. Add search space to `engine/param_optimizer.py` `SEARCH_SPACES`
4. Write tests in `tests/test_engine_core.py`
5. Run `python -m pytest tests/test_engine_core.py -v`

## Adding a New ML Model

1. Create `engine/your_model.py` with a class that has `train()` and `predict()` methods
2. Register in `engine/ml_signal.py` `MLSignalGenerator.run_all()`
3. Add to the ML Scoreboard in `engine/multi_agent_analysis.py`
4. Write tests
5. Run the evaluation harness: `python eval/run_harness.py --tickers NVDA`

## Code Style

- Python: PEP 8, type annotations on function signatures
- TypeScript: ESLint config in `orallexa-ui/`
- UI: Follow `DESIGN.md` (Art Deco theme, 4-font system)
- Tests: pytest for Python, vitest for UI, Playwright for E2E

## Pull Requests

1. Fork the repo and create a branch from `master`
2. Make your changes
3. Run `python -m pytest tests/ -q` and `cd orallexa-ui && npm test`
4. Open a PR with the template filled in
5. Ensure CI passes

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
