"""
scripts/demo_multimodal_debate.py
──────────────────────────────────────────────────────────────────
One-command demo of the multi-modal debate pipeline.

Renders a K-line for the requested ticker, runs the perspective panel
in `multimodal=True` mode (text + vision for the Quant role by default),
prints a side-by-side comparison + diff, optionally saves a markdown
report under `assets/demo_reports/`.

Two modes:

  - Live mode (default): hits Anthropic. Needs ANTHROPIC_API_KEY set.
    Cost: ~$0.005 (4 text Haiku + 1 vision Haiku call).

  - Mock mode (--mock): no LLM calls. Uses canned text and vision
    responses so the demo runs offline (recording / interview) and
    in CI. Outputs identical shape so reviewers can see the format
    without spending tokens.

Usage:
    python scripts/demo_multimodal_debate.py NVDA
    python scripts/demo_multimodal_debate.py NVDA --period 6mo
    python scripts/demo_multimodal_debate.py NVDA --mock
    python scripts/demo_multimodal_debate.py NVDA --report
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


# ── Mock-mode canned responses ────────────────────────────────────────────
# Designed to surface the kind of disagreement we'd want vision to capture:
# the text path looks at numbers and sees momentum (BULLISH); the vision
# path looks at the chart and notices a head-and-shoulders top (BEARISH).
# Wire this into the demo pre-recording so the side-by-side has signal.

_MOCK_RESPONSES = {
    "Conservative Analyst_text": {
        "bias": "NEUTRAL", "score": 5, "conviction": 50,
        "reasoning": "Above MA50 with healthy R/R, but extended past +2σ Bollinger. "
                     "Drawdown risk if FOMC surprises hawkish.",
        "key_factor": "Position size below 5% recommended.",
    },
    "Aggressive Trader_text": {
        "bias": "BULLISH", "score": 60, "conviction": 70,
        "reasoning": "Volume 2.4× average, MACD histogram positive 6 sessions, RSI 62. "
                     "Breakout looks real; trail stop under MA20.",
        "key_factor": "Momentum confirmed across volume and MACD.",
    },
    "Macro Strategist_text": {
        "bias": "BULLISH", "score": 35, "conviction": 60,
        "reasoning": "Semis sector relative strength rising vs SPY. AI capex cycle "
                     "still supportive. Watch 10Y if it spikes past 4.5%.",
        "key_factor": "Sector rotation favors continued long.",
    },
    "Quant Researcher_text": {
        "bias": "BULLISH", "score": 45, "conviction": 65,
        "reasoning": "8/10 ML models lean long, fusion conviction +52, "
                     "PEAD avg drift +1.8% post-earnings, social sentiment +0.31.",
        "key_factor": "Multi-source signal alignment.",
    },
    "Quant Researcher_vision": {
        "bias": "BEARISH", "score": -25, "conviction": 60,
        "reasoning": "Chart shows a head-and-shoulders top forming over 8 weeks; "
                     "right shoulder at $215 is rolling over. Volume on the recent "
                     "rally was lighter than the left-shoulder advance — classic "
                     "distribution. MA20 slope flattening.",
        "key_factor": "H&S pattern + declining volume on rally.",
    },
}


def _mock_call_perspective(client, role, context, ticker, mem_ctx, *, chart_png=None):
    """Inject canned PerspectiveResult instead of hitting Anthropic."""
    from llm.perspective_panel import PerspectiveResult

    modality = "vision" if chart_png is not None else "text"
    key = f"{role['name']}_{modality}"
    payload = _MOCK_RESPONSES.get(key, {
        "bias": "NEUTRAL", "score": 0, "conviction": 50,
        "reasoning": f"Mock {modality} response for {role['name']}.",
        "key_factor": "Mock data.",
    })
    return PerspectiveResult(
        role=role["name"], icon=role["icon"],
        bias=payload["bias"], score=payload["score"],
        conviction=payload["conviction"],
        reasoning=payload["reasoning"], key_factor=payload["key_factor"],
        modality=modality,
    )


# ── Pretty-print helpers ──────────────────────────────────────────────────


def _bias_emoji(bias: str) -> str:
    return {"BULLISH": "[+]", "BEARISH": "[-]", "NEUTRAL": "[0]"}.get(bias, "[?]")


def render_side_by_side(panel_result: dict, ticker: str) -> str:
    """Build the side-by-side text report. Returns markdown string."""
    lines = []
    lines.append(f"# Multi-modal Debate Demo — {ticker}")
    lines.append(f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n")
    lines.append(f"**Headline consensus (text-only):** {panel_result['consensus']} "
                 f"(score: {panel_result['avg_score']:+.1f}, "
                 f"agreement: {panel_result['agreement']}%)\n")

    lines.append("## All perspectives\n")
    lines.append("| Role | Modality | Bias | Score | Conviction | Key factor |")
    lines.append("|------|----------|------|-------|------------|------------|")
    for p in panel_result["perspectives"]:
        lines.append(
            f"| {p['role']} | `{p['modality']}` | "
            f"{_bias_emoji(p['bias'])} {p['bias']} | "
            f"{p['score']:+d} | {p['conviction']}% | {p['key_factor']} |"
        )
    lines.append("")

    diff = panel_result.get("multimodal_diff", {})
    if diff and diff.get("n_pairs", 0) > 0:
        lines.append("## Text vs Vision diff\n")
        lines.append(f"- Pairs: **{diff['n_pairs']}**")
        lines.append(f"- Agreement rate: **{diff['agreement_rate']*100:.1f}%**")
        lines.append(f"- Avg score delta (vision - text): **{diff['avg_score_delta']:+.1f}**")
        lines.append(f"- Avg conviction delta: **{diff['avg_conviction_delta']:+.1f}**\n")

        for pair in diff["pairs"]:
            verdict = "AGREE" if pair["agree"] else "DISAGREE"
            lines.append(f"### {pair['role']} — {verdict}\n")
            lines.append(f"**Text:** {_bias_emoji(pair['text']['bias'])} "
                         f"{pair['text']['bias']} (score {pair['text']['score']:+d}, "
                         f"conviction {pair['text']['conviction']}%)")
            lines.append(f"> {pair['text']['reasoning']}\n")
            lines.append(f"**Vision:** {_bias_emoji(pair['vision']['bias'])} "
                         f"{pair['vision']['bias']} (score {pair['vision']['score']:+d}, "
                         f"conviction {pair['vision']['conviction']}%)")
            lines.append(f"> {pair['vision']['reasoning']}\n")
            lines.append(f"_Score delta: {pair['score_delta']:+d} | "
                         f"Conviction delta: {pair['conviction_delta']:+d}_\n")
    else:
        lines.append("## Text vs Vision diff\n")
        lines.append("_No vision pairs available — chart render may have failed._\n")

    return "\n".join(lines)


def run_demo(ticker: str, *, period: str, mock: bool, save_report: bool) -> int:
    from engine.chart_render import save_kline_to
    from llm import perspective_panel as pp

    # Step 1: render the chart (visible artifact for the demo).
    chart_path = _ROOT / "assets" / f"demo_kline_{ticker.upper()}.png"
    if mock:
        # Mock mode skips real fetch + render — copy a pre-rendered NVDA
        # chart if available, else synthesize a 60-bar OHLCV frame.
        if chart_path.exists():
            print(f"[mock] reusing existing {chart_path}")
        else:
            import numpy as np
            import pandas as pd
            from engine.chart_render import render_kline
            rng = np.random.default_rng(42)
            close = 200 + np.cumsum(rng.normal(0.1, 1.5, 60))
            df = pd.DataFrame(
                {
                    "Open": close * (1 + rng.normal(0, 0.003, 60)),
                    "High": close * (1 + abs(rng.normal(0, 0.01, 60))),
                    "Low": close * (1 - abs(rng.normal(0, 0.01, 60))),
                    "Close": close,
                    "Volume": rng.integers(1_000_000, 5_000_000, 60),
                },
                index=pd.bdate_range("2026-01-29", periods=60),
            )
            chart_path.parent.mkdir(parents=True, exist_ok=True)
            chart_path.write_bytes(render_kline(df, ticker=ticker.upper()))
            print(f"[mock] synthesized chart at {chart_path}")
    else:
        ok = save_kline_to(str(chart_path), ticker, period=period)
        if not ok:
            print(f"Chart render failed for {ticker}")
            return 1
        print(f"Rendered {chart_path}")

    # Step 2: run the panel.
    if mock:
        # Hot-swap _call_perspective for the canned responses. Saves a real
        # API key + any cost; lets the demo run anywhere.
        original = pp._call_perspective
        pp._call_perspective = _mock_call_perspective

        # Also stub render_kline_for so multimodal=True picks up the
        # already-written chart bytes without re-fetching.
        from engine import chart_render as cr
        original_render = cr.render_kline_for
        cr.render_kline_for = lambda *a, **kw: chart_path.read_bytes()

        # Demo mode also needs get_client() to not require an API key.
        import llm.claude_client as cc
        original_get_client = cc.get_client
        cc.get_client = lambda: object()

        try:
            panel = pp.run_perspective_panel(
                summary={}, ticker=ticker.upper(),
                multimodal=True,
            )
        finally:
            pp._call_perspective = original
            cr.render_kline_for = original_render
            cc.get_client = original_get_client
    else:
        panel = pp.run_perspective_panel(
            summary={}, ticker=ticker.upper(),
            multimodal=True, chart_period=period,
        )

    # Step 3: format the report.
    report_md = render_side_by_side(panel, ticker.upper())
    print()

    # Print the report. Encode/decode so Windows cp1252 console doesn't
    # crash on the few non-ASCII chars in the markdown body.
    try:
        sys.stdout.write(report_md)
        sys.stdout.write("\n")
    except UnicodeEncodeError:
        sys.stdout.write(report_md.encode("ascii", "replace").decode("ascii"))
        sys.stdout.write("\n")

    if save_report:
        report_dir = _ROOT / "assets" / "demo_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"multimodal_demo_{ticker.upper()}.md"
        report_path.write_text(report_md, encoding="utf-8")
        print(f"\nSaved report -> {report_path}")
        json_path = report_path.with_suffix(".json")
        json_path.write_text(json.dumps(panel, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved raw  -> {json_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", nargs="?", default="NVDA")
    parser.add_argument("--period", default="3mo",
                        choices=["1mo", "3mo", "6mo", "1y", "2y"])
    parser.add_argument("--mock", action="store_true",
                        help="skip real LLM + yfinance calls — uses canned data "
                             "so the demo runs offline (CI / interview prep).")
    parser.add_argument("--report", action="store_true",
                        help="also write the markdown + JSON report to assets/demo_reports/.")
    args = parser.parse_args()

    return run_demo(args.ticker, period=args.period,
                     mock=args.mock, save_report=args.report)


if __name__ == "__main__":
    sys.exit(main())
