# Design System — Orallexa Capital

## Product Context
- **What this is:** AI-powered capital intelligence engine with voice coaching
- **Who it's for:** Individual traders seeking AI-assisted decision-making
- **Space/industry:** Fintech, trading dashboards (Bloomberg Terminal lite + AI coach)
- **Project type:** Next.js 16 web app (`orallexa-ui/`) + Streamlit prototype (`app_ui.py`)
- **Canonical UI:** `orallexa-ui/` (Next.js 16 + React 19 + Tailwind 4)
- **Streamlit:** `app_ui.py` is the prototype/legacy. Should converge toward the Next.js palette over time.

## Aesthetic Direction
- **Direction:** Art Deco Luxury. Geometric precision, gold gradients, stepped corner ornaments, decorative rules with diamond motifs.
- **Decoration level:** Expressive. Double-border card frames, L-shaped corner ornaments, gold sunburst fans, gradient gold rule dividers with diamond centers.
- **Mood:** "1920s private banking meets modern quant terminal." Opulent but functional. Every decoration earns its pixels by reinforcing hierarchy or brand.
- **Theme:** Dark only. No light mode. The darkness is the brand.
- **Anti-patterns:** No purple gradients. No 3-column icon grids. No rounded bubbly corners (0px radius on cards). No decorative blobs. No emoji in headings.

## Typography
- **Display/Brand:** Poiret One — Art Deco geometric display face. Used for brand name and decorative moments.
- **Headings/Labels:** Josefin Sans (300-700) — Clean geometric sans with Art Deco character. Used for card headers, section labels, navigation, uppercase micro-labels.
- **Body:** Lato (300-700) — Warm, legible body text. Used for all readable content, descriptions, reasoning text.
- **Data/Mono:** DM Mono (400-500) — Monospace for financial data, prices, percentages, timestamps.
- **Loading:** Google Fonts CDN:
  ```
  https://fonts.googleapis.com/css2?family=Poiret+One&family=Josefin+Sans:wght@300;400;600;700&family=Lato:wght@300;400;700&family=DM+Mono:wght@400;500&display=swap
  ```
- **Scale:**
  - 8-9px — micro sub-labels (Josefin Sans, uppercase, 0.14em tracking)
  - 10px — card headers, section labels (Josefin Sans, uppercase, 0.16-0.28em tracking)
  - 11px — card row labels, secondary text (Lato)
  - 13px — card row values (DM Mono, medium weight)
  - 14px — body content, recommendation text (Lato)
  - 36px — probability hero numbers (DM Mono, bold)
  - 42px — hero decision text (Josefin Sans)

## Color
- **Approach:** Restrained with gradient gold accents. Gold is the primary accent, used in gradients for shimmer effects. All other color is semantic (bull/bear/neutral).

### Palette
| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-deep` | `#0A0A0F` | Page background, the deepest layer |
| `--bg-panel` | `#0D1117` | Sidebar, panel backgrounds |
| `--bg-card` | `#1A1A2E` | Card backgrounds (Mod component) |
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
| `--text-muted-safe` | `#8B8E96` | Accessibility-safe muted text (higher contrast) |

