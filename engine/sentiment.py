"""
engine/sentiment.py
────────────────────────────────────────────────────────────────────────────
News sentiment analysis for Orallexa.

Primary:   FinBERT (ProsusAI/finBERT) — financial domain BERT, ~74% accuracy
Fallback:  VADER + financial lexicon
Fallback2: TextBlob
Fallback3: Simple keyword counting
"""

import re
from typing import List, Dict, Optional

# ── Sentiment backend selection ──────────────────────────────────────────

_SCORER_TYPE = "none"
_SCORER = None


def _init_finbert():
    """Try to load FinBERT (best for financial text)."""
    global _SCORER_TYPE, _SCORER
    try:
        from transformers import pipeline
        _SCORER = pipeline(
            "sentiment-analysis",
            model="ProsusAI/finBERT",
            tokenizer="ProsusAI/finBERT",
            device=-1,  # CPU (use 0 for GPU)
            top_k=None,
        )
        _SCORER_TYPE = "finbert"
        return True
    except Exception:
        return False


def _init_vader():
    """Fallback: VADER with financial lexicon."""
    global _SCORER_TYPE, _SCORER
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        new_words = {
            "bullish": 3.0, "bearish": -3.0, "surge": 2.5, "plunge": -2.5,
            "rally": 2.0, "crash": -3.0, "soar": 2.5, "tumble": -2.0,
            "beat": 1.5, "miss": -1.5, "record": 1.5, "downgrade": -2.0,
            "upgrade": 2.0, "buyout": 1.5, "layoff": -1.5, "recall": -1.5,
            "lawsuit": -1.5, "investigation": -1.5, "partnership": 1.5,
            "revenue": 0.5, "loss": -1.0, "profit": 1.0, "growth": 1.5,
            "decline": -1.0, "default": -2.5, "bankruptcy": -3.0,
        }
        analyzer.lexicon.update(new_words)
        _SCORER = analyzer
        _SCORER_TYPE = "vader"
        return True
    except ImportError:
        return False


def _init_textblob():
    """Fallback 2: TextBlob."""
    global _SCORER_TYPE, _SCORER
    try:
        from textblob import TextBlob
        _SCORER = TextBlob
        _SCORER_TYPE = "textblob"
        return True
    except ImportError:
        return False


# Initialize — try FinBERT first, then VADER, then TextBlob
if not _init_finbert():
    if not _init_vader():
        _init_textblob()


def get_scorer_type() -> str:
    """Return the active sentiment backend name."""
    return _SCORER_TYPE


# ── Core scoring ─────────────────────────────────────────────────────────

def score_text(text: str) -> Dict:
    """
    Score a single text string.
    Returns: {compound, label, positive, negative, neutral}
    compound: -1.0 (most negative) to +1.0 (most positive)
    label: 'positive' | 'neutral' | 'negative'
    """
    if not text or not text.strip():
        return {"compound": 0.0, "label": "neutral",
                "positive": 0.0, "negative": 0.0, "neutral": 1.0}

    clean = re.sub(r"https?://\S+", "", text)
    clean = re.sub(r"[^\w\s.,!?'-]", " ", clean).strip()
    if not clean:
        return {"compound": 0.0, "label": "neutral",
                "positive": 0.0, "negative": 0.0, "neutral": 1.0}

    if _SCORER_TYPE == "finbert":
        return _score_finbert(clean)
    elif _SCORER_TYPE == "vader":
        return _score_vader(clean)
    elif _SCORER_TYPE == "textblob":
        return _score_textblob(clean)
    else:
        return _score_keywords(clean)


def _score_finbert(text: str) -> Dict:
    """Score using FinBERT. Returns all 3 class probabilities."""
    try:
        # FinBERT returns: [{'label': 'positive', 'score': 0.85}, ...]
        results = _SCORER(text[:512])  # BERT max 512 tokens
        if isinstance(results, list) and results and isinstance(results[0], list):
            results = results[0]

        scores = {r["label"]: r["score"] for r in results}
        pos = scores.get("positive", 0.0)
        neg = scores.get("negative", 0.0)
        neu = scores.get("neutral", 0.0)

        # Map to compound score (-1 to +1)
        compound = pos - neg

        label = "positive" if compound >= 0.05 else ("negative" if compound <= -0.05 else "neutral")

        return {
            "compound": round(compound, 4),
            "label": label,
            "positive": round(pos, 4),
            "negative": round(neg, 4),
            "neutral": round(neu, 4),
        }
    except Exception:
        # Fallback to VADER if FinBERT fails on this text
        if _init_vader():
            return _score_vader(text)
        return {"compound": 0.0, "label": "neutral",
                "positive": 0.0, "negative": 0.0, "neutral": 1.0}


