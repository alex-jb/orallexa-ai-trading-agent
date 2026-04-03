# Orallexa UI — Next.js Dashboard

Art Deco luxury trading intelligence dashboard built with Next.js 16, React 19, and Tailwind CSS 4.

## Quick Start

```bash
npm install
npm run dev          # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL` to point at the FastAPI backend (defaults to `http://localhost:8002`).

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
