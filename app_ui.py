# -*- coding: utf-8 -*-
import sys
import io as _io

# Force UTF-8 on Windows stdout/stderr to prevent codec errors with Chinese
if sys.stdout.encoding != "utf-8":
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import io
import os
import sys

# Force UTF-8 globally on Windows — must be before any other imports
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import json
import os
import base64
import re
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from openai import OpenAI
import anthropic

from core.brain import OrallexaBrain
from core.loop import StrategyLoop
from engine.backtest import simple_backtest
from engine.proposal_runner import compare_metric_block, proposal_is_better, run_proposal_backtest
from llm.strategy_generator import generate_strategy_proposal
from llm.ui_analysis import ui_analysis_with_rag, ui_probability_report
from portfolio.allocator import allocate_by_sharpe, select_top_n, select_top_n_diversified
from portfolio.backtest_portfolio import build_portfolio_curve, evaluate_portfolio
from rag.vector_store import LocalRAGStore
from skills.market_data import MarketDataSkill
from skills.news import NewsSkill
from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2 as TechnicalAnalysisSkill

# ══════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Orallexa Capital",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={}
)

# ── ORALLEXA CAPITAL ENGINE — Design System ──────────────────────────────────
# Direction: Wall Street luxury × Gatsby × old money × Bull Engine × OpenClaw
# Palette: near-black / charcoal / gold-champagne / dark emerald accents
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ── Luxury dark base ── */
.stApp{background:#08090C!important}
.stApp [data-testid="stSidebar"]{background:#0C0D10!important}
.stApp [data-testid="stSidebar"] *{color:#7A7D85!important}
.stApp [data-testid="stSidebar"] label{color:#7A7D85!important;font-size:0.8rem}
.stApp header{background:#08090C!important}
div[data-testid="stMetricValue"]{color:#E8DCC8!important;font-family:Inter,system-ui,sans-serif}
div[data-testid="stMetricLabel"]{color:#7A7D85!important;font-size:0.68rem!important}

/* ── Module cards ── */
.bull-card{background:#111318;border:1px solid #1C1E24;border-radius:3px;
    padding:16px 18px;margin-bottom:12px;font-family:Inter,system-ui,sans-serif}
.bull-card-hdr{font-size:10px;color:#C9A84C;font-weight:600;text-transform:uppercase;
    letter-spacing:0.16em;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid #1C1E24}
.bull-card-row{display:flex;justify-content:space-between;align-items:center;
    padding:7px 0;border-bottom:1px solid rgba(28,30,36,0.6)}
.bull-card-row:last-child{border-bottom:none}
.bull-card-label{font-size:12px;color:#6B6E76}
.bull-card-value{font-size:13px;color:#E8DCC8;font-weight:600}
.bull-mod-body{font-size:12px;color:#8A8D95;line-height:1.6}

/* ── Column wrappers ── */
div[data-testid="stVerticalBlockBorderWrapper"]{border:none!important;padding:0!important}
.stColumn>div{padding-top:0!important}

/* ── Top bar (luxury) ── */
.ox-topbar{background:#0C0D10;border-bottom:1px solid #1C1E24;
    padding:12px 24px;display:flex;justify-content:space-between;align-items:center;
    margin:-1rem -1rem 20px -1rem;font-family:Inter,system-ui,sans-serif}
.ox-topbar-left{display:flex;align-items:center;gap:24px}
.ox-topbar-brand{display:flex;align-items:center;gap:10px}
.ox-topbar-dot{width:6px;height:6px;border-radius:50%;background:#C9A84C}
.ox-topbar-name{font-size:11px;color:#C9A84C;font-weight:700;letter-spacing:0.18em;
    text-transform:uppercase}
.ox-topbar-state{font-size:10px;color:#4A6741;font-weight:600;text-transform:uppercase;
    letter-spacing:0.1em}
.ox-topbar-meta{display:flex;gap:20px}
.ox-topbar-tag{font-size:10px;color:#5A5D65;text-transform:uppercase;letter-spacing:0.1em}
.ox-topbar-tag span{color:#E8DCC8;font-weight:600;margin-left:5px}
.ox-topbar-right{font-size:10px;color:#5A5D65;letter-spacing:0.08em}

/* ── Decision card (hero — capital decision) ── */
.pro-card{background:#111318;border:1px solid #1C1E24;border-radius:3px;overflow:hidden;
    margin-bottom:16px;font-family:Inter,system-ui,sans-serif;
    border-top:2px solid #C9A84C}
.pro-card *{font-family:Inter,system-ui,sans-serif}
.pro-overline{font-size:10px;color:#C9A84C;font-weight:600;text-transform:uppercase;
    letter-spacing:0.18em;padding:16px 24px 0}
.pro-hero{padding:8px 24px 12px;display:flex;justify-content:space-between;align-items:flex-start}
.pro-dec{font-size:38px;font-weight:800;line-height:1;letter-spacing:-0.03em}
.pro-sub{font-size:12px;color:#6B6E76;margin-top:4px;font-weight:500}
.pro-ctx{font-size:10px;color:#5A5D65;text-align:right;padding-top:6px;line-height:1.4;
    text-transform:uppercase;letter-spacing:0.1em}
.pro-rec{padding:4px 24px 20px}
.pro-rec-inner{font-size:14px;color:#D4C9B0;line-height:1.5;padding:10px 14px;
    border-radius:2px;font-weight:500;border-left:2px solid #C9A84C}
.pro-metrics{display:grid;grid-template-columns:1fr 1fr 1fr;gap:0;
    border-top:1px solid #1C1E24}
.pro-metric{padding:14px 16px;text-align:center;border-right:1px solid #1C1E24}
.pro-metric:last-child{border-right:none}
.pro-metric-hdr{font-size:10px;color:#5A5D65;font-weight:600;text-transform:uppercase;
    letter-spacing:0.12em;margin-bottom:4px}
.pro-metric-val{font-size:15px;font-weight:700;color:#E8DCC8;line-height:1.2}
.pro-metric-sub{font-size:11px;color:#5A5D65;margin-top:2px}

/* ── Buttons (luxury) ── */
.stButton>button{border-radius:2px!important;font-family:Inter,system-ui,sans-serif!important;
    font-weight:600!important;font-size:12px!important;letter-spacing:0.06em!important;
    text-transform:uppercase!important;transition:all 120ms ease!important;border:1px solid #1C1E24!important}
.stButton>button[kind="primary"]{background:#C9A84C!important;color:#08090C!important;
    border:1px solid #C9A84C!important;font-weight:700!important}
.stButton>button[kind="primary"]:hover{background:#B8973F!important}
.stButton>button[kind="secondary"]{background:#111318!important;color:#D4C9B0!important}
.stButton>button[kind="secondary"]:hover{background:#1C1E24!important}

/* ── Expanders ── */
.streamlit-expanderHeader{color:#7A7D85!important;font-family:Inter,system-ui,sans-serif!important;
    font-size:11px!important;background:#111318!important;border-radius:2px!important;
    text-transform:uppercase!important;letter-spacing:0.1em!important}
details[data-testid="stExpander"]{border:1px solid #1C1E24!important;border-radius:2px!important;
    background:#0C0D10!important}
details[data-testid="stExpander"] *{color:#7A7D85}

/* ── Alerts ── */
div[data-testid="stAlert"]{background:#111318!important;border:1px solid #1C1E24!important;
    color:#7A7D85!important;border-radius:2px!important}

/* ── Text ── */
.stMarkdown p,.stMarkdown li,.stCaption{color:#7A7D85!important}
.stMarkdown h1,.stMarkdown h2,.stMarkdown h3,.stMarkdown strong{color:#E8DCC8!important}
.stMarkdown hr{border-color:#1C1E24!important}

/* ── Inputs ── */
.stTextInput input,.stTextArea textarea,.stSelectbox select{
    background:#111318!important;color:#E8DCC8!important;border:1px solid #1C1E24!important;
    border-radius:2px!important;font-family:Inter,system-ui,sans-serif!important}
.stTextInput input:focus,.stTextArea textarea:focus{border-color:#C9A84C!important}

/* ── System labels ── */
.bull-sys{font-size:10px;color:#5A5D65;text-transform:uppercase;letter-spacing:0.14em;
    font-family:Inter,system-ui,sans-serif;font-weight:600}
.bull-active{color:#4A6741}
.bull-dim{color:#5A5D65}
</style>
""", unsafe_allow_html=True)

SESSIONS_PATH      = "memory_data/sessions.json"
DAILY_MEMORY_PATH  = "memory_data/daily_memory.json"
VOICE_HISTORY_PATH = "memory_data/voice_history.json"

store            = LocalRAGStore()
openai_client    = OpenAI()
anthropic_client = anthropic.Anthropic()

# ══════════════════════════════════════════════════════════
# THEME — clean, calm, modern. Advice-first not dashboard.
# ══════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }

/* ── sidebar ── */
section[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e5e7eb !important;
}
section[data-testid="stSidebar"] .stRadio label { font-size: 0.875rem !important; }

/* ── main padding ── */
.block-container { padding-top: 2.2rem !important; max-width: 1080px !important; }

/* ── hero section ── */
.hero-title {
    font-size: 2rem;
    font-weight: 700;
    color: #111827;
    letter-spacing: -0.03em;
    line-height: 1.2;
    margin-bottom: 0.4rem;
}
.hero-sub {
    font-size: 1rem;
    color: #6b7280;
    line-height: 1.6;
    margin-bottom: 1.4rem;
    max-width: 500px;
}

/* ── answer card ── */
.answer-card {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 1.4rem 1.5rem;
    margin-top: 0.6rem;
}
.answer-section-label {
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #9ca3af;
    margin-bottom: 0.25rem;
}
.answer-conclusion {
    font-size: 1.35rem;
    font-weight: 700;
    color: #111827;
    letter-spacing: -0.02em;
    margin-bottom: 0.1rem;
}
.answer-value {
    font-size: 0.95rem;
    color: #374151;
    line-height: 1.6;
}
.answer-risk {
    font-size: 0.95rem;
    color: #b45309;
    line-height: 1.6;
}

/* ── 3 summary cards row ── */
.summary-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1rem 1.1rem;
}
.sc-label { font-size: 0.68rem; font-weight: 600; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.3rem; }
.sc-value { font-size: 1rem; font-weight: 600; color: #111827; line-height: 1.4; }
.sc-sub   { font-size: 0.8rem; color: #6b7280; margin-top: 0.1rem; }

/* ── ticker card (Today page) ── */
.ticker-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 1.1rem 1.2rem;
    margin-bottom: 0.7rem;
}
.tk-name  { font-size: 1.3rem; font-weight: 700; color: #111827; letter-spacing: -0.02em; }
.tk-label { font-size: 0.72rem; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.2rem; }
.tk-val   { font-size: 0.88rem; color: #374151; line-height: 1.5; }

/* ── memory card ── */
.mem-card {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 1.1rem 1.25rem;
    margin-bottom: 0.6rem;
}
.mem-date { font-size: 0.72rem; color: #9ca3af; margin-bottom: 0.5rem; font-weight: 500; }
.mem-summary { font-size: 0.88rem; color: #374151; line-height: 1.6; }

/* ── behavior card ── */
.beh-card {
    border-radius: 12px;
    padding: 1rem 1.1rem;
    margin-bottom: 0.5rem;
}
.beh-strength   { background: #f0fdf4; border: 1px solid #bbf7d0; }
.beh-pattern    { background: #fffbeb; border: 1px solid #fde68a; }
.beh-improve    { background: #eff6ff; border: 1px solid #bfdbfe; }
.beh-label { font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.3rem; }
.beh-strength .beh-label { color: #15803d; }
.beh-pattern  .beh-label { color: #b45309; }
.beh-improve  .beh-label { color: #1d4ed8; }
.beh-text { font-size: 0.875rem; color: #374151; line-height: 1.5; }

/* ── chat bubbles ── */
.user-bubble {
    background: #4f46e5;
    color: #fff;
    padding: 0.55rem 0.9rem;
    border-radius: 18px 18px 4px 18px;
    margin: 0.3rem 0 0.3rem 18%;
    font-size: 0.88rem;
    line-height: 1.55;
    word-wrap: break-word;
}
.coach-bubble {
    background: #f3f4f6;
    color: #111827;
    padding: 0.55rem 0.9rem;
    border-radius: 18px 18px 18px 4px;
    margin: 0.3rem 18% 0.3rem 0;
    font-size: 0.88rem;
    line-height: 1.6;
    word-wrap: break-word;
}
.bubble-lbl { font-size: 0.65rem; color: #9ca3af; margin-bottom: 0.08rem; }
.bubble-lbl-r { text-align: right; }

/* ── badge ── */
.bdg {
    display: inline-block;
    padding: 0.18rem 0.65rem;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}
.bdg-watch { background: #fef9c3; color: #713f12; }
.bdg-enter { background: #dcfce7; color: #14532d; }
.bdg-avoid { background: #fee2e2; color: #7f1d1d; }
.bdg-hold  { background: #ede9fe; color: #4c1d95; }

/* ── section heading ── */
.sec-h {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #9ca3af;
    margin: 1.4rem 0 0.6rem 0;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid #f3f4f6;
}

/* ── page title ── */
.pg-title { font-size: 1.5rem; font-weight: 700; color: #111827; letter-spacing: -0.02em; margin-bottom: 0.2rem; }
.pg-sub   { font-size: 0.88rem; color: #6b7280; margin-bottom: 1.2rem; }

/* ── wordmark ── */
.wm     { font-size: 1.15rem; font-weight: 700; color: #111827; letter-spacing: -0.02em; }
.wm em  { color: #4f46e5; font-style: normal; }
.wm-sub { font-size: 0.7rem; color: #9ca3af; }

/* ── quick prompt chips ── */
.qp-row { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.8rem; }

/* ── metric override — readable ── */
[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 12px !important;
    padding: 0.9rem 1rem !important;
}

audio { width: 100%; border-radius: 8px; margin-top: 0.3rem; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# COACH ENGINE
# ══════════════════════════════════════════════════════════
def build_system_prompt(top_row, all_results, resp_mode, persona, coach_name):
    valid = [r for r in all_results if "error" not in r]
    lines = []
    for r in valid:
        wfs  = round(r.get("wf_metrics", {}).get("avg_test_sharpe", 0) or 0, 3)
        ret  = round(r["test_metrics"]["net"].get("total_return", 0), 3)
        dd   = round(r["test_metrics"]["net"].get("max_drawdown", 0), 3)

        # ML signal info
        ml   = r.get("full_result", {}).get("ml_analysis", {})
        ml_str = ""
        if ml and ml.get("best_model"):
            ml_sharpe = ml.get("best_metrics", {}).get("sharpe", 0)
            ml_str = f"  ml_best={ml['best_model']} ml_sharpe={ml_sharpe:.2f}"

        # Sentiment info
        sent = r.get("full_result", {}).get("sentiment", {})
        sent_str = ""
        if sent and not sent.get("error"):
            sent_str = f"  sentiment={sent.get('sentiment_label','neutral')} signal={sent.get('signal','neutral')}"

        # Multi-strategy best
        ms   = r.get("full_result", {}).get("multi_strategy", {})
        ms_str = ""
        if ms and ms.get("best_strategy"):
            ms_sharpe = ms.get("test_metrics", {}).get("sharpe", 0)
            ms_str = f"  best_strategy={ms['best_strategy']} strategy_sharpe={ms_sharpe:.2f}"

        lines.append(
            f"[{r['ticker']}] action={r['prob']['action']} conf={r['prob']['confidence']} "
            f"wf_sharpe={wfs} ret={ret} dd={dd}\n"
            f"  driver: {r['prob']['key_driver']}\n"
            f"  risk:   {r['prob']['main_risk']}"
            + ml_str + sent_str + ms_str
        )

    ps = {
        "Calm Coach":      "You are calm, measured, and reassuring. Be honest about risk.",
        "Trader Mode":     "You are direct and actionable. No fluff. Talk like a trader.",
        "Bilingual Mentor":"Match the user's language. Be warm and nuanced.",
    }
    ls = {
        "English":    "Respond only in English.",
        "中文":       "只用中文回答，语气自然口语化。",
        "Bilingual":  "English first, then Chinese.",
        "Follow User":"Detect language and match it.",
    }
    return f"""You are {coach_name}, an AI trading coach inside Orallexa.
{ps.get(persona, "")}
{ls.get(resp_mode, "Respond in English.")}

Your answer will be read aloud (TTS). Rules:
- Natural flowing sentences. No bullets. No markdown symbols.
- 3-5 sentences max. Reference real numbers when relevant.
- Use ML signal, sentiment, and strategy data when answering.
- Answer the specific question asked. Never be generic.

=== TODAY'S MARKET DATA ===
Top ticker: {top_row["ticker"] if top_row else "N/A"}
{chr(10).join(lines) if lines else "No data yet — user needs to run Orallexa first."}"""


def ask_coach(question, top_row, all_results, resp_mode, persona, history, coach_name):
    system = build_system_prompt(top_row, all_results, resp_mode, persona, coach_name)
    msgs = list(history) + [{"role": "user", "content": question}]
    try:
        r = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=512,
            system=system, messages=msgs)
        return r.content[0].text.strip()
    except Exception as e:
        err = str(e).encode("ascii", errors="replace").decode("ascii")
        if "api_key" in err.lower() or "authentication" in err.lower():
            return "API key error: Make sure ANTHROPIC_API_KEY is set."
        if not top_row:
            return "No market data yet. Please run Orallexa first."
        p = top_row["prob"]
        return (f"[API unavailable: {err[:80]}] "
                f"Fallback: {top_row['ticker']} — {p['action']}. {p['key_driver'][:100]}")


# ══════════════════════════════════════════════════════════
# AUDIO
# ══════════════════════════════════════════════════════════
def transcribe(audio_bytes):
    try:
        f = io.BytesIO(audio_bytes)
        f.name = "voice.wav"
        t = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )
        text = getattr(t, "text", "") or ""
        return str(text).strip()
    except Exception:
        st.error("语音识别出错，请检查 API 或网络")
        return ""


def _spoken(text):
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    t = re.sub(r"#{1,4}\s*", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.MULTILINE)
    t = t.replace("%", " percent")
    t = re.sub(r"\n+", ". ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Ensure UTF-8 safe (keeps Chinese characters intact)
    return t.encode("utf-8", errors="ignore").decode("utf-8")


VOICE_MAP = {"nova": "nova", "shimmer": "shimmer", "alloy": "alloy",
             "onyx": "onyx", "echo": "echo"}


def tts(text, voice="nova"):
    if not text.strip(): return None
    if text.startswith("[API"): return None
    try:
        spoken = _spoken(text)
        # Ensure the string is safe for OpenAI SDK on Windows
        # Keep Chinese and all Unicode — encode to bytes first to verify
        spoken = spoken.encode("utf-8").decode("utf-8")
        r = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice=VOICE_MAP.get(voice, "nova"),
            input=spoken)
        return r.read()
    except UnicodeEncodeError:
        # Fallback: strip all non-ASCII and try again with English only
        try:
            spoken_safe = _spoken(text).encode("ascii", errors="ignore").decode("ascii").strip()
            if not spoken_safe:
                spoken_safe = "Coach response ready."
            r = openai_client.audio.speech.create(
                model="tts-1-hd",
                voice=VOICE_MAP.get(voice, "nova"),
                input=spoken_safe)
            return r.read()
        except Exception:
            return None
    except Exception as e:
        safe_err = str(e).encode("ascii", errors="replace").decode("ascii")
        st.warning(f"TTS failed: {safe_err}")
        return None


def play_audio(audio_bytes):
    """Play audio ONCE per new answer using a played-flag in session_state."""
    if not audio_bytes:
        return
    # Only autoplay if this audio hasn't been played yet
    if st.session_state.get("audio_played_id") == id(audio_bytes):
        # Already played — render controls only (no autoplay)
        b64 = base64.b64encode(audio_bytes).decode()
        st.markdown(
            f'<audio controls src="data:audio/mp3;base64,{b64}"></audio>',
            unsafe_allow_html=True)
    else:
        # First time — autoplay and mark as played
        st.session_state["audio_played_id"] = id(audio_bytes)
        b64 = base64.b64encode(audio_bytes).decode()
        st.markdown(
            f'<audio controls autoplay src="data:audio/mp3;base64,{b64}"></audio>',
            unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# MEMORY
# ══════════════════════════════════════════════════════════
def _ensure(path):
    d = os.path.dirname(path)
    if d: os.makedirs(d, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w") as f: f.write("[]")


def load_list(path):
    _ensure(path)
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except: return []


def save_list(path, data):
    _ensure(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def push(path, entry, limit=200):
    r = load_list(path); r.insert(0, entry); save_list(path, r[:limit])


# ══════════════════════════════════════════════════════════
# CACHED DATA
# ══════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False, ttl=60)
def fetch_realtime_price(ticker: str):
    """Fetch today's intraday price — cached for 60 seconds."""
    try:
        import yfinance as yf
        df = yf.download(ticker, period="2d", interval="5m",
                         progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        last  = float(df["Close"].iloc[-1])
        prev  = float(df["Close"].iloc[0])
        chg   = last - prev
        pct   = chg / prev * 100 if prev else 0.0
        return {"price": round(last, 2), "change": round(chg, 2),
                "pct_change": round(pct, 2), "ticker": ticker}
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def split_data(ticker, train_ratio=0.7):
    data = MarketDataSkill(ticker).execute()
    ta   = TechnicalAnalysisSkill(data).add_indicators().dropna().copy()
    idx  = int(len(ta) * train_ratio)
    return ta.iloc[:idx].copy(), ta.iloc[idx:].copy()


@st.cache_data(show_spinner=False)
def equity_data(ticker, params, train_ratio=0.7, tc=0.001, sl=0.001):
    tr, te = split_data(ticker, train_ratio)
    kw = dict(params=params, debug=False, transaction_cost=tc, slippage=sl)
    return simple_backtest(tr, **kw), simple_backtest(te, **kw)


# ══════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════
CP = ["#4f46e5", "#10b981", "#f59e0b", "#ef4444"]


def _ls(ax, fig):
    fig.patch.set_facecolor("#fff"); ax.set_facecolor("#f9fafb")
    ax.tick_params(colors="#6b7280", labelsize=8)
    ax.title.set_color("#111827"); ax.title.set_fontsize(10)
    ax.grid(True, color="#e5e7eb", lw=0.5, ls="--")
    for sp in ax.spines.values(): sp.set_edgecolor("#e5e7eb")


def chart_equity(ticker, tr, te):
    fig, axes = plt.subplots(2, 1, figsize=(9, 6))
    for ax, bt, lbl in zip(axes, [tr, te], ["Train", "Test"]):
        _ls(ax, fig)
        ax.plot(bt["CumulativeGrossStrategyReturn"], label="Gross",  color=CP[0], lw=1.3)
        ax.plot(bt["CumulativeNetStrategyReturn"],   label="Net",    color=CP[1], lw=1.3)
        ax.plot(bt["CumulativeMarketReturn"],        label="Market", color="#9ca3af", lw=1, ls="--")
        ax.set_title(f"{ticker} — {lbl}")
        ax.legend(fontsize=7, facecolor="#fff", edgecolor="#e5e7eb")
    plt.tight_layout(); return fig


def chart_portfolio(df):
    fig, ax = plt.subplots(figsize=(9, 3.5))
    _ls(ax, fig)
    ax.plot(df["PortfolioNetCumulative"],    label="Strategy", color=CP[0], lw=1.5)
    ax.plot(df["PortfolioMarketCumulative"], label="Buy & Hold", color="#9ca3af", lw=1, ls="--")
    ax.fill_between(df.index, df["PortfolioNetCumulative"], alpha=0.07, color=CP[0])
    ax.set_title("Portfolio Equity Curve")
    ax.legend(fontsize=7, facecolor="#fff", edgecolor="#e5e7eb")
    plt.tight_layout(); return fig


def chart_vs(ticker, cur, prop):
    fig, ax = plt.subplots(figsize=(9, 3.5))
    _ls(ax, fig)
    ax.plot(cur["CumulativeNetStrategyReturn"],  label="Current",  color=CP[1], lw=1.3)
    ax.plot(prop["CumulativeNetStrategyReturn"], label="Proposal", color=CP[0], lw=1.3)
    ax.plot(cur["CumulativeMarketReturn"],       label="Market",   color="#9ca3af", lw=1, ls="--")
    ax.set_title(f"{ticker} — Current vs Proposal")
    ax.legend(fontsize=7, facecolor="#fff", edgecolor="#e5e7eb")
    plt.tight_layout(); return fig


def chart_sharpe(results):
    valid = [r for r in results if "error" not in r]
    if not valid: return None
    tks  = [r["ticker"] for r in valid]
    vals = [r.get("wf_metrics", {}).get("avg_test_sharpe", 0) or 0 for r in valid]
    fig, ax = plt.subplots(figsize=(7, 2.8))
    _ls(ax, fig)
    clrs = [CP[1] if v > 0 else CP[3] for v in vals]
    bars = ax.bar(tks, vals, color=clrs, width=0.4, zorder=3)
    ax.axhline(0, color="#d1d5db", lw=0.7, ls="--")
    ax.set_title("Walk-Forward Avg Sharpe by Ticker")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.02,
                f"{v:.2f}", ha="center", va="bottom", color="#6b7280", fontsize=8)
    plt.tight_layout(); return fig


def chart_strategy_comparison(ticker, ms_results: dict):
    """3 curves on one chart: best rule strategy vs ML vs buy-and-hold."""
    if not ms_results: return None
    try:
        all_res = ms_results.get("all_results", {})
        if not all_res: return None

        fig, ax = plt.subplots(figsize=(9, 4))
        _ls(ax, fig)

        colors = [CP[0], CP[1], CP[2], CP[3], "#f59e0b", "#8b5cf6"]
        plotted = 0
        for i, (name, data) in enumerate(all_res.items()):
            if data.get("error") or "test_signal" not in data:
                continue
            color = colors[i % len(colors)]
            lw = 2.0 if name == ms_results.get("best_strategy") else 1.0
            ls = "--" if name == "buy_and_hold" else "-"
            # compute cumulative from signal
            sig = data["test_signal"]
            # just plot the label with metrics
            ret = data.get("test_metrics", {}).get("total_return", 0)
            sharpe = data.get("test_metrics", {}).get("sharpe", 0)
            label = f"{name} (S={sharpe:.2f}, R={ret:+.1%})"
            ax.plot([], [], color=color, lw=lw, ls=ls, label=label)
            plotted += 1

        # Plot actual equity curves if we have backtest data
        from engine.multi_strategy import _run_strategy_backtest
        import yfinance as yf
        ax.cla(); _ls(ax, fig)

        best_name = ms_results.get("best_strategy", "")
        for i, (name, data) in enumerate(all_res.items()):
            if "error" in data and data["error"]: continue
            if "test_signal" not in data: continue
            color = colors[i % len(colors)]
            lw = 2.2 if name == best_name else 1.1
            ls_style = "--" if name == "buy_and_hold" else "-"
            alpha = 1.0 if name == best_name or name == "buy_and_hold" else 0.6
            sharpe = data.get("test_metrics", {}).get("sharpe", 0)
            ret    = data.get("test_metrics", {}).get("total_return", 0)
            label  = f"{name} (Sharpe={sharpe:.2f})"
            # dummy line for legend
            ax.plot([], [], color=color, lw=lw, ls=ls_style,
                    alpha=alpha, label=label)

        ax.set_title(f"{ticker} — Strategy Comparison")
        ax.legend(fontsize=7, facecolor="#fff", edgecolor="#e5e7eb",
                  loc="upper left", framealpha=0.9)
        ax.text(0.5, 0.5, "Strategy comparison\n(equity curves in Analysis tab)",
                ha="center", va="center", transform=ax.transAxes,
                color="#9ca3af", fontsize=10)
        plt.tight_layout()
        return fig
    except Exception:
        return None


def chart_feature_importance(fi_df: pd.DataFrame, ticker: str):
    """Horizontal bar chart of top ML feature importances."""
    if fi_df is None or fi_df.empty: return None
    try:
        top = fi_df.head(10).sort_values("importance")
        fig, ax = plt.subplots(figsize=(7, 3.5))
        _ls(ax, fig)
        bars = ax.barh(top["feature"], top["importance"],
                       color=CP[0], alpha=0.85, height=0.6)
        ax.set_title(f"{ticker} — Top Feature Importances (Random Forest)")
        ax.set_xlabel("Importance", fontsize=8, color="#6b7280")
        for bar, val in zip(bars, top["importance"]):
            ax.text(val + 0.001, bar.get_y() + bar.get_height()/2,
                    f"{val:.3f}", va="center", fontsize=7, color="#6b7280")
        plt.tight_layout()
        return fig
    except Exception:
        return None


def chart_ml_comparison(ml_result: dict, ticker: str):
    """Bar chart comparing ML models by test Sharpe."""
    if not ml_result or ml_result.get("summary", pd.DataFrame()).empty:
        return None
    try:
        df = ml_result["summary"]
        fig, ax = plt.subplots(figsize=(7, 2.8))
        _ls(ax, fig)
        colors = [CP[1] if v > 0 else CP[3] for v in df["sharpe"]]
        bars = ax.bar(df["model"], df["sharpe"], color=colors, width=0.5, zorder=3)
        ax.axhline(0, color="#d1d5db", lw=0.7, ls="--")
        ax.set_title(f"{ticker} — ML Models vs Buy-and-Hold (Test Sharpe)")
        ax.tick_params(axis="x", rotation=15, labelsize=8)
        for b, v in zip(bars, df["sharpe"]):
            ax.text(b.get_x() + b.get_width()/2,
                    b.get_height() + (0.02 if v >= 0 else -0.08),
                    f"{v:.2f}", ha="center", fontsize=8, color="#6b7280")
        plt.tight_layout()
        return fig
    except Exception:
        return None


def chart_factor_scores(results):
    """Radar-style bar chart showing factor breakdown per ticker."""
    valid = [r for r in results if "error" not in r]
    if not valid: return None
    try:
        from engine.factor_engine import FactorEngine
        rows = []
        for r in valid:
            bt = r.get("bt_test")
            if bt is None or bt.empty: continue
            fe = FactorEngine(bt)
            fe.compute_all()
            factors = fe._factors
            rows.append({
                "ticker":    r["ticker"],
                "momentum":  round(float(factors.get("momentum", pd.Series([0])).iloc[-1]), 2),
                "trend":     round(float(factors.get("trend",    pd.Series([0])).iloc[-1]), 2),
                "volume":    round(float(factors.get("volume",   pd.Series([0])).iloc[-1]), 2),
            })
        if not rows: return None
        df = pd.DataFrame(rows)
        x  = range(len(df))
        w  = 0.25
        fig, ax = plt.subplots(figsize=(8, 3.2))
        _ls(ax, fig)
        ax.bar([i - w for i in x], df["momentum"], width=w,
               label="Momentum", color=CP[0], alpha=0.85)
        ax.bar([i     for i in x], df["trend"],    width=w,
               label="Trend",    color=CP[1], alpha=0.85)
        ax.bar([i + w for i in x], df["volume"],   width=w,
               label="Volume",   color=CP[2], alpha=0.85)
        ax.set_xticks(list(x)); ax.set_xticklabels(df["ticker"], fontsize=9)
        ax.axhline(0, color="#d1d5db", lw=0.7, ls="--")
        ax.set_title("Factor Scores by Ticker (latest)")
        ax.legend(fontsize=7, facecolor="#fff", edgecolor="#e5e7eb")
        plt.tight_layout()
        return fig
    except Exception:
        return None


# ══════════════════════════════════════════════════════════
# PRODUCT HELPERS
# ══════════════════════════════════════════════════════════
def market_mood(results):
    valid = [r for r in results if "error" not in r]
    if not valid: return "—"
    top = max(valid, key=lambda x: x.get("wf_metrics", {}).get("avg_test_sharpe", float("-inf")))
    s   = top.get("wf_metrics", {}).get("avg_test_sharpe", 0) or 0
    if s >= 2:   return "Constructive"
    if s >= 0.5: return "Cautious"
    return "Defensive"


def mood_color(m):
    return {"Constructive": "#15803d", "Cautious": "#b45309"}.get(m, "#b91c1c")


def alabel(action):
    a = (action or "").lower()
    if "avoid" in a: return "Avoid"
    if "long"  in a or "enter" in a: return "Enter"
    return "Watch"


def bdg(text):
    cls = {"Watch": "bdg-watch", "Enter": "bdg-enter", "Avoid": "bdg-avoid"}.get(text, "bdg-hold")
    return f'<span class="bdg {cls}">{text}</span>'


def risk_level(top_row):
    if not top_row: return "—"
    conf = (top_row["prob"].get("confidence") or "").lower()
    if "high" in conf: return "Medium"
    if "low"  in conf: return "Low"
    return "Medium"


def portfolio_tone(results):
    m = market_mood(results)
    return {"Constructive": "Constructive", "Cautious": "Cautious"}.get(m, "Defensive")


def daily_entry(results, resp_mode, persona):
    valid = [r for r in results if "error" not in r]
    if not valid: return None
    top = max(valid, key=lambda x: x.get("wf_metrics", {}).get("avg_test_sharpe", float("-inf")))
    return {
        "date":             datetime.now().strftime("%Y-%m-%d"),
        "created_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "language_mode":    resp_mode,
        "persona_mode":     persona,
        "tickers_reviewed": [r["ticker"] for r in valid],
        "top_ticker":       top["ticker"],
        "top_action":       top["prob"]["action"],
        "market_mood":      market_mood(valid),
        "portfolio_stance": portfolio_tone(valid),
        "ai_summary":       f"Focused on {top['ticker']}. Action: {top['prob']['action']}. {top['prob']['key_driver']}.",
        "main_risks":       [top["prob"]["main_risk"]],
        "user_questions":   [], "user_action_summary": "",
        "end_of_day_review": "", "discipline_score": None,
        "emotion_label": "", "mistake_flags": [], "strength_flags": []
    }


def sess_entry(q, top_row, resp_mode, persona):
    return {
        "session_id":    f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "language_mode": resp_mode, "persona_mode": persona,
        "user_input":    q,
        "ticker_focus":  [top_row["ticker"]],
        "top_ticker":    top_row["ticker"],
        "ai_conclusion": top_row["prob"]["action"],
        "confidence":    top_row["prob"]["confidence"],
    }


# ══════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════
with st.sidebar:
    lang = st.selectbox("Language / 语言", ["English", "中文"], key="sb_lang")

    st.markdown(
        '<div class="wm">Oral<em>lexa</em></div>'
        '<div class="wm-sub">AI trading coach · voice · memory</div>',
        unsafe_allow_html=True)
    st.divider()

    page = st.radio(
        "NAV",
        ["Home", "Today", "Memory", "Analysis", "Settings"],
        label_visibility="collapsed",
        key="sb_page")
    st.divider()

    # ── coach identity (always visible) ──
    st.markdown("**🎙 Coach**")
    sb_cname = st.text_input(
        "Coach name",
        value=st.session_state.get("coach_name", ""),
        placeholder="Nova, Aria, Rex…",
        key="sb_cname")
    if sb_cname.strip():
        st.session_state["coach_name"] = sb_cname.strip()
    else:
        st.caption("💡 Give your coach a name")

    sb_persona = st.selectbox(
        "Persona style",
        ["Calm Coach", "Trader Mode", "Bilingual Mentor"],
        index=["Calm Coach", "Trader Mode", "Bilingual Mentor"].index(
            st.session_state.get("persona", "Calm Coach")),
        key="sb_persona")
    st.session_state["persona"] = sb_persona

    sb_resp = st.selectbox(
        "Response language",
        ["English", "Follow User", "中文", "Bilingual"],
        index=["English", "Follow User", "中文", "Bilingual"].index(
            st.session_state.get("resp_mode", "English")),
        key="sb_resp")
    st.session_state["resp_mode"] = sb_resp

    voice_opts = {
        "Nova ✦ warm female": "nova",
        "Shimmer — soft female": "shimmer",
        "Alloy — neutral": "alloy",
        "Onyx — deep male": "onyx",
        "Echo — balanced": "echo",
    }
    cur_vk  = st.session_state.get("voice_key", "nova")
    cur_lbl = next((k for k, v in voice_opts.items() if v == cur_vk), "Nova ✦ warm female")
    sb_voice = st.selectbox("Voice", list(voice_opts.keys()),
        index=list(voice_opts.keys()).index(cur_lbl), key="sb_voice")
    st.session_state["voice_key"] = voice_opts[sb_voice]

    st.divider()

    # ── run settings ──
    st.markdown("**Run Settings**")
    tickers_raw = st.text_input("Tickers", value="NVDA,AAPL,TSLA", key="sb_tickers")
    n_iter      = st.number_input("Iterations", 1, 5, 2, key="sb_iters")

    with st.expander("Advanced"):
        train_r = st.slider("Train split", 0.5, 0.9, 0.7, 0.05, key="sb_tr")
        wf_tr   = st.slider("WF train",   0.3, 0.8, 0.6, 0.05, key="sb_wftr")
        wf_te   = st.slider("WF test",    0.1, 0.4, 0.2, 0.05, key="sb_wfte")
        wf_st   = st.slider("WF step",    0.05, 0.3, 0.1, 0.05, key="sb_wfst")
        tc      = st.slider("Tx cost",    0.0, 0.01, 0.001, 0.0005, key="sb_tc")
        sl_     = st.slider("Slippage",   0.0, 0.01, 0.001, 0.0005, key="sb_sl")
        top_n   = st.number_input("Top N", 1, 5, 2, key="sb_topn")

    st.divider()
    ai_on  = st.checkbox("AI Analysis",        True, key="sb_ai")
    rag_on = st.checkbox("RAG Notes",          True, key="sb_rag")
    sg_on  = st.checkbox("Strategy Generator", True, key="sb_sg")
    sv_on  = st.checkbox("Validate Proposal",  True, key="sb_sv")

    if rag_on:
        with st.expander("RAG / Notes"):
            tklist = [t.strip().upper() for t in tickers_raw.replace("，", ",").split(",") if t.strip()]
            rtk = st.selectbox("Ticker", tklist or ["AAPL"], key="rag_tk")
            if st.button("Import news", key="rag_imp"):
                try:
                    n = store.add_news_documents(rtk, NewsSkill(rtk).fetch_news(limit=8))
                    st.success(f"Imported {n}")
                except Exception as e: st.error(str(e))
            rt = st.text_input("Title", "", key="rag_t")
            rb = st.text_area("Note", "", height=70, key="rag_b")
            if st.button("Save", key="rag_sv"):
                if rb.strip():
                    store.add_document(ticker=rtk, title=rt or "Untitled", text=rb, source="manual")
                    st.success("Saved.")
                else: st.warning("Enter text first.")

    st.divider()

    # ── Decision Mode ──
    st.markdown("**Decision Mode**")
    _mode_opts = ["scalp", "intraday", "swing"]
    _mode_default = st.session_state.get("trade_mode", "intraday")
    if _mode_default not in _mode_opts:
        _mode_default = "intraday"
    trade_mode = st.selectbox(
        "Mode", _mode_opts,
        index=_mode_opts.index(_mode_default),
        key="sb_mode")
    st.session_state["trade_mode"] = trade_mode

    _tf_map = {"scalp": ["1m", "5m"], "intraday": ["15m", "1h"], "swing": ["1D"]}
    _tf_opts = _tf_map[trade_mode]
    _tf_default = st.session_state.get("trade_timeframe", _tf_opts[0])
    if _tf_default not in _tf_opts:
        _tf_default = _tf_opts[0]
    trade_timeframe = st.selectbox(
        "Timeframe", _tf_opts,
        index=_tf_opts.index(_tf_default),
        key="sb_timeframe")
    st.session_state["trade_timeframe"] = trade_timeframe

    st.markdown("")
    run_btn = st.button("▶  Run Orallexa", use_container_width=True, key="sb_run")

tickers = [t.strip().upper() for t in tickers_raw.replace("，", ",").split(",") if t.strip()]


# ══════════════════════════════════════════════════════════
# SETTINGS (all set live in sidebar above)
# ══════════════════════════════════════════════════════════
coach_name = st.session_state.get("coach_name", "Coach") or "Coach"
persona    = st.session_state.get("persona",    "Calm Coach")
resp_mode  = st.session_state.get("resp_mode",  "English")
voice_key  = st.session_state.get("voice_key",  "nova")
user_pref  = st.session_state.get("user_pref",  "Balanced")


# ══════════════════════════════════════════════════════════
# RUN PIPELINE
# ══════════════════════════════════════════════════════════
if run_btn:
    results = []
    bar = st.progress(0, text="Starting…")
    for i, tk in enumerate(tickers):
        bar.progress(i / max(len(tickers), 1), text=f"Analysing {tk}…")
        try:
            brain  = OrallexaBrain(tk)
            loop   = StrategyLoop(brain)
            res    = loop.run(iterations=int(n_iter), save_prefix=None,
                              train_ratio=float(train_r),
                              wf_train_ratio=float(wf_tr),
                              wf_test_ratio=float(wf_te),
                              wf_step_ratio=float(wf_st))
            best   = res.get("best_result", {})
            summ   = best.get("summary", {})
            wfm    = best.get("walk_forward_metrics", {})
            bt_te, det = brain.evaluate_test(
                params=res.get("best_params"),
                train_ratio=float(train_r),
                transaction_cost=float(tc), slippage=float(sl_))

            rag = ""
            if rag_on:
                try:
                    retr = store.retrieve(query=f"{tk} trend risk outlook", ticker=tk, top_k=5)
                    rag  = "\n\n".join(
                        f"[{j+1}] {d['title']}: {d['text']}"
                        for j, (d, _) in enumerate(retr)) if retr else ""
                except Exception as e: rag = f"RAG error: {e}"

            ai_rep = ui_analysis_with_rag(summary=summ, metrics=det, rag_context=rag, ticker=tk) \
                     if ai_on else "AI disabled."
            prob = ui_probability_report(summary=summ, metrics=det, rag_context=rag, ticker=tk) \
                   if ai_on else {
                       "bull_probability": 45, "neutral_probability": 30, "bear_probability": 25,
                       "confidence": "medium", "action": "Watch", "bias": "Neutral",
                       "key_driver": "AI disabled.", "main_risk": "AI disabled."}

            strat = generate_strategy_proposal(summary=summ, metrics=det, ticker=tk, rag_context=rag) \
                    if sg_on else {
                        "strategy_type": "trend_following", "use_ma_filter": True,
                        "use_rsi_filter": True, "rsi_min": 35, "rsi_max": 65,
                        "stop_loss": 0.03, "take_profit": 0.08, "max_positions": 2,
                        "holding_bias": "medium_term",
                        "reasoning": "Disabled.", "risk_notes": "Disabled."}

            pv = cmp = None; acc = False
            if sv_on:
                _, raw = split_data(tk, train_ratio=float(train_r))
                pv   = run_proposal_backtest(raw, proposal=strat,
                           fallback_params=res.get("best_params"),
                           transaction_cost=float(tc), slippage=float(sl_))
                cmp  = compare_metric_block(det, pv["metrics"])
                acc  = proposal_is_better(det, pv["metrics"])

            results.append({
                "ticker": tk, "summary": summ,
                "best_params": res.get("best_params"),
                "best_train_sharpe": res.get("best_train_sharpe"),
                "test_metrics": det, "wf_metrics": wfm,
                "ai_report": ai_rep, "prob": prob, "strategy_proposal": strat,
                "proposal_validation": pv, "comparison": cmp, "accepted": acc,
                "rag_context": rag, "full_result": res, "bt_test": bt_te})
        except Exception as e:
            results.append({"ticker": tk, "error": str(e)})

    bar.progress(1.0, text="Done.")

    # ── 相关性过滤选股 ──────────────────────────────────────
    try:
        from portfolio.correlation_filter import filter_by_correlation, correlation_report
        # 给 correlation filter 提供每个 ticker 的 bt_test 数据
        ticker_dfs = {r["ticker"]: r["bt_test"]
                      for r in results if "error" not in r and "bt_test" in r}
        sel = filter_by_correlation(results, ticker_dfs,
                                    max_corr=0.75, top_n=int(top_n))
        if not sel:  # 如果过滤掉太多，退回到原来的选法
            sel = select_top_n(results, n=int(top_n))
        corr_rpt = correlation_report(ticker_dfs)
    except Exception:
        sel = select_top_n(results, n=int(top_n))
        corr_rpt = {}
    # ──────────────────────────────────────────────────────────

    pw    = allocate_by_sharpe(sel)
    bmap  = {r["ticker"]: r["bt_test"] for r in sel}
    pdf   = build_portfolio_curve(bmap, pw)
    pmets = evaluate_portfolio(pdf)

    st.session_state.update({
        "final_results":     results,
        "portfolio_weights": pw,
        "portfolio_df":      pdf,
        "portfolio_metrics": pmets,
        "corr_report":       corr_rpt})

    me = daily_entry(results, resp_mode, persona)
    if me: push(DAILY_MEMORY_PATH, me)
    st.success("✓ Run complete — head to Home or Today to see your brief.")


# ══════════════════════════════════════════════════════════
# LOAD SHARED STATE
# ══════════════════════════════════════════════════════════
results = st.session_state.get("final_results", [])
pw      = st.session_state.get("portfolio_weights", {})
pdf     = st.session_state.get("portfolio_df", pd.DataFrame())
pmets   = st.session_state.get("portfolio_metrics", {})
mem_recs  = load_list(DAILY_MEMORY_PATH)
sess_recs = load_list(SESSIONS_PATH)
vh_recs   = load_list(VOICE_HISTORY_PATH)

valid  = [r for r in results if "error" not in r]
ranked = sorted(valid,
    key=lambda x: x.get("wf_metrics", {}).get("avg_test_sharpe", float("-inf")),
    reverse=True)
top = ranked[0] if ranked else None

QP_EN = [
    "What should I focus on today?",
    "Explain today's setup in English",
    "Give me the safest setup",
    "What's the biggest risk right now?",
    "Hold or exit?",
    "Compare my tickers",
    "Record today's trading thought",
    "What's the trend?",
]
QP_ZH = [
    "今天我该关注什么？",
    "用中文解释今日机会",
    "给我最安全的方案",
    "现在最大的风险是什么？",
    "持仓还是离场？",
    "对比我的标的",
    "记录今日交易想法",
    "目前趋势如何？",
]


# ══════════════════════════════════════════════════════════
# HOME — Trading cockpit + coach
# ══════════════════════════════════════════════════════════
if page == "Home":
    for k, v in [("voice_transcript", ""), ("last_audio_hash", None),
                 ("conversation_history", []), ("pending_auto_ask", ""),
                 ("voice_answer_audio", None), ("last_answer_text", ""),
                 ("audio_played_id", None), ("home_decision", None),
                 ("home_ma_result", None), ("chart_decision", None)]:
        if k not in st.session_state: st.session_state[k] = v

    _trade_mode      = st.session_state.get("trade_mode", "intraday")
    _trade_timeframe = st.session_state.get("trade_timeframe", "15m")

    home_ticker_raw = tickers[0] if tickers else "NVDA"
    home_ticker = home_ticker_raw.strip().upper()
    setup_notes = ""

    # ── Top bar ──
    st.markdown(
        f'<div class="ox-topbar">'
        f'<div class="ox-topbar-left">'
        f'<div class="ox-topbar-brand">'
        f'<div class="ox-topbar-dot"></div>'
        f'<span class="ox-topbar-name">Orallexa Capital Engine</span>'
        f'<span class="ox-topbar-state">Active</span>'
        f'</div>'
        f'<div class="ox-topbar-meta">'
        f'<span class="ox-topbar-tag">Asset<span>{home_ticker}</span></span>'
        f'<span class="ox-topbar-tag">Strategy<span>{_trade_mode.upper()}</span></span>'
        f'<span class="ox-topbar-tag">Horizon<span>{_trade_timeframe}</span></span>'
        f'</div>'
        f'</div>'
        f'<div class="ox-topbar-right">{lang}</div>'
        f'</div>',
        unsafe_allow_html=True)

    # ── 3-panel layout ──
    col_left, col_center, col_right = st.columns([1, 2.5, 1.5], gap="medium")

    # ────────────────────────────────────────────────────────
    # LEFT — System Controls
    # ────────────────────────────────────────────────────────
    with col_left:
        # ── Symbol & Mode ──
        home_ticker_raw = st.text_input(
            "Asset", value=tickers[0] if tickers else "NVDA",
            placeholder="NVDA", key="home_ticker")
        home_ticker = home_ticker_raw.strip().upper() or (tickers[0] if tickers else "NVDA")
        setup_notes = st.text_input(
            "Context", key="home_notes", placeholder="Catalyst, level, thesis...")

        # System state card
        st.markdown(
            f'<div class="bull-card">'
            f'<div class="bull-card-hdr">Engine Status</div>'
            f'<div class="bull-card-row"><span class="bull-card-label">Engine</span>'
            f'<span class="bull-card-value bull-active">Active</span></div>'
            f'<div class="bull-card-row"><span class="bull-card-label">Strategy</span>'
            f'<span class="bull-card-value">{_trade_mode.upper()}</span></div>'
            f'<div class="bull-card-row"><span class="bull-card-label">Horizon</span>'
            f'<span class="bull-card-value">{_trade_timeframe}</span></div>'
            f'</div>',
            unsafe_allow_html=True)

        _do_analyze = st.button("RUN SIGNAL", key="dec_run_btn",
                                use_container_width=True, type="primary")
        _do_deep    = st.button("OPEN INTELLIGENCE", key="deep_run_btn",
                                use_container_width=True,
                                help="Multi-agent deep scan (60-120s)")

        # ── Market Snapshot ──
        st.markdown(
            '<div class="bull-card">'
            '<div class="bull-card-hdr">Upload Market Snapshot</div>'
            '</div>', unsafe_allow_html=True)

        chart_file = st.file_uploader(
            "Upload chart", type=["png", "jpg", "jpeg"],
            key="chart_upload", label_visibility="collapsed")

        _do_chart = False
        if chart_file is not None:
            _img_bytes_left = chart_file.read()
            chart_file.seek(0)
            _do_chart = st.button("ANALYZE SNAPSHOT", key="chart_analyze_btn",
                                  use_container_width=True, type="primary")

        # ── Voice Command ──
        with st.expander("Voice Command"):
            audio_in = st.audio_input("Record", key="mic", label_visibility="collapsed")
            if audio_in is not None:
                ab = audio_in.read(); ah = hash(ab)
                if ah != st.session_state["last_audio_hash"]:
                    st.session_state["last_audio_hash"] = ah
                    with st.spinner("Transcribing..."):
                        txt = transcribe(ab)
                    if txt:
                        st.session_state["voice_transcript"] = txt
                        st.session_state["pending_auto_ask"] = txt

    # ────────────────────────────────────────────────────────
    # ────────────────────────────────────────────────────────
    # CENTER — Decision Engine
    # ────────────────────────────────────────────────────────
    with col_center:
        _do_deep_analyze = _do_deep

        if True:
            if _do_deep_analyze:
                st.markdown('<div class="bull-card" style="padding:10px 16px;text-align:center">'
                            '<span style="color:#4A6741;font-size:11px;font-weight:600;'
                            'text-transform:uppercase;letter-spacing:0.1em">'
                            'Bull scanning market...</span></div>',
                            unsafe_allow_html=True)
                with st.spinner(f"Running multi-agent analysis for {home_ticker}…"):
                    try:
                        from datetime import date as _today
                        _brain = OrallexaBrain(home_ticker)
                        _ma_result = _brain.run_deep_analysis(
                            trade_date=_today.today().isoformat(),
                        )
                        st.session_state["home_decision"]    = _ma_result.decision_output
                        st.session_state["home_ma_result"]   = _ma_result
                        # Save to decision log
                        try:
                            from engine.decision_log import save_decision
                            save_decision(
                                decision=_ma_result.decision_output,
                                ticker=home_ticker,
                                mode="deep",
                                timeframe="1D",
                                notes=setup_notes,
                            )
                        except Exception:
                            pass
                    except Exception as _e:
                        st.markdown('<div class="bull-card" style="padding:10px 16px">'
                                    '<span style="color:#8B3A3A;font-size:12px">'
                                    'Analysis unavailable. Check connection and retry.</span></div>',
                                    unsafe_allow_html=True)

            if st.session_state.get("home_ma_result"):
                _mar = st.session_state["home_ma_result"]
                with st.expander("Market Report", expanded=False):
                    st.markdown(_mar.market_report or "_No market report._")
                with st.expander("News Report", expanded=False):
                    st.markdown(_mar.news_report or "_No news report._")
                with st.expander("Fundamentals Report", expanded=False):
                    st.markdown(_mar.fundamentals_report or "_No fundamentals report._")
                with st.expander("Investment Plan", expanded=False):
                    st.markdown(_mar.investment_plan or "_No plan._")
                st.divider()

            if _do_analyze:
                with st.spinner(f"Analyzing {home_ticker} ({_trade_mode}/{_trade_timeframe})…"):
                    try:
                        # Auto-fetch RAG context
                        _rag_ctx = ""
                        try:
                            _retr = store.retrieve(
                                query=f"{home_ticker} {_trade_mode} setup outlook",
                                ticker=home_ticker, top_k=3)
                            _rag_ctx = "\n\n".join(
                                f"[{j+1}] {d['title']}: {d['text']}"
                                for j, (d, _) in enumerate(_retr)) if _retr else ""
                        except Exception:
                            pass

                        # Auto-fetch sentiment for swing
                        _sent_score = None
                        if _trade_mode == "swing":
                            try:
                                from engine.sentiment import analyze_ticker_sentiment
                                _sent_res = analyze_ticker_sentiment(ticker=home_ticker)
                                _sent_score = _sent_res.get("avg_compound")
                            except Exception:
                                pass

                        _brain = OrallexaBrain(home_ticker)
                        if _trade_mode == "swing" and _sent_score is not None:
                            _decision = _brain.run_prediction(
                                use_claude=True,
                                rag_context=_rag_ctx,
                                sentiment_score=_sent_score,
                                mode="swing",
                            )
                        else:
                            _decision = _brain.run_for_mode(
                                mode=_trade_mode,
                                timeframe=_trade_timeframe,
                                use_claude=True,
                                rag_context=_rag_ctx,
                            )
                        st.session_state["home_decision"]  = _decision
                        st.session_state["home_ma_result"] = None   # clear deep analysis

                        # Save to decision log
                        try:
                            from engine.decision_log import save_decision
                            save_decision(
                                decision=_decision,
                                ticker=home_ticker,
                                mode=_trade_mode,
                                timeframe=_trade_timeframe,
                                notes=setup_notes,
                            )
                        except Exception:
                            pass
                    except Exception as _e:
                        st.markdown('<div class="bull-card" style="padding:10px 16px">'
                                    '<span style="color:#8B3A3A;font-size:12px">'
                                    'Analysis unavailable. Check connection and retry.</span></div>',
                                    unsafe_allow_html=True)

            _dec = st.session_state.get("home_decision")
            if _dec:
                from models.card_formatter import (
                    humanize_reasoning, signal_label, confidence_label,
                    risk_description, decision_subtitle, decision_display,
                )

                _sig_str = getattr(_dec, "signal_strength", 0.0)
                _recom   = getattr(_dec, "recommendation", "")

                # Decision accent color (bright on dark)
                # Luxury palette: emerald bull / muted rose bear / champagne neutral
                _dc = {"BUY": "#4A6741", "SELL": "#8B3A3A", "WAIT": "#C9A84C"
                       }.get(_dec.decision, "#5A5D65")
                _rec_bg = {"BUY": "rgba(74,103,65,0.08)", "SELL": "rgba(139,58,58,0.08)",
                           "WAIT": "rgba(201,168,76,0.06)"}.get(_dec.decision, "rgba(90,93,101,0.04)")
                _r_color = {"LOW": "#4A6741", "MEDIUM": "#C9A84C", "HIGH": "#8B3A3A"
                            }.get(_dec.risk_level, "#5A5D65")

                st.markdown(
                    f'<div class="pro-card">'
                    f'<div class="pro-overline">Engine Decision</div>'

                    f'<div class="pro-hero">'
                    f'<div>'
                    f'<div class="pro-dec" style="color:{_dc}">{decision_display(_dec.decision)}</div>'
                    f'<div class="pro-sub">{decision_subtitle(_dec.decision)}</div>'
                    f'</div>'
                    f'<div class="pro-ctx">{home_ticker}<br>'
                    f'{_trade_mode.title()} ({_trade_timeframe})</div>'
                    f'</div>'

                    # ── Recommendation ──
                    f'<div class="pro-rec">'
                    f'<div class="pro-rec-inner" style="background:{_rec_bg};'
                    f'border-left:3px solid {_dc}">'
                    f'{_recom or "Analysis complete."}'
                    f'</div></div>',
                    unsafe_allow_html=True)

                # News context line (subtle, 1 line)
                _ns_val = st.session_state.get("_news_sentiment", 0)
                _ns_cnt = st.session_state.get("_news_count", 0)
                if _ns_cnt > 0:
                    _ns_lbl = "bullish" if _ns_val > 0.1 else "bearish" if _ns_val < -0.1 else "neutral"
                    _ns_col = "#4A6741" if _ns_val > 0.1 else "#8B3A3A" if _ns_val < -0.1 else "#6B7280"
                    st.markdown(
                        f'<div style="background:#121821;border:1px solid #1F2933;border-radius:4px;'
                        f'padding:6px 16px;margin-bottom:2px;font-family:Inter,system-ui,sans-serif;'
                        f'font-size:11px;color:#6B7280">'
                        f'News: <span style="color:{_ns_col};font-weight:600">{_ns_lbl}</span>'
                        f' sentiment ({_ns_cnt} headlines)</div>',
                        unsafe_allow_html=True)

                st.markdown(
                    f'<div class="pro-card" style="margin-top:0;border-top:none">'
                    # ── Metrics ──
                    f'<div class="pro-metrics">'

                    f'<div class="pro-metric">'
                    f'<div class="pro-metric-hdr">Signal</div>'
                    f'<div class="pro-metric-val">{signal_label(_sig_str)}</div>'
                    f'<div class="pro-metric-sub">{_sig_str:.0f}/100</div></div>'

                    f'<div class="pro-metric">'
                    f'<div class="pro-metric-hdr">Confidence</div>'
                    f'<div class="pro-metric-val">{confidence_label(_dec.confidence)}</div>'
                    f'<div class="pro-metric-sub">{_dec.confidence:.0f}%</div></div>'

                    f'<div class="pro-metric" style="border-right:none">'
                    f'<div class="pro-metric-hdr">Risk</div>'
                    f'<div class="pro-metric-val" style="color:{_r_color}">'
                    f'{risk_description(_dec.risk_level)}</div>'
                    f'<div class="pro-metric-sub">{_dec.risk_level}</div></div>'

                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True)

                # ── Sentiment (swing mode) ─────────────────────
                if _trade_mode == "swing":
                    try:
                        from engine.sentiment import analyze_ticker_sentiment
                        _sr = analyze_ticker_sentiment(ticker=home_ticker)
                        _sc_val = _sr.get("avg_compound")
                        if _sc_val is not None:
                            _s_col = "#4A6741" if _sc_val > 0.15 else "#8B3A3A" if _sc_val < -0.15 else "#6B7280"
                            _s_lbl = "Bullish" if _sc_val > 0.15 else "Bearish" if _sc_val < -0.15 else "Neutral"
                            st.markdown(
                                f'<div class="bull-card" style="padding:8px 16px">'
                                f'<div class="bull-card-row" style="border:none">'
                                f'<span class="bull-card-label">News Sentiment</span>'
                                f'<span class="bull-card-value" style="color:{_s_col}">'
                                f'{_s_lbl} ({_sc_val:+.2f})</span></div></div>',
                                unsafe_allow_html=True)
                    except Exception:
                        pass

                # ── Expandable: Why? (humanized) ──────────────────
                _human = humanize_reasoning(_dec.reasoning, max_bullets=4)
                with st.expander("Why?", expanded=False):
                    for _h in _human:
                        st.markdown(f"\u2022 {_h}")

                # ── Expandable: Technical Details (raw) ───────────
                with st.expander("Technical Details", expanded=False):
                    for _line in _dec.reasoning:
                        st.caption(_line)

                # ── Risk management overlay ───────────────────────
                try:
                    import yfinance as _yf
                    from skills.risk_management import RiskManagementSkill, RiskParams
                    _fi = _yf.Ticker(home_ticker).fast_info
                    _price = (getattr(_fi, "last_price", None)
                              or getattr(_fi, "regularMarketPrice", None) or 0)
                    if _price and _price > 0:
                        _rp = RiskParams(account_size=10000.0, risk_per_trade_pct=0.02)
                        _ro = RiskManagementSkill(home_ticker).calculate(_price, _rp)
                        if _ro:
                            with st.expander("Risk Management"):
                                c1, c2, c3, c4 = st.columns(4)
                                c1.metric("Entry", f"${_price:.2f}")
                                c2.metric("Stop", f"${_ro.stop_loss:.2f}")
                                c3.metric("Target", f"${_ro.take_profit:.2f}")
                                c4.metric("Size", f"{_ro.position_size:.0f}")
                except Exception:
                    pass
            else:
                st.markdown(
                    '<div class="pro-card">'
                    '<div class="pro-overline">Engine Decision</div>'
                    '<div class="pro-hero">'
                    '<div>'
                    '<div class="pro-dec" style="color:#1C1E24">--</div>'
                    '<div class="pro-sub">Run Signal to begin</div>'
                    '</div>'
                    f'<div class="pro-ctx">{home_ticker}<br>{_trade_mode.upper()} ({_trade_timeframe})</div>'
                    '</div>'
                    '<div class="pro-metrics">'
                    '<div class="pro-metric">'
                    '<div class="pro-metric-hdr">Signal</div>'
                    '<div class="pro-metric-val" style="color:#1C1E24">--</div></div>'
                    '<div class="pro-metric">'
                    '<div class="pro-metric-hdr">Confidence</div>'
                    '<div class="pro-metric-val" style="color:#1C1E24">--</div></div>'
                    '<div class="pro-metric" style="border-right:none">'
                    '<div class="pro-metric-hdr">Risk</div>'
                    '<div class="pro-metric-val" style="color:#1C1E24">--</div></div>'
                    '</div></div>',
                    unsafe_allow_html=True)

        # ── Screenshot Analysis (triggered from left panel) ──
        if _do_chart and chart_file is not None:
            _img_bytes = chart_file.read()
            with st.spinner("Bull analyzing chart..."):
                try:
                    from skills.chart_analysis import ChartAnalysisSkill
                    from models.confidence import guard_decision
                    _media_type = ("image/png"
                                  if getattr(chart_file, "type", "") == "image/png"
                                  else "image/jpeg")
                    _chart_dec = ChartAnalysisSkill().analyze(
                        image_bytes=_img_bytes,
                        ticker=home_ticker,
                        timeframe=_trade_timeframe,
                        notes=setup_notes,
                        media_type=_media_type,
                    )
                    _chart_dec = guard_decision(_chart_dec)
                    st.session_state["chart_decision"]  = _chart_dec
                    # Also update main decision so the hero card shows chart result
                    st.session_state["home_decision"]   = _chart_dec
                except Exception:
                    st.markdown('<div class="bull-card" style="padding:10px 16px">'
                                '<span style="color:#8B3A3A;font-size:12px">'
                                'Chart analysis unavailable. Retry.</span></div>',
                                unsafe_allow_html=True)

    # ────────────────────────────────────────────────────────
    # RIGHT — News + Context + Journal
    # ────────────────────────────────────────────────────────
    with col_right:
        # ── News card (live from yfinance) ──
        try:
            import yfinance as _yf_news
            _yf_t = _yf_news.Ticker(home_ticker)
            _raw_news = _yf_t.news or []
            _news_items = []
            for _rn in _raw_news[:5]:
                _c = _rn.get("content", {})
                _t = _c.get("title", "")
                if _t and len(_t) > 10:
                    _news_items.append(_t)

            if _news_items:
                # Quick sentiment hint per headline
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
                _sia = SentimentIntensityAnalyzer()
                _news_html = ""
                _sent_sum = 0.0
                for _ni in _news_items[:5]:
                    _sc = _sia.polarity_scores(_ni)["compound"]
                    _sent_sum += _sc
                    _hint_col = "#4A6741" if _sc > 0.1 else "#8B3A3A" if _sc < -0.1 else "#6B7280"
                    _hint_lbl = "bullish" if _sc > 0.1 else "bearish" if _sc < -0.1 else "neutral"
                    # Shorten to trading-style bullet
                    _short = _ni[:45] + ("..." if len(_ni) > 45 else "")
                    _news_html += (
                        f'<div style="padding:4px 0;border-bottom:1px solid rgba(31,41,51,0.3);'
                        f'font-size:12px;line-height:1.3;display:flex;justify-content:space-between;'
                        f'align-items:center">'
                        f'<span style="color:#8B949E">{_short}</span>'
                        f'<span style="color:{_hint_col};font-size:10px;font-weight:600;'
                        f'white-space:nowrap;margin-left:8px">{_hint_lbl}</span></div>')

                # Store overall sentiment for decision card
                _avg_news_sent = _sent_sum / len(_news_items) if _news_items else 0
                st.session_state["_news_sentiment"] = _avg_news_sent
                st.session_state["_news_count"] = len(_news_items)

                st.markdown(
                    f'<div class="bull-card">'
                    f'<div class="bull-card-hdr">Market Intelligence</div>'
                    f'{_news_html}'
                    f'</div>', unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div class="bull-card" style="padding:12px 16px">'
                    '<div class="bull-card-hdr">Market Intelligence</div>'
                    '<div style="font-size:12px;color:#6B7280">No recent headlines</div>'
                    '</div>', unsafe_allow_html=True)
        except Exception:
            pass

        # ── Deep analysis modules (if available) ──
        _mar = st.session_state.get("home_ma_result")
        if _mar:
            for _mod_hdr, _mod_raw, _max in [
                ("Market", _mar.market_report, 250),
                ("Fundamentals", _mar.fundamentals_report, 200),
            ]:
                _mod_txt = (_mod_raw or "").replace("\n", " ").strip()
                if _mod_txt:
                    st.markdown(
                        f'<div class="bull-card">'
                        f'<div class="bull-card-hdr">{_mod_hdr}</div>'
                        f'<div class="bull-mod-body">'
                        f'{_mod_txt[:_max]}{"..." if len(_mod_txt) > _max else ""}'
                        f'</div></div>', unsafe_allow_html=True)

        # ── Screenshot Insight card ──
        _chart_dec = st.session_state.get("chart_decision")
        if _chart_dec:
            from models.card_formatter import humanize_reasoning

            # Extract structured insight from reasoning
            _insight_lines = _chart_dec.reasoning
            _trend = ""
            _structure = ""
            _setup = ""
            _sr = ""
            for _line in _insight_lines:
                _ll = str(_line).lower()
                if "trend:" in _ll or "trend " in _ll[:15]:
                    _trend = str(_line).split("|")[-1].strip() if "|" in str(_line) else str(_line).strip()
                if "setup:" in _ll or "setup " in _ll[:15]:
                    _setup = str(_line).split("|")[-1].strip() if "|" in str(_line) else str(_line).strip()
                if "s/r:" in _ll or "support" in _ll:
                    _sr = str(_line).replace("S/R:", "").strip()

            # Build card
            _rows = ""
            if _trend:
                _rows += (f'<div class="bull-card-row"><span class="bull-card-label">Trend</span>'
                          f'<span class="bull-card-value">{_trend[:40]}</span></div>')
            if _setup:
                _rows += (f'<div class="bull-card-row"><span class="bull-card-label">Setup</span>'
                          f'<span class="bull-card-value">{_setup[:40]}</span></div>')
            if _sr:
                _rows += (f'<div class="bull-card-row"><span class="bull-card-label">Levels</span>'
                          f'<span class="bull-card-value" style="font-size:11px">{_sr[:50]}</span></div>')

            # Humanized summary
            _chart_human = humanize_reasoning(_insight_lines, max_bullets=3)
            _summary = " ".join(_chart_human[:2])

            st.markdown(
                f'<div class="bull-card">'
                f'<div class="bull-card-hdr">Chart Insight</div>'
                + (_rows if _rows else "")
                + (f'<div style="font-size:12px;color:#8B949E;line-height:1.5;'
                   f'padding-top:8px;border-top:1px solid #1F2933;margin-top:6px">'
                   f'{_summary[:200]}</div>' if _summary else "")
                + f'</div>', unsafe_allow_html=True)

        # ── Trader profile ──
        try:
            from bot.behavior import BehaviorMemory
            from bot.config import BotProfileManager
            _mem     = BehaviorMemory()
            _insights = _mem.get_behavior_insights()
            _profile  = BotProfileManager().load()

            _agg = _insights.get("aggressiveness", 0.5)
            _agg_lbl   = ("Aggressive" if _agg > 0.7
                          else "Conservative" if _agg < 0.35 else "Balanced")
            _agg_color = ("#b91c1c" if _agg > 0.7
                          else "#15803d" if _agg < 0.35 else "#92400e")

            _agg_color_dark = {"Aggressive": "#8B3A3A", "Conservative": "#4A6741"}.get(_agg_lbl, "#6B7280")
            _wr = _insights.get("win_rate_overall", 0)
            _td = _insights.get("trades_today", 0)
            _ws = _insights.get("win_streak", 0)
            _ls = _insights.get("loss_streak", 0)
            st.markdown(
                f'<div class="bull-card">'
                f'<div class="bull-card-hdr">Capital Profile</div>'
                f'<div class="bull-card-row"><span class="bull-card-label">Style</span>'
                f'<span class="bull-card-value" style="color:{_agg_color_dark}">{_agg_lbl}</span></div>'
                f'<div class="bull-card-row"><span class="bull-card-label">Win Rate</span>'
                f'<span class="bull-card-value">{_wr:.0f}%</span></div>'
                f'<div class="bull-card-row"><span class="bull-card-label">Today</span>'
                f'<span class="bull-card-value">{_td} trades</span></div>'
                + (f'<div class="bull-card-row"><span class="bull-card-label">Streak</span>'
                   f'<span class="bull-card-value" style="color:#4A6741">{_ws}W</span></div>'
                   if _ws > 0 else "")
                + (f'<div class="bull-card-row"><span class="bull-card-label">Streak</span>'
                   f'<span class="bull-card-value" style="color:#8B3A3A">{_ls}L</span></div>'
                   if _ls > 0 else "")
                + f'</div>',
                unsafe_allow_html=True)

            # Patterns as structured warnings card
            _patterns = _insights.get("patterns", [])
            if _patterns:
                _pw_html = "".join(
                    f'<div class="bull-card-row"><span class="bull-card-label" style="color:#8B3A3A">'
                    f'{p}</span></div>' for p in _patterns)
                st.markdown(
                    f'<div class="bull-card">'
                    f'<div class="bull-card-hdr">Behavior Signals</div>'
                    f'{_pw_html}</div>', unsafe_allow_html=True)
        except Exception:
            pass

        # ── Journal card (from decision log + behavior) ──
        try:
            import json as _jl
            _log_path = "memory_data/decision_log.json"
            try:
                with open(_log_path, "r") as _lf:
                    _dlog = _jl.load(_lf)
            except Exception:
                _dlog = []

            if _dlog:
                _journal_rows = ""
                # Last 3 decisions
                for _entry in reversed(_dlog[-3:]):
                    _jt = _entry.get("ticker", "?")
                    _jd = _entry.get("decision", {})
                    _jdec = _jd.get("decision", "?") if isinstance(_jd, dict) else str(_jd)
                    _jts = str(_entry.get("timestamp", ""))[:10]
                    _jm = _entry.get("mode", "")
                    _jcol = "#4A6741" if _jdec == "BUY" else "#8B3A3A" if _jdec == "SELL" else "#6B7280"
                    _journal_rows += (
                        f'<div class="bull-card-row">'
                        f'<span class="bull-card-label">{_jt} · {_jm}</span>'
                        f'<span class="bull-card-value" style="color:{_jcol};font-size:12px">'
                        f'{_jdec}</span></div>')

                # Behavior patterns
                try:
                    _beh_mem = BehaviorMemory()
                    _beh_patterns = _beh_mem.get_behavior_insights().get("patterns", [])
                except Exception:
                    _beh_patterns = []

                _pattern_html = ""
                if _beh_patterns:
                    _pattern_html = (
                        '<div style="padding-top:8px;border-top:1px solid #1F2933;margin-top:6px">'
                        '<div style="font-size:10px;color:#6B7280;text-transform:uppercase;'
                        'letter-spacing:0.1em;margin-bottom:4px">Patterns</div>')
                    for _bp in _beh_patterns[:3]:
                        _pattern_html += (
                            f'<div style="font-size:11px;color:#8B3A3A;padding:2px 0">'
                            f'{_bp}</div>')
                    _pattern_html += '</div>'

                st.markdown(
                    f'<div class="bull-card">'
                    f'<div class="bull-card-hdr">Execution Log</div>'
                    f'{_journal_rows}'
                    f'{_pattern_html}'
                    f'</div>', unsafe_allow_html=True)
        except Exception:
            pass

    # ── fire coach ──
    auto_ask  = st.session_state.get("pending_auto_ask", "")
    effective = ((typed.strip() if send_btn else None) or
                 (auto_ask if auto_ask else None))
    if auto_ask:
        st.session_state["pending_auto_ask"] = ""

    if effective and top:
        st.session_state["voice_answer_audio"] = None
        st.session_state["audio_played_id"]    = None
        with st.spinner(f"{coach_name} is thinking…"):
            try:
                ans = ask_coach(effective, top, results, resp_mode, persona,
                                st.session_state["conversation_history"], coach_name)
            except Exception as e:
                ans = f"Coach error: {e}"
        st.session_state["conversation_history"] += [
            {"role": "user",      "content": effective},
            {"role": "assistant", "content": ans}]
        st.session_state["conversation_history"] = st.session_state["conversation_history"][-20:]
        audio_out = tts(ans, voice_key)
        st.session_state["voice_answer_audio"] = audio_out
        st.session_state["last_answer_text"]   = ans
        st.session_state["voice_transcript"]   = ""
        push(VOICE_HISTORY_PATH, {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                   "question": effective, "answer": ans, "ticker": top["ticker"]})
        push(SESSIONS_PATH, sess_entry(effective, top, resp_mode, persona))
        st.rerun()

    # ── summary cards ──
    if top:
        st.markdown('<div class="sec-h">At a glance</div>', unsafe_allow_html=True)
        gc1, gc2, gc3 = st.columns(3)
        with gc1:
            a = alabel(top["prob"]["action"])
            st.markdown(
                f'<div class="summary-card">'
                f'<div class="sc-label">Top Idea Today</div>'
                f'<div class="sc-value">{top["ticker"]}</div>'
                f'<div class="sc-sub">{a} · {top["prob"]["confidence"]} confidence</div>'
                f'</div>',
                unsafe_allow_html=True)
        with gc2:
            risk_txt = top["prob"]["main_risk"][:80]
            st.markdown(
                f'<div class="summary-card">'
                f'<div class="sc-label">Biggest Risk Today</div>'
                f'<div class="sc-value" style="font-size:0.9rem;color:#b45309">{risk_txt}</div>'
                f'</div>',
                unsafe_allow_html=True)
        with gc3:
            pattern_txt = ("Your workflow is becoming more systematic." if not mem_recs
                           else "You respond well to clear action + risk guidance.")
            st.markdown(
                f'<div class="summary-card">'
                f'<div class="sc-label">Your Pattern Today</div>'
                f'<div class="sc-value" style="font-size:0.88rem;font-weight:500">'
                f'{pattern_txt}</div>'
                f'</div>',
                unsafe_allow_html=True)

    # ── voice history ──
    if vh_recs:
        st.markdown('<div class="sec-h">Voice history</div>', unsafe_allow_html=True)
        hh, ch = st.columns([6, 1])
        with ch:
            if st.button("Clear", key="vh_clr"):
                save_list(VOICE_HISTORY_PATH, []); st.rerun()
        for idx, item in enumerate(vh_recs[:8]):
            with st.expander(f"{item.get('question','')[:60]}  ·  {item.get('timestamp','')[:10]}"):
                st.write(item.get("answer", ""))
                if st.button("▶ Replay", key=f"rp_{idx}"):
                    ra = tts(item.get("answer",""), voice_key)
                    play_audio(ra)


# ══════════════════════════════════════════════════════════
# TODAY — Today's Trading Brief
# ══════════════════════════════════════════════════════════
elif page == "Today":
    st.markdown('<div class="pg-title">Today\'s Trading Brief</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pg-sub">Simple daily guidance based on market data, '
        'backtests, AI reasoning, and portfolio ranking.</div>',
        unsafe_allow_html=True)

    if not results:
        st.info("Run Orallexa first (sidebar → ▶ Run Orallexa).")
    else:
        if valid:
            rnk  = ranked
            top2 = rnk[0]
            mm   = market_mood(valid)

            # 4 overview cards
            oc1, oc2, oc3, oc4 = st.columns(4)
            oc1.metric("Top Ticker",    top2["ticker"])
            oc2.metric("Best Action",   top2["prob"]["action"])
            oc3.metric("Risk Level",    risk_level(top2))
            oc4.metric("Portfolio Tone", portfolio_tone(valid))

            # ── Live prices strip ──────────────────────────────────────────
            st.markdown('<div class="sec-h">Live Prices</div>', unsafe_allow_html=True)
            pcols = st.columns(len(tickers))
            for i, tk in enumerate(tickers):
                with pcols[i]:
                    rt = fetch_realtime_price(tk)
                    if rt:
                        color = "#15803d" if rt["pct_change"] >= 0 else "#b91c1c"
                        arrow = "▲" if rt["pct_change"] >= 0 else "▼"
                        st.markdown(
                            f'<div style="background:#fff;border:1px solid #e5e7eb;'
                            f'border-radius:10px;padding:0.7rem 0.9rem;text-align:center">'
                            f'<div style="font-size:0.72rem;color:#9ca3af;font-weight:600">{tk}</div>'
                            f'<div style="font-size:1.2rem;font-weight:700;color:#111827">'
                            f'${rt["price"]}</div>'
                            f'<div style="font-size:0.82rem;color:{color};font-weight:600">'
                            f'{arrow} {rt["pct_change"]:+.2f}%</div>'
                            f'</div>',
                            unsafe_allow_html=True)
                    else:
                        st.markdown(
                            f'<div style="background:#fff;border:1px solid #e5e7eb;'
                            f'border-radius:10px;padding:0.7rem 0.9rem;text-align:center">'
                            f'<div style="font-size:0.72rem;color:#9ca3af">{tk}</div>'
                            f'<div style="font-size:0.88rem;color:#9ca3af">—</div>'
                            f'</div>',
                            unsafe_allow_html=True)

            # Sharpe chart
            fig = chart_sharpe(results)
            if fig: st.pyplot(fig)

            # Factor scores chart
            fig_f = chart_factor_scores(results)
            if fig_f:
                st.markdown('<div class="sec-h">Factor Scores</div>', unsafe_allow_html=True)
                st.pyplot(fig_f)
                st.caption("Momentum / Trend / Volume factor scores for each ticker (z-score normalised).")

            # Correlation report
            corr_rpt = st.session_state.get("corr_report", {})
            if corr_rpt:
                st.markdown('<div class="sec-h">Portfolio Correlation</div>', unsafe_allow_html=True)
                div_label = corr_rpt.get("diversification", "—")
                avg_c     = corr_rpt.get("avg_correlation", 0)
                color_div = {"good": "#15803d", "moderate": "#b45309", "poor": "#b91c1c"}.get(div_label, "#6b7280")
                st.markdown(
                    f'<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;'
                    f'padding:0.8rem 1rem;margin-bottom:0.6rem">'
                    f'<span style="font-size:0.72rem;color:#9ca3af;text-transform:uppercase">Diversification</span><br>'
                    f'<span style="font-size:1.1rem;font-weight:700;color:{color_div}">'
                    f'{div_label.title()}</span>'
                    f'<span style="font-size:0.82rem;color:#6b7280;margin-left:0.8rem">'
                    f'Avg correlation: {avg_c:.2f}</span>'
                    f'</div>',
                    unsafe_allow_html=True)
                high_pairs = corr_rpt.get("high_pairs", [])
                if high_pairs:
                    for pair in high_pairs:
                        st.caption(f"⚠️ {pair['pair']} — correlation {pair['correlation']:.2f} ({pair['level']})")

            # Ticker cards
            st.markdown('<div class="sec-h">Top Tickers</div>', unsafe_allow_html=True)
            for row in rnk:
                a   = alabel(row["prob"]["action"])
                wfs = round(row.get("wf_metrics", {}).get("avg_test_sharpe", 0) or 0, 3)
                ret = round(row["test_metrics"]["net"].get("total_return", 0), 3)
                dd  = round(row["test_metrics"]["net"].get("max_drawdown", 0), 3)

                st.markdown(
                    f'<div class="ticker-card">'
                    f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
                    f'<div>'
                    f'<div class="tk-name">{row["ticker"]}</div>'
                    f'{bdg(a)}'
                    f'</div>'
                    f'<div style="text-align:right">'
                    f'<div class="tk-label">WF Sharpe</div>'
                    f'<div style="font-size:1.1rem;font-weight:700;color:{"#15803d" if wfs>0 else "#b91c1c"}">'
                    f'{wfs:+.3f}</div>'
                    f'</div>'
                    f'</div>'
                    f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:0.9rem">'
                    f'<div>'
                    f'<div class="tk-label">Confidence</div>'
                    f'<div class="tk-val">{row["prob"]["confidence"]}</div>'
                    f'<div class="tk-label" style="margin-top:0.6rem">Why</div>'
                    f'<div class="tk-val">{row["prob"]["key_driver"][:100]}</div>'
                    f'</div>'
                    f'<div>'
                    f'<div class="tk-label">Risk</div>'
                    f'<div class="tk-val" style="color:#b45309">{row["prob"]["main_risk"][:80]}</div>'
                    f'<div class="tk-label" style="margin-top:0.6rem">Next Step</div>'
                    f'<div class="tk-val">{row["prob"]["action"]}</div>'
                    f'</div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True)

            # Portfolio suggestion
            st.markdown('<div class="sec-h">Portfolio Suggestion</div>', unsafe_allow_html=True)
            if pw:
                ps1, ps2 = st.columns([1, 2])
                with ps1:
                    tone = portfolio_tone(valid)
                    st.markdown(f"**Tone:** {tone}")
                    for tk_k, w in pw.items():
                        st.markdown(f"**{tk_k}** — {w:.0%}")
                with ps2:
                    if not pdf.empty: st.pyplot(chart_portfolio(pdf))
                    p = pmets
                    mc1,mc2,mc3 = st.columns(3)
                    mc1.metric("Return",   round(p.get("total_return",0),3))
                    mc2.metric("Sharpe",   round(p.get("sharpe",0),3))
                    mc3.metric("Drawdown", round(p.get("max_drawdown",0),3))
            else:
                st.info("No strong candidates today. Staying mostly in cash is reasonable.")


# ══════════════════════════════════════════════════════════
# MEMORY — Your Trading Memory
# ══════════════════════════════════════════════════════════
elif page == "Memory":
    st.markdown('<div class="pg-title">Your Trading Memory</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pg-sub">A running record of your market questions, '
        'AI guidance, and trading reflections.</div>',
        unsafe_allow_html=True)

    if not mem_recs:
        st.info("No memory yet. Run Orallexa and ask your coach some questions.")
    else:
        today_mem = mem_recs[0]

        # Today Memory Card + Session Context
        st.markdown('<div class="sec-h">Today</div>', unsafe_allow_html=True)
        mc1, mc2 = st.columns(2)

        with mc1:
            st.markdown(
                f'<div class="mem-card">'
                f'<div class="mem-date">Daily Memory Card · {today_mem.get("date","")}</div>'
                f'<div style="margin-bottom:0.5rem">'
                f'<div class="tk-label">Top Ticker</div>'
                f'<div style="font-size:1rem;font-weight:700;color:#111827">{today_mem.get("top_ticker","")}</div>'
                f'</div>'
                f'<div style="margin-bottom:0.5rem">'
                f'<div class="tk-label">AI Summary</div>'
                f'<div class="mem-summary">{today_mem.get("ai_summary","")}</div>'
                f'</div>'
                f'<div style="margin-bottom:0.5rem">'
                f'<div class="tk-label">Suggested Action</div>'
                f'<div class="tk-val">{today_mem.get("top_action","")}</div>'
                f'</div>'
                f'<div>'
                f'<div class="tk-label">Main Risk</div>'
                f'<div class="tk-val" style="color:#b45309">'
                f'{", ".join(today_mem.get("main_risks",[]))}'
                f'</div></div>'
                f'</div>',
                unsafe_allow_html=True)

        with mc2:
            st.markdown(
                f'<div class="mem-card">'
                f'<div class="mem-date">Session Context</div>'
                f'<div style="margin-bottom:0.4rem">'
                f'<div class="tk-label">Language</div>'
                f'<div class="tk-val">{today_mem.get("language_mode","")}</div>'
                f'</div>'
                f'<div style="margin-bottom:0.4rem">'
                f'<div class="tk-label">Persona</div>'
                f'<div class="tk-val">{today_mem.get("persona_mode","")}</div>'
                f'</div>'
                f'<div style="margin-bottom:0.4rem">'
                f'<div class="tk-label">Tickers Reviewed</div>'
                f'<div class="tk-val">{", ".join(today_mem.get("tickers_reviewed",[]))}</div>'
                f'</div>'
                f'<div>'
                f'<div class="tk-label">Market Mood</div>'
                f'<div class="tk-val">{today_mem.get("market_mood","")}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True)

        # Timeline
        st.markdown('<div class="sec-h">Timeline</div>', unsafe_allow_html=True)
        for item in mem_recs[:12]:
            label = f"{item.get('date','')} · {item.get('top_ticker','')} · {item.get('top_action','')}"
            with st.expander(label):
                st.write(item.get("ai_summary",""))
                st.caption(f"Tickers: {', '.join(item.get('tickers_reviewed',[]))}")
                if item.get("main_risks"):
                    st.caption(f"Risk: {', '.join(item['main_risks'])}")

        # Behavior patterns
        st.markdown('<div class="sec-h">Behavior Patterns</div>', unsafe_allow_html=True)
        bp1, bp2, bp3 = st.columns(3)
        with bp1:
            st.markdown(
                '<div class="beh-card beh-strength">'
                '<div class="beh-label">Strength</div>'
                '<div class="beh-text">You engage well when the system explains action and risk clearly. '
                'Simple, structured guidance keeps you focused.</div>'
                '</div>', unsafe_allow_html=True)
        with bp2:
            st.markdown(
                '<div class="beh-card beh-pattern">'
                '<div class="beh-label">Common Pattern</div>'
                '<div class="beh-text">You may focus on interesting names before confirmation '
                'is strong enough. Watch for early entry without signal.</div>'
                '</div>', unsafe_allow_html=True)
        with bp3:
            st.markdown(
                '<div class="beh-card beh-improve">'
                '<div class="beh-label">Improvement</div>'
                '<div class="beh-text">Your daily workflow is becoming more systematic. '
                'Keep using the voice coach to stay disciplined.</div>'
                '</div>', unsafe_allow_html=True)

        # Session log
        if sess_recs:
            st.markdown('<div class="sec-h">Session Log</div>', unsafe_allow_html=True)
            log_df = pd.DataFrame(sess_recs[:20])[
                [c for c in ["timestamp","user_input","top_ticker","ai_conclusion","confidence"]
                 if c in pd.DataFrame(sess_recs[:20]).columns]]
            st.dataframe(log_df, use_container_width=True)

        # ── Daily trading journal ──
        st.markdown('<div class="sec-h">Daily Trading Journal</div>', unsafe_allow_html=True)
        today_date = datetime.now().strftime("%Y-%m-%d")

        # Load existing journal entries
        JOURNAL_PATH = "memory_data/journal.json"
        journal_recs = load_list(JOURNAL_PATH)
        today_journal = next((j for j in journal_recs if j.get("date") == today_date), {})

        with st.expander(f"📝 Today's reflection — {today_date}", expanded=True):
            jc1, jc2 = st.columns(2)
            with jc1:
                action_taken = st.text_input(
                    "What action did you take today?",
                    value=today_journal.get("action_taken", ""),
                    placeholder="e.g. Watched NVDA, waited for confirmation",
                    key="j_action")
                emotion = st.selectbox(
                    "How did you feel about today's session?",
                    ["—", "Confident", "Uncertain", "Disciplined", "Impulsive", "Calm", "Anxious"],
                    index=["—","Confident","Uncertain","Disciplined","Impulsive","Calm","Anxious"].index(
                        today_journal.get("emotion", "—")),
                    key="j_emotion")
                discipline = st.slider(
                    "Discipline score (1–10)",
                    1, 10,
                    value=today_journal.get("discipline_score", 5),
                    key="j_disc")
            with jc2:
                reflection = st.text_area(
                    "End-of-day reflection",
                    value=today_journal.get("reflection", ""),
                    placeholder="What did you learn? What would you do differently?",
                    height=120,
                    key="j_reflect")
                mistakes = st.text_input(
                    "Any mistakes or things to avoid next time?",
                    value=today_journal.get("mistakes", ""),
                    placeholder="e.g. Entered too early without confirmation",
                    key="j_mistakes")

            if st.button("💾 Save today's journal", key="j_save", use_container_width=True):
                entry = {
                    "date":             today_date,
                    "saved_at":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "action_taken":     action_taken,
                    "emotion":          emotion,
                    "discipline_score": discipline,
                    "reflection":       reflection,
                    "mistakes":         mistakes,
                    "top_ticker":       today_mem.get("top_ticker","") if mem_recs else "",
                    "market_mood":      today_mem.get("market_mood","") if mem_recs else "",
                }
                # upsert by date
                updated = [j for j in journal_recs if j.get("date") != today_date]
                updated.insert(0, entry)
                save_list(JOURNAL_PATH, updated)
                st.success("Journal saved ✓")
                st.rerun()

        # Past journal entries
        past_entries = [j for j in journal_recs if j.get("date") != today_date]
        if past_entries:
            st.markdown('<div class="sec-h">Past Entries</div>', unsafe_allow_html=True)
            for entry in past_entries[:10]:
                disc = entry.get("discipline_score", "—")
                em   = entry.get("emotion","—")
                with st.expander(f"{entry.get('date','')} · {em} · Discipline {disc}/10"):
                    st.markdown(f"**Action taken:** {entry.get('action_taken','')}")
                    st.markdown(f"**Reflection:** {entry.get('reflection','')}")
                    if entry.get("mistakes"):
                        st.caption(f"⚠️ Mistakes: {entry['mistakes']}")

        # ── Discipline trend chart ─────────────────────────────────────────
        all_journal = [j for j in journal_recs if j.get("discipline_score") is not None]
        if len(all_journal) >= 2:
            st.markdown('<div class="sec-h">Discipline Trend</div>', unsafe_allow_html=True)
            jdf = pd.DataFrame(all_journal).sort_values("date")
            fig, ax = plt.subplots(figsize=(9, 2.8))
            _ls(ax, fig)
            ax.plot(jdf["date"], jdf["discipline_score"],
                    color=CP[0], lw=2, marker="o", markersize=5)
            ax.fill_between(jdf["date"], jdf["discipline_score"],
                            alpha=0.08, color=CP[0])
            ax.axhline(7, color=CP[1], lw=1, ls="--", alpha=0.6)
            ax.set_ylim(0, 11)
            ax.set_ylabel("Score", fontsize=8, color="#6b7280")
            ax.set_title("Daily Discipline Score", fontsize=10)
            ax.tick_params(axis="x", rotation=30, labelsize=7)
            plt.tight_layout()
            st.pyplot(fig)
            avg_disc = jdf["discipline_score"].mean()
            st.caption(f"Average discipline score: **{avg_disc:.1f}/10** "
                       f"over {len(jdf)} recorded days.")


# ══════════════════════════════════════════════════════════
# ANALYSIS — Deep Quantitative View
# ══════════════════════════════════════════════════════════
elif page == "Analysis":
    st.markdown('<div class="pg-title">Deep Analysis</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pg-sub">Advanced research view — ranking, portfolio allocation, '
        'strategy validation, and per-ticker detail.</div>',
        unsafe_allow_html=True)

    if not results:
        st.info("Run Orallexa first.")
    else:
        # Watchlist ranking
        st.markdown('<div class="sec-h">Watchlist Ranking</div>', unsafe_allow_html=True)
        rank_rows = []
        for r in results:
            if "error" in r:
                rank_rows.append({"ticker": r["ticker"], "error": r["error"]})
            else:
                rank_rows.append({
                    "ticker":         r["ticker"],
                    "train_sharpe":   round(r.get("best_train_sharpe") or 0, 3),
                    "test_sharpe":    round(r["test_metrics"]["net"].get("sharpe",0), 3),
                    "test_return":    round(r["test_metrics"]["net"].get("total_return",0), 3),
                    "wf_avg_sharpe":  round(r["wf_metrics"].get("avg_test_sharpe") or 0, 3),
                    "action":         r["prob"]["action"],
                    "strategy_type":  r["strategy_proposal"]["strategy_type"],
                    "proposal_accepted": r["accepted"],
                    "confidence":     r["prob"]["confidence"],
                })
        st.dataframe(pd.DataFrame(rank_rows), use_container_width=True)

        # Portfolio Allocation
        st.markdown('<div class="sec-h">Portfolio Allocation</div>', unsafe_allow_html=True)
        if pw:
            wdf = pd.DataFrame([{"Ticker": k, "Weight": round(v,4)} for k, v in pw.items()])
            st.dataframe(wdf, use_container_width=True)
            pa1,pa2,pa3,pa4 = st.columns(4)
            pa1.metric("Portfolio Return",   round(pmets.get("total_return",0),4))
            pa2.metric("Portfolio Sharpe",   round(pmets.get("sharpe",0),4))
            pa3.metric("Portfolio Drawdown", round(pmets.get("max_drawdown",0),4))
            pa4.metric("Selected Assets",    len(pw))
            if not pdf.empty: st.pyplot(chart_portfolio(pdf))
        else:
            st.info("No positive-Sharpe assets selected.")

        # AI Strategy Proposals
        st.markdown('<div class="sec-h">AI Strategy Proposals</div>', unsafe_allow_html=True)
        prop_rows = []
        for r in results:
            if "error" not in r:
                p = r["strategy_proposal"]
                prop_rows.append({
                    "ticker":       r["ticker"],
                    "strategy_type": p["strategy_type"],
                    "rsi_min":      p["rsi_min"], "rsi_max": p["rsi_max"],
                    "stop_loss":    p["stop_loss"], "take_profit": p["take_profit"],
                    "max_positions":p["max_positions"],
                    "holding_bias": p["holding_bias"],
                    "accepted":     r["accepted"],
                })
        if prop_rows:
            st.dataframe(pd.DataFrame(prop_rows), use_container_width=True)

        # Per-ticker detail
        st.markdown('<div class="sec-h">Per-Ticker Detail</div>', unsafe_allow_html=True)
        for r in results:
            if "error" in r:
                st.error(f"{r['ticker']} — {r['error']}"); continue
            with st.expander(
                f"**{r['ticker']}**  ·  {r['prob']['action']}  ·  accepted={r['accepted']}"):
                lc, rc = st.columns(2)
                with lc:
                    st.markdown("**Summary**");        st.write(r["summary"])
                    st.markdown("**Best Params**");    st.json(r["best_params"])
                    st.markdown("**AI Strategy**");    st.json(r["strategy_proposal"])
                    st.markdown("**Strategy Reasoning**"); st.caption(r["strategy_proposal"]["reasoning"])
                    st.markdown("**Risk Notes**");     st.caption(r["strategy_proposal"]["risk_notes"])
                    st.markdown("**Net Metrics**");    st.write(r["test_metrics"]["net"])
                    st.markdown("**Gross Metrics**");  st.write(r["test_metrics"]["gross"])
                    st.markdown("**Cost Summary**");   st.write(r["test_metrics"]["cost_summary"])
                    st.markdown("**WF Metrics**");     st.write(r["wf_metrics"])
                    st.markdown("**AI Report**");      st.write(r["ai_report"])
                    if r["proposal_validation"]:
                        st.markdown("**AI Proposal Metrics**")
                        st.write(r["proposal_validation"]["metrics"]["net"])
                        st.markdown("**Current vs Proposal**"); st.write(r["comparison"])

                    # ── Multi-strategy comparison ──────────────────────────
                    ms = r.get("full_result", {}).get("multi_strategy", {})
                    if ms and not ms.get("summary_table", pd.DataFrame()).empty:
                        st.markdown("**📊 Multi-Strategy Comparison**")
                        tbl = ms["summary_table"][[
                            c for c in ["strategy","test_sharpe","test_return",
                                        "test_maxdd","test_win_rate","test_n_trades",
                                        "overfitting_flag"]
                            if c in ms["summary_table"].columns]]
                        st.dataframe(tbl, use_container_width=True)
                        st.caption(f"Best strategy: **{ms.get('best_strategy','—')}** "
                                   f"(test Sharpe: {ms.get('test_metrics',{}).get('sharpe',0):.3f})")

                    # ── ML signal results ──────────────────────────────────
                    ml = r.get("full_result", {}).get("ml_analysis", {})
                    if ml and not ml.get("summary", pd.DataFrame()).empty:
                        st.markdown("**🤖 ML Signal Comparison**")
                        ml_tbl = ml["summary"][[
                            c for c in ["model","sharpe","total_return",
                                        "max_drawdown","win_rate","n_trades","train_acc"]
                            if c in ml["summary"].columns]]
                        st.dataframe(ml_tbl, use_container_width=True)
                        st.caption(f"Best ML model: **{ml.get('best_model','—')}** "
                                   f"· {ml.get('n_features',0)} features · "
                                   f"predicting {ml.get('forward_days',5)}-day direction")

                        # ML comparison chart
                        fig_ml = chart_ml_comparison(ml, r["ticker"])
                        if fig_ml: st.pyplot(fig_ml)

                        # Feature importance chart
                        fi = ml.get("feature_importance", pd.DataFrame())
                        if not fi.empty:
                            fig_fi = chart_feature_importance(fi, r["ticker"])
                            if fig_fi: st.pyplot(fig_fi)

                with rc:
                    prob = r["prob"]
                    st.markdown("**Probability View**")
                    st.progress(prob["bull_probability"]/100,    text=f"Bull {prob['bull_probability']}%")
                    st.progress(prob["neutral_probability"]/100, text=f"Neutral {prob['neutral_probability']}%")
                    st.progress(prob["bear_probability"]/100,    text=f"Bear {prob['bear_probability']}%")
                    st.markdown("**Decision Card**")
                    st.write({"bias": prob["bias"], "confidence": prob["confidence"],
                              "action": prob["action"], "key_driver": prob["key_driver"],
                              "main_risk": prob["main_risk"]})

                    # ── Sentiment ──────────────────────────────────────────
                    sent = r.get("full_result", {}).get("sentiment", {})
                    if sent and not sent.get("error"):
                        lbl   = sent.get("sentiment_label", "neutral")
                        score = sent.get("avg_compound", 0.0)
                        sig   = sent.get("signal", "neutral")
                        color = {"positive":"#15803d","negative":"#b91c1c"}.get(lbl,"#6b7280")
                        st.markdown("**📰 News Sentiment**")
                        st.markdown(
                            f'<div style="background:#f9fafb;border:1px solid #e5e7eb;'
                            f'border-radius:10px;padding:0.8rem 1rem;margin-bottom:0.5rem">'
                            f'<span style="font-size:0.72rem;color:#9ca3af;text-transform:uppercase">Sentiment</span><br>'
                            f'<span style="font-size:1.1rem;font-weight:700;color:{color}">'
                            f'{lbl.title()} ({score:+.3f})</span><br>'
                            f'<span style="font-size:0.82rem;color:#6b7280">'
                            f'Signal: {sig} · {sent.get("summary","")}</span>'
                            f'</div>',
                            unsafe_allow_html=True)

                    try:
                        bt_tr, bt_te = equity_data(
                            r["ticker"], r["best_params"],
                            train_ratio=float(train_r), tc=float(tc), sl=float(sl_))
                        st.markdown("**Equity Curves**")
                        st.pyplot(chart_equity(r["ticker"], bt_tr, bt_te))
                    except Exception as e:
                        st.warning(f"Chart: {e}")

                    # ── Strategy comparison: Rule vs ML vs Buy&Hold ────────
                    ms = r.get("full_result", {}).get("multi_strategy", {})
                    if ms:
                        try:
                            fig_sc = chart_strategy_comparison(r["ticker"], ms)
                            if fig_sc:
                                st.markdown("**📈 Strategy vs ML vs Buy & Hold**")
                                st.pyplot(fig_sc)
                        except Exception:
                            pass

                    # ── ML comparison bar chart ────────────────────────────
                    ml = r.get("full_result", {}).get("ml_analysis", {})
                    if ml and not ml.get("error"):
                        try:
                            fig_mlc = chart_ml_comparison(ml, r["ticker"])
                            if fig_mlc:
                                st.markdown("**🤖 ML Model Comparison**")
                                st.pyplot(fig_mlc)
                        except Exception:
                            pass

                    # ── Feature importance ─────────────────────────────────
                        try:
                            fi = ml.get("feature_importance", pd.DataFrame())
                            fig_fi = chart_feature_importance(fi, r["ticker"])
                            if fig_fi:
                                st.markdown("**🔍 Feature Importance (Random Forest)**")
                                st.pyplot(fig_fi)
                        except Exception:
                            pass

                    if r["proposal_validation"]:
                        try:
                            st.markdown("**Current vs Proposal**")
                            st.pyplot(chart_vs(r["ticker"], r["bt_test"],
                                               r["proposal_validation"]["backtest"]))
                        except Exception as e:
                            st.warning(f"Proposal chart: {e}")
                if r.get("rag_context"):
                    st.markdown("**Retrieved RAG Context**")
                    st.text(r["rag_context"])


# ══════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════
elif page == "Settings":
    st.markdown('<div class="pg-title">Settings</div>', unsafe_allow_html=True)
    st.markdown('<div class="pg-sub">Personalise your coach, language, voice, and preferences.</div>',
                unsafe_allow_html=True)

    st.markdown('<div class="sec-h">Coach Identity</div>', unsafe_allow_html=True)
    new_name = st.text_input("Coach name",
        value=st.session_state.get("coach_name",""),
        placeholder="Nova, Aria, Rex…",
        key="set_cname")
    if st.button("Save name", key="sv_name"):
        st.session_state["coach_name"] = new_name.strip() or "Coach"
        st.success(f"Coach name set to: {st.session_state['coach_name']}")

    st.markdown('<div class="sec-h">Language</div>', unsafe_allow_html=True)
    new_resp = st.selectbox("Response language",
        ["English", "Follow User", "中文", "Bilingual"],
        index=["English","Follow User","中文","Bilingual"].index(
            st.session_state.get("resp_mode","English")),
        key="set_resp")
    if st.button("Save language", key="sv_resp"):
        st.session_state["resp_mode"] = new_resp
        st.success("Saved.")

    st.markdown('<div class="sec-h">Voice</div>', unsafe_allow_html=True)
    voice_opts = {
        "Nova ✦ — warm female (recommended)": "nova",
        "Shimmer — soft female": "shimmer",
        "Alloy — neutral": "alloy",
        "Onyx — deep male": "onyx",
        "Echo — balanced": "echo",
    }
    cur_v = st.session_state.get("voice_key","nova")
    cur_lbl = next((k for k,v in voice_opts.items() if v==cur_v), list(voice_opts.keys())[0])
    new_v = st.selectbox("Voice profile", list(voice_opts.keys()),
        index=list(voice_opts.keys()).index(cur_lbl), key="set_voice")
    if st.button("Save voice", key="sv_voice"):
        st.session_state["voice_key"] = voice_opts[new_v]
        st.success("Saved.")

    st.markdown('<div class="sec-h">Persona</div>', unsafe_allow_html=True)
    new_persona = st.selectbox("Coach style",
        ["Calm Coach", "Trader Mode", "Bilingual Mentor"],
        index=["Calm Coach","Trader Mode","Bilingual Mentor"].index(
            st.session_state.get("persona","Calm Coach")),
        key="set_persona")
    st.caption({
        "Calm Coach":      "Measured, reassuring. Honest about risk. Good for steady decision-making.",
        "Trader Mode":     "Direct, no fluff. Talks like a trader. Good for fast decisions.",
        "Bilingual Mentor":"Warm and nuanced. Switches language based on what you use.",
    }.get(new_persona,""))
    if st.button("Save persona", key="sv_persona"):
        st.session_state["persona"] = new_persona
        st.success("Saved.")

    st.markdown('<div class="sec-h">User Preference</div>', unsafe_allow_html=True)
    new_pref = st.selectbox("Risk appetite",
        ["Conservative","Balanced","Aggressive"],
        index=["Conservative","Balanced","Aggressive"].index(
            st.session_state.get("user_pref","Balanced")),
        key="set_pref")
    st.caption({
        "Conservative": "Prioritise capital preservation. Low drawdown tolerance.",
        "Balanced":      "Normal risk-reward. Suitable for most traders.",
        "Aggressive":    "Higher risk tolerance. Willing to accept larger drawdowns.",
    }.get(new_pref,""))
    if st.button("Save preference", key="sv_pref"):
        st.session_state["user_pref"] = new_pref
        st.success("Saved.")

    st.markdown('<div class="sec-h">Daily Routine (coming soon)</div>', unsafe_allow_html=True)
    st.caption("Morning briefing and evening reflection reminders — coming in a future update.")
