"""weekly_review.py — Sunday NY 12:00 ET cron.

Reads last 7 daily briefs, extracts §5 STACK + §6 STRATEGIC, asks Claude
Sonnet 4.6 to find signals that appeared ≥3 days across the week.

Outputs:
  ~/.solo-founder-os/weekly-review/YYYY-WXX.json     (candidate upgrades, HITL queue)
  ~/.orallexa/daily-brief/weekly/YYYY-WXX.html       (book-quality digest)
  ~/Desktop/Interview-Prep/Projects/alex-brain/research/daily-brief/weekly/YYYY-WXX.html  (brain archive)

  Email via Resend to xji1@mail.yu.edu (or dry-run + open if no key)

Design constraints:
  - DOES NOT touch the L4 evolver. Evolver works on reflexion failure patterns,
    these are news-derived suggestions — different threat model. Alex manually
    creates GH issues from this digest.
  - Distinguishes code_upgrade (low risk, this-week actionable) vs
    positioning (high risk, requires user conversations + Alex gut, never auto)
  - Signals appearing only 1x get demoted to "watchlist" — not a proposal.
"""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Reuse helpers from daily_brief
sys.path.insert(0, str(Path(__file__).parent))
from daily_brief import (  # type: ignore
    inline_md,
    inline_format,
    send_email_resend,
    ANTHROPIC_API_KEY,
)


HOME = Path.home()
SCRIPT_DIR = Path(__file__).parent
DAILY_BRIEF_DIR = SCRIPT_DIR.parent
BRAIN_BRIEF_DIR = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "daily-brief"
WEEKLY_BRAIN_DIR = BRAIN_BRIEF_DIR / "weekly"
WEEKLY_LOCAL_DIR = DAILY_BRIEF_DIR / "weekly"
PROPOSALS_DIR = HOME / ".solo-founder-os" / "weekly-review"
MIN_BRIEFS = 5  # Need at least 5 briefs to do a meaningful review

DEEP_MODEL = "claude-sonnet-4-6"


# ────────────────────────────────────────────────────────────────────
# READ LAST 7 BRIEFS
# ────────────────────────────────────────────────────────────────────

def load_recent_briefs(days: int = 7) -> list[dict]:
    """Returns list of {date, path, stack_text, strategic_text} for the last N days."""
    out = []
    today = datetime.now(timezone.utc).date()
    for d in range(days):
        date_obj = today - timedelta(days=d)
        date_str = date_obj.strftime("%Y-%m-%d")
        path = BRAIN_BRIEF_DIR / f"{date_str}.md"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        stack = _extract_section(text, "对现有 stack 的影响")
        strategic = _extract_section(text, "对未来创业的影响")
        out.append({
            "date": date_str,
            "path": str(path),
            "stack": stack,
            "strategic": strategic,
        })
    out.sort(key=lambda b: b["date"])
    return out


