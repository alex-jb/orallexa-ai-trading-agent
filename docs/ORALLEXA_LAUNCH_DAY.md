# Orallexa — Launch Day Runbook

**Target:** parallel-launch with VibeXForge, Wed 2026-05-13.
Different audience (quant traders + AI infra crowd vs. AI tinkerers),
different pitch (production-grade Sharpe + multi-agent debate vs. evolution-RPG-as-a-product),
same week.

> docs/ in this repo isn't in any vercel ignoreCommand — every commit
> here triggers the full Pages build. Update sparingly during launch.

---

## Pre-launch checklist (Sun evening, ~20 min)

### 1. Pull + rebuild orallexa-ui

```bash
cd ~/Desktop/orallexa-ai-trading-agent/orallexa-ui
git pull && npm install && npm run build
# Verify /leaderboard renders with the latest README EVAL_TABLE block
```

### 2. Verify multimodal-lift cron is green

```bash
gh run list --workflow=multimodal-lift.yml --limit 5
# Expect last 2-3 runs to be ✅ success after commit c28cd0f.
```

### 3. Alpaca paper pilot — start the data accumulation BEFORE launch

If you haven't yet:

```bash
# Fast track per docs/UNBLOCK_30_DAYS.md
open https://app.alpaca.markets/signup
# Generate paper keys → add to .env

# Then load the daily cron:
# (plist contents copied below for convenience)
cp ~/Desktop/orallexa-ai-trading-agent/scripts/launchd/com.alexji.orallexa-paper-daily.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.alexji.orallexa-paper-daily.plist

# Smoke test
python scripts/run_daily_pilot.py --dry-run
```

By Wed launch, you want at least 3-4 days of decision_log entries
showing real traction. Helps the "we have production decisions
flowing" line in the maker comment.

### 4. Confirm leaderboard URL is sharable

```bash
open https://orallexa-ui.vercel.app/leaderboard
# Should render Art Deco dark page, table sorted by OOS Sharpe DESC,
# rsi_reversal INTC at top with 1.41.
```

This is the URL you're sharing in every distribution post. Make sure
it loads cleanly on mobile + dark/light browsers.

---

## Audiences (different from VibeX!)

VibeX targets indie hackers and AI tinkerers. Orallexa targets:
- **Quant traders** (r/algotrading, Quantopian/QuantConnect refugees, hedge fund junior ICs)
- **AI infra builders** (Latent Space, swyx's circle, MOIRAI/Chronos paper authors who care about Kronos foundation model integration)
- **Solo prop-trading curious** (hedge fund ICs thinking about going solo)

Pitch should NOT be "look at my AI bot." Pitch SHOULD be "production-grade
walk-forward verified system, with the engineering to back it up."

---

## Tuesday 2026-05-12 — Soft drop

### 8:00 AM PT — Show HN

Use `~/.marketing_agent/queue/pending/20260507T053417Z-orallexa-hacker_news.md`.

Title to swap to (sharper for HN):

```
Show HN: Walk-forward Sharpe 1.41 OOS for an AI-judged trading system.
What I learned about Bull/Bear/Judge debate in production.
```

URL: `https://orallexa-ui.vercel.app/leaderboard?ref=hn`

First comment includes:
- Live demo link: https://orallexa-ui.vercel.app
- Source: https://github.com/alex-jb/orallexa-ai-trading-agent
- "Open to feedback on the eval methodology — the walk-forward
  setup is documented in docs/evaluation_report.md, happy to argue
  about p-value gates."

Sit at the keyboard. Reply within 30 min to every comment. HN values
authors who engage with statistical critiques substantively, not
defensively.

### 11:00 AM PT — r/algotrading

Use `~/.marketing_agent/queue/pending/20260507T053417Z-orallexa-reddit.md`.

The leaderboard URL is the hook. Lead with the result, then methodology.
This subreddit allergic to "AI bot" hype but very receptive to
"here's my walk-forward setup, here's the OOS Sharpe, roast it."

---

## Wednesday 2026-05-13 — Coordinated push

### 6:05 AM PT (after VibeX PH 12:01 storm) — Twitter thread

Use `~/.marketing_agent/queue/pending/20260507T053417Z-orallexa-x.md`.

Tag @AnthropicAI in tweet 6 (Claude Opus 4.7 is your reasoning layer).
Tag @hedgehogquant @0xfbifemboy @QuantopianAI in tweet 1's reply if
they engaged with the HN thread overnight.

### 7:00 AM PT — LinkedIn

Use the linkedin draft. Tone: "shipping in public, here's the moat."

### 9:30 AM PT — Bluesky

Use the bluesky draft. Bluesky's quant-finance crowd is small but
Latent Space adjacent — high signal-to-noise.

### 11:00 AM PT — Dev.to long-form

Use the dev_to draft. Title swap to:

```
How I built a Bull/Bear/Judge debate engine on Claude Opus 4.7
for trading decisions. 990 tests, walk-forward Sharpe 1.41.
```

Tags: ai, python, trading, postgres, claude.

---

## Thursday 2026-05-14 — Outreach + decks

### Morning — VC outreach

Use `vc-outreach-agent` (not yet wired against orallexa, but trivial):

```bash
cd ~/Desktop/orallexa-ai-trading-agent
# Pre-fill the agent with the new fundraise-traction.md
vc-outreach-agent enrich --signal-file docs/fundraise-traction.md \
  --traction-link https://orallexa-ui.vercel.app/leaderboard
```

Drafts land in `~/.vc_outreach_agent/queue/pending/`. HITL approve,
send via `sfos-ui`.

Targets: indie/seed VCs who specifically write into AI infra +
algorithmic trading. Per memory:
- Not Andreessen / Sequoia / Founders Fund — too big for seed
- Targets: South Park Commons (early AI), 1517 (anti-traditional, fits the indie story), Pioneer (solo-founder programmatic), Y Combinator W26 batch (if not too late), Long Journey, Lerer Hippeau (NYC fintech bias)

### Afternoon — submit to AI infra directories

- Hugging Face Spaces (orallexa-ui-as-Space)
- Latent Space "Picks & Shovels" newsletter pitch
- AINews (Smol AI)
- Machine Learning Mastery (more academic)

---

## Decision gate — Day 7 (2026-05-20)

| Signal | Good | Bad |
|---|---|---|
| GitHub stars (7d delta) | > 100 | < 30 |
| HN score on submit day | > 50 points | < 10 |
| Leaderboard pageviews | > 1k | < 200 |
| `decision_log.json` rows after Alpaca pilot starts | > 30 | < 10 |
| VC reply rate (outreach) | > 15% | < 5% |
| GH issues filed (real engagement) | 5+ engaged threads | crickets |

**If good** → proceed to YC W26 application or seed round outreach with traction
**If bad** → not necessarily a kill — quant projects build slowly. Re-eval at Day 30 with cleaner alpha story.

---

## Where things live (bookmarks)

- Live demo: https://orallexa-ui.vercel.app
- Leaderboard: https://orallexa-ui.vercel.app/leaderboard
- Source: https://github.com/alex-jb/orallexa-ai-trading-agent
- Multi-modal lift cron: https://github.com/alex-jb/orallexa-ai-trading-agent/actions/workflows/multimodal-lift.yml
- DSPy compile cron: https://github.com/alex-jb/orallexa-ai-trading-agent/actions/workflows/dspy-compile.yml (new this commit)
- Pilot logs: `~/Desktop/orallexa-ai-trading-agent/logs/pilot.log`
- Funnel briefs: `~/.funnel_analytics/briefs/`

---

_Generated 2026-05-07. Update in place as you learn._
