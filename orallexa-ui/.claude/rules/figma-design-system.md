# Figma Design System Rules — Orallexa Capital

## Design Identity

This is an **Art Deco Luxury** financial trading dashboard. Every implementation must reflect:
- Geometric precision, gold gradients, stepped corner ornaments, decorative rules with diamond motifs
- Dark-only theme — `#0A0A0F` deep black is the brand
- "1920s private banking meets modern quant terminal"
- **Anti-patterns:** No purple gradients. No rounded bubbly corners. No decorative blobs. No emoji in headings. 0px border-radius on all cards.

## Component Organization

- UI components are currently in `app/page.tsx` (monolithic)
- New extracted components go in `app/components/` using PascalCase filenames
- Component naming: PascalCase, feature-descriptive (e.g., `DecisionCard`, `BullBearPanel`, `MLScoreboard`)
- All components are function components with TypeScript types
- Export pattern: named exports preferred

### Existing Components (in page.tsx)
| Component | Purpose |
|-----------|---------|
| `DecisionCard` | Hero trading decision display |
| `ProbBar` | Probability distribution visualization |
| `BullBearPanel` | Bull/Bear debate section |
| `InvestmentPlanCard` | Risk management metrics |
| `MLScoreboard` | ML model performance tracker |
| `BreakingBanner` | Market alert display |
| `MarketStrip` | Price/sentiment strip |
| `WatchlistGrid` | Asset watchlist grid |
| `DailyIntelView` | Market intelligence dashboard |
| `DecoFan` | Decorative sunburst SVG |

## Design Tokens

IMPORTANT: All colors are defined as CSS custom properties in `app/globals.css`. Never hardcode hex values — use the token system.

### Color Tokens
| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-deep` | `#0A0A0F` | Page background |
| `--bg-panel` | `#0D1117` | Sidebar, panel backgrounds |
| `--bg-card` | `#1A1A2E` | Card backgrounds |
| `--bg-input` | `#2A2A3E` | Input fields, interactive surfaces |
| `--gold` | `#D4AF37` | Primary gold accent |
| `--gold-bright` | `#FFD700` | Bright gold for gradients, focus states |
| `--gold-muted` | `#C5A255` | Muted gold for secondary accents |
| `--gold-dim` | `rgba(212,175,55,0.15)` | Subtle gold backgrounds |
| `--border` | `#2A2A3E` | Card borders, dividers |
| `--border-gold` | `rgba(212,175,55,0.25)` | Gold-tinted borders on premium elements |
| `--emerald` | `#006B3F` | Bull/buy signals, success states |
| `--ruby` | `#8B0000` | Bear/sell signals, error states |
| `--champagne` | `#F5E6CA` | Primary text color |
| `--ivory` | `#FAFAF0` | High-contrast text (rare) |
| `--bronze` | `#CD7F32` | Warning states |
| `--text-muted` | `#6B6E76` | Secondary text, labels |
| `--text-dim` | `#4A4D55` | Disabled text, placeholders |
| `--text-muted-safe` | `#8B8E96` | Accessibility-safe muted text |

