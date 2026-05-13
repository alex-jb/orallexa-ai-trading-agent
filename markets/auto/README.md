# markets/auto — daily-research automation cron stack

3-cron pipeline that runs unattended on the operator's Mac via launchd.
Canonical install lives at `~/.orallexa/markets/scripts/` + `~/.orallexa/markets/strategies/`;
this directory is a git-tracked mirror for version history and ops review.

## Timing (NY ET)

| Time | Script | Cron label | Output |
|---|---|---|---|
| 09:00 | `news_morning.py` via `news-morning.sh` | `com.orallexa.news-morning` | `alex-brain/research/markets-news/YYYY-MM-DD.md` |
| 14:00 | `spacex-daily.sh` (existing) → triggers `master-lens.py` | `com.orallexa.spacex-daily` | `alex-brain/research/spacex-daily/YYYY-MM-DD.md` |
| 22:00 | `brier_audit.py` via `brier-audit.sh` | `com.orallexa.brier-audit` | `alex-brain/research/brier-audit/YYYY-MM-DD.md` |

## What each does

### `news_morning.py`
Pulls RSS (Yahoo / CNBC × 3 / Reuters / SEC EDGAR), filters to 14-ticker watchlist
(whole-word regex) + 4-sector keyword list, asks Claude Sonnet 4.6 to tag impact
(HIGH/MED/LOW + 1-sentence angle). Surfaces pre-market catalysts that drive
the 14:00 SpaceX decision context.

### `spacex-daily.sh` + setup classifier (inline Python heredoc)
Runs the Orallexa pilot on 14 tickers across 4 sectors (Space / Physical AI /
AI Infra / Drones — per Sun Yuchen 2026 thesis). Renders a ranking table
enriched with:

- **Setup type** — Trend / Trend+chase⚠ / MR-bounce / Breakdown / —
- **Position sizing** — Full / Half / Tiny / Short-half / Pass (1-2% risk rule)
- **Stop hint** — verbal stop-loss derived from BB% + setup type

After the brief is written, calls `master-lens.py` to append §3.7.

### `master-lens.py`
Picks today's weekday-rotation investor-master framework from `markets/strategies/`:
- Mon — Buffett (moats + compounding)
- Tue — Druckenmiller (macro top-down + concentrated)
- Wed — Lynch (PEG + grassroots)
- Thu — Soros (reflexivity 8-stage)
- Fri — Burry (contrarian + balance sheet)

Asks Claude to apply the framework to top-3 movers from today's brief, appends
the analysis as §3.7 in place. Sat/Sun → Lynch repeat.

### `brier_audit.py`
Nightly calibration audit. For each historical BUY/SELL decision >= 1 trading
day old, fetches actual close via yfinance, computes Brier score
`(forecast_p - actual)^2`, aggregates by ticker and confidence band.

Tells you whether "BUY 60% confidence" actually wins ~60% of the time, or whether
the system is over-confident. Output includes verdict (🔴 no edge / 🟡 mild / 🟢 real)
and confidence-band table.

## Watchlist

Defined in **2 places** that must stay in sync:
1. `spacex-daily.sh:20` (`WATCHLIST` env default)
2. `news_morning.py:WATCHLIST`

14 tickers across 4 sectors (Sun Yuchen 2026 thesis):

| Sector | Emoji | Tickers |
|---|---|---|
| Space | 🛰 | RKLB, ASTS, LUNR, BKSY, PL, RDW, LMT, LIN |
| Physical AI | 🤖 | TSLA, SYM |
| AI Infra | 🧠 | NVDA, AVGO |
| Drones | 🚁 | AVAV, KTOS |

## Cost

~$0.10/day total (Claude calls):
- news_morning: 1 call/day, ~0.02
- spacex-daily: 14 calls + 1 master-lens, ~0.06
- brier_audit: 0 Claude calls (pure stats)

≈ $3/month.

## Known issues

- **SYM price = $?** — yfinance doesn't resolve this ticker; needs Polygon/Alpaca fallback.
- **Polymarket offline** — Cloudflare IP-ban (since 2026-05-11), markets cron paused. News scan filter includes `polymarket` keyword so when news mentions it we still surface.
- **PL substring fix shipped 2026-05-14** — filter now uses `\bPL\b` whole-word regex, dropped ~21 false positives.

## Deploying changes

Canonical files live at `~/.orallexa/markets/`. Edits there take effect immediately
on the next cron fire. This `markets/auto/` directory is a **mirror for git
history**. To sync after editing canonical:

```bash
cp ~/.orallexa/markets/scripts/{news_morning.py,master-lens.py,brier_audit.py,*.sh} \
   markets/auto/
cp ~/.orallexa/markets/strategies/*.md markets/strategies/
git add markets/auto markets/strategies && git commit -m "..."
```

Future enhancement: invert this — make `~/.orallexa/markets/scripts/` a symlink
into the git repo, so edits go straight to version control.
