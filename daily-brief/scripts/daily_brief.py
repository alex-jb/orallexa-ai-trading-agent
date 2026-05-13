"""daily_brief.py — orchestrator for Alex's NY 12:00 ET daily brief.

Pulls AI news (HN + RSS) + AI 人物 feeds + SpaceX brief, asks Claude Sonnet 4.6
to synthesize a Chinese-language brief framed as a 日记 (daily journal).

Output is a book-quality HTML file (no markdown surface) — Alex 想以后出书.
The same HTML body is emailed via Resend if RESEND_API_KEY is set.

Sections:
  1. 今日要点 (≤120 字, 一句 takeaway)
  2. AI 人物动态 (Karpathy / 李飞飞 / Altman / Hassabis / LeCun / Sutskever / Amodei / Andrej / Roy Lee / Dovey Wan)
  3. AI 新闻摘要 (5-8 条, 翻译 + Alex 视角解读)
  4. SpaceX 跟踪 (#1 mover + 1 句 commentary)
  5. 今日 AI 学习 — Day N (~400 字 友好科普, Phase 0 假设读者零基础)
  6. 跟你 stack 的连接 (VibeXForge / Orallexa / SFOS)
  7. 一句话 wrap

Writes:
  ~/Desktop/Interview-Prep/Projects/alex-brain/research/daily-brief/YYYY-MM-DD.html  (book-quality)
  ~/Desktop/Interview-Prep/Projects/alex-brain/research/daily-brief/YYYY-MM-DD.md   (grep-friendly sidecar)
  ~/.orallexa/daily-brief/briefs/YYYY-MM-DD.html  (local cache)
"""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


# ────────────────────────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────────────────────────

HOME = Path.home()
SCRIPT_DIR = Path(__file__).parent
DAILY_BRIEF_DIR = SCRIPT_DIR.parent
CURRICULUM_PATH = DAILY_BRIEF_DIR / "curriculum.yaml"
BRAIN_BRIEF_DIR = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "daily-brief"
LOCAL_BRIEF_DIR = DAILY_BRIEF_DIR / "briefs"
SPACEX_BRIEF_DIR = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "spacex-daily"

CURRICULUM_START_DATE = "2026-05-12"  # Day 1
EMAIL_TO = "xixiaichiyu09@gmail.com"
EMAIL_FROM = "Daily Brief <onboarding@resend.dev>"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

DEEP_MODEL = "claude-sonnet-4-6"


# ────────────────────────────────────────────────────────────────────
# AI NEWS FETCHERS
# ────────────────────────────────────────────────────────────────────

def fetch_hn_ai_stories(top_n: int = 15) -> list[dict]:
    import urllib.request
    KEYWORDS = (
        "gpt", "llm", "ai", "claude", "anthropic", "openai", "gemini",
        "deepseek", "mistral", "llama", "transformer", "agent", "rag",
        "diffusion", "fine-tun", "embed", "tokeniz", "inference", "training",
        "neural", "model", "prompt", "ollama", "lora", "qlora", "moe", "rlhf",
    )
    try:
        with urllib.request.urlopen(
            "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=20,
        ) as resp:
            ids = json.loads(resp.read())[:80]
    except Exception as exc:
        return [{"error": f"HN top fetch failed: {exc}"}]

    stories = []
    for sid in ids:
        try:
            with urllib.request.urlopen(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=15,
            ) as resp:
                item = json.loads(resp.read())
        except Exception:
            continue
        if not item or item.get("type") != "story":
            continue
        title = (item.get("title") or "").lower()
        if not any(kw in title for kw in KEYWORDS):
            continue
        stories.append({
            "title": item.get("title", ""),
            "url": item.get("url") or f"https://news.ycombinator.com/item?id={sid}",
            "hn_url": f"https://news.ycombinator.com/item?id={sid}",
            "points": item.get("score", 0),
            "comments": item.get("descendants", 0),
        })
        if len(stories) >= top_n:
            break
    return stories


def fetch_blog_rss(feed_url: str, max_items: int = 3) -> list[dict]:
    import urllib.request
    try:
        req = urllib.request.Request(
            feed_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml_bytes = resp.read()
    except Exception as exc:
        return [{"error": f"RSS fetch failed for {feed_url}: {exc}"}]

    xml = xml_bytes.decode("utf-8", errors="ignore")
    items = []
    for m in re.finditer(r"<(item|entry)>(.*?)</\1>", xml, re.DOTALL):
        block = m.group(2)

        def grab(tag):
            mm = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.DOTALL)
            if not mm:
                return ""
            v = mm.group(1).strip()
            v = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", v, flags=re.DOTALL)
            v = re.sub(r"<[^>]+>", "", v)
            return v[:400]

        title = grab("title")
        link = grab("link")
        if not link:
            ml = re.search(r"<link[^>]+href=\"([^\"]+)\"", block)
            link = ml.group(1) if ml else ""
        summary = grab("description") or grab("summary") or grab("content")
        if title and link:
            items.append({"title": title, "url": link, "summary": summary})
        if len(items) >= max_items:
            break
    return items


