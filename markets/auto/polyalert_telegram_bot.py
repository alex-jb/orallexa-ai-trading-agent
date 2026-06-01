#!/usr/bin/env python3
"""polyalert_telegram_bot.py — PolyAlert Phase 1 Telegram notifier.

Runs daily at NY 10:00 ET via launchd. Reads polymarket_decide.py output,
filters to user-tier-allowed events, pushes each READY/strong-WATCH
verdict to subscribed Telegram chat IDs.

Subscriber list in rules.json (`subscribers` section). For MVP, we
hardcode the maintainer (Alex) as the sole subscriber. Phase 2 adds
Supabase-backed user table + Stripe-gated tier check.

Cost: $0 (Telegram bot API is free).
Schedule: launchd ~/Library/LaunchAgents/com.orallexa.polyalert-bot.plist
"""
from __future__ import annotations

import json
import os
import re
import sys
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
RULES_PATH = HOME / ".orallexa" / "markets" / "rules.json"
DECIDE_SCRIPT = HOME / ".orallexa" / "markets" / "scripts" / "polymarket_decide.py"


def load_telegram_token() -> str:
    """Pull TELEGRAM_BOT_TOKEN from env or ~/.zshrc (matches daily-brief.sh)."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if tok:
        return tok
    zshrc = HOME / ".zshrc"
    if zshrc.exists():
        try:
            for line in zshrc.read_text().splitlines():
                m = re.match(
                    r'^export\s+TELEGRAM_BOT_TOKEN\s*=\s*"?([^"\s]+)"?',
                    line.strip(),
                )
                if m:
                    return m.group(1)
        except Exception:
            pass
    return ""


def load_subscribers() -> list[dict]:
    """Read subscribers from rules.json. Each is {chat_id, tier, email}."""
    if not RULES_PATH.exists():
        return []
    try:
        rules = json.loads(RULES_PATH.read_text())
        subs = rules.get("subscribers", [])
        return [s for s in subs if "chat_id" in s and "tier" in s]
    except Exception as exc:
        print(f"[polyalert] rules.json load failed: {exc!r}", file=sys.stderr)
        return []


def fetch_decisions() -> list[dict]:
    """Run polymarket_decide.py --json to get today's verdicts."""
    if not DECIDE_SCRIPT.exists():
        print(f"[polyalert] {DECIDE_SCRIPT} missing", file=sys.stderr)
        return []
    try:
        out = subprocess.check_output(
            ["/usr/bin/python3", str(DECIDE_SCRIPT), "--json"],
            stderr=subprocess.DEVNULL,
            timeout=120,
        ).decode()
        return json.loads(out)
    except Exception as exc:
        print(f"[polyalert] fetch_decisions failed: {exc!r}", file=sys.stderr)
        return []


def event_tier(slug: str, watchlist: list[dict]) -> str:
    """Look up the tier required to see this event."""
    for e in watchlist:
        if e.get("friendly") == slug or e.get("slug") == slug:
            return e.get("tier", "pro")
    return "pro"


def tier_can_see(user_tier: str, event_tier_val: str) -> bool:
    """free < starter < pro hierarchy."""
    order = {"free": 0, "starter": 1, "pro": 2}
    return order.get(user_tier, 0) >= order.get(event_tier_val, 99)


def format_alert(decision: dict) -> str:
    """Render a decision dict into a concise Telegram-friendly message."""
    verdict = decision.get("verdict", "?")
    question = decision.get("question", "?")[:120]
    delta = decision.get("delta")
    market_p = decision.get("market_p")
    our_p = decision.get("our_p")

    lines = [f"<b>{verdict}</b>", "", f"<i>{question}</i>", ""]

    if isinstance(market_p, (int, float)) and isinstance(our_p, (int, float)):
        delta_str = f"+{delta*100:.1f}%" if isinstance(delta, (int, float)) and delta > 0 else f"{delta*100:.1f}%" if isinstance(delta, (int, float)) else "?"
        lines.append(
            f"📊 Market: <b>{market_p:.3f}</b> · "
            f"Ours: <b>{our_p:.3f}</b> · Δ <b>{delta_str}</b>"
        )

    persistence = decision.get("persistence_days")
    if persistence:
        lines.append(f"⏱ Persistence: <b>{persistence} days</b>")

    if verdict.startswith("🟢") and "action" in decision:
        a = decision["action"]
        lines.append("")
        lines.append("<b>Buy plan</b>:")
        lines.append(
            f"  · ${a['usdc']} USDC YES @ ≤ ${a['entry_price_max']:.3f}"
        )
        lines.append(f"  · ~{a['yes_shares']:.0f} shares")
        lines.append(f"  · 🟢 TP: ${a['take_profit_price']:.3f}")
        lines.append(f"  · 🔴 SL: ${a['stop_loss_price']:.3f}")
        lines.append(
            f"  · ✅ Max +${a['max_profit_if_yes']:.2f}  "
            f"❌ Max -${a['max_loss_if_no']:.2f}"
        )

    lines.append("")
    lines.append(f"<a href='https://polymarket.com'>Trade on Polymarket</a>")
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str | int, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "polyalert/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return bool(data.get("ok"))
    except Exception as exc:
        print(f"[polyalert] telegram send failed: {exc!r}", file=sys.stderr)
        return False


def main() -> int:
    token = load_telegram_token()
    if not token:
        print(
            "[polyalert] TELEGRAM_BOT_TOKEN not set. Get one from "
            "@BotFather on Telegram, then export in ~/.zshrc:\n"
            '  export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."',
            file=sys.stderr,
        )
        return 1

    subs = load_subscribers()
    if not subs:
        print(
            "[polyalert] no subscribers. Add to rules.json:\n"
            '  "subscribers": [{"chat_id": "12345", "tier": "pro", '
            '"email": "you@example.com"}]\n'
            "  Get chat_id by sending /start to your bot, then visit "
            "https://api.telegram.org/bot$TOKEN/getUpdates",
            file=sys.stderr,
        )
        return 1

    # Load watchlist for tier lookup
    rules = json.loads(RULES_PATH.read_text()) if RULES_PATH.exists() else {}
    watchlist = rules.get("watchlist", [])

    decisions = fetch_decisions()
    # Only alert on READY (🟢) and high-Δ WATCH (🟡 with avg_delta_window > 0.08)
    alertable = []
    for d in decisions:
        v = d.get("verdict", "")
        if v.startswith("🟢"):
            alertable.append(d)
        elif v.startswith("🟡"):
            avg_d = d.get("avg_delta_window")
            if isinstance(avg_d, (int, float)) and avg_d >= 0.08:
                alertable.append(d)

    if not alertable:
        print("[polyalert] no alertable verdicts today")
        return 0

    today = datetime.now(timezone.utc).date().isoformat()
    sent_count = 0

    for sub in subs:
        chat_id = sub["chat_id"]
        user_tier = sub.get("tier", "free")
        # Header
        send_telegram(
            token,
            chat_id,
            f"<b>📊 PolyAlert — {today}</b>\n\n"
            f"{len(alertable)} flagged events you can see (tier: {user_tier})",
        )
        # Per-event message
        for d in alertable:
            ev_tier = event_tier(d.get("slug", ""), watchlist)
            if not tier_can_see(user_tier, ev_tier):
                continue
            text = format_alert(d)
            if send_telegram(token, chat_id, text):
                sent_count += 1

    print(f"[polyalert] sent {sent_count} message(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