def _extract_section(md: str, section_title: str) -> str:
    """Find `## §N {title}` and return the body until the next `##` heading."""
    # Match `## §5 对现有 stack 的影响` (number flexible, title flexible)
    pattern = rf"^##\s+§\d+\s+{re.escape(section_title)}\s*$"
    match = re.search(pattern, md, re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_h2 = re.search(r"^##\s", md[start:], re.MULTILINE)
    end = start + next_h2.start() if next_h2 else len(md)
    return md[start:end].strip()


# ────────────────────────────────────────────────────────────────────
# CLAUDE SYNTHESIS
# ────────────────────────────────────────────────────────────────────

def compile_weekly_review(briefs: list[dict], week_label: str) -> dict:
    """Returns parsed delimiter dict with takeaway, code_proposals, positioning_watchlist, demoted, audit_intro."""
    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build input block
    input_lines = []
    for b in briefs:
        input_lines.append(f"\n=== {b['date']} ===\n")
        input_lines.append(f"### §5 对现有 stack 的影响\n{b['stack']}\n")
        input_lines.append(f"### §6 对未来创业的影响\n{b['strategic']}\n")
    input_block = "\n".join(input_lines)

    system_prompt = f"""你是 Alex 的私人 weekly review 助手。

Alex 是 NY 的 solo founder + AI/ML SDE。他维护:VibeXForge (AI marketing platform)、Orallexa (multi-agent trading bot)、Solo Founder OS (11-agent OSS Python stack)、念念 niànniàn (voice-first emotional journal iOS app,launch 准备中)。

每天会有一份 daily brief。今天 {datetime.now().strftime('%Y-%m-%d (%A)')} 是周日,要做一次 {week_label} 的 weekly review。

**任务:从过去 7 天的 §5 + §6 sections 里,找出 *重复出现 ≥3 天* 的信号 — 单点出现的不算 trend,要 archive 掉。**

分类规则严格:
- **code_upgrade (低风险)** = 改某个现有 agent 的 prompt / config / source / cost 维度 / structured output。每条:target_repo + target_files + 50 行内 change_summary + rationale + estimated_loc。**这些会让 Alex 手动开 GH issue / PR**,不会被 evolver 自动执行。
- **positioning (高风险)** = 公司方向 / 主打用户 / SaaS 定位 / 商业模式。**绝不能进 code 队列,只是 watchlist**。需要 14-30 天连续信号 + 用户访谈 + Alex gut 才能决定。
- **demoted (信号不足)** = 只出现 1-2 天的"诱人但还不到 act 的程度"。archive,记下哪天来的,以后可以再看。

**输出格式:严格按 delimiter,中文,不要 JSON 不要 code block 包裹。**

### TAKEAWAY ###
一句话本周核心 trend ≤ 120 字。

### CODE_PROPOSALS ###
列 1-5 个 code_upgrade proposal。每条用这个格式(空行分隔):

**[001] 标题**
- target_repo: <repo name 例如 cost-audit-agent>
- target_files: <relative file path>
- signal_count: <出现几天>
- mentioned_on: <YYYY-MM-DD, YYYY-MM-DD, ...>
- change_summary: <1-2 句话具体改什么>
- rationale: <为什么这条 signal 是真的>
- estimated_loc: <预估改动行数>

如果没有 ≥3 天的 code signal,坦诚写"本周没有足够 confirm 的 code upgrade proposal,等下周积累更多 signal"。

### POSITIONING_WATCHLIST ###
列 0-3 个 positioning 信号(出现 ≥2 天)。每条 markdown bullet:

- **[标题]** — 出现于 [dates]。Alex 视角的简短观察 (≤ 50 字)。**Action: 还在 watchlist,需要 14-30 天 confirm + 用户访谈**。

如果一个都没有,写"本周没有 positioning level 信号"。

### DEMOTED ###
列 0-N 个只出现 1-2 天的 signal,markdown bullet,标注哪天出现。这是 archive,以后 grep 用。

### AUDIT_INTRO ###
2-3 句话总结本周整体 mood + 给 Alex 一个 reflection question(不是问句 stack,是问他自己)。

---

输入:过去 7 天的 §5 + §6 sections。注意每个日期都标了。

{{input_block_placeholder}}

现在产出 delimiter 格式。"""

    user_content = f"""周次: {week_label}
分析了 {len(briefs)} 天的 brief (要求 ≥ {MIN_BRIEFS} 才有意义,本周 {len(briefs)})

{input_block}

现在按 5 个 delimiter 严格输出 weekly review。"""

    resp = client.messages.create(
        model=DEEP_MODEL,
        max_tokens=4000,
        system=system_prompt.replace("{input_block_placeholder}", ""),
        messages=[{"role": "user", "content": user_content}],
    )

    text = ""
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text += block.text
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)

    # Parse delimiters
    section_map = {
        "TAKEAWAY": "takeaway",
        "CODE_PROPOSALS": "code_proposals",
        "POSITIONING_WATCHLIST": "positioning",
        "DEMOTED": "demoted",
        "AUDIT_INTRO": "audit_intro",
    }
    parts = {v: "" for v in section_map.values()}
    pattern = re.compile(r"^\s*###\s+([A-Z_]+)\s+###\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        print("[weekly] delimiter parse failed", file=sys.stderr)
        parts["takeaway"] = "(delimiter 解析失败,见 raw 输出)"
        parts["audit_intro"] = text
        return parts
    for i, m in enumerate(matches):
        key_upper = m.group(1)
        if key_upper not in section_map:
            continue
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        parts[section_map[key_upper]] = body
    return parts


# ────────────────────────────────────────────────────────────────────
# RENDER JSON PROPOSALS (HITL queue, NOT evolver)
# ────────────────────────────────────────────────────────────────────

def extract_proposals_json(code_proposals_text: str, week_label: str, briefs_analyzed: list[str]) -> dict:
    """Best-effort parse of the markdown proposal list into JSON for HITL queue."""
    proposals = []
    blocks = re.split(r"^\*\*\[\d+\]\s+", code_proposals_text, flags=re.MULTILINE)
    for blk in blocks[1:]:  # blocks[0] is preamble before first proposal
        # Find title (text before first \n)
        m_title = re.match(r"([^\n*]+)\*\*", blk)
        title = m_title.group(1).strip() if m_title else "(unnamed)"
        def grab(field: str) -> str:
            mm = re.search(rf"-\s+{field}:\s*(.+)", blk)
            return mm.group(1).strip() if mm else ""
        proposals.append({
            "title": title,
            "target_repo": grab("target_repo"),
            "target_files": grab("target_files"),
            "signal_count": grab("signal_count"),
            "mentioned_on": grab("mentioned_on"),
            "change_summary": grab("change_summary"),
            "rationale": grab("rationale"),
            "estimated_loc": grab("estimated_loc"),
            "status": "pending",
        })
    return {
        "week": week_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "briefs_analyzed": briefs_analyzed,
        "min_signal_threshold": 3,
        "source": "daily-brief-weekly",
        "notes": "Manual HITL review. NOT consumed by L4 evolver (different threat model).",
        "proposals": proposals,
    }


# ────────────────────────────────────────────────────────────────────
# RENDER HTML DIGEST
# ────────────────────────────────────────────────────────────────────

WEEKLY_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --ink: #1a1a1a; --ink-soft: #4a4a4a; --ink-dim: #707070;
    --paper: #fbfaf6; --rule: #cfc8b8;
    --accent: #8c3a14; --accent-soft: #f0e3d4;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; padding: 0; background: var(--paper); color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
                 "Songti SC", "Noto Serif CJK SC", "Source Han Serif SC", Georgia, serif;
    font-size: 17px; line-height: 1.78; -webkit-font-smoothing: antialiased;
  }}
  .page {{ max-width: 760px; margin: 0 auto; padding: 56px 28px 80px; }}
  .masthead {{
    display: flex; justify-content: space-between; align-items: baseline;
    border-bottom: 3px double var(--ink); padding-bottom: 10px; margin-bottom: 28px;
  }}
  .masthead h1 {{
    font-family: ui-serif, Georgia, serif; font-size: 34px; font-weight: 700;
    letter-spacing: -0.5px; margin: 0 0 4px; color: var(--ink);
  }}
  .masthead .subtitle {{ font-size: 13px; color: var(--ink-dim); text-transform: uppercase; letter-spacing: 1.5px; }}
  .masthead .week-badge {{
    text-align: right; font-family: ui-serif, Georgia, serif; color: var(--accent);
  }}
  .masthead .week-badge .num {{ font-size: 32px; font-weight: 700; display: block; line-height: 1; }}
  .masthead .week-badge .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 2px; color: var(--ink-dim); }}

  section.entry {{ margin: 36px 0; }}
  section.entry h2 {{
    font-family: ui-serif, Georgia, serif; font-size: 22px; font-weight: 700;
    margin: 0 0 14px; padding-bottom: 6px; border-bottom: 1px dashed var(--rule);
  }}
  section.entry h2 .sec-num {{
    color: var(--accent); font-size: 14px; margin-right: 8px;
    font-family: ui-monospace, SF Mono, Menlo, monospace;
  }}
  section.entry p, section.entry li {{ color: var(--ink-soft); }}
  section.entry ul {{ padding-left: 22px; }}
  section.entry a {{ color: var(--accent); border-bottom: 1px solid var(--accent-soft); text-decoration: none; }}
  section.entry code {{
    font-family: ui-monospace, SF Mono, Menlo, monospace;
    background: var(--accent-soft); padding: 1px 5px; border-radius: 3px;
    color: var(--accent); font-size: 13px;
  }}
  section.entry strong {{ color: var(--ink); font-weight: 600; }}
  section.entry em {{ color: var(--ink); font-style: italic; }}

  .pullquote {{
    margin: 28px 0; padding: 18px 22px;
    border-left: 3px solid var(--accent); background: var(--accent-soft);
    font-family: ui-serif, Georgia, serif; font-size: 19px; line-height: 1.6;
    color: var(--ink); font-style: italic;
  }}
  .proposals-table {{
    margin: 14px 0 18px; padding: 12px; background: #fff;
    border: 1px solid var(--rule); border-radius: 6px;
    font-size: 14px; line-height: 1.5;
  }}
  .gate-note {{
    margin: 12px 0; padding: 10px 14px;
    background: #fffae0; border-left: 3px solid #d4a017;
    font-size: 13px; color: var(--ink-soft);
  }}
  .colophon {{
    margin-top: 60px; padding-top: 18px; border-top: 1px solid var(--rule);
    font-size: 12px; color: var(--ink-dim); text-align: center; line-height: 1.6;
  }}
  @media (max-width: 600px) {{ .page {{ padding: 32px 18px 56px; }} body {{ font-size: 16px; }} }}