PEOPLE_FEEDS = [
    ("Karpathy", "https://karpathy.github.io/feed.xml"),
    ("Stanford HAI (李飞飞)", "https://hai.stanford.edu/news/feed"),
    ("Sam Altman", "https://blog.samaltman.com/posts.atom"),
    ("DeepMind (Hassabis)", "https://deepmind.google/discover/blog/rss.xml"),
    ("Latent Space (swyx)", "https://www.latent.space/feed"),
    ("Interconnects (Nathan Lambert)", "https://www.interconnects.ai/feed"),
]

PEOPLE_KEYWORDS = (
    "karpathy", "fei-fei", "feifei", "fei fei", "李飞飞",
    "sam altman", "altman", "demis hassabis", "hassabis",
    "yann lecun", "lecun", "ilya", "sutskever",
    "dario amodei", "mira murati", "sundar pichai",
    "andrej", "roy lee", "cluely", "dovey wan",
    "kaiming he", "ross girshick", "anthropic", "openai",
    "deepmind", "google deepmind", "primitive ventures",
    "andrew ng",
)


def fetch_ai_news() -> dict:
    hn = fetch_hn_ai_stories(top_n=10)
    anthropic = fetch_blog_rss("https://www.anthropic.com/news/rss.xml", max_items=2)
    openai = fetch_blog_rss("https://openai.com/blog/rss.xml", max_items=2)
    huggingface = fetch_blog_rss("https://huggingface.co/blog/feed.xml", max_items=2)

    people = []
    for label, url in PEOPLE_FEEDS:
        if not url:
            continue
        items = fetch_blog_rss(url, max_items=2)
        for it in items:
            if "error" in it:
                continue
            it["source"] = label
            people.append(it)

    people_in_hn = []
    for s in hn:
        title_low = s.get("title", "").lower()
        if any(kw in title_low for kw in PEOPLE_KEYWORDS):
            people_in_hn.append(s)

    return {
        "hn": hn,
        "anthropic": anthropic,
        "openai": openai,
        "huggingface": huggingface,
        "people_blogs": people,
        "people_in_hn": people_in_hn,
    }


# ────────────────────────────────────────────────────────────────────
# SPACEX BRIEF
# ────────────────────────────────────────────────────────────────────

def get_today_spacex_brief() -> tuple[Optional[str], str]:
    """Returns (brief_text, freshness_note).

    freshness_note is one of:
      "today"     — today's brief, fresh
      "stale-Xd"  — fallback to most recent, X days old
      "missing"   — no SpaceX brief ever
    """
    today_date = datetime.now(timezone.utc).date()
    today_str = today_date.strftime("%Y-%m-%d")
    path = SPACEX_BRIEF_DIR / f"{today_str}.md"
    if path.exists():
        return path.read_text(encoding="utf-8"), "today"
    if SPACEX_BRIEF_DIR.exists():
        briefs = sorted(SPACEX_BRIEF_DIR.glob("*.md"))
        if briefs:
            latest = briefs[-1]
            text = latest.read_text(encoding="utf-8")
            try:
                fname_date = datetime.strptime(latest.stem, "%Y-%m-%d").date()
                age_days = (today_date - fname_date).days
                return text, f"stale-{age_days}d"
            except ValueError:
                return text, "stale-?d"
    return None, "missing"


def get_morning_news_brief() -> tuple[Optional[str], str]:
    """Read today's news-morning brief if it ran (NY 09:00 ET). Returns
    (text, freshness). Daily-brief at NY 12:00 should see today's; if
    not, fall back gracefully."""
    today_date = datetime.now(timezone.utc).date()
    today_str = today_date.strftime("%Y-%m-%d")
    path = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "markets-news" / f"{today_str}.md"
    if path.exists():
        return path.read_text(encoding="utf-8"), "today"
    # Fall back to yesterday's if today's hasn't generated yet
    yest = (today_date - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")
    yest_path = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "markets-news" / f"{yest}.md"
    if yest_path.exists():
        return yest_path.read_text(encoding="utf-8"), "stale-1d"
    return None, "missing"


def get_polymarket_status() -> str:
    """Polymarket data is currently UNAVAILABLE (Cloudflare IP ban, per
    alex-brain markets module). Returns a status string that the brief
    prompt can render gracefully.

    When polymarket cron re-enables (IP unban), this should read a
    real brief file. Path TBD — likely
    ~/Desktop/Interview-Prep/Projects/alex-brain/research/polymarket-daily/.
    """
    poly_dir = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "polymarket-daily"
    if poly_dir.exists():
        briefs = sorted(poly_dir.glob("*.md"))
        if briefs:
            return briefs[-1].read_text(encoding="utf-8")
    return "OFFLINE — Polymarket scraper paused since 2026-05-11 due to Cloudflare IP ban. Cron resumes after unban (24-48h windows). No fresh signal today."


# ────────────────────────────────────────────────────────────────────
# CURRICULUM
# ────────────────────────────────────────────────────────────────────

def get_lookback_briefs() -> dict:
    """Read past briefs for the AUDIT section. Returns dict with 1d / 7d entries if they exist."""
    result = {"d1": None, "d7": None}
    today = datetime.now(timezone.utc).date()
    for days_back, key in [(1, "d1"), (7, "d7")]:
        check_date = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days_back)).strftime("%Y-%m-%d")
        path = BRAIN_BRIEF_DIR / f"{check_date}.md"
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
                result[key] = {"date": check_date, "text": text}
            except Exception:
                pass
    return result


