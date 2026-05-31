#!/usr/bin/env python3
"""polymarket_decide.py — per-event entry decision + concrete buy instructions.

Reads polymarket_history.jsonl, groups by event, and for each event outputs:
  - VERDICT: 🟢 READY (buy now) / 🟡 WATCH (signal forming) / ⚪ SKIP (no edge)
  - 具体操作: 多少 USDC / 买 YES 还是 NO / 价格区间 / 止盈 / 止损 / 持有多久

Decision rules (in plain English):
  READY = persistent mispricing for ≥3 consecutive days
        + |our_p - market_p| > 0.10 (10% not 5% — 5% threshold too noisy)
        + average conviction ≥ medium across the persistence window
        + volume_24hr ≥ $1000 (basic liquidity)
        + resolution > 14 days away (enough time for thesis to play)

  WATCH = signal forming (1-2 days flagged OR Δ between 5-10% OR low volume)

  SKIP = no edge OR our model errored OR event resolves too soon

Sizing: Kelly-ish but conservative. fractional = 0.20 × full Kelly, capped
at $100 per event (Phase 1 budget = $300 total spread across 2-3 events).

This is the missing "what do I do TODAY" layer between raw probability
estimates and Alex actually opening MetaMask.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
HISTORY = HOME / ".orallexa" / "markets" / "polymarket_history.jsonl"
SESSIONS_DIR = HOME / ".orallexa" / "markets" / "sessions"
REPORTS_DIR = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "polymarket-decisions"

# Decision thresholds — calibrated for $300 Phase 1 budget across 2-3 events
PERSISTENCE_MIN_DAYS = 3
MISPRICING_STRONG = 0.10
MISPRICING_WEAK = 0.05
VOLUME_MIN = 1000.0
DAYS_TO_RESOLUTION_MIN = 14
PHASE_1_BUDGET_TOTAL = 300.0
MAX_PER_EVENT = 100.0  # Phase 1 ceiling
MIN_POSITION = 20.0    # below this, transaction friction kills the trade
KELLY_FRACTION = 0.20


def load_history() -> dict[str, list[dict]]:
    """Returns {event_slug: [day1_entry, day2_entry, ...]} sorted by date."""
    if not HISTORY.exists():
        return {}
    by_event: dict[str, list[dict]] = defaultdict(list)
    for line in HISTORY.read_text().splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        key = d.get("friendly") or d.get("event_slug") or d.get("slug")
        if not key:
            continue
        by_event[key].append(d)
    for k in by_event:
        by_event[k].sort(key=lambda x: x.get("date", ""))
    return dict(by_event)


def days_until(end_date_iso: str | None) -> int | None:
    if not end_date_iso:
        return None
    try:
        end = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
    except Exception:
        return None
    now = datetime.now(timezone.utc)
    return (end.date() - now.date()).days


def kelly_size(our_p: float, market_p: float, budget_per_event: float) -> float:
    """Conservative fractional Kelly for binary YES.
    Returns USDC to bet on YES.

    f* = (b·p - q) / b where b = (1-market) / market is payoff ratio.
    Then fraction × KELLY_FRACTION × budget.
    """
    if market_p <= 0 or market_p >= 1 or our_p <= 0 or our_p >= 1:
        return 0
    # If our p < market p, we'd buy NO instead — but for simplicity, only
    # flag those cases and return 0 (Alex can do NO manually if needed)
    if our_p <= market_p:
        return 0
    b = (1 - market_p) / market_p
    p = our_p
    q = 1 - p
    f_star = (b * p - q) / b
    if f_star <= 0:
        return 0
    sized = KELLY_FRACTION * f_star * budget_per_event
    return min(sized, MAX_PER_EVENT)


def decide_event(slug: str, entries: list[dict]) -> dict:
    """Return decision dict for one event."""
    if not entries:
        return {"verdict": "SKIP", "reason": "no data", "slug": slug}
    last = entries[-1]
    question = last.get("question") or last.get("event_title") or slug
    market_p = last.get("yes_price")
    our_p = last.get("our_p_yes")
    delta = last.get("mispricing_delta")
    vol = last.get("volume24hr") or 0.0
    end = last.get("end_date")
    days_left = days_until(end)
    conviction = last.get("our_conviction", "")

    # Count consecutive days flag=YES (from most recent backwards)
    persistence = 0
    deltas_window = []
    convictions_window = []
    for e in reversed(entries):
        if e.get("mispricing_flag") == "YES":
            persistence += 1
            if isinstance(e.get("mispricing_delta"), (int, float)):
                deltas_window.append(e["mispricing_delta"])
            if e.get("our_conviction"):
                convictions_window.append(e["our_conviction"])
        else:
            break

    avg_delta = sum(deltas_window) / len(deltas_window) if deltas_window else 0
    conv_score = sum({"high": 3, "medium": 2, "low": 1}.get(c, 0)
                     for c in convictions_window)
    avg_conv = conv_score / max(len(convictions_window), 1)

    base = {
        "slug": slug,
        "question": question,
        "market_p": market_p,
        "our_p": our_p,
        "delta": delta,
        "avg_delta_window": round(avg_delta, 3) if deltas_window else None,
        "persistence_days": persistence,
        "volume24h": vol,
        "days_to_resolution": days_left,
        "conviction": conviction,
        "avg_conviction": round(avg_conv, 2) if convictions_window else 0,
    }

    # ─── SKIP cases ───────────────────────────────────────────────
    if market_p is None or our_p is None:
        base.update({"verdict": "⚪ SKIP", "reason": "数据缺失(可能 polymarket 拿不到 market price 或 Claude 估计失败)"})
        return base
    if days_left is not None and days_left < 7:
        base.update({"verdict": "⚪ SKIP", "reason": f"事件还有 {days_left} 天就 resolve,时间不够让 thesis 走"})
        return base
    if delta is not None and abs(delta) < MISPRICING_WEAK:
        base.update({"verdict": "⚪ SKIP", "reason": f"市场跟我们估计差距 {delta:+.3f},小于 5% 阈值,没有 edge"})
        return base
    if our_p <= market_p:
        base.update({"verdict": "⚪ SKIP", "reason": f"我们 {our_p:.2f} ≤ 市场 {market_p:.2f},按 YES 方向无 edge(NO 方向需手动评估)"})
        return base

    # ─── READY: all conditions met ────────────────────────────────
    persistent = persistence >= PERSISTENCE_MIN_DAYS
    strong_edge = (avg_delta if avg_delta else (delta or 0)) >= MISPRICING_STRONG
    decent_conv = avg_conv >= 2.0  # avg ≥ medium
    enough_volume = vol >= VOLUME_MIN
    enough_time = days_left is None or days_left >= DAYS_TO_RESOLUTION_MIN

    if persistent and strong_edge and decent_conv and enough_volume and enough_time:
        # Kelly on full bankroll; clamp to [MIN, MAX]
        raw_size = kelly_size(our_p, market_p, PHASE_1_BUDGET_TOTAL)
        if raw_size <= 0:
            base.update({"verdict": "⚪ SKIP", "reason": "Kelly 算出 0(可能 our_p 比 market_p 低)"})
            return base
        # Floor: $20 minimum (transaction friction below this kills the trade)
        # Cap: $100 per event (Phase 1 ceiling)
        size_usdc = max(MIN_POSITION, min(MAX_PER_EVENT, raw_size))
        # Estimated YES share count
        yes_shares = size_usdc / market_p if market_p > 0 else 0
        # Profit if event resolves YES (1.0): shares * (1 - entry)
        max_profit = yes_shares * (1 - market_p)
        # Loss if resolves NO: full position
        max_loss = size_usdc
        # Take-profit: market price moves halfway from current to our estimate
        take_profit_price = market_p + (our_p - market_p) * 0.5
        # Stop-loss: -30% on entry price
        stop_loss_price = market_p * 0.70

        base.update({
            "verdict": "🟢 READY",
            "reason": (
                f"已连续 {persistence} 天 mispricing flagged,"
                f"平均差距 +{avg_delta*100:.1f}%,"
                f"avg conviction {avg_conv:.1f}/3,"
                f"流动性 ${vol:,.0f},"
                f"距 resolution {days_left or '?'} 天"
            ),
            "action": {
                "side": "YES",
                "usdc": round(size_usdc, 2),
                "entry_price_max": round(market_p * 1.05, 4),  # don't chase >5% above current
                "yes_shares": round(yes_shares, 0),
                "take_profit_price": round(take_profit_price, 3),
                "stop_loss_price": round(stop_loss_price, 3),
                "max_profit_if_yes": round(max_profit, 2),
                "max_loss_if_no": round(max_loss, 2),
                "hold_until": f"event resolves OR price hits TP/SL (estimated {days_left} days max)",
            },
        })
        return base

    # ─── WATCH: signal forming but not yet ────────────────────────
    weak_edge = MISPRICING_WEAK <= abs(delta or 0) < MISPRICING_STRONG
    forming_persistence = 1 <= persistence < PERSISTENCE_MIN_DAYS

    reasons = []
    if not persistent:
        reasons.append(f"信号才连续 {persistence} 天(需 ≥{PERSISTENCE_MIN_DAYS})")
    if not strong_edge:
        reasons.append(f"差距 {avg_delta*100:.1f}% 偏弱(需 ≥10%)")
    if not decent_conv:
        reasons.append(f"Claude 把握度均值 {avg_conv:.1f}/3 偏低")
    if not enough_volume:
        reasons.append(f"流动性 ${vol:,.0f} 太薄(需 ≥${VOLUME_MIN:,.0f})")
    if not enough_time:
        reasons.append(f"resolution 太近({days_left} 天)")

    base.update({
        "verdict": "🟡 WATCH",
        "reason": "信号在形成但不够强:" + " · ".join(reasons),
    })
    return base


def render_markdown(decisions: list[dict]) -> str:
    """Output for human (Alex) reading. Plain Chinese, no jargon."""
    today = datetime.now(timezone.utc).date().isoformat()
    lines = [f"# Polymarket 入场决策 — {today}", ""]

    if not decisions:
        lines.append("_没有事件数据。polymarket_daily 还没跑出第一份 history。_")
        return "\n".join(lines)

    # Group by verdict
    ready = [d for d in decisions if d["verdict"].startswith("🟢")]
    watch = [d for d in decisions if d["verdict"].startswith("🟡")]
    skip = [d for d in decisions if d["verdict"].startswith("⚪")]

    lines.append("## 🎯 今天的 verdict")
    lines.append("")
    lines.append(f"- 🟢 **可以买**: {len(ready)} 个事件")
    lines.append(f"- 🟡 **观察中**: {len(watch)} 个事件")
    lines.append(f"- ⚪ **跳过**: {len(skip)} 个事件")
    lines.append("")

    if ready:
        lines.append("## 🟢 立刻可以买的事件")
        lines.append("")
        for i, d in enumerate(ready, 1):
            a = d["action"]
            lines.append(f"### {i}. {d['question']}")
            lines.append("")
            lines.append(f"**为什么**: {d['reason']}")
            lines.append("")
            lines.append("**怎么买**:")
            lines.append(f"1. 打开 polymarket.com,连 MetaMask 钱包")
            lines.append(f"2. 搜事件:`{d['slug']}`")
            lines.append(f"3. 点 **YES** 那一侧")
            lines.append(f"4. 买 **${a['usdc']} USDC**(约 {a['yes_shares']:.0f} 股 YES @ ${a['entry_price_max']:.3f} 上限)")
            lines.append(f"5. **不要追**:如果市场价已经超过 ${a['entry_price_max']:.3f},不买,改 watch")
            lines.append("")
            lines.append("**什么时候卖**:")
            lines.append(f"- 🟢 take-profit: 市场价涨到 **${a['take_profit_price']:.3f}** → 卖出 50% 锁利")
            lines.append(f"- 🔴 stop-loss: 市场价跌到 **${a['stop_loss_price']:.3f}** → 全部卖,认输")
            lines.append(f"- ⏰ 事件 resolve: 等到 {a['hold_until']}")
            lines.append("")
            lines.append("**P&L 上下限**:")
            lines.append(f"- ✅ 如果 YES → 最大 +${a['max_profit_if_yes']:.2f}")
            lines.append(f"- ❌ 如果 NO → 最大 -${a['max_loss_if_no']:.2f}")
            lines.append("")

    if watch:
        lines.append("## 🟡 观察中(信号在形成但不够强)")
        lines.append("")
        lines.append("| 事件 | 市场 | 我们 | 差距 | 连续天 | 流动性 | resolve | 原因 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for d in watch:
            mkt = f"{d['market_p']:.3f}" if isinstance(d.get('market_p'), (int, float)) else "?"
            ours = f"{d['our_p']:.3f}" if isinstance(d.get('our_p'), (int, float)) else "?"
            dlt = f"{d['delta']:+.3f}" if isinstance(d.get('delta'), (int, float)) else "?"
            vol = f"${d['volume24h']:,.0f}"
            days = d.get('days_to_resolution', '?')
            lines.append(f"| {d['question'][:50]} | {mkt} | {ours} | {dlt} | {d['persistence_days']} | {vol} | {days}d | {d['reason']} |")
        lines.append("")

    if skip:
        lines.append("## ⚪ 跳过(没 edge 或风险高)")
        lines.append("")
        for d in skip:
            lines.append(f"- **{d['question'][:60]}**: {d['reason']}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 💡 这套规则在做什么(一句话解释)")
    lines.append("")
    lines.append(
        "每天比较「Claude 估的事件概率」vs「Polymarket 市场价」。"
        "**只在 3 个条件同时满足时建议买**:"
        "(1) **差距 > 10%** 不是 1-2 天的噪声;"
        "(2) **流动性够**,你能进得了出得来;"
        "(3) **resolution 还远**,thesis 有时间走。"
        "满足就给具体 USDC 数 + 止盈止损价 + 最大 P&L。"
        "不满足就 WATCH(攒数据)或 SKIP(没 edge)。"
    )
    lines.append("")
    lines.append("**Phase 1 总预算**: $300 across 2-3 events,单事件不超过 $100。")
    lines.append("")

    return "\n".join(lines)


def load_yesterday_session() -> list[dict] | None:
    """TradingView MCP session_get pattern — read yesterday's decisions for diff."""
    yesterday_files = sorted(SESSIONS_DIR.glob("*.json"))
    if not yesterday_files:
        return None
    # Skip if the latest is today (we want the prior one)
    today_str = datetime.now(timezone.utc).date().isoformat()
    for f in reversed(yesterday_files):
        if today_str not in f.name:
            try:
                return json.loads(f.read_text())
            except Exception:
                continue
    return None


