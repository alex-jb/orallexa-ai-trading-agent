"""
tests/test_brain_bridge.py
─────────────────────────────────────────────────────────────
Unit tests for desktop_agent/brain_bridge.py intent detection,
ticker extraction, mode extraction, and timeframe extraction.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from desktop_agent.brain_bridge import (
    _extract_ticker,
    _extract_mode,
    _extract_timeframe,
    _kw_match,
    _ANALYSIS_KW,
    _DASHBOARD_KW,
    _SCREENSHOT_KW,
    _GREETING_KW,
)


# ── Ticker extraction ────────────────────────────────────────────────────────

class TestExtractTicker:
    def test_dollar_notation(self):
        assert _extract_ticker("Check $NVDA now", "SPY") == "NVDA"

    def test_dollar_notation_priority(self):
        assert _extract_ticker("$AAPL vs TSLA", "SPY") == "AAPL"

    def test_known_ticker(self):
        assert _extract_ticker("How is TSLA doing?", "SPY") == "TSLA"

    def test_known_ticker_in_sentence(self):
        assert _extract_ticker("Should I buy NVDA today", "AAPL") == "NVDA"

    def test_unknown_uppercase(self):
        assert _extract_ticker("Check PLXYZ for me", "SPY") == "PLXYZ"

    def test_noise_words_skipped(self):
        assert _extract_ticker("Should I buy now?", "NVDA") == "NVDA"

    def test_fallback_to_default(self):
        # Sentence where ALL uppercase words are in the noise set → default
        assert _extract_ticker("I think the market is good now", "QQQ") == "QQQ"

    def test_empty_string(self):
        assert _extract_ticker("", "NVDA") == "NVDA"

    def test_uppercase_converts(self):
        # _extract_ticker uppercases the input, so "nvda" becomes "NVDA"
        assert _extract_ticker("check nvda please", "SPY") == "NVDA"


# ── Mode extraction ──────────────────────────────────────────────────────────

class TestExtractMode:
    def test_scalp_keyword(self):
        assert _extract_mode("scalp setup on NVDA", "intraday") == "scalp"

    def test_swing_keyword(self):
        assert _extract_mode("NVDA swing analysis", "intraday") == "swing"

    def test_intraday_keyword(self):
        assert _extract_mode("intraday view", "scalp") == "intraday"

    def test_chinese_scalp(self):
        assert _extract_mode("NVDA 超短线", "intraday") == "scalp"

    def test_chinese_swing(self):
        assert _extract_mode("波段分析", "intraday") == "swing"

    def test_timeframe_implies_mode(self):
        assert _extract_mode("show me the 5m chart", "swing") == "scalp"

    def test_default_when_no_match(self):
        assert _extract_mode("how is the market?", "intraday") == "intraday"


# ── Timeframe extraction ────────────────────────────────────────────────────

class TestExtractTimeframe:
    def test_explicit_5m(self):
        assert _extract_timeframe("5m chart for NVDA", "scalp", "15m") == "5m"

    def test_explicit_1h(self):
        assert _extract_timeframe("show 1h candles", "intraday", "15m") == "1h"

    def test_explicit_daily(self):
        assert _extract_timeframe("daily chart", "swing", "15m") == "1D"

    def test_mode_default_tf(self):
        # If mode is scalp but no explicit TF, use scalp's default (5m)
        assert _extract_timeframe("looking good", "scalp", "15m") == "5m"

    def test_fallback(self):
        assert _extract_timeframe("just checking", "intraday", "15m") == "15m"


# ── Keyword matching (intent detection) ─────────────────────────────────────

class TestKwMatch:
    def test_analysis_en(self):
        assert _kw_match("should i buy NVDA", "en", _ANALYSIS_KW) is True

    def test_analysis_zh(self):
        assert _kw_match("NVDA能买吗", "zh", _ANALYSIS_KW) is True

    def test_dashboard_en(self):
        assert _kw_match("open dashboard", "en", _DASHBOARD_KW) is True

    def test_screenshot_en(self):
        assert _kw_match("screenshot this chart", "en", _SCREENSHOT_KW) is True

    def test_greeting_en(self):
        assert _kw_match("hello", "en", _GREETING_KW) is True

    def test_greeting_zh(self):
        assert _kw_match("你好", "zh", _GREETING_KW) is True

    def test_no_match(self):
        assert _kw_match("random text here", "en", _DASHBOARD_KW) is False

    def test_cross_language_match(self):
        # English keywords should match even when lang is "zh"
        assert _kw_match("open dashboard", "zh", _DASHBOARD_KW) is True

    def test_case_insensitive(self):
        assert _kw_match("SHOULD I BUY", "en", _ANALYSIS_KW) is True