### Semantic Color Mapping
- **Success/Bull:** `--emerald` (#006B3F)
- **Warning/Neutral:** `--gold` (#D4AF37)
- **Error/Bear:** `--ruby` (#8B0000)

### Gold Gradient (Brand Signature)
```css
background: linear-gradient(135deg, #D4AF37, #FFD700, #C5A255);
```
Used for: card header text (via `background-clip: text`), shimmer animation, topbar accent lines.

## Typography

IMPORTANT: Use the 4-font system. Each font has a specific role — do not mix roles.

| Font | Variable | Role | Usage |
|------|----------|------|-------|
| Poiret One (400) | `--font-poiret` | Display/Brand | Brand name, decorative moments only |
| Josefin Sans (300-700) | `--font-josefin` | Headings/Labels | Card headers, section labels, navigation, uppercase micro-labels |
| Lato (300-700) | `--font-lato` | Body | All readable content, descriptions, reasoning text |
| DM Mono (400-500) | `--font-dm-mono` | Data/Mono | Financial data, prices, percentages, timestamps |

### Type Scale
| Size | Font | Usage |
|------|------|-------|
| 8-9px | Josefin Sans, uppercase, 0.14em tracking | Micro sub-labels |
| 10px | Josefin Sans, uppercase, 0.16-0.28em tracking | Card headers, section labels |
| 11px | Lato | Card row labels, secondary text |
| 13px | DM Mono, medium | Card row values |
| 14px | Lato | Body content, recommendation text |
| 36px | DM Mono, bold | Probability hero numbers |
| 42px | Josefin Sans | Hero decision text |

## Styling Approach

- **Framework:** Tailwind CSS 4 utility classes
- **Dynamic styles:** Inline `style={{ }}` for computed colors (e.g., decision-based coloring)
- **No CSS Modules, no styled-components, no CSS-in-JS**
- **Custom properties:** Defined in `app/globals.css` root scope
- IMPORTANT: Use Tailwind utilities for layout/spacing. Use CSS variables for colors. Use inline styles only for dynamic values.

## Spacing

- **Base unit:** 4px (Tailwind scale)
- **Density:** Compact — trading dashboards need information density
- **Card padding:** `px-4 py-3` (16px horizontal, 12px vertical)
- **Card row padding:** `py-[7px]`
- **Section gaps:** `mb-3` (12px) between cards

## Component Patterns

### Mod (Card)
- Double-border frame (outer + inner 3px inset)
- L-shaped stepped corner ornaments at all 4 corners
- Gold gradient accent line across top
- Header: Josefin Sans 10px uppercase, gold gradient text
- Separator: gold diamond decorative rule
- Background: `--bg-card` (#1A1A2E)
- IMPORTANT: Border-radius is always 0px

### Data Row
- Label: Lato 11px, `--text-muted`
- Value: DM Mono 13px medium, `--champagne`
- Border-bottom: gold-tinted at 0.06 opacity
- Last child: no border

### Heading (Section Label)
- Diamond motif prefix (rotated squares)
- Josefin Sans 10px semibold uppercase, 0.28em tracking
- Gold gradient text (`background-clip: text`)
- Trailing gold gradient line

### Gold Rule (Decorative Divider)
- Three diamond shapes centered (two small filled, one larger outlined)
- Gradient lines extending to edges

### Buttons
- Primary: gold background, dark text, uppercase, letter-spacing
- Border-radius: 0px (sharp edges)
- Transition: 120ms colors

## Layout

- **Home cockpit:** 3-panel (sidebar ~240px fixed / center flex / right ~320px)
- **Sidebar:** Fixed left, `--bg-panel` background
- **Tablet (< 1024px):** Sidebar collapses, mobile menu appears
- **Mobile (< 768px):** Single-column stack

## Motion & Animation

Available animation classes (defined in `globals.css`):
| Class | Effect | Duration |
|-------|--------|----------|
| `.anim-fade-in` | Fade entrance | 0.3s ease-out |
| `.anim-slide-right` | Slide from left | 0.3s ease-out |
| `.anim-slide-left` | Slide from right | 0.3s ease-out |
| `.anim-error` | Error shake | 0.4s |
| `.anim-spin` | Loading spinner | 1s linear |
| `.anim-skeleton` | Loading pulse | 1.5s infinite |
| `.anim-price-tick` | Price flash | 0.8s |
| `.anim-breaking` | Alert pulse | 2s infinite |
| Gold shimmer | Brand shimmer | 3s infinite |

Rule: Motion serves hierarchy and feedback. Gold shimmer = brand. Pulse = attention. Shake = error.

## Accessibility

- Focus-visible: `outline: 2px solid var(--gold-bright)` with 4px gold box-shadow
- Use `--text-muted-safe` (#8B8E96) for WCAG AA compliance on muted text
- Keyboard navigation on all interactive elements
- `@media (prefers-reduced-motion: reduce)` support built in

## Figma MCP Integration Rules

These rules define how to translate Figma inputs into code for this project.

### Required Flow (do not skip)

1. Run `get_design_context` first to fetch the structured representation for the exact node(s)
2. If the response is too large or truncated, run `get_metadata` to get the high-level node map, then re-fetch only the required node(s)
3. Run `get_screenshot` for a visual reference of the node variant being implemented
4. Only after you have both `get_design_context` and `get_screenshot`, download any assets and start implementation
5. Translate the output into this project's conventions — replace generic styles with the Art Deco token system
6. Validate against Figma for 1:1 look and behavior before marking complete

### Implementation Rules

- Treat Figma MCP output as a representation of design intent, not final code
- Replace generic colors with CSS custom properties from `app/globals.css`
- Reuse existing components from `app/page.tsx` or `app/components/` instead of duplicating
- Map Figma typography to the 4-font system (Poiret One / Josefin Sans / Lato / DM Mono)
- Ensure all cards have 0px border-radius with Art Deco corner ornaments
- Use Tailwind utilities for layout, CSS variables for colors
- Strive for 1:1 visual parity with the Figma design while maintaining the Art Deco identity

## Asset Handling

- IMPORTANT: If the Figma MCP server returns a localhost source for an image or SVG, use that source directly
- IMPORTANT: DO NOT import/add new icon packages — all assets should come from the Figma payload
- IMPORTANT: DO NOT use or create placeholders if a localhost source is provided
- Store downloaded assets in `public/assets/`
- Prefer inline SVG React components for decorative elements (like `DecoFan`)

## i18n

- Full bilingual support: English + Chinese
- All UI strings must be in the `T` dictionary, keyed by `EN`/`ZH`
- Language toggle in sidebar
