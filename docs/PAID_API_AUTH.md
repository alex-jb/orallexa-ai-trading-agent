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
Public `POST /api/analyze` requests return rule-based results without writing
the decision or breaking-signal logs. A valid `X-API-Key` is required to persist
those records for later analysis/training.
Authentication blocks anonymous requests, but **does not enforce an aggregate
weekly cost cap** for authenticated callers. The strategy evolution engine's
`MAX_COST_PER_RUN` is per invocation, and a repeated caller can still incur
multiple charges. Deployments should add an authenticated account-level spend
limit before opening a non-demo API to untrusted users.

Verify without broker or model credentials:

```bash
python -m pytest tests/test_api_auth.py tests/test_api_paid_auth.py -q
```