</style>
</head>
<body>
<div class="page">
  <header class="masthead">
    <div>
      <h1>Weekly Review</h1>
      <div class="subtitle">Alex 的 AI 战略周报 · {week_label}</div>
    </div>
    <div class="week-badge">
      <span class="num">W{week_num}</span>
      <span class="label">{briefs_count} / 7 briefs</span>
    </div>
  </header>

  <div class="pullquote">{takeaway_html}</div>

  <section class="entry">
    <h2><span class="sec-num">§1</span>Code upgrade proposals</h2>
    <div class="gate-note">
      <strong>Gate:</strong> 这些是 HITL queue,不被 L4 evolver 自动执行。
      JSON 已写入 <code>{proposals_path}</code>。Alex 手动决定开 GH issue / PR。
    </div>
    {code_html}
  </section>

  <section class="entry">
    <h2><span class="sec-num">§2</span>Positioning watchlist</h2>
    <div class="gate-note">
      <strong>不要动:</strong> 这些是定位级 signal。需要 14-30 天连续 confirm + 用户访谈 + Alex gut 才能 act。绝不让 LLM 直接驱动 pivot。
    </div>
    {positioning_html}
  </section>

  <section class="entry">
    <h2><span class="sec-num">§3</span>Demoted · 信号不足</h2>
    {demoted_html}
  </section>

  <section class="entry">
    <h2><span class="sec-num">§4</span>Reflection</h2>
    {audit_html}
  </section>

  <div class="colophon">
    <div>{date_human}</div>
    <div style="font-style:italic">每周日 NY 12:00 · 由 daily-brief 7 天聚合而成</div>
    <div style="margin-top:4px">JSON proposals → <code>~/.solo-founder-os/weekly-review/</code></div>
  </div>
