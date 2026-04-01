"""
app.py — Orallexa AI Trading Research Dashboard
────────────────────────────────────────────────
Modes:
  research — full multi-strategy backtest + Claude narrative (original)
  scalp    — 5-minute scalping decision with risk management
  predict  — daily/swing probability forecast
"""

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timezone

from core.logger import get_logger
from core.settings import Settings
from skills.market_data import MarketDataSkill
from skills.technical_analysis import TechnicalAnalysisSkill
from skills.news import NewsSkill
from engine.backtest import simple_backtest
from core.brain import OrallexaBrain
from core.loop import StrategyLoop
from rag.vector_store import LocalRAGStore
from llm.ui_analysis import ui_analysis_with_rag, ui_probability_report
from models.decision import DecisionOutput

st.set_page_config(page_title="Orallexa", layout="wide")

logger = get_logger("app")

# ══════════════════════════════════════════════════════════════════════════
# CSS — decision card styles
# ══════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
.decision-card {
    padding: 20px 24px;
    border-radius: 10px;
    background: #0f1117;
    margin-bottom: 16px;
}
.decision-title {
    font-size: 2.4rem;
    font-weight: 800;
    margin: 0 0 4px 0;
    letter-spacing: 0.05em;
}
.decision-meta {
    color: #aaa;
    font-size: 0.95rem;
    margin: 0;
}
.step-box {
    background: #1a1a2e;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 6px;
    font-size: 0.88rem;
    color: #ddd;
}
.bot-status-card {
    background: #111827;
    border-radius: 8px;
    padding: 16px 20px;
    color: #ccc;
}
</style>
""", unsafe_allow_html=True)

store = LocalRAGStore()
user_settings = Settings()

# ══════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════

DECISION_COLORS = {"BUY": "#22c55e", "SELL": "#ef4444", "WAIT": "#f59e0b"}
DECISION_ICONS  = {"BUY": "\u25B2", "SELL": "\u25BC", "WAIT": "\u25CF"}  # ▲ ▼ ●
RISK_COLORS     = {"LOW": "#22c55e", "MEDIUM": "#f59e0b", "HIGH": "#ef4444"}
RISK_ICONS      = {"LOW": "\u2713", "MEDIUM": "\u26A0", "HIGH": "\u2716"}  # ✓ ⚠ ✖


def render_decision_card(output: DecisionOutput):
    """Section B — highlighted decision output."""
    color      = DECISION_COLORS.get(output.decision, "#888")
    risk_color = RISK_COLORS.get(output.risk_level, "#888")
    confidence = output.confidence

    # Data freshness
    data_ts = st.session_state.get("data_timestamp")
    freshness_html = ""
    if data_ts is not None:
        try:
            ts = pd.Timestamp(data_ts)
            if ts.tzinfo is not None:
                age_min = (pd.Timestamp.now(tz=ts.tzinfo) - ts).total_seconds() / 60
            else:
                age_min = (pd.Timestamp.now() - ts).total_seconds() / 60
            ts_str = ts.strftime("%H:%M:%S")
            age_color = "#22c55e" if age_min < 5 else "#f59e0b" if age_min < 30 else "#ef4444"
            freshness_html = (
                f'&nbsp;|&nbsp; Data: <span style="color:{age_color}">'
                f'{ts_str} ({age_min:.0f}m ago)</span>'
            )
        except Exception:
            pass

    dec_icon  = DECISION_ICONS.get(output.decision, "")
    risk_icon = RISK_ICONS.get(output.risk_level, "")

    st.markdown(f"""
    <div class="decision-card" style="border-left: 6px solid {color}">
        <p class="decision-title" style="color:{color}">{dec_icon} {output.decision}</p>
        <p class="decision-meta">
            Confidence: <b>{confidence:.0f}%</b>
            &nbsp;|&nbsp;
            Risk: <b style="color:{risk_color}">{risk_icon} {output.risk_level}</b>
            &nbsp;|&nbsp;
            Source: <b>{output.source}</b>
            {freshness_html}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Probability bars
    probs = output.probabilities
    up    = probs.get("up", 0)
    neut  = probs.get("neutral", 0)
    down  = probs.get("down", 0)
    st.progress(min(up, 1.0),   text=f"Up      {up*100:.0f}%")
    st.progress(min(neut, 1.0), text=f"Neutral {neut*100:.0f}%")
    st.progress(min(down, 1.0), text=f"Down    {down*100:.0f}%")

    # Step-by-step reasoning
    st.markdown("**Decision Reasoning:**")
    for step in output.reasoning:
        st.markdown(f'<div class="step-box">{step}</div>', unsafe_allow_html=True)