def get_today_curriculum() -> tuple[int, str, str, int]:
    """Returns (day_number, phase_name, topic, phase_idx)."""
    with open(CURRICULUM_PATH) as f:
        cur = yaml.safe_load(f)

    start = datetime.strptime(CURRICULUM_START_DATE, "%Y-%m-%d").date()
    today = datetime.now(timezone.utc).date()
    delta = (today - start).days
    day_number = delta + 1

    flat = []
    for pi, phase in enumerate(cur["phases"]):
        for topic in phase["topics"]:
            flat.append((pi, phase["name"], topic))

    if day_number < 1:
        idx = 0
    elif day_number > len(flat):
        idx = (day_number - 1) % len(flat)
    else:
        idx = day_number - 1

    pi, phase_name, topic = flat[idx]
    return day_number, phase_name, topic, pi


# ────────────────────────────────────────────────────────────────────
# CLAUDE SYNTHESIS
# ────────────────────────────────────────────────────────────────────

def compile_brief(news: dict, spacex_brief: Optional[str], spacex_freshness: str,
                   polymarket_status: str, morning_news: Optional[str],
                   morning_news_freshness: str,
                   day_n: int, phase: str, topic: str,
                   phase_idx: int, lookback: dict) -> dict:
    """Returns structured dict with 10 sections."""
    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    news_lines = []
    if news.get("hn"):
        news_lines.append("## Hacker News top AI stories")
        for s in news["hn"][:10]:
            if "error" in s:
                news_lines.append(f"  [HN fetch error: {s['error']}]")
                continue
            news_lines.append(f"- [{s.get('points', 0)}pts/{s.get('comments', 0)}c] {s['title']}")
            news_lines.append(f"  {s['url']}")

    for src in ("anthropic", "openai", "huggingface"):
        if news.get(src):
            news_lines.append(f"\n## {src.title()} blog")
            for it in news[src][:2]:
                if "error" in it:
                    continue
                news_lines.append(f"- {it['title']}")
                news_lines.append(f"  {it['url']}")
                if it.get("summary"):
                    news_lines.append(f"  > {it['summary'][:200]}")

    if news.get("people_blogs"):
        news_lines.append("\n## AI 人物 blog")
        for it in news["people_blogs"][:8]:
            news_lines.append(f"- [{it.get('source','?')}] {it['title']}")
            news_lines.append(f"  {it['url']}")
            if it.get("summary"):
                news_lines.append(f"  > {it['summary'][:250]}")

    if news.get("people_in_hn"):
        news_lines.append("\n## AI 人物 mentioned on HN today")
        for s in news["people_in_hn"][:6]:
            news_lines.append(f"- [{s.get('points',0)}pts] {s['title']}")
            news_lines.append(f"  {s['url']}")

    news_block = "\n".join(news_lines) if news_lines else "(no news fetched)"

    spacex_block = ""
    if spacex_brief:
        spacex_block = "\n".join(spacex_brief.splitlines()[:80])

    today_str = datetime.now().strftime("%Y-%m-%d (%A)")

    # Phase-aware tone calibration for the lesson section
    if phase_idx == 0:  # Phase 0 — 朋友也能听懂
        lesson_tone = (
            "Phase 0 = 假设读者是一个聪明的高中生,从来没碰过 ML。零数学,先用类比和故事建立直觉。"
            "举一个 Alex 平时生活能 relate 的例子(比如打字、看新闻、用 ChatGPT 的感受)。"
        )
    elif phase_idx == 1:  # Phase 1 — Transformer 内部
        lesson_tone = "Phase 1 = 开始打开数学,但是先直觉后公式。给一个 Python pseudocode snippet 帮助理解。"
    else:
        lesson_tone = "正常 deep-dive 模式 — 直觉 + 数学/代码 + 工程考量。"

    # Build lookback context
    lookback_lines = []
    if lookback.get("d1"):
        lookback_lines.append("### Yesterday (D-1) brief (for audit):")
        lookback_lines.append(lookback["d1"]["text"][:3000])
    if lookback.get("d7"):
        lookback_lines.append("\n### 7-day-ago (D-7) brief (for audit, check 'has thesis held?'):")
        lookback_lines.append(lookback["d7"]["text"][:3000])
    lookback_block = "\n".join(lookback_lines) if lookback_lines else "(no prior briefs — this is Day 1 or near-Day-1)"

    system_prompt = f"""你是 Alex 的私人 daily research 助手 + 写书 co-author。

Alex 是 NY 的 solo founder + AI/ML SDE。他维护:
- **VibeXForge** — AI marketing platform
- **Orallexa** — multi-agent trading bot (含 SpaceX-IPO-Tracker public daily research)
- **Solo Founder OS** — 11-agent OSS Python stack
- **念念 niànniàn** — voice-first emotional journal iOS app (on-device, Shinkai-style 3D scenes, mumu+ashen personas;launch 准备中,网信办 7-15 合规已完成 2 个月前)

他中文 native,讨厌 hype 词,要 signal density。

**这份 daily brief 不只是日常 newsletter — Alex 想把它积累成一本书的素材。所以每天的"今日 AI 学习"
部分要写成一篇能直接放进书里的章节片段 — 友好、有故事感、有 Alex 视角,而不是 wiki 式罗列。**

**你不只是新闻搬运 — 你是 Alex 的策略顾问。今天看到的每条信号,你需要主动问:这对 Alex 现有 stack 意味着什么?对未来要不要做新的 bet 意味着什么?这才是 brief 的真正价值。**

今天是 {today_str}。请用中文写一个 10-section 的 daily 日记。

**输出格式:严格用下面的 10 个 delimiter 分隔,每个 section 一段。delimiter 一行单独占用,前后空一行。不要用 JSON,不要用 code block 包裹。直接输出。**

### TAKEAWAY ###
今日要点 — 一句话 ≤ 120 字。

### PEOPLE ###
AI 人物动态 — 1-3 段。Alex 关注:Karpathy、李飞飞、Sam Altman、Demis Hassabis、Yann LeCun、Ilya Sutskever、Dario Amodei、Mira Murati、Andrej、Kaiming He、Roy Lee (Cluely)、Dovey Wan、Andrew Ng。如果今天 input 出现他们,优先放这里 — 每人 1-2 句(说了什么 + Alex angle)。没出现就坦诚说"今天这些人没新闻",别硬塞。

### NEWS ###
AI 新闻摘要 — 5-8 条 bullet。每条:中文翻译标题 + 一句 Alex 视角解读(观点,不是直译)。过滤 clickbait。每条后括号附原 url,用 markdown 链接形式 [title](url)。
**重要:**如果今早 markets news scan (input 里 "今早 markets news scan") 抓到 HIGH/MED impact 的 watchlist catalyst,在这个 section 顶部加一个 ✨ "今早 catalyst" 子部分,1-2 句概括最重要的 1-2 条 — 让 §2 NEWS 跟 markets cron 联动。

### SPACEX ###
SpaceX & Frontier Hardware 跟踪 — **完整 14-ticker watchlist ranking,4 个 sector(孙宇晨 2026 thesis)**:
- 🛰 Space: RKLB / ASTS / LUNR / BKSY / PL / RDW / LMT / LIN
- 🤖 Physical AI / 机器人: TSLA / SYM
- 🧠 AI Infra: NVDA / AVGO
- 🚁 无人机: AVAV / KTOS

列出 brief 里全部 14 个 ticker 的 ranking,按 p(up) - p(down) 排序。
表格格式:`Rank | Sector | Ticker | Decision | Conf | Δ probs | RSI`,Sector 用 emoji。
表格下面 2-3 句 commentary:**分 sector 总结**(各 sector 今天哪个方向最强),不是逐 ticker 复述。
**数据新鲜度披露:** spacex_freshness=today → 直接用。stale-1d → 开头明说"⚠ 数据来自昨天 brief,SpaceX cron 在 NY 14:00 ET 才跑,今天的更新还没出"。更老显示对应天数。
没 brief 才写"今天没新数据"。

### POLYMARKET ###
Polymarket / Kalshi 预测市场跟踪。
如果 polymarket_status 以 "OFFLINE" 开头,直接说"预测市场数据离线 — Cloudflare IP ban,等解禁。orallexa-markets 接入后这里会有 Kalshi + Polymarket 的 binary event signal 列表"。
如果有真数据(future state):列今天 watchlist 上 top 3 binary events 的 yes-price + 7d 变化 + Alex 视角 commentary。

### LESSON ###
今日 AI 学习 — Day {day_n},phase: {phase},topic: {topic}。
{lesson_tone}
长度 400-500 字。结构:(a) 概念解释,(b) 一个 Alex 能 relate 的例子或 code snippet,(c) 一个 reflection question。**这是要写进书里的素材,语气要像一个好朋友/导师在讲故事,而不是 wiki**。

### STACK ###
**今天对现有 stack 的 actionable 影响** — 1-2 条具体。例:"Needle 的 26M 蒸馏路线意味着 Orallexa 的 tool routing 可以本地化 — 你 cost-audit-agent 应该加 'tool routing API spend' 维度"。聚焦于 *现有 4 个项目*:VibeXForge / Orallexa (+ markets/) / Solo Founder OS 11-agent stack / 念念 niànniàn (iOS),他能这周/这月就动手的事。

### STRATEGIC ###
**今天对未来创业 bets 的影响** — 1-2 条长期。聚焦于:今天信号暗示哪个赛道有窗口期、哪个方向的 SaaS 会被 AI agent 替代、什么定位/叙事是 Alex 应该 take(or avoid)。例:"Anthropic 10x 增长 + 同行裁员 — 印证 OSS infrastructure 路线是反向 bet,Solo Founder OS 应该明确不学 SaaS pricing,走 self-hostable 路线"。这条是写给"未来 3-12 个月的 Alex"看的。

### AUDIT ###
**Look back — 上周/昨天押注 audit**。看下面的"Yesterday / 7-day-ago brief"input:
- 如果有 D-1 brief:挑出昨天 takeaway 或 STRATEGIC 里的核心观点,1 句话 audit "今天有没有验证 / 反驳 / 进展"
- 如果有 D-7 brief:挑出 7 天前的核心 thesis,1 句话 audit "7 天后看,这条 hold up 了吗?"
- 如果两个都没有(Day 1 或前几天):坦诚说"还没有积累足够的历史 brief 做 audit,从 Day 8 起这个 section 就有内容了"。**不要硬编造**。

### WRAP ###
一句话 wrap — ≤ 30 字 收尾。

---

格式细节:
- 文本里可以用 *强调*、链接 [text](url)、`code`、bullet `-` — 会被渲染成 HTML
- 不要在 section 内部用 `### ... ###` 三井号(那是 delimiter 专用)
- 不要用 markdown H1/H2 标题(`#` / `##`),section 标题我已经有了
- 总长 controlled: 1800-2500 字 中文 (加了 strategic + audit 后稍长)
- 不要硬塞,没货就坦诚说没货(takeaway 和 lesson 必须有)"""

    user_content = f"""今天的 news input:

{news_block}

---

今天的 SpaceX brief (SPACEX section reference,不要 verbatim copy,提炼):
**Freshness: {spacex_freshness}** ({"today" if spacex_freshness == "today" else f"⚠ FALLBACK to most recent, {spacex_freshness}"})

{spacex_block if spacex_block else "(no SpaceX brief today)"}

---

Polymarket / 预测市场 status (POLYMARKET section reference):
{polymarket_status}

---

**今早 markets news scan (NY 09:00 ET, freshness: {morning_news_freshness})** — 已经过滤到 14-ticker watchlist + sector keyword,Claude 标了 HIGH/MED/LOW impact:

{(morning_news[:3500] if morning_news else "(news-morning 没跑或没数据)")}

---

今天的 curriculum topic (LESSON section):
Day {day_n}, Phase: {phase}
Topic: {topic}

---

**历史 brief (for AUDIT section)**:
{lookback_block}

---

现在按 9 个 delimiter 严格输出 brief。"""

    resp = client.messages.create(
        model=DEEP_MODEL,
        max_tokens=5000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    text = ""
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text += block.text
    text = text.strip()

    # Strip any leading code fence if Claude added it
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)

    # Parse delimiter format: ### KEY ### lines
    section_map = {
        "TAKEAWAY": "takeaway",
        "PEOPLE": "people",
        "NEWS": "news",
        "SPACEX": "spacex",
        "POLYMARKET": "polymarket",
        "LESSON": "lesson",
        "STACK": "stack_links",
        "STRATEGIC": "strategic",
        "AUDIT": "audit",
        "WRAP": "wrap",
    }
    parts: dict = {v: "" for v in section_map.values()}

    # Split on lines that are exactly "### KEY ###"
    pattern = re.compile(r"^\s*###\s+([A-Z]+)\s+###\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        print("[daily-brief] no delimiters found, dumping raw to news", file=sys.stderr)
        parts["takeaway"] = "(delimiter 解析失败,见下方原文)"
        parts["news"] = text
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
# INLINE MARKDOWN → HTML (for body text inside sections)
# ────────────────────────────────────────────────────────────────────

def inline_md(text: str) -> str:
    """Convert inline markdown (links, bold, code) + paragraphs/lists → HTML.
    Used per-section, not for full doc."""
    if not text:
        return ""

    lines = text.split("\n")
    out_blocks = []
    para_buffer = []
    list_buffer = []

    def flush_para():
        if para_buffer:
            joined = " ".join(para_buffer).strip()
            if joined:
                out_blocks.append(f"<p>{inline_format(joined)}</p>")
            para_buffer.clear()

    def flush_list():
        if list_buffer:
            items = "".join(f"<li>{inline_format(it)}</li>" for it in list_buffer)
            out_blocks.append(f"<ul>{items}</ul>")
            list_buffer.clear()

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            flush_list()
            continue
        if re.match(r"^\s*[-*]\s+", line):
            flush_para()
            item = re.sub(r"^\s*[-*]\s+", "", line)
            list_buffer.append(item)
        else:
            flush_list()
            para_buffer.append(line.strip())

    flush_para()
    flush_list()
    return "\n".join(out_blocks)


def inline_format(s: str) -> str:
    """Inline transformations on a single string of text."""
    # Escape first
    s = html_lib.escape(s)
    # Inline code `...`
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    # Bold **...** or *...* → <strong>
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<em>\1</em>", s)
    # Markdown links [text](url) — but we escaped < > already so urls might have &amp;
    s = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        lambda m: f'<a href="{m.group(2).replace("&amp;","&")}" target="_blank" rel="noopener">{m.group(1)}</a>',
        s,
    )
    # Bare urls
    s = re.sub(
        r"(?<![\">])(https?://[^\s<)]+)",
        r'<a href="\1" target="_blank" rel="noopener">\1</a>',
        s,
    )
    return s


