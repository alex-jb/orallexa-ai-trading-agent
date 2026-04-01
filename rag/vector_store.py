import os
import json
from typing import List, Dict, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class LocalRAGStore:
    def __init__(self, storage_path: str = "rag_data/market_notes.json"):
        self.storage_path = storage_path
        self.documents: List[Dict] = []
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.matrix = None

        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self.documents = json.load(f)
        else:
            self.documents = []

        self._rebuild_index()

    def _save(self):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, indent=2, ensure_ascii=False)

    def _rebuild_index(self):
        if not self.documents:
            self.matrix = None
            return

        corpus = [doc["text"] for doc in self.documents]
        self.matrix = self.vectorizer.fit_transform(corpus)

    def add_document(self, ticker: str, title: str, text: str, source: str = "manual"):
        text = (text or "").strip()
        if not text:
            return

        self.documents.append({
            "ticker": ticker.strip().upper(),
            "title": title.strip() if title else "Untitled",
            "text": text,
            "source": source
        })
        self._save()
        self._rebuild_index()

    def add_news_documents(self, ticker: str, news_items: List[Dict]):
        ticker = ticker.strip().upper()
        existing_titles = {
            (doc.get("ticker", ""), doc.get("title", ""))
            for doc in self.documents
        }

        added = 0

        for item in news_items:
            title = item.get("title", "Untitled")
            summary = item.get("summary", "")
            publisher = item.get("publisher", "")
            published = item.get("published", "")
            link = item.get("link", "")

            key = (ticker, title)
            if key in existing_titles:
                continue

            text = f"""
Title: {title}
Publisher: {publisher}
Published: {published}
Summary: {summary}
Link: {link}
""".strip()

            self.documents.append({
                "ticker": ticker,
                "title": title,
                "text": text,
                "source": "news"
            })
            added += 1

        if added > 0:
            self._save()
            self._rebuild_index()

        return added

    def list_documents(self, ticker: str = None) -> List[Dict]:
        if not ticker:
            return self.documents
        ticker = ticker.strip().upper()
        return [doc for doc in self.documents if doc["ticker"] == ticker]

    def retrieve(self, query: str, ticker: str = None, top_k: int = 3) -> List[Tuple[Dict, float]]:
        if not self.documents:
            return []

        filtered_docs = self.documents

        if ticker:
            ticker = ticker.strip().upper()
            filtered_docs = [doc for doc in self.documents if doc["ticker"] == ticker]

        if not filtered_docs:
            return []

        corpus = [doc["text"] for doc in filtered_docs]
        temp_vectorizer = TfidfVectorizer(stop_words="english")
        temp_matrix = temp_vectorizer.fit_transform(corpus)
        query_vec = temp_vectorizer.transform([query])

        scores = cosine_similarity(query_vec, temp_matrix).flatten()
        ranked = sorted(
            zip(filtered_docs, scores),
            key=lambda x: x[1],
            reverse=True
        )

        return ranked[:top_k]