#!/usr/bin/env python3
"""markets_weekly_retro_email.py — Sunday 17:00 ET cron, emails Alex.

Composes a one-page markets-status email by:
  1. Running portfolio_paper.py sim over 7 + 14 day windows
  2. Reading last 7 polymarket_history.jsonl entries (mispricing flags)
  3. Counting recent BUY/SELL/WAIT decisions
  4. Comparing to last week's email (P&L delta)

Sends via Resend using same pattern as daily-brief.

EMAIL_TO + EMAIL_FROM + RESEND_API_KEY come from env (sourced from
~/.zshrc by the launchd wrapper).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter

HOME = Path.home()
POLYMARKET_HISTORY = HOME / ".orallexa" / "markets" / "polymarket_history.jsonl"
DECISION_LOG = HOME / "Desktop" / "orallexa-ai-trading-agent" / "memory_data" / "decision_log.json"
OUT_DIR = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "markets-weekly"
PORTFOLIO_PAPER = HOME / ".orallexa" / "markets" / "scripts" / "portfolio_paper.py"


def _load_zsh_key(name: str) -> str:
    env = os.environ.get(name, "").strip()
    if env:
        return env
    zshrc = HOME / ".zshrc"
    if not zshrc.exists():
        return ""
    try:
        for line in zshrc.read_text().splitlines():
            m = re.match(rf'^export\s+{name}\s*=\s*"?([^"\s]+)"?', line.strip())
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


def run_portfolio_sim(since_days: int) -> dict:
    """Invoke portfolio_paper.py --compare and parse the 4-scenario output."""
    cmd = ["/usr/bin/python3", str(PORTFOLIO_PAPER),
           "--since-days", str(since_days), "--compare"]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=600).decode()
    except Exception as exc:
        return {"error": str(exc)}
    rows = {}
    # Lines like "baseline (fixed stops, no cap): P&L $-873.23 win 22.7% stops 78/128 maxDD 20.3% blocked 0"
    for line in out.splitlines():
        m = re.match(r"^([^:]+):\s+P&L \$(-?[\d,.]+)\s+win\s+([\d.]+)%\s+stops\s+(\d+)/(\d+)\s+maxDD\s+([\d.]+)%\s+blocked\s+(\d+)", line)
        if m:
            label, pnl, win, stops, total, dd, blocked = m.groups()
            rows[label.strip()] = {
                "pnl": float(pnl.replace(",", "")),
                "win_pct": float(win),
                "stops": int(stops),
                "total": int(total),
                "dd_pct": float(dd),
                "blocked": int(blocked),
            }
    return rows


def recent_polymarket(n: int = 7) -> list[dict]:
    if not POLYMARKET_HISTORY.exists():
        return []
    lines = POLYMARKET_HISTORY.read_text().splitlines()[-n:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def decision_counts(window_days: int) -> dict:
    if not DECISION_LOG.exists():
        return {}
    try:
        data = json.loads(DECISION_LOG.read_text())
    except Exception:
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    recent = []
    for d in data:
        ts = d.get("timestamp")
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if t < cutoff:
            continue
        recent.append(d)
    return Counter(x.get("decision") for x in recent)


def fetch_polymarket_decisions_markdown() -> str:
    """Invoke polymarket_decide.py and return its markdown output."""
    decide_script = HOME / ".orallexa" / "markets" / "scripts" / "polymarket_decide.py"
    if not decide_script.exists():
        return ""
    try:
        out = subprocess.check_output(
            ["/usr/bin/python3", str(decide_script),
             "--save-session", "--save-report"],
            stderr=subprocess.DEVNULL, timeout=120
        ).decode()
        return out
    except Exception as exc:
        return f"_polymarket_decide invocation failed: {exc!r}_"


def render_email(week7: dict, week14: dict, poly: list[dict],
                 dec_counts: dict) -> tuple[str, str, str]:
    """Returns (subject, text_body, html_body). Chinese-first verdicts at top."""
    today = datetime.now(timezone.utc).date().isoformat()

    # ─── Compute stock verdict for subject line ───────────────────
    stock_verdict_short = "—"
    atr14 = week14.get("+ATR stops only", {}) if isinstance(week14, dict) else {}
    if atr14:
        pnl = atr14.get("pnl", 0)
        if pnl > 1000:
            stock_verdict_short = "✅ ENTER"
        elif pnl > -500:
            stock_verdict_short = "⏸ WAIT"
        else:
            stock_verdict_short = "❌ STOP"

    subject = f"📊 {today} — Stock: {stock_verdict_short} | Polymarket 决策见正文"

    # ─── compose markdown / text body ─────────────────────────────
    lines = [f"# Markets 周报 — {today}", ""]

    # ── PART 1: Stock 决策 (verdict-first) ─────────────────────
    lines.append("## 📈 股票:能不能用真钱进场?")
    lines.append("")
    if "error" in week14 or not week14:
        lines.append("⚠️ 14 天 portfolio 模拟失败,先 debug 再决策")
    elif atr14:
        pnl = atr14.get("pnl", 0)
        win = atr14.get("win_pct", 0)
        stops = atr14.get("stops", 0)
        total = atr14.get("total", 0)
        baseline = week14.get("baseline (fixed stops, no cap)", {})
        baseline_pnl = baseline.get("pnl", 0)

        if pnl > 1000:
            verdict_line = "✅ **建议入场** $300 BKSY 单仓"
            why = f"过去 14 天系统用 ATR 止损跑 paper +${pnl:,.0f}({win:.0f}% win),超过 backtest 一半门槛"
        elif pnl > -500:
            verdict_line = "⏸ **再等等**(信号不够强)"
            why = f"过去 14 天 paper ${pnl:+,.0f}({win:.0f}% win),还不够 +$1000 入场门槛。再观察 1 周"
        else:
            verdict_line = "❌ **停**(backtest 没 generalize)"
            why = f"过去 14 天 paper ${pnl:+,.0f},比 backtest +$5,950 差太多。entry rule 可能没 edge,debug 再说"
        lines.append(f"### {verdict_line}")
        lines.append("")
        lines.append(f"**为什么**: {why}")
        lines.append(f"_对照:如果还用老版 5% 固定止损,过去 14 天会是 ${baseline_pnl:+,.0f}({baseline.get('win_pct', 0):.0f}% win),ATR 版救了 ${pnl - baseline_pnl:+,.0f}_")
        lines.append(f"_统计:{stops}/{total} 笔被止损平仓,maxDD {atr14.get('dd_pct', 0):.1f}%_")
        lines.append("")
        if pnl > 1000:
            lines.append("**怎么买**:")
            lines.append("1. Robinhood 入金 ≥$300")
            lines.append("2. NY 9:31 开盘 + 5 分钟看 BKSY 价")
            lines.append("3. 买 7 股 BKSY,Limit 单(吃 ask + $0.05)")
            lines.append("4. 立刻挂 stop-loss: entry × 0.90, GTC")
            lines.append("5. 5 个交易日满或 stop 触发 → 平仓")
            lines.append("")
    else:
        lines.append("⚠️ ATR 场景没数据(过去 14 天 0 BUY/SELL 决策)")
    lines.append("")

    # ── PART 2: Polymarket 决策 (从 decide.py 拉) ──────────────
    lines.append("---")
    lines.append("")
    decide_md = fetch_polymarket_decisions_markdown()
    if decide_md:
        # decide.py output already has "# Polymarket 入场决策" — keep it
        lines.append(decide_md.rstrip())
    else:
        lines.append("## 🎲 Polymarket")
        lines.append("_polymarket_decide 没产 output_")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📊 详细数据(可跳过)")
    lines.append("")
    lines.append("### Stock 14-day backtest 4-scenario 对比")
    lines.append("")
    if "error" in week14:
        lines.append(f"sim error: {week14.get('error')}")
    else:
        lines.append("| Scenario | P&L | Win | Stops | maxDD | Blocked |")
        lines.append("|---|---|---|---|---|---|")
        for label, r in week14.items():
            lines.append(f"| {label} | ${r['pnl']:+,.2f} | {r['win_pct']:.1f}% | {r['stops']}/{r['total']} | {r['dd_pct']:.1f}% | {r['blocked']} |")
    lines.append("")

    lines.append("## Polymarket — last 7 self-estimates")
    lines.append("")
    if not poly:
        lines.append("_no polymarket history yet_")
    else:
        lines.append("| Date | Event | Market | Ours | Δ | Flag |")
        lines.append("|---|---|---|---|---|---|")
        for e in poly:
            mkt = e.get("yes_price")
            ours = e.get("our_p_yes")
            d = e.get("mispricing_delta")
            flag = e.get("mispricing_flag") or ""
            flag_emoji = "🚨" if flag == "YES" else ("" if flag == "NO" else "?")
            mkt_str = f"{mkt:.3f}" if isinstance(mkt, (int, float)) else "?"
            ours_str = f"{ours:.3f}" if isinstance(ours, (int, float)) else "n/a"
            d_str = f"{d:+.3f}" if isinstance(d, (int, float)) else "?"
            lines.append(f"| {e.get('date', '?')} | {e.get('friendly', '?')} | {mkt_str} | {ours_str} | {d_str} | {flag_emoji} {flag} |")
    lines.append("")

    lines.append("## Decision volume (last 7 days)")
    lines.append("")
    if dec_counts:
        for k, v in sorted(dec_counts.items()):
            lines.append(f"- {k}: {v}")
    else:
        lines.append("_no decisions logged_")
    lines.append("")

    lines.append("---")
    lines.append("_Auto-sent by `markets_weekly_retro_email.py` Sunday 17:00 ET. Reply nothing — this is one-way info._")

    text_body = "\n".join(lines)

    # ─── compose simple HTML ──────────────────────────────────────
    html_lines = [f"<html><body style='font-family: -apple-system, sans-serif; max-width: 720px;'>"]
    in_table = False
    for line in lines:
        if line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("|"):
            # Build table rows
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(c.startswith("---") or not c for c in cells):
                continue  # separator
            if not in_table:
                html_lines.append("<table border='1' cellspacing='0' cellpadding='6' style='border-collapse: collapse;'>")
                in_table = True
            tag = "th" if (lines.index(line) > 0 and lines[lines.index(line) - 1].startswith("## ")) or "Date" in line or "Scenario" in line else "td"
            html_lines.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
        else:
            if in_table:
                html_lines.append("</table>")
                in_table = False
            if line.startswith("- "):
                html_lines.append(f"<li>{line[2:]}</li>")
            elif line == "":
                html_lines.append("<br>")
            else:
                html_lines.append(f"<p>{line}</p>")
    if in_table:
        html_lines.append("</table>")
    html_lines.append("</body></html>")
    html_body = "\n".join(html_lines)

    return subject, text_body, html_body


def send_email(subject: str, text_body: str, html_body: str) -> bool:
    api_key = _load_zsh_key("RESEND_API_KEY")
    if not api_key:
        print("[markets-retro] RESEND_API_KEY not set — printing instead", file=sys.stderr)
        print(text_body)
        return False

    email_from = _load_zsh_key("DAILY_BRIEF_EMAIL_FROM") or "Markets Retro <onboarding@resend.dev>"
    email_to = _load_zsh_key("DAILY_BRIEF_EMAIL_TO") or "xji1@mail.yu.edu"

    payload = json.dumps({
        "from": email_from,
        "to": [email_to],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "markets-weekly-retro/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"[markets-retro] sent: id={result.get('id', '?')} to={email_to}")
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        print(f"[markets-retro] Resend HTTP {exc.code}: {body}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"[markets-retro] send failed: {exc!r}", file=sys.stderr)
        return False


def main():
    print(f"[markets-retro] starting {datetime.now(timezone.utc).isoformat()}", file=sys.stderr)
    week7 = run_portfolio_sim(7)
    week14 = run_portfolio_sim(14)
    poly = recent_polymarket(7)
    dec = decision_counts(7)

    subject, text_body, html_body = render_email(week7, week14, poly, dec)

    # Persist to alex-brain
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"{datetime.now(timezone.utc).date().isoformat()}.md"
    out_file.write_text(text_body, encoding="utf-8")
    print(f"[markets-retro] wrote {out_file}", file=sys.stderr)

    sent = send_email(subject, text_body, html_body)
    sys.exit(0 if sent else 1)


if __name__ == "__main__":
    main()
