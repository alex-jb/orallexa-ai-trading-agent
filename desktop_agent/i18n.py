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
    "bull_coach":               {"en": "Bull Coach",              "zh": "牛教练",           "ja": "ブルコーチ"},

    # ── Chat popover: buttons & labels ───────────────────────────
    "clear":                    {"en": "Clear",                   "zh": "清除",             "ja": "クリア"},
    "ticker":                   {"en": "Ticker",                  "zh": "代码",             "ja": "銘柄"},
    "scalp":                    {"en": "Scalp",                   "zh": "超短",             "ja": "スキャルプ"},
    "intra":                    {"en": "Intra",                   "zh": "日内",             "ja": "日中"},
    "swing":                    {"en": "Swing",                   "zh": "波段",             "ja": "スウィング"},
    "last":                     {"en": "Last",                    "zh": "上次",             "ja": "前回"},
    "voice_on":                 {"en": "Voice ON",                "zh": "语音 开",          "ja": "音声 オン"},
    "voice_off":                {"en": "Voice OFF",               "zh": "语音 关",          "ja": "音声 オフ"},
    "lang_label":               {"en": "Lang:",                   "zh": "语言:",            "ja": "言語:"},
    "why":                      {"en": "Why?",                    "zh": "为什么?",          "ja": "なぜ?"},
    "tech_details":             {"en": "Technical Details",       "zh": "技术详情",         "ja": "技術詳細"},
    "analysis_complete":        {"en": "Analysis complete.",      "zh": "分析完成。",       "ja": "分析完了。"},
    "you":                      {"en": "You",                     "zh": "你",               "ja": "あなた"},
    "thinking":                 {"en": "thinking\u2026",          "zh": "思考中\u2026",     "ja": "考え中\u2026"},
    "transcribing":             {"en": "transcribing\u2026",      "zh": "转录中\u2026",     "ja": "文字起こし中\u2026"},
    "no_speech":                {"en": "(no speech detected)",    "zh": "(未检测到语音)",   "ja": "(音声が検出されません)"},
    "chat_cleared":             {"en": "Chat cleared. What's next?",
                                 "zh": "聊天已清除，接下来呢？",
                                 "ja": "チャットをクリアしました。次は？"},

    # ── Chat popover: metric labels ──────────────────────────────
    "signal":                   {"en": "SIGNAL",                  "zh": "信号",             "ja": "シグナル"},
    "confidence":               {"en": "CONFIDENCE",              "zh": "置信度",           "ja": "信頼度"},
    "risk":                     {"en": "RISK",                    "zh": "风险",             "ja": "リスク"},

    # ── Chat popover: welcome & empty-state hint ───────────────────
    "welcome_back":             {"en": "Welcome back, Master!",
                                 "zh": "欢迎回来, Master!",
                                 "ja": "おかえりなさい、マスター!"},
    "hint": {
        "en": (
            "Welcome back, Master!\n"
            "Try:\n"
            "  \"Analyze NVDA\"\n"
            "  \"TSLA swing\"\n"
            "  \"Screenshot this chart\"\n"
            "  or press Ctrl+Shift+S"
        ),
        "zh": (
            "欢迎回来, Master!\n"
            "试试:\n"
            "  \"分析 NVDA\"\n"
            "  \"TSLA 波段\"\n"
            "  \"截图分析图表\"\n"
            "  或按 Ctrl+Shift+S"
        ),
        "ja": (
            "おかえりなさい、マスター!\n"
            "試してみて:\n"
            "  \"NVDAを分析\"\n"
            "  \"TSLAスウィング\"\n"
            "  \"このチャートをスクリーンショット\"\n"
            "  またはCtrl+Shift+Sを押す"
        ),
    },

    # ── Character window: state bubbles ──────────────────────────
    "listening":                {"en": "listening...",            "zh": "在听...",          "ja": "聞いています..."},
    "go_ahead":                 {"en": "go ahead...",             "zh": "请说...",          "ja": "どうぞ..."},
    "im_here":                  {"en": "I'm here...",             "zh": "我在...",          "ja": "ここにいます..."},
    "analysing":                {"en": "analysing...",            "zh": "分析中...",        "ja": "分析中..."},
    "let_me_check":             {"en": "let me check...",         "zh": "我看看...",        "ja": "確認します..."},
    "one_sec":                  {"en": "one sec...",              "zh": "稍等...",          "ja": "少々お待ちを..."},
    "checking_charts":          {"en": "checking charts...",      "zh": "看图中...",        "ja": "チャートを確認中..."},
    "thinking_bubble":          {"en": "thinking...",             "zh": "思考中...",        "ja": "考え中..."},
    "strong_signal":            {"en": "strong signal!",          "zh": "强信号!",          "ja": "強いシグナル!"},
    "looking_good":             {"en": "looking good!",           "zh": "看好!",            "ja": "良い感じ!"},
    "setup_confirmed":          {"en": "setup confirmed!",        "zh": "形态确认!",        "ja": "セットアップ確認!"},
    "careful_here":             {"en": "careful here...",         "zh": "小心...",          "ja": "注意して..."},
    "risk_is_high":             {"en": "risk is high!",           "zh": "风险很高!",        "ja": "リスクが高い!"},
    "watch_out":                {"en": "watch out...",            "zh": "注意...",          "ja": "気をつけて..."},
    "not_yet":                  {"en": "not yet...",              "zh": "还不行...",        "ja": "まだです..."},
    "stand_aside":              {"en": "stand aside",             "zh": "观望",             "ja": "様子見"},
    "no_setup":                 {"en": "no setup here",           "zh": "没有形态",         "ja": "セットアップなし"},

    # ── Character window: decision state messages ────────────────
    "careful_high_risk":        {"en": "careful \u2014 high risk",
                                 "zh": "小心 \u2014 高风险",
                                 "ja": "注意 \u2014 高リスク"},
    "signal_looks_good":        {"en": "signal looks good!",      "zh": "信号不错!",        "ja": "シグナル良好!"},
    "sell_watch_risk":          {"en": "sell signal \u2014 watch risk",
                                 "zh": "卖出信号 \u2014 注意风险",
                                 "ja": "売りシグナル \u2014 リスクに注意"},
    "no_clear_setup":           {"en": "no clear setup",          "zh": "暂无明确形态",     "ja": "明確なセットアップなし"},
    "ready":                    {"en": "ready!",                  "zh": "就绪!",            "ja": "準備完了!"},

    # ── Main: screenshot hotkey feedback ─────────────────────────
    "already_analyzing":        {"en": "already analyzing...",    "zh": "正在分析中...",    "ja": "分析中..."},
    "capturing":                {"en": "capturing...",            "zh": "截图中...",        "ja": "キャプチャ中..."},
    "analyzing_chart":          {"en": "analyzing chart...",      "zh": "分析图表中...",    "ja": "チャート分析中..."},
    "capture_failed":           {"en": "capture failed",          "zh": "截图失败",         "ja": "キャプチャ失敗"},
    "analysis_failed":          {"en": "analysis failed",         "zh": "分析失败",         "ja": "分析失敗"},

    # ── Tray icon: menu items ────────────────────────────────────
    "tray_screenshot":          {"en": "Screenshot Analysis (Ctrl+Shift+S)",
                                 "zh": "截图分析 (Ctrl+Shift+S)",
                                 "ja": "スクリーンショット分析 (Ctrl+Shift+S)"},
    "tray_show_hide":           {"en": "Show / Hide",             "zh": "显示 / 隐藏",      "ja": "表示 / 非表示"},
    "tray_scalp":               {"en": "Mode: Scalp (5m)",        "zh": "模式: 超短 (5m)",  "ja": "モード: スキャルプ (5m)"},
    "tray_intraday_15m":        {"en": "Mode: Intraday (15m)",    "zh": "模式: 日内 (15m)", "ja": "モード: 日中 (15m)"},
    "tray_intraday_1h":         {"en": "Mode: Intraday (1h)",     "zh": "模式: 日内 (1h)",  "ja": "モード: 日中 (1h)"},
    "tray_swing":               {"en": "Mode: Swing (1D)",        "zh": "模式: 波段 (1D)",  "ja": "モード: スウィング (1D)"},
    "tray_ticker":              {"en": "Ticker",                  "zh": "代码",             "ja": "銘柄"},
    "tray_quit":                {"en": "Quit",                    "zh": "退出",             "ja": "終了"},

    # ── Brain bridge: display labels ─────────────────────────────
    "mode_scalping":            {"en": "Scalping",                "zh": "超短",             "ja": "スキャルピング"},
    "mode_intraday":            {"en": "Intraday",                "zh": "日内",             "ja": "日中"},
    "mode_swing":               {"en": "Swing",                   "zh": "波段",             "ja": "スウィング"},

    # ── Risk levels (card metrics) ───────────────────────────────
    "risk_low":                 {"en": "Low",                     "zh": "低",               "ja": "低"},
    "risk_medium":              {"en": "Moderate",                "zh": "中等",             "ja": "中程度"},
    "risk_high":                {"en": "Elevated",                "zh": "高",               "ja": "高"},

    # ── Risk management labels ───────────────────────────────────
    "entry":                    {"en": "Entry",                   "zh": "入场",             "ja": "エントリー"},
    "stop":                     {"en": "Stop",                    "zh": "止损",             "ja": "ストップ"},
    "target":                   {"en": "Target",                  "zh": "目标",             "ja": "ターゲット"},
    "risk_reward":              {"en": "R:R",                     "zh": "风险收益比",       "ja": "リスクリワード"},

    # ── Error categories ─────────────────────────────────────────
    "error_api_key_missing":    {"en": "API key not set. Check ANTHROPIC_API_KEY.",
                                 "zh": "API密钥未设置，请检查 ANTHROPIC_API_KEY。",
                                 "ja": "APIキーが設定されていません。ANTHROPIC_API_KEYを確認してください。"},
    "error_network":            {"en": "Network error — check your connection.",
                                 "zh": "网络错误 — 请检查连接。",
                                 "ja": "ネットワークエラー — 接続を確認してください。"},
    "error_service_unavailable": {"en": "Service temporarily unavailable. Try again.",
                                  "zh": "服务暂时不可用，请重试。",
                                  "ja": "サービスが一時的に利用できません。再試行してください。"},
    "error_timeout":            {"en": "Analysis timed out. Try a shorter timeframe.",
                                 "zh": "分析超时，请尝试较短的周期。",
                                 "ja": "分析がタイムアウトしました。より短い時間枠を試してください。"},
    "error_invalid_ticker":     {"en": "Ticker not found. Check the symbol.",
                                 "zh": "代码未找到，请检查。",
                                 "ja": "銘柄が見つかりません。シンボルを確認してください。"},
    "error_generic":            {"en": "Something went wrong. Check logs for details.",
                                 "zh": "出现错误，请查看日志了解详情。",
                                 "ja": "エラーが発生しました。詳細はログを確認してください。"},

    # ── Loading step messages ────────────────────────────────────
    "step_fetching_data":       {"en": "Fetching market data...",    "zh": "获取市场数据...",  "ja": "市場データを取得中..."},
    "step_computing":           {"en": "Computing indicators...",    "zh": "计算指标...",      "ja": "指標を計算中..."},
    "step_analyzing":           {"en": "Running analysis...",        "zh": "执行分析...",      "ja": "分析を実行中..."},
    "step_ai_overlay":          {"en": "Claude AI reviewing...",     "zh": "Claude AI 审核...", "ja": "Claude AIが確認中..."},
    "step_complete":            {"en": "Done!",                      "zh": "完成!",            "ja": "完了!"},

    # ── Startup validation ───────────────────────────────────────
    "startup_checking":         {"en": "Initializing...",            "zh": "初始化中...",      "ja": "初期化中..."},
    "startup_ready":            {"en": "Ready",                      "zh": "就绪",             "ja": "準備完了"},
    "startup_api_missing":      {"en": "API key missing — limited mode",
                                 "zh": "API密钥缺失 — 有限模式",
                                 "ja": "APIキーがありません — 制限モード"},

    # ── Sleep mode ───────────────────────────────────────────────
    "sleeping":                 {"en": "zzZ...",                     "zh": "zzZ...",           "ja": "zzZ..."},
    "waking_up":                {"en": "yawn~ good morning!",        "zh": "哈欠~ 早安!",      "ja": "あくび〜おはよう!"},
    "sleepy":                   {"en": "getting sleepy...",          "zh": "有点困了...",      "ja": "眠くなってきた..."},

    # ── Time-aware greetings ─────────────────────────────────────
    "greeting_morning":         {"en": "Good morning, Master! Pre-market prep time.",
                                 "zh": "早安Master! 盘前准备时间。",
                                 "ja": "おはようございます、マスター！プレマーケットの準備時間です。"},
    "greeting_market_open":     {"en": "Market is OPEN! Let's find setups.",
                                 "zh": "开盘了! 找信号吧。",
                                 "ja": "市場がオープンしました！セットアップを探しましょう。"},
    "greeting_lunch":           {"en": "Lunch time. Market slows here.",
                                 "zh": "午间休息，行情通常放缓。",
                                 "ja": "ランチタイム。市場は落ち着いています。"},
    "greeting_afternoon":       {"en": "Afternoon session. Stay focused.",
                                 "zh": "下午盘，保持专注。",
                                 "ja": "午後のセッション。集中を保ちましょう。"},
    "greeting_market_close":    {"en": "Market closing soon! Review your P&L.",
                                 "zh": "快收盘了! 检查一下盈亏。",
                                 "ja": "もうすぐ閉場です！損益を確認しましょう。"},
    "greeting_evening":         {"en": "Markets closed. Time to review & plan.",
                                 "zh": "收盘了，复盘时间。",
                                 "ja": "市場が閉まりました。振り返りと計画の時間です。"},
    "greeting_night":           {"en": "Late night trading? Be careful with futures.",
                                 "zh": "夜盘交易? 期货小心操作。",
                                 "ja": "深夜取引？先物には気をつけて。"},
    "greeting_weekend":         {"en": "Weekend! Rest up for Monday.",
                                 "zh": "周末啦! 休息一下准备周一。",
                                 "ja": "週末！月曜日に備えて休みましょう。"},

    # ── Expression reactions ─────────────────────────────────────
    "happy_reaction":           {"en": "Yay! Great trade!",          "zh": "耶! 好交易!",      "ja": "やった！良いトレード！"},
    "surprised_reaction":       {"en": "Whoa! Big move!",            "zh": "哇! 大行情!",      "ja": "おお！大きな動き！"},
    "angry_reaction":           {"en": "Ugh, stop loss hit...",      "zh": "唉，止损了...",    "ja": "うっ、ストップロスに当たった..."},

    # ── Follow cursor ────────────────────────────────────────────
    "follow_on":                {"en": "Following you~",             "zh": "跟着你~",          "ja": "ついていきます〜"},
    "follow_off":               {"en": "Free roaming~",              "zh": "自由漫步~",        "ja": "自由に動きます〜"},

    # ── Auto market check ────────────────────────────────────────
    "market_alert":             {"en": "Alert: {ticker} moved {pct}%!",
                                 "zh": "提醒: {ticker} 变动 {pct}%!",
                                 "ja": "アラート: {ticker}が{pct}%動きました！"},
    "market_check_ok":          {"en": "{ticker} is quiet. No action needed.",
                                 "zh": "{ticker} 平稳，无需操作。",
                                 "ja": "{ticker}は落ち着いています。操作不要です。"},

    # ── Particle effects ─────────────────────────────────────────
    "confetti":                 {"en": "Bullish!",                   "zh": "看涨!",            "ja": "強気！"},

    # ── Jump animation ───────────────────────────────────────────
    "jump_excited":             {"en": "Let's go!",                  "zh": "冲!",              "ja": "行くぞ！"},

    # ── Mood-aware idle tips ─────────────────────────────────────
    "streak_positive_1":        {"en": "On a roll!",                 "zh": "连胜中!",          "ja": "好調が続いています！"},
    "streak_positive_2":        {"en": "Stay disciplined on streaks","zh": "保持冷静，别大意", "ja": "連勝中も規律を保ちましょう"},
    "streak_negative_1":        {"en": "Tough streak. Review your plan.", "zh": "别气馁，回顾策略", "ja": "厳しい流れ。計画を見直しましょう。"},
    "streak_negative_2":        {"en": "Take a break, reset.",       "zh": "连亏了，休息一下", "ja": "休憩してリセットしましょう。"},

    # ── Pet interaction ──────────────────────────────────────────
    "pet_1":                    {"en": "Moo~ ♥",                     "zh": "哞~ ♥",            "ja": "モー〜 ♥"},
    "pet_2":                    {"en": "Bull happy!",                "zh": "嘿嘿~",            "ja": "うれしい！"},
    "pet_3":                    {"en": "Hey~",                       "zh": "摸摸~",            "ja": "なでなで〜"},

    # ── Missing dependency warnings ──────────────────────────────
    "yfinance_missing":         {"en": "pip install yfinance for market alerts",
                                 "zh": "请安装 yfinance 以启用市场提醒",
                                 "ja": "市場アラートにはpip install yfinanceが必要です"},
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