# ────────────────────────────────────────────────────────────────────
# RENDER BOOK-QUALITY HTML
# ────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --ink: #1a1a1a;
    --ink-soft: #4a4a4a;
    --ink-dim: #707070;
    --paper: #fbfaf6;
    --rule: #cfc8b8;
    --accent: #8c3a14;
    --accent-soft: #f0e3d4;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; padding: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
                 "Songti SC", "Noto Serif CJK SC", "Source Han Serif SC", Georgia, serif;
    font-size: 17px; line-height: 1.78;
    -webkit-font-smoothing: antialiased;
  }}
  .page {{ max-width: 720px; margin: 0 auto; padding: 56px 28px 80px; }}
  .masthead {{
    display: flex; justify-content: space-between; align-items: baseline;
    border-bottom: 2px solid var(--ink);
    padding-bottom: 8px; margin-bottom: 28px;
  }}
  .masthead .title-block {{ }}
  .masthead h1 {{
    font-family: ui-serif, Georgia, "Source Han Serif SC", serif;
    font-size: 32px; font-weight: 700; letter-spacing: -0.5px;
    margin: 0 0 4px; color: var(--ink);
  }}
  .masthead .subtitle {{
    font-size: 13px; color: var(--ink-dim); text-transform: uppercase; letter-spacing: 1.5px;
  }}
  .masthead .day-badge {{
    font-family: ui-serif, Georgia, serif;
    font-size: 14px; color: var(--accent);
    text-align: right;
  }}
  .masthead .day-badge .num {{
    font-size: 28px; font-weight: 700; display: block; line-height: 1;
  }}
  .masthead .day-badge .label {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 2px; color: var(--ink-dim);
  }}

  section.entry {{ margin: 36px 0; }}
  section.entry h2 {{
    font-family: ui-serif, Georgia, serif;
    font-size: 20px; font-weight: 700;
    color: var(--ink);
    margin: 0 0 14px;
    padding-bottom: 6px;
    border-bottom: 1px dashed var(--rule);
  }}
  section.entry h2 .sec-num {{
    color: var(--accent); font-size: 14px; margin-right: 8px;
    font-family: ui-monospace, SF Mono, Menlo, monospace;
  }}
  section.entry p {{ margin: 0 0 14px; color: var(--ink-soft); }}
  section.entry ul {{ margin: 0 0 14px 0; padding-left: 22px; }}
  section.entry li {{ margin-bottom: 8px; color: var(--ink-soft); }}
  section.entry a {{ color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--accent-soft); }}
  section.entry a:hover {{ border-bottom-color: var(--accent); }}
  section.entry code {{
    font-family: ui-monospace, SF Mono, Menlo, monospace;
    font-size: 13px; background: var(--accent-soft); padding: 1px 5px; border-radius: 3px;
    color: var(--accent);
  }}
  section.entry strong {{ color: var(--ink); font-weight: 600; }}
  section.entry em {{ color: var(--ink); font-style: italic; }}

  .pullquote {{
    margin: 28px 0;
    padding: 18px 22px;
    border-left: 3px solid var(--accent);
    background: var(--accent-soft);
    font-family: ui-serif, Georgia, serif;
    font-size: 19px; line-height: 1.6;
    color: var(--ink);
    font-style: italic;
  }}
  .lesson-banner {{
    margin: 18px 0 22px;
    padding: 10px 14px;
    background: var(--accent-soft);
    border-left: 3px solid var(--accent);
  }}
  .lesson-banner .meta {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 2px; color: var(--ink-dim);
    margin-bottom: 4px;
  }}
  .lesson-banner .topic {{
    font-family: ui-serif, Georgia, serif; font-size: 18px; font-weight: 700; color: var(--ink);
    line-height: 1.4;
  }}

  .colophon {{
    margin-top: 60px; padding-top: 18px; border-top: 1px solid var(--rule);
    font-size: 12px; color: var(--ink-dim); text-align: center; line-height: 1.6;
  }}
  .colophon .quote {{ font-style: italic; }}
  @media (max-width: 600px) {{
    .page {{ padding: 32px 18px 56px; }}
    body {{ font-size: 16px; }}
    .masthead h1 {{ font-size: 26px; }}
    .masthead .day-badge .num {{ font-size: 22px; }}
  }}
