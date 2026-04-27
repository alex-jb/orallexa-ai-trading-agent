"""Tests for desktop_agent/i18n.py — coverage for the trilingual string table."""
from __future__ import annotations

import pytest

from desktop_agent import i18n
from desktop_agent.i18n import _STRINGS, get_lang, set_lang, t


SUPPORTED = ("en", "zh", "ja")


class TestStringTableCoverage:
    @pytest.mark.parametrize("lang", SUPPORTED)
    def test_every_key_has_translation(self, lang):
        missing = [key for key, entry in _STRINGS.items() if lang not in entry]
        assert not missing, f"Missing {lang} translations for: {missing}"

    @pytest.mark.parametrize("lang", SUPPORTED)
    def test_no_translation_is_empty(self, lang):
        empty = [key for key, entry in _STRINGS.items() if not entry.get(lang, "").strip()]
        assert not empty, f"Empty {lang} translations for: {empty}"

    def test_format_placeholders_match_across_languages(self):
        # If `{ticker}` or `{pct}` exists in en, it must exist in zh and ja too,
        # otherwise `.format(...)` calls would silently lose values.
        import re

        ph = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
        bad = []
        for key, entry in _STRINGS.items():
            keys_per_lang = {lang: set(ph.findall(entry.get(lang, ""))) for lang in SUPPORTED}
            if len({frozenset(s) for s in keys_per_lang.values()}) > 1:
                bad.append((key, keys_per_lang))
        assert not bad, f"Placeholder mismatch across languages: {bad}"


class TestLookup:
    def test_japanese_lookup_returns_japanese(self):
        assert t("ticker", lang="ja") == "銘柄"
        assert t("bull_coach", lang="ja") == "ブルコーチ"

    def test_english_unchanged(self):
        assert t("ticker", lang="en") == "Ticker"

    def test_chinese_unchanged(self):
        assert t("ticker", lang="zh") == "代码"

    def test_unknown_key_returns_key(self):
        assert t("__does_not_exist__", lang="ja") == "__does_not_exist__"

    def test_unknown_lang_falls_back_to_english(self):
        # The lookup logic falls back to English for unsupported language codes;
        # this is the documented behavior, not a hard whitelist.
        assert t("ticker", lang="fr") == "Ticker"


class TestGlobalLang:
    def teardown_method(self):
        # Restore default after each test so we don't leak state.
        set_lang("en")

    def test_set_and_get_lang_roundtrip(self):
        set_lang("ja")
        assert get_lang() == "ja"

    def test_default_lang_uses_global(self):
        set_lang("ja")
        assert t("ticker") == "銘柄"