### Semantic Colors
- **Success/Bull:** `--emerald` (#006B3F)
- **Warning:** `--gold` (#D4AF37)
- **Error/Bear:** `--ruby` (#8B0000)
- **Info/Neutral:** `--text-muted` (#6B6E76)

### Gold Gradient (brand signature)
```css
background: linear-gradient(135deg, #D4AF37, #FFD700, #C5A255);
```
Used for: card header text (via background-clip), gold shimmer animation, topbar accent lines.

## Spacing
- **Base unit:** 4px (Tailwind scale)
- **Density:** Compact (trading dashboards need information density)
- **Card padding:** px-4 py-3 (16px horizontal, 12px vertical)
- **Card row padding:** py-[7px]
- **Section gaps:** mb-3 (12px) between cards

## Layout
- **Approach:** Grid-disciplined. Dense but organized. Each panel has one job.
- **Home cockpit:** 3-panel (sidebar fixed ~240px / center flex / right ~320px)
- **Sidebar:** Fixed left, dark panel background
- **Border radius:** 0px on cards (sharp, Art Deco). Only dots/indicators use rounded.

### Border Radius Scale
| Usage | Value |
|-------|-------|
| Cards, containers | 0px (sharp edges) |
| Inputs | 0px |
| Probability bar segments | 0px |
| Indicator dots | 50% (rounded) |
| Scrollbar thumb | 0px |

## Motion
- **Approach:** Intentional. Art Deco-flavored entrance animations and shimmer effects.
- **Animations defined:**
  - `fadeIn` — 0.3s ease-out (element entrance)
  - `slideInRight` / `slideInLeft` — 0.3s ease-out (panel slides)
  - `goldShimmer` — 3s infinite (brand shimmer on gold text)
  - `priceTick` — 0.8s (price update flash)
  - `breakingPulse` — 2s infinite (breaking signal pulse)
  - `skeletonPulse` — 1.5s infinite (loading placeholder)
  - `errorShake` — 0.4s (error feedback)
  - `spin` — 1s linear (loading spinner)
- **Rule:** Motion serves hierarchy and feedback. Gold shimmer = brand. Pulse = attention. Shake = error.

## Component Patterns

### Mod (Card)
- Double-border frame (outer + inner 3px inset)
- L-shaped stepped corner ornaments at all 4 corners
- Gold gradient accent line across top
- Header: Josefin Sans 10px uppercase, gold gradient text
- Header separator with gold diamond decorative rule
- Background: `--bg-card` (#1A1A2E)

### Decision Card (Hero)
- Gold border-top gradient (linear-gradient across full width)
- Overline: Josefin Sans 10px uppercase, gold
- Decision text: 42px, colored by decision (emerald/ruby/gold)
- Subtitle: contextual text below decision
- Probability bar: Polymarket-inspired stacked segments
- Bull/Bear debate panel: 2-column with colored left borders
- Investment plan: 5-column metrics grid

### Row (Data Row)
- Label: Lato 11px, `--text-muted`
- Value: DM Mono 13px medium, `--champagne`
- Border-bottom: gold-tinted at 0.06 opacity
- Last child: no border

### Heading (Section Label)
- Diamond motif prefix (rotated squares)
- Josefin Sans 10px semibold uppercase, 0.28em tracking
- Gold gradient text (background-clip)
- Trailing gold gradient line

### Gold Rule (Decorative Divider)
- Three diamond shapes centered (two small filled, one larger outlined)
- Gradient lines extending to edges
- Opacity controlled by `strength` prop

### Buttons
- Primary: gold background, dark text, uppercase, tracking
- No border-radius (sharp edges)
- Transition: 120ms colors

## Responsive Design
- Desktop: 3-panel layout
- Tablet (< 1024px): sidebar collapses, mobile menu button appears
- Mobile (< 768px): single-column stack
- Touch: all interactive elements adequately sized

## Accessibility
- Focus-visible: 2px solid gold-bright outline with 4px gold box-shadow
- `--text-muted-safe` (#8B8E96) variant for WCAG AA compliance
- Keyboard navigation on all interactive elements
- `lang` attribute on html element
- Print stylesheet strips backgrounds

## i18n
- Full bilingual support: English + Chinese (中文)
- Language toggle in sidebar
- All UI strings in T dictionary, keyed by EN/ZH

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-02 | Next.js app is canonical UI | orallexa-ui/ is the production frontend. Streamlit is prototype. |
| 2026-04-02 | Art Deco aesthetic direction | Geometric precision + gold luxury. Differentiates from generic trading dashboards. |
| 2026-04-02 | Poiret One + Josefin Sans + Lato + DM Mono | 4-font system: display + headings + body + data. Each font has a clear role. |
| 2026-04-02 | Gold gradient as brand signature | Linear-gradient gold shimmer on headers. Not flat color, gradient = luxury. |
| 2026-04-02 | 0px border-radius on cards | Sharp edges are the Art Deco signature. Rounded = SaaS. Sharp = finance. |
| 2026-04-02 | Stepped corner ornaments | L-shaped corner decorations on Mod cards. Earns its pixels by reinforcing Art Deco identity. |
| 2026-04-02 | Champagne text (#F5E6CA) | Warmer than white, softer than ivory. The entire app feels differently lit. |
| 2026-04-02 | Emerald (#006B3F) for bull, not muted green | Deeper, richer green matches the luxury register. |
| 2026-04-02 | Streamlit app_ui.py dark theme unified | Legacy Streamlit uses approximated palette. Will converge to Next.js tokens. |
