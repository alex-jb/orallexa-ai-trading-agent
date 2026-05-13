"""master-lens.py — apply the day's investor-master framework to top
3 movers in today's SpaceX brief.

Runs after spacex-daily.sh writes the brief. Picks the day's framework
(weekday-rotation: Mon=Buffett, Tue=Druckenmiller, Wed=Lynch, Thu=Soros,
Fri=Burry, Sat/Sun=Lynch repeat for weekend reading), loads its prompt
file from strategies/, asks Claude to apply the framework to today's
top 3 movers from the brief's ranking table, and APPENDS a §3.7
"今日大师视角" section to the brief markdown file.

Designed to fail gracefully — if anything goes wrong, brief is
unchanged. We never overwrite, only append.

Path:
  brief in:  ~/Desktop/Interview-Prep/Projects/alex-brain/research/spacex-daily/YYYY-MM-DD.md
  strategy:  ~/.orallexa/markets/strategies/{weekday-name}.md
  brain:     same brief file (in-place append)
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
STRATEGY_DIR = HOME / ".orallexa" / "markets" / "strategies"
BRIEF_DIR = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "spacex-daily"
PUBLIC_REPO_DIR = HOME / "Desktop" / "spacex-ipo-tracker" / "briefs"

WEEKDAY_STRATEGY = {
    0: "monday-buffett",
    1: "tuesday-druckenmiller",
    2: "wednesday-lynch",
    3: "thursday-soros",
    4: "friday-burry",
    5: "wednesday-lynch",   # Sat → repeat Lynch (most accessible)
    6: "wednesday-lynch",   # Sun
}

MODEL = "claude-sonnet-4-6"


def load_strategy(weekday: int) -> tuple[str, str]:
    """Returns (strategy_name, prompt_body)."""
    name = WEEKDAY_STRATEGY[weekday]
    path = STRATEGY_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Strategy file missing: {path}")
    return name, path.read_text(encoding="utf-8")


def parse_top_movers(brief_text: str, n: int = 3) -> list[dict]:
    """Pull top N rows from the ranking table.

    Brief table format:
      | Rank | Sector | Ticker | Decision | Conf | Setup | Sizing | Price | RSI | Stop | Δ probs |
    """
    out = []
    in_table = False
    for line in brief_text.splitlines():
        if line.startswith("| Rank |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|") or line.startswith("|---"):
            if out:
                break
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 11:
            continue
        try:
            rank = int(cells[0])
        except ValueError:
            continue
        out.append({
            "rank": rank,
            "sector": cells[1],
            "ticker": cells[2].strip("*").strip(),
            "decision": cells[3],
            "conf": cells[4],
            "setup": cells[5],
            "sizing": cells[6],
            "price": cells[7],
            "rsi": cells[8],
            "stop": cells[9],
            "delta": cells[10],
        })
        if len(out) >= n:
            break
    return out


def render_lens_section(strategy_name: str, strategy_body: str, movers: list[dict]) -> str:
    """Call Claude Sonnet 4.6 to apply the framework. Returns a complete
    markdown section starting with `## §3.7 今日大师视角 — ...`."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _stub_section(strategy_name, movers, reason="ANTHROPIC_API_KEY not set")

    try:
        from anthropic import Anthropic
    except ImportError:
        return _stub_section(strategy_name, movers, reason="anthropic SDK not installed")

    movers_block = "\n".join(
        f"- **#{m['rank']} {m['sector']} {m['ticker']}** "
        f"(Decision: {m['decision']} {m['conf']}, Setup: {m['setup']}, "
        f"Sizing: {m['sizing']}, Price: {m['price']}, RSI: {m['rsi']}, "
        f"Stop: {m['stop']}, Δ probs: {m['delta']})"
        for m in movers
    )

    system_prompt = (
        "你是 Alex 的投资笔记助手。Alex 是 NY solo founder + AI/ML SDE,运营 14-ticker watchlist。\n"
        "他每周轮换 5 位大师的框架去 audit 同一批 ticker —— 不是要你复制大师观点,是要你**用大师的框架去问问题**。\n"
        "输出中文,简洁,直接,不要 hype。每个 ticker 1 段(≤120 字),按大师框架的核心问题来 audit。"
    )

    user_content = f"""## 今日 ({datetime.now().strftime("%Y-%m-%d %A")}) 框架: {strategy_name}

### 框架原文 (摘要)
{strategy_body[:2500]}

---

## 今日 brief Top {len(movers)} movers:
{movers_block}

---

## 任务
针对上面 {len(movers)} 个 ticker,各写 1 段(≤120 字),用本周大师的框架问:
- Top #1 用框架审 → pass / lean in / 跳过 + 1 句 reason
- Top #2 同
- Top #3 同

最后加 1-2 句 "本周大师视角 takeaway" —— 这 3 个 ticker 综合起来今天的信号在告诉你什么。

格式:
```
### Top #1 — [ticker]
[1 段中文 ≤120 字]

### Top #2 — [ticker]
[同]

### Top #3 — [ticker]
[同]

### 本周大师 takeaway
[1-2 句]
```

直接出内容,不要前后客套。"""

    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    text = ""
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text += block.text

    pretty_name = strategy_name.split("-", 1)[1].title() if "-" in strategy_name else strategy_name
    weekday_name = datetime.now().strftime("%A")
    return (
        f"\n## §3.7 今日大师视角 — {pretty_name} ({weekday_name})\n\n"
        f"_本周轮换框架: `{strategy_name}.md`. 不是复制大师观点,是用大师的框架审今天 top 3 movers._\n\n"
        f"{text.strip()}\n"
    )


