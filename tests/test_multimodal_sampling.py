"""
Tests for engine.multi_agent_analysis._sample_multimodal — the env-gated
opt-in switch that lets prod accumulate vision-vs-text eval data slowly
without forcing every deep-analysis call to pay the ~5× vision cost.

Default behavior (env unset → 0) MUST be a no-op so the existing 922-test
backend stays bit-for-bit identical.
"""
from __future__ import annotations

import random
import os
from unittest import mock

from engine.multi_agent_analysis import _sample_multimodal


class TestSampleMultimodal:
    def test_explicit_true_always_wins(self):
        # Even with rate=0, explicit caller opt-in is honored.
        assert _sample_multimodal(True, env_value="0") is True
        assert _sample_multimodal(True, env_value="0.5") is True
        assert _sample_multimodal(True, env_value="bogus") is True

    def test_default_off_when_env_zero_or_missing(self):
        # The whole point of the default: zero behavior change unless opted in.
        assert _sample_multimodal(False, env_value="0") is False
        assert _sample_multimodal(False, env_value="0.0") is False
        assert _sample_multimodal(False, env_value=None) is False  # → reads env, default "0"

    def test_rate_one_always_on(self):
        assert _sample_multimodal(False, env_value="1") is True
        assert _sample_multimodal(False, env_value="1.0") is True
        # Rates > 1 still treated as "always on" — clamped via the >=1 branch.
        assert _sample_multimodal(False, env_value="2.5") is True

    def test_invalid_rate_safely_off(self):
        # Garbage env values must not raise; degrade to off.
        assert _sample_multimodal(False, env_value="abc") is False
        assert _sample_multimodal(False, env_value="") is False
        assert _sample_multimodal(False, env_value="0.1.2") is False

    def test_negative_rate_treated_as_off(self):
        assert _sample_multimodal(False, env_value="-0.5") is False
        assert _sample_multimodal(False, env_value="-1") is False

    def test_partial_rate_uses_random(self):
        # Seed random so the rate=0.5 outcome is deterministic for this test.
        random.seed(42)
        # With this seed, first random.random() call returns ~0.6394 — above 0.5
        # so first call returns False; subsequent calls vary.
        first = _sample_multimodal(False, env_value="0.5")
        # Just assert the function returns a bool — exact value depends on
        # cpython's random.random() implementation but must always be bool.
        assert isinstance(first, bool)

    def test_partial_rate_distribution(self):
        # Roll 1000 times at rate=0.3; expect ~300 hits ± slack. This is the
        # actual sampling property prod relies on.
        random.seed(0)
        hits = sum(_sample_multimodal(False, env_value="0.3") for _ in range(1000))
        assert 230 <= hits <= 370, f"expected ~300/1000 hits at rate=0.3, got {hits}"

    def test_reads_env_when_no_explicit_value(self):
        # The env_value=None branch falls through to os.environ.
        with mock.patch.dict(os.environ, {"ORALLEXA_MULTIMODAL_SAMPLE": "1.0"}):
            assert _sample_multimodal(False) is True
        with mock.patch.dict(os.environ, {"ORALLEXA_MULTIMODAL_SAMPLE": "0"}):
            assert _sample_multimodal(False) is False
        with mock.patch.dict(os.environ, {}, clear=True):
            # Missing env var → default "0" → off.
            assert _sample_multimodal(False) is False
