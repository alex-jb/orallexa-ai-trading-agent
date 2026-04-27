"""
tests/test_api_e2e.py
────────────────────────────────────────────────────────────────────
API endpoint E2E tests using FastAPI TestClient.

Tests all API endpoints without needing a running server.
LLM calls are NOT mocked — tests that require API keys are
marked with @pytest.mark.llm and skipped if key is not set.
"""
import os
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create FastAPI test client."""
    from api_server import app
    return TestClient(app)


@pytest.fixture
def has_api_key():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ═══════════════════════════════════════════════════════════════════════════
# HEALTHZ — liveness probe used by Docker / K8s
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthz:
    def test_healthz_returns_200(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200

    def test_healthz_payload(self, client):
        data = client.get("/healthz").json()
        assert data["ok"] is True
        assert data["service"] == "orallexa-api"


# ═══════════════════════════════════════════════════════════════════════════
# ANALYZE ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

class TestAnalyzeEndpoint:
    def test_analyze_returns_200(self, client):
        resp = client.post("/api/analyze", data={"ticker": "AAPL", "mode": "intraday", "timeframe": "15m"})
        assert resp.status_code == 200

    def test_analyze_response_structure(self, client):
        resp = client.post("/api/analyze", data={"ticker": "AAPL", "mode": "intraday"})
        data = resp.json()
        assert "decision" in data
        assert "confidence" in data
        assert "risk_level" in data
        assert "reasoning" in data
        assert "probabilities" in data

    def test_analyze_decision_valid(self, client):
        resp = client.post("/api/analyze", data={"ticker": "MSFT", "mode": "scalp"})
        data = resp.json()
        assert data["decision"] in ("BUY", "SELL", "WAIT")

    def test_analyze_confidence_in_range(self, client):
        resp = client.post("/api/analyze", data={"ticker": "AAPL"})
        data = resp.json()
        assert 0 <= data["confidence"] <= 100

    def test_analyze_risk_level_valid(self, client):
        resp = client.post("/api/analyze", data={"ticker": "AAPL"})
        data = resp.json()
        assert data["risk_level"] in ("LOW", "MEDIUM", "HIGH")

    def test_analyze_probabilities_sum(self, client):
        resp = client.post("/api/analyze", data={"ticker": "AAPL"})
        data = resp.json()
        probs = data["probabilities"]
        total = probs.get("up", 0) + probs.get("neutral", 0) + probs.get("down", 0)
        assert abs(total - 1.0) < 0.1, f"Probabilities sum to {total}"

    def test_analyze_with_context(self, client):
        resp = client.post("/api/analyze", data={
            "ticker": "NVDA", "mode": "swing", "context": "Earnings next week"
        })
        assert resp.status_code == 200

    def test_analyze_modes(self, client):
        for mode in ("scalp", "intraday", "swing"):
            resp = client.post("/api/analyze", data={"ticker": "AAPL", "mode": mode})
            assert resp.status_code == 200, f"Mode {mode} failed"


# ═══════════════════════════════════════════════════════════════════════════
# NEWS ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

class TestNewsEndpoint:
    def test_news_returns_200(self, client):
        resp = client.get("/api/news/AAPL")
        assert resp.status_code == 200

    def test_news_has_items(self, client):
        resp = client.get("/api/news/AAPL")
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_news_item_structure(self, client):
        resp = client.get("/api/news/AAPL")
        data = resp.json()
        if data["items"]:
            item = data["items"][0]
            assert "title" in item
            assert "sentiment" in item
            assert item["sentiment"] in ("bullish", "bearish", "neutral")


# ═══════════════════════════════════════════════════════════════════════════
# PROFILE ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

class TestProfileEndpoint:
    def test_profile_returns_200(self, client):
        resp = client.get("/api/profile")
        assert resp.status_code == 200

    def test_profile_structure(self, client):
        resp = client.get("/api/profile")
        data = resp.json()
        assert "style" in data
        assert "win_rate" in data
        assert "today" in data


# ═══════════════════════════════════════════════════════════════════════════
# JOURNAL ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

class TestJournalEndpoint:
    def test_journal_returns_200(self, client):
        resp = client.get("/api/journal")
        assert resp.status_code == 200

    def test_journal_structure(self, client):
        resp = client.get("/api/journal")
        data = resp.json()
        assert "entries" in data
        assert isinstance(data["entries"], list)


# ═══════════════════════════════════════════════════════════════════════════
# CHART ANALYSIS ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

class TestChartAnalysis:
    @pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="No API key")
    def test_chart_analysis_with_image(self, client, tmp_path):
        """Test chart analysis with a dummy image (requires API key)."""
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="white")
        img_path = tmp_path / "test_chart.png"
        img.save(img_path)

        with open(img_path, "rb") as f:
            resp = client.post("/api/chart-analysis", data={"ticker": "NVDA"}, files={"file": f})
        assert resp.status_code == 200
        data = resp.json()
        assert "decision" in data


# ═══════════════════════════════════════════════════════════════════════════
# DEEP ANALYSIS ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

class TestDeepAnalysis:
    @pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="No API key")
    def test_deep_analysis_returns_200(self, client):
        resp = client.post("/api/deep-analysis", data={"ticker": "AAPL"}, timeout=120)
        assert resp.status_code == 200

    @pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="No API key")
    def test_deep_analysis_structure(self, client):
        resp = client.post("/api/deep-analysis", data={"ticker": "AAPL"}, timeout=120)
        data = resp.json()
        assert "decision" in data
        assert "reports" in data or "detail" in data


# ═══════════════════════════════════════════════════════════════════════════
# EVOLVE STRATEGIES ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

class TestEvolveStrategies:
    @pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="No API key")
    def test_evolve_returns_200(self, client):
        resp = client.post("/api/evolve-strategies", data={
            "ticker": "AAPL", "generations": "1", "population": "1"
        }, timeout=60)
        assert resp.status_code == 200

    @pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="No API key")
    def test_evolve_structure(self, client):
        resp = client.post("/api/evolve-strategies", data={
            "ticker": "AAPL", "generations": "1", "population": "1"
        }, timeout=60)
        data = resp.json()
        assert "total_strategies" in data
        assert "leaderboard" in data