</style>
</head>
<body>
<div class="page">
  <header class="masthead">
    <div class="title-block">
      <h1>Daily Brief</h1>
      <div class="subtitle">Alex 的 AI 日记 · 第 {issue_no} 期</div>
    </div>
    <div class="day-badge">
      <span class="num">{day_n}</span>
      <span class="label">Day · {phase_short}</span>
    </div>
  </header>

  <div class="pullquote">{takeaway_html}</div>

  <section class="entry">
    <h2><span class="sec-num">§1</span>AI 人物动态</h2>
    {people_html}
  </section>

  <section class="entry">
    <h2><span class="sec-num">§2</span>AI 新闻摘要</h2>
    {news_html}
  </section>

  <section class="entry">
    <h2><span class="sec-num">§3</span>SpaceX 跟踪</h2>
    {spacex_html}
  </section>

  <section class="entry">
    <h2><span class="sec-num">§3.5</span>Polymarket / 预测市场</h2>
    {polymarket_html}
  </section>

  <section class="entry">
    <h2><span class="sec-num">§4</span>今日 AI 学习</h2>
    <div class="lesson-banner">
      <div class="meta">Curriculum · Day {day_n} · {phase_short}</div>
      <div class="topic">{topic_safe}</div>
    </div>
    {lesson_html}
  </section>

  <section class="entry">
    <h2><span class="sec-num">§5</span>对现有 stack 的影响</h2>
    {stack_html}
  </section>

  <section class="entry">
    <h2><span class="sec-num">§6</span>对未来创业的影响</h2>
    {strategic_html}
  </section>

  <section class="entry">
    <h2><span class="sec-num">§7</span>历史 audit · 上周押注</h2>
    {audit_html}
  </section>

  <div class="pullquote">{wrap_html}</div>

  <div class="colophon">
    <div>{date_human}</div>
    <div class="quote">这些都是宝贵材料 — 写日记是为了以后写书</div>
    <div style="margin-top:4px">Generated by claude-sonnet-4-6 · NY 12:00 ET cron</div>
  </div>