def _score_vader(text: str) -> Dict:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    # Use module-level scorer if it's VADER, otherwise create temp one
    scorer = _SCORER if _SCORER_TYPE == "vader" else SentimentIntensityAnalyzer()
    scores = scorer.polarity_scores(text)
    compound = scores["compound"]
    label = "positive" if compound >= 0.05 else ("negative" if compound <= -0.05 else "neutral")
    return {
        "compound": round(compound, 4),
        "label": label,
        "positive": round(scores["pos"], 4),
        "negative": round(scores["neg"], 4),
        "neutral": round(scores["neu"], 4),
    }


def _score_textblob(text: str) -> Dict:
    from textblob import TextBlob
    blob = TextBlob(text)
    compound = float(blob.sentiment.polarity)
    label = "positive" if compound >= 0.05 else ("negative" if compound <= -0.05 else "neutral")
    return {
        "compound": round(compound, 4),
        "label": label,
        "positive": max(compound, 0.0),
        "negative": max(-compound, 0.0),
        "neutral": 1.0 - abs(compound),
    }


def _score_keywords(text: str) -> Dict:
    text_lower = text.lower()
    pos_words = ["beat", "surge", "rally", "growth", "profit", "upgrade",
                 "record", "bullish", "soar", "strong", "partnership"]
    neg_words = ["miss", "crash", "decline", "loss", "downgrade", "bearish",
                 "tumble", "weak", "lawsuit", "bankruptcy", "layoff"]
    pos = sum(1 for w in pos_words if w in text_lower)
    neg = sum(1 for w in neg_words if w in text_lower)
    total = max(pos + neg, 1)
    compound = (pos - neg) / total
    label = "positive" if compound > 0.1 else ("negative" if compound < -0.1 else "neutral")
    return {"compound": round(compound, 3), "label": label,
            "positive": pos / total, "negative": neg / total, "neutral": 0.0}


# ── Batch & aggregation (unchanged interface) ────────────────────────────

def score_news_items(news_items: List[Dict]) -> List[Dict]:
    """Score a list of news items. Adds sentiment fields to each."""
    scored = []
    for item in news_items:
        text = f"{item.get('title', '')} {item.get('summary', '')}".strip()
        sentiment = score_text(text)
        enriched = {**item, **sentiment}
        scored.append(enriched)
    return scored


def aggregate_sentiment(scored_items: List[Dict]) -> Dict:
    """Aggregate sentiment across multiple news items."""
    if not scored_items:
        return {
            "avg_compound": 0.0, "sentiment_label": "neutral",
            "n_positive": 0, "n_negative": 0, "n_neutral": 0,
            "sentiment_score": 0.0, "signal": "neutral",
        }

    compounds = [item.get("compound", 0.0) for item in scored_items]
    avg = sum(compounds) / len(compounds)

    n_pos = sum(1 for item in scored_items if item.get("label") == "positive")
    n_neg = sum(1 for item in scored_items if item.get("label") == "negative")
    n_neu = sum(1 for item in scored_items if item.get("label") == "neutral")

    label = "positive" if avg >= 0.05 else ("negative" if avg <= -0.05 else "neutral")
    signal = "bullish" if avg > 0.15 else ("bearish" if avg < -0.15 else "neutral")

    return {
        "avg_compound": round(avg, 4),
        "sentiment_label": label,
        "n_positive": n_pos,
        "n_negative": n_neg,
        "n_neutral": n_neu,
        "total_items": len(scored_items),
        "sentiment_score": round(avg, 4),
        "signal": signal,
        "scorer": _SCORER_TYPE,
        "summary": f"{n_pos} positive, {n_neg} negative, {n_neu} neutral out of {len(scored_items)} news items. (via {_SCORER_TYPE})",
    }


def analyze_ticker_sentiment(ticker: str, rag_store=None, news_skill=None, limit: int = 10) -> Dict:
    """One-call: fetch news → score → aggregate → return signal."""
    items = []

    if rag_store is not None:
        try:
            docs = rag_store.list_documents(ticker=ticker)
            items = [{"title": d.get("title", ""), "summary": d.get("text", "")} for d in docs[:limit]]
        except Exception:
            pass

    if not items and news_skill is not None:
        try:
            items = news_skill.fetch_news(limit=limit)
        except Exception:
            pass

    if not items:
        return {
            "ticker": ticker, "error": "No news found",
            "avg_compound": 0.0, "sentiment_label": "neutral",
            "signal": "neutral", "scored_items": [],
        }

    scored = score_news_items(items)
    agg = aggregate_sentiment(scored)
    return {"ticker": ticker, "error": None, "scored_items": scored, **agg}
