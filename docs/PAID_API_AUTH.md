# Paid API authentication

Non-demo API startup requires `ORALLEXA_API_KEY`. Real paid-model requests also
require that secret in `X-API-Key`; never expose it through a `NEXT_PUBLIC_*`
variable or client-side JavaScript. The current Next.js UI fetches the API
directly from the browser. Its paid features return 401 against a non-demo
backend until a trusted server-side relay is built. Broker routes have their
own, stricter dependency and remain disabled in demo mode.

| Route | When it can spend | Demo behavior |
|---|---|---|
| `POST /api/analyze` | `use_debate=true` or `use_claude=true` | Mock response |
| `POST /api/deep-analysis` | Non-demo request; caller caps are optional | Mock response |
| `POST /api/deep-analysis-stream` | Non-demo request; several model calls | Mock stream |
| `POST /api/chart-analysis` | Non-demo Claude Vision request | Mock response |
| `GET /api/daily-intel` | Cache miss or `force=true`; generation uses model calls | Mock response |
| `POST /api/daily-intel/refresh` | Every non-demo regeneration | Mock response |
| `GET /api/regime/{ticker}` | `use_llm=true` | Heuristic example |
| `POST /api/scenario` | Every request; Claude Opus | 403, no model call |
| `POST /api/evolve-strategies` | Every run; limit applies per run only | 403, no model call |

Other listed analysis endpoints use local rules/data sources and remain public.
Authentication blocks anonymous requests. The API now also reserves an
estimated worst-case amount before every Anthropic model call in these routes.
The shared SQLite ledger enforces `ORALLEXA_WEEKLY_LLM_BUDGET_USD` (default
`5.00`, or `0` to block spending) across requests and processes using the
same file, with a Monday 00:00 UTC reset. A successful provider response with
usage releases excess reservation; an error or missing usage retains it. Set
`ORALLEXA_WEEKLY_LLM_BUDGET_DB` to a **persistent shared volume** when API
workers run on more than one host. The file under `logs/` is gitignored. Do
not delete or rotate the ledger midweek. Unknown model pricing, invalid cap,
and unavailable ledger fail closed.

This is an admission budget based on the local pricing table and a
conservative estimate of input tokens plus requested maximum output tokens.
It is **not an invoice guarantee**: vendor prices can change; image token
counts, provider retries, unreported billed errors, and actual usage above
the estimate can differ. It covers calls through `llm.call_logger.logged_create`,
including chart analysis and trade reflection. Other processes (desktop agent,
standalone scripts) and the optional OpenAI/Gemini/GLM provider adapters do
not share this API admission gate unless routed through the same boundary.
`engine.token_budget.TokenBudget` remains a separate, optional per-run soft
budget for deep analysis. The fixed-rule paper loop does not use paid models.

Verify without broker or model credentials:

```bash
python -m pytest tests/test_api_auth.py tests/test_api_paid_auth.py tests/test_weekly_llm_budget.py -q
```