def _stub_section(strategy_name: str, movers: list[dict], reason: str) -> str:
    pretty = strategy_name.split("-", 1)[1].title() if "-" in strategy_name else strategy_name
    return (
        f"\n## §3.7 今日大师视角 — {pretty}\n\n"
        f"⚠ Skipped: {reason}. Strategy file: `{strategy_name}.md`. "
        f"Top movers today: {', '.join(m['ticker'] for m in movers)}.\n"
    )


def main() -> int:
    today_str = datetime.now().strftime("%Y-%m-%d")
    weekday = datetime.now().weekday()
    brief_path = BRIEF_DIR / f"{today_str}.md"

    if not brief_path.exists():
        print(f"[master-lens] No brief today at {brief_path}, skip.")
        return 0

    text = brief_path.read_text(encoding="utf-8")
    if "## §3.7 今日大师视角" in text:
        print(f"[master-lens] Brief already has master-lens section, skip.")
        return 0

    strategy_name, strategy_body = load_strategy(weekday)
    print(f"[master-lens] Today's strategy: {strategy_name}")

    movers = parse_top_movers(text, n=3)
    if not movers:
        print(f"[master-lens] No movers parsed — skip.")
        return 0
    print(f"[master-lens] Top {len(movers)} movers: {[m['ticker'] for m in movers]}")

    section = render_lens_section(strategy_name, strategy_body, movers)

    # Append after "Per-ticker Claude reasoning" section if present, else at end
    insert_marker = "## Per-ticker Claude reasoning"
    if insert_marker in text:
        # Insert BEFORE this header (master lens goes above per-ticker reasoning)
        idx = text.find(insert_marker)
        new_text = text[:idx] + section + "\n" + text[idx:]
    else:
        new_text = text + section

    brief_path.write_text(new_text, encoding="utf-8")
    print(f"[master-lens] Appended §3.7 to {brief_path}")

    # Mirror to public repo if present
    public_path = PUBLIC_REPO_DIR / f"{today_str}.md"
    if public_path.parent.exists():
        public_path.write_text(new_text, encoding="utf-8")
        print(f"[master-lens] Mirrored to public repo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
