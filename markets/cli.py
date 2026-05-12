"""orallexa-markets CLI — v0.1 read-only surface.

Subcommands:
    list-kalshi      List open Kalshi markets (demo by default)
    list-polymarket  List active Polymarket markets (read-only Gamma)
    debate           Run one Bull/Bear/Judge debate on a single market
    queue            Fetch top markets + debate + write HITL morning queue

Usage:
    python -m markets list-kalshi --limit 10
    python -m markets list-polymarket --limit 10 --category geopolitics
    python -m markets debate --platform kalshi --ticker POTUS-2028-DEM
    python -m markets queue --platform polymarket --limit 5 --bankroll 300

The CLI deliberately exposes NO trading subcommand. There is no path
from this entrypoint to placing an order. Every trade is placed by hand
on kalshi.com or polymarket.com.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from markets.market import BinaryMarket
from markets.kalshi_client import KalshiClient, KalshiConfig
from markets.polymarket_client import PolymarketClient
from markets.event_debate import run_event_debate
from markets.queue import QueueWriter, QueueEntry
from markets.sizing import SizingConfig, size_position
from markets.pnl_tracker import (
    harvest_decided_dir, PositionLedger, compute_pnl,
)
from markets.retro import run_retro, make_lookup_from_clients
from markets.scheduler import SchedulerConfig, install as scheduler_install


def _print_market_row(m: BinaryMarket) -> None:
    price = f"{m.yes_price:.3f}" if m.yes_price is not None else "  —  "
    vol = f"${m.volume:,.0f}" if m.volume else "—"
    print(
        f"  [{m.platform:10s}] {m.ticker[:40]:40s} "
        f"YES={price}  vol={vol:>14s}  cat={m.category}"
    )


def cmd_list_kalshi(args) -> int:
    config = KalshiConfig.prod() if args.prod else KalshiConfig.demo()
    client = KalshiClient(config=config)
    env = "prod" if args.prod else "demo"
    print(f"Kalshi ({env}) — first {args.limit} open markets:")
    count = 0
    for m in client.iter_markets(status="open", max_pages=3):
        if count >= args.limit:
            break
        _print_market_row(m)
        count += 1
    if count == 0:
        print("  (no markets returned — check connectivity / endpoint)")
    return 0


def cmd_list_polymarket(args) -> int:
    client = PolymarketClient()
    print(
        f"Polymarket (Gamma, read-only) — top {args.limit} by 24h volume "
        f"(min_vol24={args.min_volume_24hr}, min_liq={args.min_liquidity}"
        f"{', meme events excluded' if not args.include_memes else ''}):"
    )
    count = 0
    for m in client.iter_markets(
        active=True,
        max_pages=3,
        min_volume_24hr=args.min_volume_24hr,
        min_liquidity=args.min_liquidity,
        exclude_meme_events=not args.include_memes,
    ):
        if count >= args.limit:
            break
        _print_market_row(m)
        count += 1
    if count == 0:
        print("  (no markets returned — try lowering --min-volume-24hr)")
    return 0


def _fetch_one(platform: str, ticker: str, prod: bool) -> Optional[BinaryMarket]:
    if platform == "kalshi":
        config = KalshiConfig.prod() if prod else KalshiConfig.demo()
        return KalshiClient(config=config).get_market(ticker)
    if platform == "polymarket":
        return PolymarketClient().get_market(ticker)
    raise ValueError(f"unknown platform: {platform}")


def cmd_debate(args) -> int:
    m = _fetch_one(args.platform, args.ticker, prod=args.prod)
    if m is None:
        print(f"Market not found: {args.platform}/{args.ticker}", file=sys.stderr)
        return 1
    print(f"\n## {m.question}")
    print(f"   {m.platform}/{m.ticker}  YES={m.yes_price}")
    print("   Running debate (Bull/Bear Haiku → Judge Sonnet)...")
    result = run_event_debate(m, news_context=args.context or "")
    print()
    print(f"   p_yes      = {result.p_yes:.3f}")
    print(f"   market     = {m.yes_price}")
    edge = result.edge
    if edge is not None:
        print(f"   edge       = {edge:+.3f}")
    print()
    print("─── Judge reasoning ───")
    print(result.judge_reasoning)
    if result.evidence_for:
        print("\n─── Evidence FOR ───")
        for e in result.evidence_for:
            print(f"  - {e}")
    if result.evidence_against:
        print("\n─── Evidence AGAINST ───")
        for e in result.evidence_against:
            print(f"  - {e}")
    return 0


def cmd_queue(args) -> int:
    sizing = SizingConfig(bankroll_usd=args.bankroll)

    if args.platform == "kalshi":
        config = KalshiConfig.prod() if args.prod else KalshiConfig.demo()
        client = KalshiClient(config=config)
        markets = list(client.iter_markets(status="open", max_pages=3))
    elif args.platform == "polymarket":
        client = PolymarketClient()
        markets = list(
            client.iter_markets(
                active=True,
                max_pages=3,
                min_volume_24hr=args.min_volume_24hr,
                min_liquidity=args.min_liquidity,
                exclude_meme_events=not args.include_memes,
            )
        )
    else:
        print(f"unknown platform: {args.platform}", file=sys.stderr)
        return 1

    # Filter to highest-volume markets to avoid running debates on thin
    # ones where slippage will dominate any edge.
    markets = sorted(markets, key=lambda m: m.volume, reverse=True)[: args.limit]

    if not markets:
        print("no markets returned; nothing to queue.")
        return 0

    writer = QueueWriter.default()
    written: list[str] = []
    for m in markets:
        print(f"  debating {m.platform}/{m.ticker[:40]}...")
        debate = run_event_debate(m, news_context="")
        if m.yes_price is None:
            sizing_result = None
            position_usd = 0.0
            sizing_notes = "no market price; skipping sizing"
        else:
            sizing_result = size_position(
                p_yes=debate.p_yes, market_price=m.yes_price, config=sizing
            )
            position_usd = sizing_result.position_usd
            sizing_notes = sizing_result.notes
            if sizing_result.skip_reason:
                sizing_notes = (
                    f"SKIP: {sizing_result.skip_reason} — {sizing_result.notes}"
                )

        entry = QueueEntry(
            market=m,
            debate=debate,
            suggested_position_usd=position_usd,
            sizing_notes=sizing_notes,
        )
        path = writer.write(entry)
        written.append(str(path))

    print()
    print(f"Wrote {len(written)} queue cards to {writer.root / 'pending'}/")
    for p in written:
        print(f"  {p}")
    return 0


def cmd_pnl(args) -> int:
    """Harvest decided cards + print PnL summary against live outcomes."""
    decisions = harvest_decided_dir()
    ledger = PositionLedger.default()
    new_rows = ledger.append(decisions)
    if new_rows:
        print(f"Appended {new_rows} new decisions to {ledger.path}")
    all_decisions = ledger.load_all()
    if not all_decisions:
        print("Ledger empty. Move some decided/*.md cards into the decided/ dir first.")
        return 0
    lookup = make_lookup_from_clients(
        kalshi_client=KalshiClient(KalshiConfig.prod() if args.prod else KalshiConfig.demo()),
        polymarket_client=PolymarketClient(),
    )
    rows = compute_pnl(all_decisions, outcome_lookup=lookup)
    total = sum(r.realized_pnl_usd for r in rows if r.settled)
    n_settled = sum(1 for r in rows if r.settled)
    n_open = sum(1 for r in rows if not r.settled and r.decision.decision != "PASS")
    print(f"\nLedger: {len(all_decisions)} decisions | settled={n_settled} open={n_open}")
    print(f"Realized PnL cumulative: ${total:+,.2f}")
    print()
    for r in rows:
        d = r.decision
        outcome_str = "YES" if r.outcome == 1 else "NO" if r.outcome == 0 else "—"
        pnl_str = f"${r.realized_pnl_usd:+,.2f}" if r.settled else "(open)"
        brier_str = f"brier={r.brier:.3f}" if r.brier is not None else ""
        print(
            f"  [{d.platform[:10]}] {d.ticker[:40]:40s} {d.decision:11s} "
            f"side={d.side or '—':3s} ${d.position_usd:6.2f}  "
            f"outcome={outcome_str:3s} {pnl_str:>10s}  {brier_str}"
        )
    return 0


def cmd_retro(args) -> int:
    lookup = make_lookup_from_clients(
        kalshi_client=KalshiClient(KalshiConfig.prod() if args.prod else KalshiConfig.demo()),
        polymarket_client=PolymarketClient(),
    )
    path, summary = run_retro(
        bankroll_start=args.bankroll, outcome_lookup=lookup, date=args.date
    )
    print(f"Wrote retro to {path}")
    print(f"  decisions today: {summary.n_decisions_today}")
    print(f"  settled / open:  {summary.n_settled} / {summary.n_open}")
    print(f"  PnL today:       ${summary.realized_pnl_today:+,.2f}")
    print(f"  PnL cumulative:  ${summary.realized_pnl_cumulative:+,.2f}")
    if summary.brier_mean is not None:
        baseline = (
            f"{summary.brier_market_baseline:.4f}"
            if summary.brier_market_baseline is not None else "—"
        )
        print(f"  Brier (LLM):     {summary.brier_mean:.4f}")
        print(f"  Brier (mkt):     {baseline}")
    if summary.kill_conditions_tripped:
        print("\n  ⚠️ kill conditions tripped:")
        for k in summary.kill_conditions_tripped:
            print(f"    - {k}")
    return 0


def cmd_scheduler_install(args) -> int:
    config = SchedulerConfig(
        queue_hour=args.queue_hour,
        retro_hour=args.retro_hour,
        platform=args.platform,
        bankroll=args.bankroll,
        queue_limit=args.queue_limit,
        repo_path=args.repo_path or "",
    )
    print(scheduler_install(config))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="orallexa-markets")
    sub = parser.add_subparsers(dest="cmd", required=True)

    lk = sub.add_parser("list-kalshi", help="List open Kalshi markets")
    lk.add_argument("--limit", type=int, default=10)
    lk.add_argument("--prod", action="store_true", help="Use prod base (default demo)")
    lk.set_defaults(func=cmd_list_kalshi)

    lp = sub.add_parser("list-polymarket", help="List active Polymarket markets")
    lp.add_argument("--limit", type=int, default=10)
    lp.add_argument(
        "--min-volume-24hr", type=float, default=5_000.0,
        help="Skip markets with <$X 24h volume (default $5k — keeps queue tight)",
    )
    lp.add_argument(
        "--min-liquidity", type=float, default=10_000.0,
        help="Skip markets with CLOB liquidity below $X (default $10k)",
    )
    lp.add_argument(
        "--include-memes", action="store_true",
        help="Include meme umbrella events like 'what-will-happen-before-gta-vi'",
    )
    lp.set_defaults(func=cmd_list_polymarket)

    d = sub.add_parser("debate", help="Run one debate")
    d.add_argument("--platform", choices=["kalshi", "polymarket"], required=True)
    d.add_argument("--ticker", required=True)
    d.add_argument("--prod", action="store_true")
    d.add_argument("--context", default="", help="Optional news context")
    d.set_defaults(func=cmd_debate)

    q = sub.add_parser("queue", help="Generate morning HITL queue")
    q.add_argument("--platform", choices=["kalshi", "polymarket"], required=True)
    q.add_argument("--limit", type=int, default=5)
    q.add_argument("--prod", action="store_true")
    q.add_argument("--bankroll", type=float, default=300.0)
    q.add_argument("--min-volume-24hr", type=float, default=10_000.0,
                   help="Polymarket only: skip markets with <$X 24h volume")
    q.add_argument("--min-liquidity", type=float, default=10_000.0,
                   help="Polymarket only: skip thin order books")
    q.add_argument("--include-memes", action="store_true",
                   help="Polymarket only: include meme umbrella events")
    q.set_defaults(func=cmd_queue)

    pnl = sub.add_parser("pnl", help="Harvest decided cards + print PnL summary")
    pnl.add_argument("--prod", action="store_true", help="Use Kalshi prod for outcome lookup")
    pnl.set_defaults(func=cmd_pnl)

    rt = sub.add_parser("retro", help="Write evening retro markdown to ~/.orallexa/markets/retro/")
    rt.add_argument("--bankroll", type=float, default=300.0)
    rt.add_argument("--date", default=None, help="YYYY-MM-DD (defaults to today UTC)")
    rt.add_argument("--prod", action="store_true")
    rt.set_defaults(func=cmd_retro)

    sch = sub.add_parser("scheduler-install", help="Install daily launchd jobs (macOS) or print crontab")
    sch.add_argument("--queue-hour", type=int, default=9)
    sch.add_argument("--retro-hour", type=int, default=21)
    sch.add_argument("--platform", choices=["kalshi", "polymarket"], default="polymarket")
    sch.add_argument("--bankroll", type=float, default=300.0)
    sch.add_argument("--queue-limit", type=int, default=5)
    sch.add_argument("--repo-path", default=None, help="Defaults to CWD at install time")
    sch.set_defaults(func=cmd_scheduler_install)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