def render_risk_output(risk_out):
    """Render RiskOutput inside the decision section."""
    if not risk_out.approved:
        st.warning(f"Trade not approved: {risk_out.rejection_reason}")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Position Size",  f"{risk_out.position_size:.2f} shares")
        st.metric("Position Value", f"${risk_out.position_value:,.2f}")
    with col2:
        st.metric("Stop Loss",      f"${risk_out.stop_loss_price:.2f}")
        st.metric("Take Profit",    f"${risk_out.take_profit_price:.2f}")
    with col3:
        st.metric("Risk Amount",    f"${risk_out.risk_amount:.2f}")
        st.metric("Risk/Reward",    f"{risk_out.risk_reward_ratio:.1f}:1")


def render_bot_status(mem_summary: dict):
    """Section C — bot behavior feedback."""
    agg    = mem_summary.get("aggressiveness", 0.5)
    agg_pct = int(agg * 100)
    agg_color = "#22c55e" if agg < 0.5 else "#f59e0b" if agg < 0.75 else "#ef4444"

    st.markdown(f"""
    <div class="bot-status-card">
        <b>Bot Behavior</b><br>
        Aggressiveness: <span style="color:{agg_color}"><b>{agg_pct}%</b></span>
        &nbsp;|&nbsp; Trades today: <b>{mem_summary.get('trades_today', 0)}</b>
        &nbsp;|&nbsp; Total: <b>{mem_summary.get('total_trades', 0)}</b>
        &nbsp;|&nbsp; Win rate: <b>{mem_summary.get('win_rate_pct', 0)}%</b><br>
        Win streak: {mem_summary.get('win_streak', 0)}
        &nbsp;|&nbsp; Loss streak: {mem_summary.get('loss_streak', 0)}
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
# Research mode helpers (unchanged from original)
# ══════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False)
def build_equity_chart_and_data(ticker: str, params: dict, train_ratio: float = 0.7):
    data = MarketDataSkill(ticker).execute()
    ta   = TechnicalAnalysisSkill(data).add_indicators().dropna().copy()

    split_idx = int(len(ta) * train_ratio)
    train_df  = ta.iloc[:split_idx].copy()
    test_df   = ta.iloc[split_idx:].copy()

    bt_train = simple_backtest(train_df, params=params, debug=False)
    bt_test  = simple_backtest(test_df,  params=params, debug=False)
    return bt_train, bt_test


def render_equity_chart(ticker: str, bt_train: pd.DataFrame, bt_test: pd.DataFrame):
    fig, axes = plt.subplots(2, 1, figsize=(10, 7))

    axes[0].plot(bt_train["CumulativeStrategyReturn"], label="Train Strategy")
    axes[0].plot(bt_train["CumulativeMarketReturn"],   label="Train Buy & Hold")
    axes[0].set_title(f"{ticker} Train Equity Curve")
    axes[0].legend()
    axes[0].grid(True)

    axes[1].plot(bt_test["CumulativeStrategyReturn"], label="Test Strategy")
    axes[1].plot(bt_test["CumulativeMarketReturn"],   label="Test Buy & Hold")
    axes[1].set_title(f"{ticker} Test Equity Curve")
    axes[1].legend()
    axes[1].grid(True)

    plt.tight_layout()
    return fig


# ══════════════════════════════════════════════════════════════════════════
# SIDEBAR — mode selector + inputs
# ══════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("Orallexa")

    _saved_mode = user_settings.get("mode", "scalp")
    _mode_opts = ["scalp", "predict", "research"]
    mode = st.selectbox(
        "Analysis Mode",
        _mode_opts,
        index=_mode_opts.index(_saved_mode) if _saved_mode in _mode_opts else 0,
        help="scalp = 5-min live signal | predict = daily swing forecast | research = full backtest"
    )

    st.divider()

    if mode in ("scalp", "predict"):
        # ── Section A inputs ──────────────────────────────────────────────
        st.header("A. Trade Setup")
        trade_ticker  = st.text_input("Ticker", value=user_settings.get("ticker", "NVDA")).strip().upper()
        account_size  = st.number_input("Account Size ($)", value=user_settings.get("account_size", 10_000), step=500, min_value=100)
        risk_pct_input = st.slider("Risk Per Trade (%)", 0.5, 5.0, user_settings.get("risk_pct", 1.0), 0.5)
        risk_pct      = risk_pct_input / 100.0

        enable_claude = st.checkbox("Claude AI overlay", value=True)
        enable_rag    = st.checkbox("RAG context", value=True)

        analyze_btn = st.button("Analyze", type="primary", use_container_width=True)

        st.divider()

        # ── Price Alerts (sidebar) ────────────────────────────────────
        from bot.alerts import AlertManager, PriceAlert
        alert_mgr = AlertManager()

        with st.expander("Price Alerts"):
            al_dir = st.selectbox("Condition", ["above", "below"], key="al_dir")
            al_price = st.number_input("Target $", value=0.0, step=0.50, key="al_price", min_value=0.0)
            al_note = st.text_input("Note (optional)", key="al_note")
            if st.button("Add Alert") and al_price > 0:
                alert_mgr.add(PriceAlert(
                    ticker=trade_ticker, target=al_price,
                    direction=al_dir, note=al_note,
                ))
                st.success(f"Alert: {trade_ticker} {al_dir} ${al_price:.2f}")
                st.rerun()

            active_alerts = alert_mgr.get_active()
            if active_alerts:
                st.caption(f"{len(active_alerts)} active alert(s)")
                for i, a in enumerate(alert_mgr.get_all()):
                    if a.get("triggered"):
                        continue
                    arrow = "^" if a["direction"] == "above" else "v"
                    col_a, col_d = st.columns([3, 1])
                    with col_a:
                        st.write(f"{arrow} {a['ticker']} {a['direction']} ${a['target']:.2f}")
                    with col_d:
                        if st.button("X", key=f"del_alert_{i}"):
                            alert_mgr.remove(i)
                            st.rerun()

        st.caption(f"Mode: **{mode.upper()}**")

    else:
        # ── Research mode sidebar (original) ──────────────────────────────
        st.header("Run Settings")
        tickers_input = st.text_input("Tickers", value="NVDA,AAPL,TSLA")
        iterations    = st.number_input("Iterations", min_value=1, max_value=5, value=2, step=1)
        train_ratio   = st.slider("Train/Test Split", 0.5, 0.9, 0.7, 0.05)

        st.markdown("### Walk-Forward")
        wf_train_ratio = st.slider("WF Train Ratio", 0.3, 0.8, 0.6, 0.05)
        wf_test_ratio  = st.slider("WF Test Ratio",  0.1, 0.4, 0.2, 0.05)
        wf_step_ratio  = st.slider("WF Step Ratio",  0.05, 0.3, 0.1, 0.05)

        st.divider()
        st.header("AI + RAG")
        enable_ai  = st.checkbox("Enable Claude AI Analysis", value=True)
        enable_rag = st.checkbox("Enable RAG Notes", value=True)

        run_clicked = st.button("Run Dashboard")

# ══════════════════════════════════════════════════════════════════════════
# PAGE HEADER
# ══════════════════════════════════════════════════════════════════════════

mode_labels = {"scalp": "Scalp Mode (5-min)", "predict": "Prediction Mode", "research": "Research Mode"}
st.title("Orallexa")
st.subheader(mode_labels.get(mode, ""))

# ══════════════════════════════════════════════════════════════════════════
# SCALP / PREDICT MODE
# ══════════════════════════════════════════════════════════════════════════

if mode in ("scalp", "predict"):
    if analyze_btn:
        # ── Validate ticker ──────────────────────────────────────────
        if not trade_ticker or len(trade_ticker) > 5 or not trade_ticker.isalpha():
            st.error("Invalid ticker. Use 1-5 letters (e.g. NVDA, AAPL).")
            st.stop()

        import yfinance as yf
        _check = yf.Ticker(trade_ticker)
        try:
            _info = _check.info
            if not _info or _info.get("regularMarketPrice") is None:
                _hist = _check.history(period="5d")
                if _hist.empty:
                    st.error(f"Ticker **{trade_ticker}** not found. Check the symbol and try again.")
                    st.stop()
        except Exception:
            st.warning(f"Could not verify **{trade_ticker}** — proceeding anyway.")

        # Persist user preferences
        user_settings.update(
            ticker=trade_ticker, mode=mode,
            account_size=account_size, risk_pct=risk_pct_input,
        )
        user_settings.save()

        brain = OrallexaBrain(trade_ticker)

        # ── Auto-fetch news into RAG before retrieval (3B-1) ─────────────
        if enable_rag:
            try:
                from skills.news import NewsSkill
                fresh_news = NewsSkill(trade_ticker).fetch_news(limit=5)
                if fresh_news:
                    store.add_news_documents(trade_ticker, fresh_news)
            except Exception as e:
                logger.warning("News fetch failed for %s: %s", trade_ticker, e)
                st.warning(f"News fetch failed — analysis will use technical indicators only.")

        # ── RAG retrieval (3B-2, 3B-3) ────────────────────────────────────
        rag_context = ""
        retrieved = []
        if enable_rag:
            # Mode-specific query for better relevance (3B-3)
            if mode == "scalp":
                rag_query = f"{trade_ticker} breakout volume momentum intraday"
            else:
                rag_query = f"{trade_ticker} trend earnings outlook support resistance news"
            try:
                retrieved = store.retrieve(
                    query=rag_query,
                    ticker=trade_ticker,
                    top_k=3,
                )
                if retrieved:
                    rag_context = "\n\n".join(
                        f"[{i+1}] {doc['title']}: {doc['text']}"
                        for i, (doc, _) in enumerate(retrieved)
                    )
            except Exception as e:
                logger.warning("RAG retrieval failed for %s: %s", trade_ticker, e)
                st.warning("RAG context unavailable — using technical analysis only.")

        # ── Run analysis ──────────────────────────────────────────────────
        progress = st.progress(0, text=f"Fetching {trade_ticker} market data...")
        logger.info("Analysis started: %s mode=%s", trade_ticker, mode)

        try:
            progress.progress(20, text="Computing technical indicators...")
            if mode == "scalp":
                progress.progress(50, text="Running scalping signal detection...")
                decision_out = brain.run_scalping()
            else:
                progress.progress(40, text="Running technical scoring...")
                if enable_claude:
                    progress.progress(60, text="Calling Claude AI for analysis overlay...")
                decision_out = brain.run_prediction(
                    use_claude=enable_claude, rag_context=rag_context
                )
            progress.progress(90, text="Finalizing decision...")
            logger.info("Analysis complete: %s -> %s (%.0f%%)",
                        trade_ticker, decision_out.decision, decision_out.confidence)
        except Exception as e:
            logger.error("Analysis failed for %s: %s", trade_ticker, e, exc_info=True)
            st.error(f"Analysis failed: {e}")
            progress.empty()
            st.stop()

        progress.progress(100, text="Done!")
        progress.empty()

        # ── Risk management ───────────────────────────────────────────────
        from skills.risk_management import RiskManagementSkill, RiskParams
        from bot.behavior import BehaviorMemory

        mem = BehaviorMemory()

        # Get live price for risk calc (3A-3: surface error when unavailable)
        import yfinance as yf
        entry_price = 0.0
        atr_val     = None
        try:
            ticker_obj = yf.Ticker(trade_ticker)
            hist       = ticker_obj.history(period="1d", interval="1m")
            if not hist.empty:
                entry_price = float(hist["Close"].iloc[-1])
                # Store data timestamp for freshness indicator
                st.session_state["data_timestamp"] = hist.index[-1]
                if mode == "scalp":
                    tr = pd.concat([
                        hist["High"] - hist["Low"],
                        (hist["High"] - hist["Close"].shift()).abs(),
                        (hist["Low"]  - hist["Close"].shift()).abs(),
                    ], axis=1).max(axis=1)
                    atr_val = float(tr.rolling(14).mean().iloc[-1])
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", trade_ticker, e)
            entry_price = 0.0
            atr_val     = None

        # ── Check price alerts ────────────────────────────────────────
        if entry_price > 0:
            triggered = alert_mgr.check_all()
            for ta in triggered:
                st.toast(
                    f"ALERT: {ta['ticker']} hit ${ta['triggered_price']:.2f} "
                    f"({ta['direction']} ${ta['target']:.2f}) — {ta.get('note', '')}",
                    icon="🔔",
                )

        # 3A-3: manual price input when live price unavailable
        if entry_price == 0.0:
            st.warning(
                f"Live price unavailable for **{trade_ticker}** (market may be closed). "
                "Enter a price manually to enable risk sizing."
            )
            manual_price = st.number_input(
                "Manual Entry Price ($)", value=0.0, min_value=0.0, step=0.01, format="%.2f"
            )
            if manual_price > 0:
                entry_price = manual_price

        risk_params = RiskParams(
            account_size=float(account_size),
            risk_pct=risk_pct,
            entry_price=entry_price,
            atr=atr_val,
            max_trades_per_day=5,
        )
        risk_out = RiskManagementSkill().compute(
            decision=decision_out,
            params=risk_params,
            trades_today=mem.get_trades_today(),
        )

        # ── Render sections ───────────────────────────────────────────────
        st.divider()

        # Section B — Decision Output
        st.markdown("## B. Decision Output")
        render_decision_card(decision_out)

        # ── Export buttons ─────────────────────────────────────────────
        exp_col1, exp_col2 = st.columns(2)
        with exp_col1:
            # CSV export
            csv_data = {
                "Ticker": [trade_ticker],
                "Decision": [decision_out.decision],
                "Confidence": [f"{decision_out.confidence:.1f}%"],
                "Risk": [decision_out.risk_level],
                "Source": [decision_out.source],
                "Signal Strength": [getattr(decision_out, "signal_strength", "")],
                "Timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            }
            probs = decision_out.probabilities
            csv_data["Up%"] = [f"{probs.get('up', 0)*100:.0f}"]
            csv_data["Down%"] = [f"{probs.get('down', 0)*100:.0f}"]
            csv_data["Neutral%"] = [f"{probs.get('neutral', 0)*100:.0f}"]
            csv_df = pd.DataFrame(csv_data)
            st.download_button(
                "Download CSV",
                csv_df.to_csv(index=False),
                file_name=f"orallexa_{trade_ticker}_{mode}.csv",
                mime="text/csv",
            )
        with exp_col2:
            # Text report export
            report_lines = [
                f"ORALLEXA ANALYSIS REPORT",
                f"{'='*40}",
                f"Ticker:     {trade_ticker}",
                f"Mode:       {mode.upper()}",
                f"Date:       {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                f"",
                f"DECISION:   {decision_out.decision}",
                f"Confidence: {decision_out.confidence:.1f}%",
                f"Risk Level: {decision_out.risk_level}",
                f"Source:     {decision_out.source}",
                f"",
                f"Probabilities:",
                f"  Up:      {probs.get('up', 0)*100:.0f}%",
                f"  Down:    {probs.get('down', 0)*100:.0f}%",
                f"  Neutral: {probs.get('neutral', 0)*100:.0f}%",
                f"",
                f"Reasoning:",
            ]
            for step in decision_out.reasoning:
                report_lines.append(f"  - {step}")
            if getattr(decision_out, "recommendation", ""):
                report_lines.extend(["", f"Recommendation:", f"  {decision_out.recommendation}"])
            report_text = "\n".join(report_lines)
            st.download_button(
                "Download Report",
                report_text,
                file_name=f"orallexa_{trade_ticker}_{mode}_report.txt",
                mime="text/plain",
            )

        # RAG quality indicator (3B-2)
        if enable_rag:
            if retrieved:
                top_score = retrieved[0][1]
                st.caption(f"RAG: {len(retrieved)} docs retrieved | top relevance: {top_score:.2f}")
            else:
                st.caption("RAG: no relevant documents found for this ticker")

        # ── Multi-Timeframe Confirmation ─────────────────────────────
        with st.expander("Multi-Timeframe Confirmation", expanded=False):
            mtf_cols = st.columns(3)
            _mtf_configs = [
                ("5m", "Scalp", "scalp"),
                ("15m", "Intraday", "intraday"),
                ("1D", "Swing", "swing"),
            ]
            for col, (tf, label, m) in zip(mtf_cols, _mtf_configs):
                with col:
                    st.markdown(f"**{label} ({tf})**")
                    try:
                        _mtf_result = brain.run_for_mode(mode=m, timeframe=tf, use_claude=False)
                        _dec = _mtf_result.decision
                        _conf = _mtf_result.confidence
                        _col = DECISION_COLORS.get(_dec, "#888")
                        st.markdown(
                            f'<span style="color:{_col};font-size:1.4rem;font-weight:bold">'
                            f'{_dec}</span> &nbsp; {_conf:.0f}%',
                            unsafe_allow_html=True,
                        )
                        if _mtf_result.reasoning:
                            st.caption(_mtf_result.reasoning[0][:80])
                    except Exception as e:
                        st.caption(f"N/A ({e})")

        if entry_price > 0:
            st.markdown("**Risk Management**")
            render_risk_output(risk_out)

        # RAG context expander
        if rag_context:
            with st.expander("Retrieved RAG Context"):
                st.text(rag_context)

        st.divider()

        # Section C — Bot Status
        st.markdown("## C. Bot Status & Behavior")
        mem_summary = mem.get_summary()
        render_bot_status(mem_summary)

        recent = mem.get_recent_trades(10)
        if recent:
            st.markdown("**Recent Trades**")
            st.dataframe(pd.DataFrame(recent), use_container_width=True)
        else:
            st.caption("No trades recorded yet. Use the trade logger below to track outcomes.")

        # Bot Arena comparison (3C-2)
        with st.expander("Bot Arena — Config Comparison"):
            from bot.arena import BotArena
            arena_results = BotArena().run(
                decision=decision_out,
                entry_price=entry_price,
                account_size=float(account_size),
                atr=atr_val,
            )

            rows = []
            for r in arena_results:
                rows.append({
                    "Config":           r.name,
                    "Approved":         "YES" if r.approved else "NO",
                    "Min Confidence":   f"{r.config['min_confidence']}%",
                    "Signal Conf":      f"{decision_out.confidence:.0f}%",
                    "Position Size":    f"{r.risk_output.position_size:.2f} sh" if r.approved else "—",
                    "Stop Loss":        f"${r.risk_output.stop_loss_price:.2f}" if r.approved else "—",
                    "Risk/Reward":      f"{r.risk_output.risk_reward_ratio:.1f}:1" if r.approved else "—",
                    "Rejection Reason": r.reason if not r.approved else "",
                })

            arena_df = pd.DataFrame(rows)
            st.dataframe(arena_df, use_container_width=True)

        # Simple trade outcome logger
        with st.expander("Log Trade Outcome"):
            from bot.behavior import TradeRecord
            from datetime import datetime

            col_a, col_b = st.columns(2)
            with col_a:
                log_outcome = st.selectbox("Outcome", ["win", "loss", "breakeven"])
                log_pnl     = st.number_input("PnL %", value=0.0, step=0.1, format="%.2f")
            with col_b:
                log_entry   = st.number_input("Entry Price", value=entry_price, step=0.01)

            if st.button("Record Trade"):
                ts = datetime.now().isoformat()
                record = TradeRecord(
                    timestamp=ts,
                    ticker=trade_ticker,
                    decision=decision_out.decision,
                    confidence=decision_out.confidence,
                    risk_level=decision_out.risk_level,
                    source=decision_out.source,
                    entry_price=log_entry,
                    outcome=log_outcome,
                    pnl_pct=log_pnl,
                )
                mem.record_trade(record)
                st.success(f"Trade recorded: {log_outcome.upper()} {log_pnl:+.2f}%")
                st.rerun()

        # ── Paper Trading ─────────────────────────────────────────────
        st.divider()
        st.markdown("## D. Paper Trading")
        from bot.paper_trading import PaperTrader, PaperTrade

        paper = PaperTrader()

        # Quick-open from current signal
        if decision_out.decision in ("BUY", "SELL") and entry_price > 0:
            direction = "LONG" if decision_out.decision == "BUY" else "SHORT"
            sl = risk_out.stop_loss_price if risk_out.approved else 0.0
            tp = risk_out.take_profit_price if risk_out.approved else 0.0
            pos = risk_out.position_size if risk_out.approved else 0.0

            if st.button(f"Open Paper {direction} — {trade_ticker} @ ${entry_price:.2f}",
                         type="primary"):
                pt = PaperTrade(
                    timestamp=datetime.now().isoformat(),
                    ticker=trade_ticker,
                    direction=direction,
                    entry_price=entry_price,
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=decision_out.confidence,
                    source=decision_out.source,
                    position_size=pos,
                )
                paper.open_trade(pt)
                st.success(f"Paper {direction} opened: {trade_ticker} @ ${entry_price:.2f}")
                st.rerun()

        # Open positions
        open_trades = paper.get_open_trades()
        if open_trades:
            st.markdown("**Open Positions**")
            for i, ot in enumerate(paper.get_all_trades()):
                if ot["status"] != "OPEN":
                    continue
                c1, c2, c3 = st.columns([2, 2, 1])
                with c1:
                    st.write(f"**{ot['ticker']}** {ot['direction']} @ ${ot['entry_price']:.2f}")
                    st.caption(f"SL: ${ot['stop_loss']:.2f} | TP: ${ot['take_profit']:.2f}")
                with c2:
                    close_price = st.number_input(
                        "Exit $", value=entry_price if ot["ticker"] == trade_ticker else 0.0,
                        step=0.01, key=f"paper_exit_{i}", min_value=0.01,
                    )
                with c3:
                    if st.button("Close", key=f"paper_close_{i}"):
                        paper.close_trade(i, close_price)
                        st.rerun()

        # Performance stats
        stats = paper.get_stats()
        if stats["total_trades"] > 0:
            st.markdown("**Paper Performance**")
            pc1, pc2, pc3, pc4 = st.columns(4)
            pnl_color = "#22c55e" if stats["total_pnl_pct"] >= 0 else "#ef4444"
            with pc1:
                st.metric("Trades", stats["total_trades"])
            with pc2:
                st.metric("Win Rate", f"{stats['win_rate']}%")
            with pc3:
                st.metric("Total P&L", f"{stats['total_pnl_pct']:+.2f}%")
            with pc4:
                st.metric("Profit Factor", f"{stats['profit_factor']:.2f}")

            closed = paper.get_closed_trades()
            if closed:
                with st.expander("Trade History"):
                    df = pd.DataFrame(closed)[
                        ["timestamp", "ticker", "direction", "entry_price",
                         "exit_price", "pnl_pct", "status"]
                    ]
                    st.dataframe(df, use_container_width=True)

    else:
        # Placeholder when page first loads
        st.info(f"Configure your trade in the sidebar and click **Analyze** to get a {mode} decision.")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("### A. Market Input")
            st.caption("Ticker, account size, risk % — set in sidebar")
        with col2:
            st.markdown("### B. Decision Output")
            st.caption("BUY / SELL / WAIT with confidence, risk, and step-by-step reasoning")
        with col3:
            st.markdown("### C. Bot Status")
            st.caption("Win rate, aggressiveness, streak tracking, trade log")


# ══════════════════════════════════════════════════════════════════════════
# RESEARCH MODE (original, unchanged logic)
# ══════════════════════════════════════════════════════════════════════════

elif mode == "research":
    tickers = [t.strip().upper() for t in tickers_input.replace("，", ",").split(",") if t.strip()]
    st.write("Parsed tickers:", tickers)

    if enable_rag:
        with st.expander("RAG Controls"):
            selected_rag_ticker = st.selectbox(
                "Ticker for RAG Notes",
                options=tickers if tickers else ["AAPL"],
                index=0
            )

            if st.button("Auto Import News to RAG"):
                try:
                    news_skill = NewsSkill(selected_rag_ticker)
                    items      = news_skill.fetch_news(limit=8)
                    added      = store.add_news_documents(selected_rag_ticker, items)
                    st.success(f"Imported {added} news items for {selected_rag_ticker}")
                except Exception as e:
                    st.error(f"News import failed: {e}")

            rag_title = st.text_input("Note Title", value="")
            rag_text  = st.text_area("Manual Note", height=120)

            if st.button("Save Manual Note"):
                if selected_rag_ticker and rag_text.strip():
                    store.add_document(
                        ticker=selected_rag_ticker,
                        title=rag_title or "Untitled",
                        text=rag_text,
                        source="manual"
                    )
                    st.success(f"Saved note for {selected_rag_ticker}")
                else:
                    st.warning("Please enter note text.")

    if run_clicked:
        results = []
        n_tickers = len(tickers)

        progress_bar = st.progress(0, text="Starting research analysis...")
        status_text = st.empty()

        for idx, tk in enumerate(tickers):
            pct = int((idx / max(n_tickers, 1)) * 100)
            progress_bar.progress(pct, text=f"Analyzing {tk}... ({idx+1}/{n_tickers})")
            status_text.caption(f"Running backtest + walk-forward for **{tk}**")
            logger.info("Research: analyzing %s (%d/%d)", tk, idx + 1, n_tickers)

            try:
                brain = OrallexaBrain(tk)
                loop  = StrategyLoop(brain)

                result = loop.run(
                    iterations=int(iterations),
                    save_prefix=None,
                    train_ratio=float(train_ratio),
                    wf_train_ratio=float(wf_train_ratio),
                    wf_test_ratio=float(wf_test_ratio),
                    wf_step_ratio=float(wf_step_ratio)
                )

                best         = result.get("best_result", {})
                summary      = best.get("summary", {})
                train_metrics = best.get("train_metrics", {})
                test_metrics  = best.get("test_metrics", {})
                wf_metrics    = best.get("walk_forward_metrics", {})

                rag_context = ""
                if enable_rag:
                    try:
                        retrieved = store.retrieve(
                            query=f"{tk} trend risk support resistance market outlook earnings news",
                            ticker=tk,
                            top_k=5,
                        )
                        if retrieved:
                            rag_context = "\n\n".join(
                                f"[{i+1}] {doc['title']}: {doc['text']}"
                                for i, (doc, score) in enumerate(retrieved)
                            )
                    except Exception as e:
                        logger.warning("RAG retrieval failed for %s: %s", tk, e)
                        rag_context = f"RAG retrieval failed: {e}"

                if enable_ai:
                    status_text.caption(f"Running Claude AI analysis for **{tk}**...")
                    ai_report = ui_analysis_with_rag(
                        summary=summary, metrics=test_metrics,
                        rag_context=rag_context, ticker=tk
                    )
                    prob = ui_probability_report(
                        summary=summary, metrics=test_metrics,
                        rag_context=rag_context, ticker=tk
                    )
                else:
                    ai_report = "AI analysis disabled."
                    prob = {
                        "bull_probability": 45, "neutral_probability": 30,
                        "bear_probability": 25, "confidence": "medium",
                        "action": "Watch", "bias": "Neutral",
                        "key_driver": "AI disabled.", "main_risk": "AI disabled."
                    }

                results.append({
                    "ticker": tk, "summary": summary,
                    "best_params": result.get("best_params"),
                    "best_train_sharpe": result.get("best_train_sharpe"),
                    "train_metrics": train_metrics, "test_metrics": test_metrics,
                    "wf_metrics": wf_metrics, "ai_report": ai_report,
                    "prob": prob, "rag_context": rag_context, "full_result": result
                })

            except Exception as e:
                logger.error("Research failed for %s: %s", tk, e, exc_info=True)
                results.append({"ticker": tk, "error": str(e)})

        progress_bar.progress(100, text="Research complete!")
        status_text.empty()
        progress_bar.empty()

        st.session_state["final_results"] = results
        st.success(f"Research complete — {len(results)} tickers analyzed")

    results = st.session_state.get("final_results", [])

    if results:
        st.markdown("## Watchlist Ranking")

        rank_rows = []
        for row in results:
            if "error" in row:
                rank_rows.append({"ticker": row["ticker"], "error": row["error"]})
            else:
                rank_rows.append({
                    "ticker":          row["ticker"],
                    "best_train_sharpe": row["best_train_sharpe"],
                    "test_sharpe":     row["test_metrics"].get("sharpe"),
                    "test_return":     row["test_metrics"].get("total_return"),
                    "test_drawdown":   row["test_metrics"].get("max_drawdown"),
                    "wf_avg_sharpe":   row["wf_metrics"].get("avg_test_sharpe"),
                    "wf_avg_return":   row["wf_metrics"].get("avg_test_return"),
                    "wf_windows":      row["wf_metrics"].get("num_windows"),
                    "action":          row["prob"]["action"],
                    "confidence":      row["prob"]["confidence"],
                })

        st.dataframe(pd.DataFrame(rank_rows), use_container_width=True)

        for row in results:
            if "error" in row:
                st.error(f"{row['ticker']} failed: {row['error']}")
                continue

            with st.expander(f"{row['ticker']} | Action: {row['prob']['action']}"):
                left, right = st.columns([1, 1])

                with left:
                    st.markdown("### Summary")
                    st.write(row["summary"])
                    st.markdown("### Best Params")
                    st.json(row["best_params"])
                    st.markdown("### Train Metrics")
                    st.write(row["train_metrics"])
                    st.markdown("### Test Metrics")
                    st.write(row["test_metrics"])
                    st.markdown("### Walk-Forward Metrics")
                    st.write(row["wf_metrics"])
                    st.markdown("### AI Report")
                    st.write(row["ai_report"])

                with right:
                    prob = row["prob"]
                    st.markdown("### Probability View")
                    st.progress(prob["bull_probability"] / 100.0,    text=f"Bullish: {prob['bull_probability']}%")
                    st.progress(prob["neutral_probability"] / 100.0, text=f"Neutral: {prob['neutral_probability']}%")
                    st.progress(prob["bear_probability"] / 100.0,    text=f"Bearish: {prob['bear_probability']}%")

                    st.markdown("### Decision Card")
                    st.write({
                        "bias":       prob["bias"],
                        "confidence": prob["confidence"],
                        "action":     prob["action"],
                        "key_driver": prob["key_driver"],
                        "main_risk":  prob["main_risk"],
                    })

                    try:
                        bt_train, bt_test = build_equity_chart_and_data(
                            row["ticker"], row["best_params"],
                            train_ratio=float(train_ratio)
                        )
                        fig = render_equity_chart(row["ticker"], bt_train, bt_test)
                        st.markdown("### Equity Curves")
                        st.pyplot(fig)
                    except Exception as e:
                        st.warning(f"Chart failed for {row['ticker']}: {e}")

                st.markdown("### Retrieved RAG Context")
                if row["rag_context"]:
                    st.text(row["rag_context"])
                else:
                    st.info("No RAG context found.")
