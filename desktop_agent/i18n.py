"""
desktop_agent/i18n.py
──────────────────────────────────────────────────────────────────
Centralised translation strings for the desktop agent UI.

Usage:
    from desktop_agent.i18n import t
    label = t("bull_coach", lang="zh")   # -> "牛教练"
"""
from __future__ import annotations

_STRINGS: dict[str, dict[str, str]] = {
    # ── App title / branding ─────────────────────────────────────
    "bull_coach":               {"en": "Bull Coach",              "zh": "牛教练"},

    # ── Chat popover: buttons & labels ───────────────────────────
    "clear":                    {"en": "Clear",                   "zh": "清除"},
    "ticker":                   {"en": "Ticker",                  "zh": "代码"},
    "scalp":                    {"en": "Scalp",                   "zh": "超短"},
    "intra":                    {"en": "Intra",                   "zh": "日内"},
    "swing":                    {"en": "Swing",                   "zh": "波段"},
    "last":                     {"en": "Last",                    "zh": "上次"},
    "voice_on":                 {"en": "Voice ON",                "zh": "语音 开"},
    "voice_off":                {"en": "Voice OFF",               "zh": "语音 关"},
    "lang_label":               {"en": "Lang:",                   "zh": "语言:"},
    "why":                      {"en": "Why?",                    "zh": "为什么?"},
    "tech_details":             {"en": "Technical Details",       "zh": "技术详情"},
    "analysis_complete":        {"en": "Analysis complete.",      "zh": "分析完成。"},
    "you":                      {"en": "You",                     "zh": "你"},
    "thinking":                 {"en": "thinking\u2026",          "zh": "思考中\u2026"},
    "transcribing":             {"en": "transcribing\u2026",      "zh": "转录中\u2026"},
    "no_speech":                {"en": "(no speech detected)",    "zh": "(未检测到语音)"},
    "chat_cleared":             {"en": "Chat cleared. What's next?",
                                 "zh": "聊天已清除，接下来呢？"},

    # ── Chat popover: metric labels ──────────────────────────────
    "signal":                   {"en": "SIGNAL",                  "zh": "信号"},
    "confidence":               {"en": "CONFIDENCE",              "zh": "置信度"},
    "risk":                     {"en": "RISK",                    "zh": "风险"},

    # ── Chat popover: empty-state hint ───────────────────────────
    "hint": {
        "en": (
            "Ready. Try:\n"
            "  \"Analyze NVDA\"\n"
            "  \"TSLA swing\"\n"
            "  \"Screenshot this chart\"\n"
            "  or press Ctrl+Shift+S"
        ),
        "zh": (
            "准备就绪，试试:\n"
            "  \"分析 NVDA\"\n"
            "  \"TSLA 波段\"\n"
            "  \"截图分析图表\"\n"
            "  或按 Ctrl+Shift+S"
        ),
    },

    # ── Character window: state bubbles ──────────────────────────
    "listening":                {"en": "listening...",            "zh": "在听..."},
    "go_ahead":                 {"en": "go ahead...",            "zh": "请说..."},
    "im_here":                  {"en": "I'm here...",            "zh": "我在..."},
    "analysing":                {"en": "analysing...",           "zh": "分析中..."},
    "let_me_check":             {"en": "let me check...",        "zh": "我看看..."},
    "one_sec":                  {"en": "one sec...",             "zh": "稍等..."},
    "checking_charts":          {"en": "checking charts...",     "zh": "看图中..."},
    "thinking_bubble":          {"en": "thinking...",            "zh": "思考中..."},
    "strong_signal":            {"en": "strong signal!",         "zh": "强信号!"},
    "looking_good":             {"en": "looking good!",          "zh": "看好!"},
    "setup_confirmed":          {"en": "setup confirmed!",      "zh": "形态确认!"},
    "careful_here":             {"en": "careful here...",        "zh": "小心..."},
    "risk_is_high":             {"en": "risk is high!",          "zh": "风险很高!"},
    "watch_out":                {"en": "watch out...",           "zh": "注意..."},
    "not_yet":                  {"en": "not yet...",             "zh": "还不行..."},
    "stand_aside":              {"en": "stand aside",            "zh": "观望"},
    "no_setup":                 {"en": "no setup here",          "zh": "没有形态"},

    # ── Character window: decision state messages ────────────────
    "careful_high_risk":        {"en": "careful \u2014 high risk",
                                 "zh": "小心 \u2014 高风险"},
    "signal_looks_good":        {"en": "signal looks good!",     "zh": "信号不错!"},
    "sell_watch_risk":          {"en": "sell signal \u2014 watch risk",
                                 "zh": "卖出信号 \u2014 注意风险"},
    "no_clear_setup":           {"en": "no clear setup",         "zh": "暂无明确形态"},
    "ready":                    {"en": "ready!",                 "zh": "就绪!"},

    # ── Main: screenshot hotkey feedback ─────────────────────────
    "already_analyzing":        {"en": "already analyzing...",   "zh": "正在分析中..."},
    "capturing":                {"en": "capturing...",           "zh": "截图中..."},
    "analyzing_chart":          {"en": "analyzing chart...",     "zh": "分析图表中..."},
    "capture_failed":           {"en": "capture failed",         "zh": "截图失败"},
    "analysis_failed":          {"en": "analysis failed",        "zh": "分析失败"},

    # ── Tray icon: menu items ────────────────────────────────────
    "tray_screenshot":          {"en": "Screenshot Analysis (Ctrl+Shift+S)",
                                 "zh": "截图分析 (Ctrl+Shift+S)"},
    "tray_show_hide":           {"en": "Show / Hide",            "zh": "显示 / 隐藏"},
    "tray_scalp":               {"en": "Mode: Scalp (5m)",       "zh": "模式: 超短 (5m)"},
    "tray_intraday_15m":        {"en": "Mode: Intraday (15m)",   "zh": "模式: 日内 (15m)"},
    "tray_intraday_1h":         {"en": "Mode: Intraday (1h)",    "zh": "模式: 日内 (1h)"},
    "tray_swing":               {"en": "Mode: Swing (1D)",       "zh": "模式: 波段 (1D)"},
    "tray_ticker":              {"en": "Ticker",                 "zh": "代码"},
    "tray_quit":                {"en": "Quit",                   "zh": "退出"},

    # ── Brain bridge: display labels ─────────────────────────────
    "mode_scalping":            {"en": "Scalping",               "zh": "超短"},
    "mode_intraday":            {"en": "Intraday",               "zh": "日内"},
    "mode_swing":               {"en": "Swing",                  "zh": "波段"},

    # ── Risk levels (card metrics) ───────────────────────────────
    "risk_low":                 {"en": "Low",                    "zh": "低"},
    "risk_medium":              {"en": "Moderate",               "zh": "中等"},
    "risk_high":                {"en": "Elevated",               "zh": "高"},

    # ── Risk management labels ───────────────────────────────────
    "entry":                    {"en": "Entry",                  "zh": "入场"},
    "stop":                     {"en": "Stop",                   "zh": "止损"},
    "target":                   {"en": "Target",                 "zh": "目标"},
    "risk_reward":              {"en": "R:R",                    "zh": "风险收益比"},

    # ── Error categories ─────────────────────────────────────────
    "error_api_key_missing":    {"en": "API key not set. Check ANTHROPIC_API_KEY.",
                                 "zh": "API密钥未设置，请检查 ANTHROPIC_API_KEY。"},
    "error_network":            {"en": "Network error — check your connection.",
                                 "zh": "网络错误 — 请检查连接。"},
    "error_service_unavailable": {"en": "Service temporarily unavailable. Try again.",
                                  "zh": "服务暂时不可用，请重试。"},
    "error_timeout":            {"en": "Analysis timed out. Try a shorter timeframe.",
                                 "zh": "分析超时，请尝试较短的周期。"},
    "error_invalid_ticker":     {"en": "Ticker not found. Check the symbol.",
                                 "zh": "代码未找到，请检查。"},
    "error_generic":            {"en": "Something went wrong. Check logs for details.",
                                 "zh": "出现错误，请查看日志了解详情。"},

    # ── Loading step messages ────────────────────────────────────
    "step_fetching_data":       {"en": "Fetching market data...",   "zh": "获取市场数据..."},
    "step_computing":           {"en": "Computing indicators...",   "zh": "计算指标..."},
    "step_analyzing":           {"en": "Running analysis...",       "zh": "执行分析..."},
    "step_ai_overlay":          {"en": "Claude AI reviewing...",    "zh": "Claude AI 审核..."},
    "step_complete":            {"en": "Done!",                     "zh": "完成!"},

    # ── Startup validation ───────────────────────────────────────
    "startup_checking":         {"en": "Initializing...",           "zh": "初始化中..."},
    "startup_ready":            {"en": "Ready",                     "zh": "就绪"},
    "startup_api_missing":      {"en": "API key missing — limited mode",
                                 "zh": "API密钥缺失 — 有限模式"},
}

# Global language default — updated by ChatPopover when user switches language
_current_lang: str = "en"


def set_lang(lang: str) -> None:
    """Set the global default language."""
    global _current_lang
    _current_lang = lang


def get_lang() -> str:
    """Get the current global default language."""
    return _current_lang


def t(key: str, lang: str | None = None) -> str:
    """Look up a translated string. Falls back to English, then to the key."""
    lang = lang or _current_lang
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("en", key))
