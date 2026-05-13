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


POLYMARKET_STATUS_FILE = Path.home() / ".orallexa" / "markets" / ".polymarket_status.json"


def polymarket_heartbeat() -> dict:
    """Try a lightweight reach to Polymarket's public Gamma API.
    Writes status JSON to disk. Returns the status dict.

    OK now = Cloudflare IP ban is lifted, we can re-enable markets cron.
    """
    status = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "reachable": False,
        "http_code": None,
        "error": None,
        "last_ok_at": None,
    }
    # Preserve historical last_ok_at across runs
    if POLYMARKET_STATUS_FILE.exists():
        try:
            prev = json.loads(POLYMARKET_STATUS_FILE.read_text())
            status["last_ok_at"] = prev.get("last_ok_at")
        except Exception:
            pass

    try:
        # Try curl_cffi if installed (matches markets/polymarket_client.py
        # TLS-fingerprint pattern); fall back to urllib otherwise.
        try:
            from curl_cffi import requests as cf_requests
            r = cf_requests.get(
                "https://gamma-api.polymarket.com/markets?limit=1",
                impersonate="chrome", timeout=10,
            )
            status["reachable"] = (r.status_code == 200)
            status["http_code"] = r.status_code
        except ImportError:
            req = urllib.request.Request(
                "https://gamma-api.polymarket.com/markets?limit=1",
                headers={"User-Agent": "polymarket-heartbeat/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status["reachable"] = (resp.status == 200)
                status["http_code"] = resp.status
    except Exception as exc:
        status["error"] = repr(exc)[:200]

    if status["reachable"]:
        status["last_ok_at"] = status["checked_at"]

    POLYMARKET_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    POLYMARKET_STATUS_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


def fetch_insider_transactions(days_back: int = 14) -> list[dict]:
    """For each watchlist ticker, pull insider Form 4 transactions via
    yfinance (cleaner than parsing SEC EDGAR XML directly). Filter to
    material trades: last `days_back` days + position is Director / CEO /
    CFO / 10%+ owner. Returns list of dicts ready for brief rendering.
    """
    try:
        import yfinance as yf
    except ImportError:
        return []

    cutoff = datetime.now(timezone.utc).date() - __import__("datetime").timedelta(days=days_back)
    MATERIAL_POSITIONS = ("Director", "Chief Executive", "Chief Financial", "President",
                          "10% Owner", "Beneficial Owner")

    rows = []
    for ticker in WATCHLIST:
        try:
            df = yf.Ticker(ticker).insider_transactions
        except Exception:
            continue
        if df is None or len(df) == 0:
            continue

        for _, r in df.iterrows():
            try:
                start = r.get("Start Date")
                if start is None:
                    continue
                # yfinance returns timezone-naive Timestamp
                if hasattr(start, "date"):
                    txn_date = start.date()
                else:
                    txn_date = datetime.fromisoformat(str(start)[:10]).date()
                if txn_date < cutoff:
                    continue
                position = str(r.get("Position", "")).strip()
                if not any(mp.lower() in position.lower() for mp in MATERIAL_POSITIONS):
                    continue
                text = str(r.get("Text", "")).strip()
                shares = r.get("Shares", 0) or 0
                value = r.get("Value", 0) or 0
                try:
                    value = float(value) if not __import__("math").isnan(float(value)) else 0
                except Exception:
                    value = 0
                insider = str(r.get("Insider", "")).strip()
                direction = "🔴 SELL" if "sale" in text.lower() else \
                             "🟢 BUY" if "purchase" in text.lower() or "buy" in text.lower() else \
                             "🟡 OTHER"
                rows.append({
                    "ticker": ticker,
                    "date": txn_date.isoformat(),
                    "insider": insider,
                    "position": position,
                    "direction": direction,
                    "shares": int(shares) if shares else 0,
                    "value_usd": float(value) if value else 0,
                    "text": text[:100],
                })
            except Exception:
                continue

    # Sort: most recent first, then by value desc
    rows.sort(key=lambda x: (x["date"], x["value_usd"]), reverse=True)
    return rows


def render_insider_section(rows: list[dict]) -> str:
    """Markdown section for the brief."""
    if not rows:
        return ""
    out = ["", "## 📋 Recent insider activity (last 14d, watchlist, material positions only)", ""]
    out.append("| Date | Dir | Ticker | Insider | Position | Shares | Value | Note |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in rows[:15]:
        val_str = f"${r['value_usd']/1e6:.2f}M" if r["value_usd"] >= 1e6 else \
                  f"${r['value_usd']/1e3:.0f}K" if r["value_usd"] >= 1000 else "—"
        position_short = r["position"][:30] + "…" if len(r["position"]) > 30 else r["position"]
        out.append(
            f"| {r['date']} | {r['direction']} | **{r['ticker']}** | {r['insider'][:25]} | "
            f"{position_short} | {r['shares']:,} | {val_str} | {r['text'][:50]} |"
        )
    return "\n".join(out) + "\n"


def render_polymarket_alert(status: dict) -> str:
    """Return a 1-line markdown alert for the brief, or '' if no change."""
    if status["reachable"]:
        return (
            f"\n## 🟢 Polymarket IP UNBANNED — back online ({status['http_code']})\n\n"
            f"Reached Gamma API at {status['checked_at']}. **Action:** "
            f"re-enable `com.orallexa.polymarket-daily` cron + start logging "
            f"event picks for Brier audit.\n"
        )
    elif status.get("last_ok_at"):
        return (
            f"\n_Polymarket still offline (last OK: {status['last_ok_at']}). "
            f"Error: {status.get('error', 'http ' + str(status.get('http_code')))}._\n"
        )
    else:
        return (
            f"\n_Polymarket still IP-banned ({status.get('error') or status.get('http_code')})._\n"
        )


def main() -> int:
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRAIN_DIR / f"{today_str}.md"

    print(f"[news-morning] {today_str} starting...")

    # Heartbeat poll — every 09:00 run checks if Polymarket IP-ban lifted
    poly_status = polymarket_heartbeat()
    print(f"[news-morning] polymarket reachable={poly_status['reachable']} (last OK: {poly_status.get('last_ok_at')})")
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

    # Pull insider Form 4 transactions for the watchlist
    print(f"[news-morning] fetching insider transactions (14d)...")
    insider_rows = fetch_insider_transactions(days_back=14)
    print(f"[news-morning]   {len(insider_rows)} material insider trades")
    insider_section = render_insider_section(insider_rows)

    body = f"""---
date: {today_str}
generated_at: {datetime.now(timezone.utc).isoformat()}
sources: {len(FEEDS)}
raw_items: {len(all_items)}
filtered_items: {len(filtered)}
insider_trades: {len(insider_rows)}
polymarket_reachable: {poly_status['reachable']}
---

# Markets pre-market news — {today_str}

Sources: {', '.join(label for label, _ in FEEDS)}.
Watchlist: 14 tickers across 4 sectors (太空 / 物理AI / AI infra / 无人机).

{table}
{render_polymarket_alert(poly_status)}
{insider_section}

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