</div>
</body>
</html>"""


def render_html(parts: dict, week_label: str, briefs_count: int, proposals_path: str) -> str:
    week_num = week_label.split("-W")[-1] if "-W" in week_label else "?"
    date_human = datetime.now().strftime("%Y年 %m月 %d日 · 周日")
    return WEEKLY_HTML.format(
        title=f"Weekly Review · {week_label}",
        week_label=html_lib.escape(week_label),
        week_num=html_lib.escape(week_num),
        briefs_count=briefs_count,
        proposals_path=html_lib.escape(proposals_path),
        date_human=html_lib.escape(date_human),
        takeaway_html=inline_format(parts.get("takeaway", "")),
        code_html=inline_md(parts.get("code_proposals", "")),
        positioning_html=inline_md(parts.get("positioning", "")),
        demoted_html=inline_md(parts.get("demoted", "")),
        audit_html=inline_md(parts.get("audit_intro", "")),
    )


def render_md_sidecar(parts: dict, week_label: str, briefs_count: int) -> str:
    return f"""---
week: {week_label}
generated_at: {datetime.now(timezone.utc).isoformat()}
briefs_analyzed: {briefs_count}
---

# Weekly Review — {week_label}

> {parts.get("takeaway", "")}

## §1 Code upgrade proposals (HITL queue, NOT evolver)
{parts.get("code_proposals", "")}