</div>
</body>
</html>"""


def render_html(parts: dict, day_n: int, phase: str, topic: str, date_str: str) -> str:
    phase_short = phase.split("—", 1)[-1].strip() if "—" in phase else phase
    date_human = datetime.now().strftime("%Y年 %m月 %d日 · %A")

    return HTML_TEMPLATE.format(
        title=f"Daily Brief · Day {day_n} — {topic[:60]}",
        issue_no=day_n,
        day_n=day_n,
        phase_short=html_lib.escape(phase_short),
        topic_safe=html_lib.escape(topic),
        date_human=html_lib.escape(date_human),
        takeaway_html=inline_format(parts.get("takeaway", "")),
        people_html=inline_md(parts.get("people", "")),
        news_html=inline_md(parts.get("news", "")),
        spacex_html=inline_md(parts.get("spacex", "")),
        polymarket_html=inline_md(parts.get("polymarket", "")),
        lesson_html=inline_md(parts.get("lesson", "")),
        stack_html=inline_md(parts.get("stack_links", "")),
        strategic_html=inline_md(parts.get("strategic", "")),
        audit_html=inline_md(parts.get("audit", "")),
        wrap_html=inline_format(parts.get("wrap", "")),
    )


def render_md_sidecar(parts: dict, day_n: int, phase: str, topic: str, date_str: str) -> str:
    """Grep-friendly markdown sidecar (committed to brain repo)."""
    return f"""---
