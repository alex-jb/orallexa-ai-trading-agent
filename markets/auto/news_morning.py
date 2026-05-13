"""news_morning.py — NY 09:00 ET pre-market news scan.

Pulls RSS feeds (FT / Bloomberg headlines from public mirrors, SEC EDGAR
filings, Yahoo Finance ticker-specific RSS), filters to today's 14-ticker
watchlist + sector keywords (space / robotics / AI infra / drones / defense),
asks Claude Sonnet 4.6 to tag impact (HIGH / MED / LOW), and writes a
markdown brief to:

  ~/Desktop/Interview-Prep/Projects/alex-brain/research/markets-news/YYYY-MM-DD.md

Designed to fail gracefully — no API key, no network → write a stub
placeholder rather than crash. Output gets read by spacex-daily.sh
(post-process step in a future enhancement) and by daily-brief
(curriculum cron at NY 12:00 can also reference it).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
BRAIN_DIR = HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain" / "research" / "markets-news"

# 14-ticker watchlist (sync with spacex-daily.sh)
WATCHLIST = [
    "RKLB", "ASTS", "LUNR", "BKSY", "PL", "RDW", "LMT", "LIN",
    "TSLA", "SYM", "NVDA", "AVGO", "AVAV", "KTOS",
]

# Sector keywords for broader filtering — catch news about the SECTOR
# even if the specific ticker isn't named
SECTOR_KEYWORDS = (
    # space
    "spacex", "starship", "satellite", "earth observation", "iss",
    "rocket lab", "ast spacemobile", "intuitive machines", "planet labs",
    "redwire", "blacksky",
    # physical AI / robotics
    "optimus", "humanoid", "robotaxi", "tesla bot", "symbotic", "warehouse robot",
    # AI infra
    "nvidia", "broadcom", "h100", "b100", "blackwell", "ai datacenter",
    "ai capex", "tsmc",
    # drones / defense
    "aerovironment", "kratos", "switchblade", "uav", "uas", "drone strike",
    "lockheed martin", "defense contract", "pentagon",
)

# RSS feeds (public, no auth required)
FEEDS = [
    ("Yahoo Finance — markets", "https://finance.yahoo.com/news/rssindex"),
    ("CNBC — markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
    ("CNBC — tech", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910"),
    ("Reuters — business", "https://feeds.reuters.com/reuters/businessNews"),
    ("SEC EDGAR — 8-K filings", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom"),
]


def fetch_feed(url: str, max_items: int = 30) -> list[dict]:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        return [{"error": f"feed fetch failed: {exc}", "url": url}]

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


_TICKER_RES = {t: re.compile(rf"\b{t}\b") for t in WATCHLIST}


def filter_to_watchlist(items: list[dict]) -> list[dict]:
    """Keep items mentioning a watchlist ticker OR a sector keyword.

    Tickers matched as WHOLE-WORD only (case-sensitive uppercase) so we
    don't false-positive on 'PL' inside 'cdt equity advances astrazeneca PLC'
    or 'LIN' inside 'pipeline'. Sector keywords matched case-insensitive
    substring (they're long enough to not collide).
    """
    keep = []
    for it in items:
        if "error" in it:
            continue
        title = it["title"]
        summary = it.get("summary", "")
        full = title + " " + summary
        haystack_lower = full.lower()
        # Whole-word uppercase ticker match
        matched_tickers = [t for t, pat in _TICKER_RES.items() if pat.search(full)]
        # Sector keywords are 5+ chars phrases — substring lowercase is safe
        matched_sector = [kw for kw in SECTOR_KEYWORDS if kw in haystack_lower]
        if matched_tickers or matched_sector:
            it["matched_tickers"] = matched_tickers
            it["matched_sector"] = matched_sector
            keep.append(it)
    return keep


def claude_tag_impact(items: list[dict]) -> str:
    """Send filtered items to Claude → returns ranked markdown."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _stub_render(items, reason="ANTHROPIC_API_KEY not set")

    try:
        from anthropic import Anthropic
    except ImportError:
        return _stub_render(items, reason="anthropic SDK not installed")

    if not items:
        return "(没有 watchlist 相关新闻今天 — 安静的 pre-market)"

    items_block = "\n".join(
        f"- **[{','.join(it.get('matched_tickers', []))}]** {it['title']}\n"
        f"  {it.get('summary', '')[:200]}\n"
        f"  {it['url']}"
        for it in items[:25]
    )

    system_prompt = (
        "你是 Alex 的 markets news triage 助手。\n"
        "Alex 的 14-ticker watchlist: RKLB / ASTS / LUNR / BKSY / PL / RDW / LMT / LIN / "
        "TSLA / SYM / NVDA / AVGO / AVAV / KTOS (4 sector: 太空 / 物理AI / AI infra / 无人机).\n"
        "用中文输出,简洁,不要 hype。每条新闻判断 HIGH / MED / LOW impact + 1 句 angle。"
    )

    user_content = f"""今天 pre-market 抓到 {len(items)} 条新闻 (已过滤到 watchlist + sector keywords):

{items_block}

---

任务:
1. 排序按 impact (HIGH 在最上)
2. 去重 (同一事件不同来源合并)
3. 输出 markdown 表格:

| Impact | Tickers | Headline (中文) | Angle |
|---|---|---|---|

每条 Angle 1 句话:Alex 该如何 read 这条 → 加仓 / 减仓 / 中立观察。

最多 8 条,刷掉低质 clickbait + 政治噪音 + 一般行业 trend。

直接出表格,不要前后客套。"""

    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    text = ""
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text += block.text
    return text.strip()


def _stub_render(items: list[dict], reason: str) -> str:
    out = [f"⚠ Claude 未调用 ({reason})。原始抓到 {len(items)} 条:\n"]
    for it in items[:15]:
        tickers = ",".join(it.get("matched_tickers", [])) or "—"
        out.append(f"- [{tickers}] {it['title']}\n  {it['url']}")
    return "\n".join(out)


def main() -> int:
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRAIN_DIR / f"{today_str}.md"

    print(f"[news-morning] {today_str} starting...")
    all_items = []
    for label, url in FEEDS:
        items = fetch_feed(url, max_items=30)
        ok = [i for i in items if "error" not in i]
        print(f"[news-morning]   {label}: {len(ok)} items")
        for i in ok:
            i["source"] = label
        all_items.extend(ok)

    print(f"[news-morning] total raw: {len(all_items)}")
    filtered = filter_to_watchlist(all_items)
    print(f"[news-morning] filtered to watchlist+sector: {len(filtered)}")

    table = claude_tag_impact(filtered)

    body = f"""---
date: {today_str}
generated_at: {datetime.now(timezone.utc).isoformat()}
sources: {len(FEEDS)}
raw_items: {len(all_items)}
filtered_items: {len(filtered)}
---

# Markets pre-market news — {today_str}

Sources: {', '.join(label for label, _ in FEEDS)}.
Watchlist: 14 tickers across 4 sectors (太空 / 物理AI / AI infra / 无人机).

{table}

---

## Raw filtered items (full list)

"""
    for it in filtered[:25]:
        tickers = ",".join(it.get("matched_tickers", [])) or "—"
        sector = ",".join(it.get("matched_sector", [])[:3]) or "—"
        body += f"- **[{tickers}] [{sector}]** {it['title']}\n  - {it['url']}\n"

    out_path.write_text(body, encoding="utf-8")
    print(f"[news-morning] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