def save_session(decisions: list[dict]) -> None:
    """TradingView MCP session_save pattern."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    out = SESSIONS_DIR / f"{today}.json"
    out.write_text(json.dumps(decisions, ensure_ascii=False, indent=2, default=str))


def diff_with_yesterday(today: list[dict], yesterday: list[dict] | None) -> list[str]:
    """Plain-Chinese day-over-day verdict changes. Returns markdown bullets."""
    if not yesterday:
        return []
    yest_by_slug = {d["slug"]: d for d in yesterday if d.get("slug")}
    changes = []
    for d in today:
        yest = yest_by_slug.get(d["slug"])
        if not yest:
            changes.append(f"🆕 **{d['question'][:50]}**: 新事件,verdict = {d['verdict']}")
            continue
        if d["verdict"] != yest.get("verdict"):
            changes.append(
                f"↻ **{d['question'][:50]}**: "
                f"昨天 {yest['verdict']} → 今天 {d['verdict']}"
            )
    for slug, yest_d in yest_by_slug.items():
        if not any(d.get("slug") == slug for d in today):
            changes.append(f"⏏️ **{yest_d['question'][:50]}**: 今天 polymarket 没拿到数据(可能 resolve 或 slug 变了)")
    return changes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true",
                   help="Output JSON instead of markdown (for piping to email script)")
    p.add_argument("--save-session", action="store_true",
                   help="Save today's decisions to sessions/ for future diff")
    p.add_argument("--save-report", action="store_true",
                   help="Persist markdown report to alex-brain")
    args = p.parse_args()

    history = load_history()
    decisions = [decide_event(slug, entries) for slug, entries in history.items()]

    if args.json:
        print(json.dumps(decisions, ensure_ascii=False, indent=2, default=str))
        return

    # Day-over-day diff (TradingView MCP borrowed pattern)
    yesterday = load_yesterday_session()
    diff_lines = diff_with_yesterday(decisions, yesterday)

    markdown = render_markdown(decisions)
    if diff_lines:
        markdown = markdown.replace(
            "## 🎯 今天的 verdict",
            "## 📈 昨天 → 今天 verdict 变化\n\n" + "\n".join(f"- {x}" for x in diff_lines)
            + "\n\n## 🎯 今天的 verdict",
            1,
        )

    if args.save_session:
        save_session(decisions)
    if args.save_report:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).date().isoformat()
        (REPORTS_DIR / f"{today}.md").write_text(markdown, encoding="utf-8")
        print(f"[polymarket-decide] wrote {REPORTS_DIR}/{today}.md", file=sys.stderr)

    print(markdown)


if __name__ == "__main__":
    main()
