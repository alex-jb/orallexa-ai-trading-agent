"""
desktop_agent/brain_bridge.py
──────────────────────────────────────────────────────────────────
Intent router + trading engine bridge.

Flow:
    user text
        ↓
    detect_intent()         → "analysis" | "coach" | "dashboard" | "status"
        ↓
    route_and_respond()     → (reply_text, action)

Actions returned:
    "none"       — just reply with text
    "dashboard"  — open Streamlit dashboard in browser
    "analysis"   — ran OrallexaBrain and reply contains the result

Usage:
    bb = BrainBridge(default_ticker="NVDA", default_mode="intraday")
    reply, action = bb.route_and_respond("NVDA今天能买吗", lang="zh")
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import webbrowser
from typing import Optional

from desktop_agent.i18n import t as _t, get_lang

# ── Intent keywords ───────────────────────────────────────────────────────────

_DASHBOARD_KW = {
    "en": ["open dashboard", "show dashboard", "open chart", "full analysis",
           "detailed analysis", "open app", "show app"],
    "zh": ["打开仪表盘", "打开图表", "详细分析", "完整分析", "打开dashboard",
           "打开app", "开启"],
}

_ANALYSIS_KW = {
    "en": ["should i buy", "should i sell", "buy signal", "sell signal",
           "analysis", "analyze", "what do you think", "entry", "breakout",
           "pullback", "signal", "trade", "scalp", "intraday", "swing"],
    "zh": ["能买吗", "买入", "卖出", "信号", "分析", "看多", "看空",
           "做多", "做空", "进场", "突破", "回调", "scalp", "日内", "波段"],
}

_SCREENSHOT_KW = {
    "en": ["screenshot", "screen shot", "analyze this chart",
           "analyze chart", "capture screen", "screenshot this",
           "what do you see", "analyze screen", "chart analysis",
           "look at this", "check this chart"],
    "zh": ["截图", "截屏", "分析图表", "看这个图", "分析这张图",
           "看看这个", "图表分析"],
}

_GREETING_KW = {
    "en": ["hello", "hi", "hey", "good morning", "good afternoon"],
    "zh": ["你好", "嗨", "早", "早上好", "下午好", "晚上好"],
}

# ── Dashboard URL / launch config ─────────────────────────────────────────────

DASHBOARD_URL    = "http://localhost:8501"
STREAMLIT_SCRIPT = None   # set in BrainBridge.__init__ if auto-launch enabled


def _kw_match(text: str, lang: str, table: dict[str, list[str]]) -> bool:
    """Return True if any keyword in the table matches the text."""
    low = text.lower()
    # Always check both language lists
    for kws in table.values():
        if any(kw in low for kw in kws):
            return True
    return False


_NOISE_WORDS = {
    "I", "A", "IN", "IS", "IT", "AT", "BE", "DO", "GO",
    "MY", "BY", "ON", "OR", "TO", "UP", "AND", "THE", "OF",
    "FOR", "BUY", "SELL", "WAIT", "LOW", "HIGH", "NOT", "NO",
    "CAN", "HOW", "NOW", "ANY", "ALL", "ITS", "HAS", "HIS",
    "HER", "WAS", "ARE", "GET", "GOT", "SET", "LET", "DID",
    "RUN", "USE", "DAY", "NEW", "OLD", "BIG", "TOP", "OUT",
    "PUT", "END", "OUR", "MAY", "SAY", "SEE", "TRY", "ASK",
    "WHY", "MAN", "OWN", "ADD", "OFF", "FAR", "FEW", "BAD",
    "SHOW", "OPEN", "HOLD", "LONG", "CALL", "RISK", "STOP",
    "GAIN", "LOOK", "HELP", "JUST", "WHAT", "THIS", "THAT",
    "WILL", "FROM", "HAVE", "WITH", "BEEN", "THEM", "THAN",
    "GOOD", "LIKE", "WHEN", "MAKE", "ALSO", "BACK", "TIME",
    "TAKE", "SOME", "EVEN", "ONLY", "OVER", "NEED", "WANT",
    "GIVE", "KEEP", "FIND", "HERE", "KNOW", "LAST", "MOST",
    "VERY", "MUCH", "SURE", "YEAH", "WELL", "OKAY", "DONE",
    "THINK", "CHECK", "TREND", "SHORT", "ENTRY", "TRADE",
    "SCALP", "SWING", "CHART", "PRICE", "POINT", "ABOUT",
    "SHOULD", "COULD", "WOULD", "THEIR", "WHICH", "WHERE",
    "SIGNAL", "MARKET", "TODAY", "STILL", "STOCK", "LOSS",
    "DAILY", "SETUP", "BREAK", "CLOSE", "ABOVE", "BELOW",
}

# Well-known tickers that might be confused with words
_KNOWN_TICKERS = {
    "AAPL", "MSFT", "GOOG", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "NFLX", "AMD", "INTC", "QCOM", "AVGO", "CRM", "ORCL", "CSCO",
    "ADBE", "PYPL", "SQ", "SHOP", "SNOW", "PLTR", "COIN", "MSTR",
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "ARKK",
    "BAC", "JPM", "GS", "MS", "WFC", "C", "V", "MA",
    "JNJ", "PFE", "UNH", "ABBV", "MRK", "LLY",
    "XOM", "CVX", "COP", "OXY", "SLB",
    "BA", "LMT", "RTX", "GE", "CAT", "DE",
    "DIS", "CMCSA", "NFLX", "ROKU", "SPOT",
    "NIO", "BABA", "PDD", "JD", "LI", "XPEV",
}


def _extract_ticker(text: str, default: str) -> str:
    """
    Extract a stock ticker from user text.

    Priority:
      1. $TICKER notation (e.g. "$NVDA")
      2. Known ticker match
      3. 1-5 uppercase letter word not in noise set
      4. Fallback to default
    """
    upper = text.upper()

    # Priority 1: $TICKER notation
    dollar = re.findall(r'\$([A-Z]{1,5})\b', upper)
    if dollar:
        return dollar[0]

    # Priority 2 + 3: scan all uppercase words, prefer known tickers
    candidates = re.findall(r'\b([A-Z]{1,5})\b', upper)
    known  = [c for c in candidates if c in _KNOWN_TICKERS]
    if known:
        return known[0]

    others = [c for c in candidates if c not in _NOISE_WORDS]
    if others:
        return others[0]

    return default


# ── Mode & timeframe extraction ──────────────────────────────────────────────

# Mode keywords: plain strings use `in`, r"..." strings use regex match
_MODE_PATTERNS: dict[str, list[str]] = {
    "scalp":    ["scalp", "scalping", r"\b1m\b", r"\b5m\b", "1min", "5min",
                 "超短", "快速", "剥头皮"],
    "intraday": ["intraday", r"\b15m\b", r"\b1h\b", "15min", "60min", "hourly",
                 "日内", "盘中"],
    "swing":    ["swing", "daily", r"\b1d\b", "weekly", "position",
                 "波段", "持仓", "日线"],
}

_TF_PATTERNS: dict[str, str] = {
    "1m":  r'\b1\s*m(?:in)?\b',
    "5m":  r'\b5\s*m(?:in)?\b',
    "15m": r'\b15\s*m(?:in)?\b',
    "1h":  r'\b(?:1\s*h(?:our)?|60\s*m(?:in)?)\b',
    "1D":  r'\b(?:1\s*d(?:ay)?|daily)\b',
}

# Mode -> default timeframe
_MODE_DEFAULT_TF = {
    "scalp":    "5m",
    "intraday": "15m",
    "swing":    "1D",
}


def _extract_mode(text: str, default_mode: str) -> str:
    """Extract trading mode from user text."""
    low = text.lower()
    for mode, keywords in _MODE_PATTERNS.items():
        for kw in keywords:
            if kw.startswith(r"\b"):
                # Regex pattern — use word boundary match
                if re.search(kw, low, re.IGNORECASE):
                    return mode
            else:
                # Plain substring match
                if kw in low:
                    return mode
    return default_mode


def _extract_timeframe(text: str, mode: str, default_tf: str) -> str:
    """Extract timeframe from user text, or infer from mode."""
    low = text.lower()
    for tf, pattern in _TF_PATTERNS.items():
        if re.search(pattern, low, re.IGNORECASE):
            return tf
    # If mode was explicitly set, use its default TF
    inferred_tf = _MODE_DEFAULT_TF.get(mode)
    if inferred_tf and inferred_tf != default_tf:
        return inferred_tf
    return default_tf


class BrainBridge:
    """
    Routes user messages to the correct action and returns a reply.

    Parameters
    ----------
    default_ticker : str     e.g. "NVDA"
    default_mode   : str     "scalp" | "intraday" | "swing"
    dashboard_url  : str     URL to open for dashboard intent
    auto_launch    : bool    start streamlit if not running
    """

    def __init__(
        self,
        default_ticker: str = "NVDA",
        default_mode:   str = "intraday",
        default_tf:     str = "15m",
        dashboard_url:  str = DASHBOARD_URL,
        auto_launch:    bool = True,
    ) -> None:
        self.ticker       = default_ticker
        self.mode         = default_mode
        self.timeframe    = default_tf
        self.dashboard_url = dashboard_url
        self.auto_launch  = auto_launch
        self._history: list[dict] = []   # conversation history for Claude

    # ── Public ────────────────────────────────────────────────────────────────

    def route_and_respond(self, text: str, lang: str = "en") -> tuple[str, str]:
        """
        Process user input.
        Returns (reply_text, action_code).
        action_code: "none" | "dashboard" | "analysis"

        Automatically extracts ticker, mode, and timeframe from natural
        language input and updates internal state before routing.
        """
        if not text.strip():
            return "", "none"

        # ── Extract context from text ─────────────────────────────
        old_ticker, old_mode, old_tf = self.ticker, self.mode, self.timeframe

        new_ticker = _extract_ticker(text, self.ticker)
        new_mode   = _extract_mode(text, self.mode)
        new_tf     = _extract_timeframe(text, new_mode, self.timeframe)

        self.ticker    = new_ticker
        self.mode      = new_mode
        self.timeframe = new_tf

        # Track what changed for notification
        self._last_changes: list[str] = []
        if new_ticker != old_ticker:
            self._last_changes.append(f"ticker -> {new_ticker}")
        if new_mode != old_mode:
            self._last_changes.append(f"mode -> {new_mode}")
        if new_tf != old_tf:
            self._last_changes.append(f"timeframe -> {new_tf}")

        # ── Route ─────────────────────────────────────────────────
        if _kw_match(text, lang, _DASHBOARD_KW):
            return self._handle_dashboard(lang), "dashboard"

        if _kw_match(text, lang, _SCREENSHOT_KW):
            return self._handle_screenshot(lang), "screenshot"

        if _kw_match(text, lang, _ANALYSIS_KW):
            return self._handle_analysis(text, lang), "analysis"

        # Default: conversational Claude coach
        return self._handle_coach(text, lang), "none"

    @property
    def display_label(self) -> str:
        """Formatted label for UI display: NVDA · Intraday (15m)"""
        mode_keys = {
            "scalp":    "mode_scalping",
            "intraday": "mode_intraday",
            "swing":    "mode_swing",
        }
        key = mode_keys.get(self.mode, "")
        mode_str = _t(key) if key else self.mode.title()
        return f"{self.ticker} \u00b7 {mode_str} ({self.timeframe})"

    @property
    def last_changes(self) -> list[str]:
        """What changed on the last route_and_respond call."""
        return getattr(self, "_last_changes", [])

    def update_ticker(self, ticker: str) -> None:
        self.ticker = ticker.upper()

    def update_mode(self, mode: str, timeframe: str = "") -> None:
        self.mode = mode
        if timeframe:
            self.timeframe = timeframe

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_screenshot(self, lang: str) -> str:
        """Capture screen, analyze via Claude vision, return summary."""
        try:
            from desktop_agent.screenshot import capture_screen
            img_bytes = capture_screen()
            if img_bytes is None:
                return ("截屏失败。" if lang == "zh" else
                        "Screenshot capture failed.")

            return self.analyze_image(img_bytes, lang=lang)
        except Exception as exc:
            return (f"截图分析暂时不可用，请稍后重试。" if lang == "zh" else
                    f"Screenshot analysis is temporarily unavailable. Please try again.")

    def analyze_image(self, image_bytes: bytes, lang: str = "en",
                      notes: str = "") -> str:
        """
        Analyze an image (screenshot or uploaded) and return a formatted reply.
        Also stores the last DecisionOutput as self.last_chart_result.
        """
        try:
            import sys
            sys.path.insert(0, str(_project_root()))
            from skills.chart_analysis import ChartAnalysisSkill
            from models.confidence import guard_decision

            result = ChartAnalysisSkill().analyze(
                image_bytes=image_bytes,
                ticker=self.ticker,
                timeframe=self.timeframe,
                notes=notes,
            )
            result = guard_decision(result)
            self.last_chart_result = result

            dec  = result.decision
            conf = result.confidence
            risk = result.risk_level
            rec  = getattr(result, "recommendation", "")

            if lang == "zh":
                summary = (
                    f"图表分析: {self.ticker} {_decision_zh(dec)} 信号\n"
                    f"置信度 {conf:.0f}%，风险 {_risk_zh(risk)}\n"
                )
                if rec:
                    summary += f"{rec}\n"
            else:
                summary = (
                    f"Chart: {self.ticker} {dec} signal\n"
                    f"Confidence {conf:.0f}%  ·  Risk {risk}\n"
                )
                if rec:
                    summary += f"{rec}\n"
            return summary

        except Exception as exc:
            self.last_chart_result = None
            return (f"图表分析失败，请检查网络连接后重试。" if lang == "zh" else
                    f"Chart analysis failed. Check your connection and try again.")

    def _handle_dashboard(self, lang: str) -> str:
        opened = self._open_dashboard()
        if lang == "zh":
            return "好的，已为你打开交易仪表盘。" if opened else "正在启动仪表盘，请稍等…"
        return "Opening your trading dashboard now." if opened else "Launching dashboard, please wait…"

    def _handle_analysis(self, text: str, lang: str) -> str:
        try:
            # Import here to avoid slow startup when not needed
            import sys, os
            sys.path.insert(0, str(_project_root()))
            from core.brain import OrallexaBrain

            brain  = OrallexaBrain(self.ticker)
            result = brain.run_for_mode(
                mode=self.mode,
                timeframe=self.timeframe,
                use_claude=True,
            )

            decision       = result.decision
            confidence     = result.confidence
            risk           = result.risk_level
            recommendation = getattr(result, "recommendation", "")
            reasons        = result.reasoning[:3]   # top 3 lines

            if lang == "zh":
                summary = (
                    f"{self.ticker} {_decision_zh(decision)} 信号\n"
                    f"置信度 {confidence:.0f}%，风险 {_risk_zh(risk)}\n"
                )
                if recommendation:
                    summary += f"{recommendation}\n"
                summary += "\n".join(f"• {r}" for r in reasons if r.strip())
            else:
                summary = (
                    f"{self.ticker}: {decision} signal\n"
                    f"Confidence {confidence:.0f}%  ·  Risk {risk}\n"
                )
                if recommendation:
                    summary += f"{recommendation}\n"
                summary += "\n".join(f"• {r}" for r in reasons if r.strip())
            return summary

        except Exception as exc:
            if lang == "zh":
                return "分析暂时不可用，请检查网络连接和API密钥。"
            return "Analysis is temporarily unavailable. Check your connection and API key."

    def _handle_coach(self, text: str, lang: str) -> str:
        """Send to Claude as a conversational trading coach."""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return ("请设置 ANTHROPIC_API_KEY 环境变量。"
                    if lang == "zh" else
                    "Please set the ANTHROPIC_API_KEY environment variable.")
        try:
            import sys
            sys.path.insert(0, str(_project_root()))
            import anthropic

            sys_prompt = (
                "你是一名专业的AI交易教练。用简洁的中文回答，聚焦交易分析。"
                if lang == "zh" else
                "You are a professional AI trading coach. Reply concisely in English, focused on trading."
            )

            self._history.append({"role": "user", "content": text})
            self._history = self._history[-10:]   # keep last 10 messages (5 turns)

            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                system=sys_prompt,
                messages=self._history,
            )
            reply = resp.content[0].text.strip()
            self._history.append({"role": "assistant", "content": reply})
            return reply

        except Exception as exc:
            return ("AI教练暂时不可用，请稍后重试。"
                    if lang == "zh" else
                    "AI coach is temporarily unavailable. Please try again.")

    # ── Dashboard launcher ────────────────────────────────────────────────────

    def _open_dashboard(self) -> bool:
        """Open dashboard URL; optionally start Streamlit if not running."""
        import socket
        host, port = "localhost", 8501

        def _is_running() -> bool:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return True
            except OSError:
                return False

        if not _is_running() and self.auto_launch:
            script = _project_root() / "app_ui.py"
            if script.exists():
                subprocess.Popen(
                    [sys.executable, "-m", "streamlit", "run", str(script),
                     "--server.headless", "true"],
                    cwd=str(_project_root()),
                )
                import time; time.sleep(3)   # give it a moment to start

        webbrowser.open(self.dashboard_url)
        return True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _project_root():
    from pathlib import Path
    return Path(__file__).parent.parent


def _decision_zh(d: str) -> str:
    return {"BUY": "买入", "SELL": "卖出", "WAIT": "观望"}.get(d, d)


def _risk_zh(r: str) -> str:
    return {"LOW": "低", "MEDIUM": "中", "HIGH": "高"}.get(r, r)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    bb = BrainBridge(default_ticker="NVDA", default_mode="intraday")

    tests = [
        ("Should I buy NVDA right now?",    "en"),
        ("NVDA今天能买吗",                   "zh"),
        ("Check TSLA on the 5m",            "en"),
        ("QQQ swing analysis",              "en"),
        ("$AAPL 15m scalp setup",           "en"),
        ("open dashboard",                  "en"),
        ("What is a stop loss?",            "en"),
    ]
    for msg, lang in tests:
        print(f"\n[{lang}] {msg}")
        reply, action = bb.route_and_respond(msg, lang=lang)
        print(f"  ticker={bb.ticker}  mode={bb.mode}  tf={bb.timeframe}")
        print(f"  label={bb.display_label}")
        print(f"  changes={bb.last_changes}")
        print(f"  action={action}")
        print(f"  reply ={reply[:120]}")
