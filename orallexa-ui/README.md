# Orallexa UI — Next.js Dashboard

Art Deco luxury trading intelligence dashboard built with Next.js 16, React 19, and Tailwind CSS 4.

## Quick Start

```bash
npm install
npm run dev          # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL` to point at the FastAPI backend (defaults to `http://localhost:8002`).

### Operator access to paper trading and paid analysis

The public dashboard stays a demo. Broker endpoints are inaccessible in demo
mode. With a non-demo backend, paper orders and paid analysis require an owner
session; the dashboard never sends the FastAPI API key to the browser.

Configure **runtime** environment variables on the Next.js server:

```bash
ORALLEXA_UI_OWNER_TOKEN=$(openssl rand -hex 32)
ORALLEXA_UI_ORIGIN=https://your-frontend.example
ORALLEXA_SERVER_API_URL=https://your-api.example
ORALLEXA_API_KEY=<same strong key as the FastAPI server>
```

The owner token must be exactly 64 lowercase hexadecimal characters generated
from 32 random bytes. Use separate values for `ORALLEXA_UI_OWNER_TOKEN` and `ORALLEXA_API_KEY`. Set
them in deployment secrets, never in `NEXT_PUBLIC_*` or a committed `.env`.
The token is entered only into the owner sign-in field. The resulting signed,
HttpOnly, SameSite=Strict cookie expires in 15 minutes. The relay is disabled
if any required setting is absent and only forwards a fixed set of UI
operations. It refuses redirects and does not cache owner responses.

`ORALLEXA_UI_ORIGIN` must match the exact HTTPS origin used in the browser.
Local `npm run dev` can use `http://localhost:3000`; for a private HTTP API
upstream, opt in with `ORALLEXA_ALLOW_HTTP_UPSTREAM=1`. Never enable that
option for an API exposed over the internet. The existing `docker-compose.yml`
does not enable the owner bridge and remains demo-only unless separately
configured. Paper **submission remains off** unless the Next server sets
`ORALLEXA_ENABLE_PAPER_UI=1`. Enable this only after the mandatory,
broker-sourced portfolio gate in PR #20 is integrated and verified. The
backend must still enforce paper-only broker credentials and auth. A signed-in
dashboard is not evidence that paper performance is validated.

This owner token is a single-operator gate, with no account recovery, MFA,
central session revocation or distributed rate limiter. Rotate it to invalidate
all sessions; a stolen session can otherwise be replayed until its 15-minute
expiry. For a public non-demo deployment, place the UI behind a managed
identity/access gateway and rate limit sign-in requests. Authenticated users
can still initiate repeated model calls; this bridge does not impose a weekly
LLM spending cap. The server must enforce one before broad access.

## Architecture

```
app/
├── page.tsx              # Main dashboard (751 lines, down from 1574)
├── layout.tsx            # Root layout with next/font
├── globals.css           # Design tokens, animations, a11y
├── types.ts              # Interfaces + helper functions
├── mock-data.ts          # Demo mode data generators
├── components/
│   ├── atoms.tsx         # DecoFan, GoldRule, Heading, Mod, Row, Toggle, BullIcon, BrandMark, CopyBtn
│   ├── decision-card.tsx # DecisionCard + ProbBar + BullBearPanel + InvestmentPlanCard
│   ├── daily-intel.tsx   # DailyIntelView (morning brief, movers, sectors, AI picks, thread)
│   ├── watchlist.tsx     # WatchlistGrid (Polymarket-style signal cards)
│   ├── breaking.tsx      # BreakingBanner (signal change alerts)
│   ├── market-strip.tsx  # MarketStrip (live price, RSI, signal, confidence)
│   ├── ml-scoreboard.tsx # MLScoreboard (model comparison table)
│   └── index.ts          # Barrel exports
└── __tests__/            # 139 tests (vitest + @testing-library/react)
    ├── types.test.ts     # 28 tests — helpers, color mapping, i18n
    ├── atoms.test.tsx    # 12 tests — render + behavior
    ├── mock-data.test.ts # 31 tests — all mock generators
    ├── decision-card.test.tsx  # 17 tests — empty/BUY/SELL, plan, toggles
    ├── breaking.test.tsx       # 11 tests — signal types, EN/ZH
    ├── market-strip.test.tsx   # 10 tests — live price, flash, indicators
    ├── ml-scoreboard.test.tsx  #  7 tests — headers, best highlight
    ├── watchlist.test.tsx      #  9 tests — click, error, probabilities
    └── daily-intel.test.tsx    # 14 tests — mood, movers, sectors, picks
```

## Design System

See [DESIGN.md](../DESIGN.md) for the full Art Deco design specification.

| Token | Usage |
|-------|-------|
| Poiret One | Brand name, decorative moments |
| Josefin Sans | Headings, labels, uppercase micro-text |
| Lato | Body text, descriptions, reasoning |
| DM Mono | Financial data, prices, percentages |

Colors: `--gold` (#D4AF37), `--emerald` (#006B3F), `--ruby` (#8B0000), `--champagne` (#F5E6CA) on `--bg-deep` (#0A0A0F).

## Testing

```bash
npm test              # Run all 139 tests
npm run test:watch    # Watch mode
```

## Features

- **Two views**: Signal (real-time analysis) + Intel (daily market intelligence)
- **Bilingual**: EN/ZH with language toggle
- **Real-time**: WebSocket price stream, 30s auto-refresh, price flash animations
- **Keyboard**: Ctrl+Enter (run), Ctrl+D (deep), Ctrl+1/2 (tabs), Escape (clear)
- **Accessible**: ARIA labels, focus indicators, prefers-reduced-motion, WCAG AA contrast
- **Mobile responsive**: 3-column desktop, single-column mobile
- **Demo mode**: Works without backend using mock data generators