## §2 Positioning watchlist (要 14-30 天 + 用户访谈 confirm)
{parts.get("positioning", "")}

## §3 Demoted · 信号不足
{parts.get("demoted", "")}

## §4 Reflection
{parts.get("audit_intro", "")}
"""


# ────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────

def get_week_label() -> tuple[str, int]:
    """Return (ISO week label like '2026-W19', week number int)."""
    today = datetime.now(timezone.utc).date()
    iso_year, iso_week, _ = today.isocalendar()
    return f"{iso_year}-W{iso_week:02d}", iso_week


def main():
    if not ANTHROPIC_API_KEY:
        print("FATAL: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    week_label, _ = get_week_label()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[weekly] {today_str} starting weekly review for {week_label}")

    print("[weekly] loading last 7 briefs...")
    briefs = load_recent_briefs(days=7)
    print(f"[weekly] found {len(briefs)} briefs: {[b['date'] for b in briefs]}")

    if len(briefs) < MIN_BRIEFS:
        print(f"[weekly] only {len(briefs)} briefs, need >= {MIN_BRIEFS}. Graceful skip.")
        # Still write a placeholder so cron has a heartbeat
        WEEKLY_BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        placeholder = WEEKLY_BRAIN_DIR / f"{week_label}.md"
        placeholder.write_text(
            f"# Weekly Review — {week_label}\n\n"
            f"Found {len(briefs)} briefs (need >= {MIN_BRIEFS}). "
            f"First real weekly review will be when daily-brief has enough history.\n",
            encoding="utf-8",
        )
        return

    print("[weekly] compiling with Claude Sonnet 4.6...")
    parts = compile_weekly_review(briefs, week_label)

    # JSON proposals → HITL queue
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    proposals_json_path = PROPOSALS_DIR / f"{week_label}.json"
    proposals_json = extract_proposals_json(
        parts.get("code_proposals", ""),
        week_label,
        [b["date"] for b in briefs],
    )
    proposals_json_path.write_text(json.dumps(proposals_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[weekly] wrote {proposals_json_path} ({len(proposals_json['proposals'])} proposals)")

    # HTML digest
    html_body = render_html(parts, week_label, len(briefs), str(proposals_json_path))
    md_sidecar = render_md_sidecar(parts, week_label, len(briefs))

    WEEKLY_BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    WEEKLY_LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    brain_html = WEEKLY_BRAIN_DIR / f"{week_label}.html"
    brain_md = WEEKLY_BRAIN_DIR / f"{week_label}.md"
    local_html = WEEKLY_LOCAL_DIR / f"{week_label}.html"
    brain_html.write_text(html_body, encoding="utf-8")
    brain_md.write_text(md_sidecar, encoding="utf-8")
    local_html.write_text(html_body, encoding="utf-8")
    print(f"[weekly] wrote {brain_html}")

    # Email
    subject = f"Weekly Review · {week_label} · {len(proposals_json['proposals'])} proposals"
    sent = send_email_resend(subject, html_body, md_sidecar)
    if not sent:
        subprocess.run(["open", str(brain_html)], check=False)

    print("[weekly] done.")


if __name__ == "__main__":
    main()
