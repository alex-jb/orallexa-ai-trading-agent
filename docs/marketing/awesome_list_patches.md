# Awesome-list submission patches — Orallexa

Ready-to-PR snippets for each curated list. Read each list's
CONTRIBUTING.md before submitting; tone and entry format vary.

---

## 1. caramaschiHG/awesome-ai-agents-2026

**Repo:** https://github.com/caramaschiHG/awesome-ai-agents-2026
**Section:** Trading & Finance Agents (or create if missing)

```markdown
- [Orallexa](https://github.com/alex-jb/orallexa-ai-trading-agent) — Self-tuning multi-agent trading system. 8-source signal fusion (Polymarket + Kalshi + 10 ML models including Kronos), Bull/Bear/Judge debate on Claude Opus 4.7, Portfolio Manager gate before Alpaca orders, DSPy Phase A scaffold. MIT.
```

PR title: `add: Orallexa — multi-agent trading system w/ adaptive signal fusion`

---

## 2. georgezouq/awesome-ai-in-finance

**Repo:** https://github.com/georgezouq/awesome-ai-in-finance
**Section:** Trading Strategies → LLMs / Multi-Agent

```markdown
- [Orallexa](https://github.com/alex-jb/orallexa-ai-trading-agent) — Multi-agent trading agent. 8-source signal fusion across technical, ML (10 models incl. Kronos foundation model), news sentiment, options flow, institutional, social, earnings/PEAD, prediction markets (Polymarket + Kalshi). Adaptive per-source weights from a rolling accuracy ledger. Bull/Bear/Judge debate (Claude Opus 4.7 on Judge). Portfolio Manager gate before Alpaca orders. MIT.
```

PR title: `Add Orallexa — adaptive multi-agent trading agent with 8-source fusion`

---

## 3. VoltAgent/awesome-agent-skills

**Repo:** https://github.com/VoltAgent/awesome-agent-skills
**Section:** Domain skills → Finance / Trading

```markdown
- **Orallexa Trading Agent Skills** — [github.com/alex-jb/orallexa-ai-trading-agent](https://github.com/alex-jb/orallexa-ai-trading-agent) — Production-grade trading agent with embeddable skills: Polymarket prediction-market reader, multi-platform news aggregator, Kronos foundation model wrapper, regime-aware role selector (DyTopo), CORAL shared memory aggregator. Each is a self-contained Python module with a focused public API.
```

PR title: `add: Orallexa trading agent skill bundle (Polymarket / Kronos / regime / memory)`

---

## 4. awesome-llm-apps-collection (search for current top match)

There are several "awesome LLM apps" lists; submit to the largest one:
- shashankvemuri/Finance — broad finance Python tools

```markdown
- [Orallexa](https://github.com/alex-jb/orallexa-ai-trading-agent) — Multi-agent AI trading system with adaptive signal fusion across 8 sources, Claude Opus 4.7 Bull/Bear/Judge debate, and Polymarket + Kalshi prediction-market integration. Live demo at orallexa-ui.vercel.app.
```

---

## 5. mahseema/awesome-ai-tools

**Section:** Finance & Trading

```markdown
- [Orallexa](https://github.com/alex-jb/orallexa-ai-trading-agent) (MIT) — Open-source multi-agent trading agent. 10 ML models (RF, XGB, EMAformer, Chronos-2, MOIRAI-2, DDPM, GNN, RL-PPO, LR, **Kronos**), 8-source signal fusion, dynamic per-source weights, Portfolio Manager risk gate, Anthropic + OpenAI + Gemini providers, Next.js dashboard with bilingual EN/ZH UI.
```

---

## 6. duanyytop/agents-radar (weekly trending)

**Submit issue/PR to weekly digest** — they curate top movers.

Subject: `Suggest for next radar: alex-jb/orallexa-ai-trading-agent`

Body:
> Open-source multi-agent trading agent that landed ~50 commits in 1 week
> covering 8-source signal fusion (Polymarket + Kalshi + Kronos + 7 more),
> adaptive per-source weights from accuracy ledger, Bull/Bear/Judge debate
> on Claude Opus 4.7, Portfolio Manager gate. Multi-provider LLM
> abstraction with Anthropic + OpenAI + Gemini all real.
>
> Repo: https://github.com/alex-jb/orallexa-ai-trading-agent
> Demo: https://orallexa-ui.vercel.app

---

## Submission checklist (per list)

For each PR / issue:

- [ ] Read the list's CONTRIBUTING.md and entry-format example
- [ ] Match the tone of existing entries (some are terse, some descriptive)
- [ ] Verify your repo passes the list's quality bar (license,
      maintenance evidence, tests, README quality)
- [ ] Use the section that gets the most traffic (top of list, not
      "Recently Added" if avoidable)
- [ ] Don't submit duplicate PRs across forks
- [ ] If rejected, ask why and resubmit once fixed

## Order of operations

1. **Day 0**: Update repo description + topics (done — see commit
   that updated GitHub About). Add demo GIF to README hero.
2. **Day 1**: Submit to caramaschiHG + georgezouq (highest signal-to-noise)
3. **Day 2**: Post HN (Tue/Wed AM PT)
4. **Day 3**: Post r/algotrading + r/quant + r/ClaudeAI (staggered, not
   simultaneous — looks spammy)
5. **Day 4**: Post X thread, quote-tweet relevant accounts
6. **Day 5+**: Submit to remaining awesome lists; respond to issues from
   week 1 traffic