date: {date_str}
curriculum_day: {day_n}
curriculum_phase: "{phase}"
curriculum_topic: "{topic}"
generated_at: {datetime.now(timezone.utc).isoformat()}
---

# Daily Brief — {date_str} · Day {day_n}

> {parts.get("takeaway", "")}

## §1 AI 人物动态
{parts.get("people", "")}

## §2 AI 新闻摘要
{parts.get("news", "")}

## §3 SpaceX 跟踪
{parts.get("spacex", "")}

## §3.5 Polymarket / 预测市场
{parts.get("polymarket", "")}

## §4 今日 AI 学习 — Day {day_n}: {topic}
*Phase: {phase}*

{parts.get("lesson", "")}

## §5 对现有 stack 的影响
{parts.get("stack_links", "")}

## §6 对未来创业的影响
{parts.get("strategic", "")}

## §7 历史 audit · 上周押注
{parts.get("audit", "")}

---

**{parts.get("wrap", "")}**
"""


# ────────────────────────────────────────────────────────────────────
# EMAIL
# ────────────────────────────────────────────────────────────────────

def send_email_resend(subject: str, html_body: str, text_body: str) -> bool:
    if not RESEND_API_KEY:
        print(f"[dry-run] would send: '{subject}' to {EMAIL_TO} (RESEND_API_KEY unset)")
        return False

    import urllib.request
    payload = json.dumps({
        "from": EMAIL_FROM,
        "to": [EMAIL_TO],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "daily-brief/1.0 (+alex-jb)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"sent: id={result.get('id', '?')}")
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        print(f"resend send failed: HTTP {exc.code} — body: {body}")
        print(f"  payload was: from={EMAIL_FROM!r}, to={[EMAIL_TO]!r}, subject={subject!r}, key_len={len(RESEND_API_KEY)}")
        return False
    except Exception as exc:
        print(f"resend send failed: {exc!r}")
        return False


# ────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────

def main():
    if not ANTHROPIC_API_KEY:
        print("FATAL: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[daily-brief] {today_str} starting...")

    print("[daily-brief] fetching AI news...")
    news = fetch_ai_news()

    print("[daily-brief] reading SpaceX brief...")
    spacex_brief, spacex_freshness = get_today_spacex_brief()
    print(f"[daily-brief] spacex freshness: {spacex_freshness}")

    print("[daily-brief] reading Polymarket status...")
    polymarket_status = get_polymarket_status()

    print("[daily-brief] reading today's markets news scan...")
    morning_news, morning_news_freshness = get_morning_news_brief()
    print(f"[daily-brief] news-morning freshness: {morning_news_freshness}")

    day_n, phase, topic, phase_idx = get_today_curriculum()
    print(f"[daily-brief] curriculum: Day {day_n} ({phase}) — {topic}")

    print("[daily-brief] reading lookback briefs (D-1 / D-7)...")
    lookback = get_lookback_briefs()
    print(f"[daily-brief] lookback: D-1={'yes' if lookback['d1'] else 'no'}, D-7={'yes' if lookback['d7'] else 'no'}")

    print("[daily-brief] compiling with Claude Sonnet 4.6 (delimiter format, 10 sections)...")
    parts = compile_brief(news, spacex_brief, spacex_freshness, polymarket_status,
                           morning_news, morning_news_freshness,
                           day_n, phase, topic, phase_idx, lookback)

    html_body = render_html(parts, day_n, phase, topic, today_str)
    md_sidecar = render_md_sidecar(parts, day_n, phase, topic, today_str)

    BRAIN_BRIEF_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_BRIEF_DIR.mkdir(parents=True, exist_ok=True)
    brain_html = BRAIN_BRIEF_DIR / f"{today_str}.html"
    brain_md = BRAIN_BRIEF_DIR / f"{today_str}.md"
    local_html = LOCAL_BRIEF_DIR / f"{today_str}.html"
    brain_html.write_text(html_body, encoding="utf-8")
    brain_md.write_text(md_sidecar, encoding="utf-8")
    local_html.write_text(html_body, encoding="utf-8")
    print(f"[daily-brief] wrote {brain_html}")
    print(f"[daily-brief] wrote {brain_md}")
    print(f"[daily-brief] wrote {local_html}")

    subject = f"Daily Brief · Day {day_n} — {topic[:50]}"
    sent = send_email_resend(subject, html_body, md_sidecar)

    if not sent:
        import subprocess
        subprocess.run(["open", str(brain_html)], check=False)

    # Heartbeat: written ONLY after a complete successful run reaches
    # this point. Stale (>25h) = silent cron failure. Check via
    # `python3 ~/.orallexa/daily-brief/scripts/heartbeat_check.py` or
    # eyeball: `stat ~/.orallexa/daily-brief/.last_success`.
    heartbeat = DAILY_BRIEF_DIR / ".last_success"
    heartbeat.write_text(datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8")

    print("[daily-brief] done.")


if __name__ == "__main__":
    main()
