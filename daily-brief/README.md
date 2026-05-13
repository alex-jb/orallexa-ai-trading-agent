# daily-brief — mirror of personal AI research pipeline

Git-tracked mirror of the canonical install at `~/.orallexa/daily-brief/`.
This directory exists for version history + multi-machine recovery only;
the cron actually executes the files at the canonical path.

## Cron — NY 12:00 ET + Sunday 12:05 ET

| Cron label | Script | Output |
|---|---|---|
| `com.orallexa.daily-brief` | `daily_brief.py` | `alex-brain/research/daily-brief/YYYY-MM-DD.{html,md}` |
| `com.orallexa.weekly-review` | `weekly_review.py` | `~/.solo-founder-os/weekly-review/YYYY-WXX.json` + HTML digest |

## What daily-brief produces (10 sections)

1. **Takeaway** (pullquote, ≤120 字)
2. **AI people watch** — Karpathy / 李飞飞 / Altman / Hassabis / Andrew Ng + 8 others
3. **AI news digest** — 5-8 items, opens with ✨ "今早 catalyst" from markets-news cron
4. **SpaceX tracking** — reads `spacex-daily/YYYY-MM-DD.md` (stale-1d aware)
5. **Polymarket** — status (offline until Cloudflare IP unbans)
6. **Curriculum lesson** — 90-day LLM curriculum (Phase 0 → Phase 4)
7. **Stack actionable** — concrete moves for VibeXForge / Orallexa / SFOS / niànniàn
8. **Strategic** — long-term bets (3-12 month horizon, future-Alex audience)
9. **Audit** — look back at D-1 + D-7 brief and verify predictions
10. **Wrap** (pullquote, ≤30 字)

Sent via Resend to xixiaichiyu09@gmail.com (sandbox via `onboarding@resend.dev`).
Heartbeat written to `~/.orallexa/daily-brief/.last_success` after each successful run.

## What weekly-review produces

Sunday 12:05 ET reads last 7 days of briefs, finds signals appearing ≥3 days,
splits into:
- `code_upgrade` JSON proposals → `~/.solo-founder-os/weekly-review/` (HITL queue)
- `positioning_watchlist` — long-horizon bets (Alex eyeball only, no auto-act)
- `demoted` — single-occurrence signals archived

## Cross-system data flow

```
09:00 markets-news ─→ markets-news/{date}.md
                           ↓
12:00 daily-brief  ─→ reads markets-news + spacex-daily(stale-1d if cron hasn't fired yet)
                           ↓ Resend → gmail
14:00 spacex-daily ─→ spacex-daily/{date}.md (master-lens appends §3.7)
22:00 brier-audit  ─→ brier-audit/{date}.md (drift detection)
```

## Cost

- daily-brief: ~$0.06/run (1 Sonnet 4.6 call ≈ 8k+4k tokens)
- weekly-review: ~$0.04/run (smaller input, Sunday only)
- **~$2.40/month** total for the 4 personal-info crons.

## Editing workflow

1. Edit canonical at `~/.orallexa/daily-brief/scripts/`
2. Manual trigger: `launchctl start com.orallexa.daily-brief`
3. Sync to this git mirror:
   ```bash
   cp ~/.orallexa/daily-brief/scripts/*.{py,sh} \
      ~/Desktop/orallexa-ai-trading-agent/daily-brief/scripts/
   cp ~/.orallexa/daily-brief/curriculum.yaml \
      ~/Desktop/orallexa-ai-trading-agent/daily-brief/
   ```
4. Commit + push

Future enhancement: invert this — make canonical a symlink into git so edits
go straight to version control.
