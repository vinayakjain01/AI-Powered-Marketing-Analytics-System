"""RAG over table and column descriptions.

Each table becomes one document: its business description, synonyms and every column's name,
type and description. The agent searches these documents with the user's question, so it only
reads the schema of the tables that matter (and managers' vocabulary like "GMV" or "budget"
lands on the right table via the synonyms in schema_docs.yaml).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import yaml


@dataclass
class TableDoc:
    table: str
    description: str
    text: str


class Embedder(Protocol):
    def fit(self, documents: list[str]) -> np.ndarray: ...
    def embed_query(self, query: str) -> np.ndarray: ...


def _l2_normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


class TfidfEmbedder:
    """Offline fallback: TF-IDF over word unigrams and bigrams (no API key, no network)."""

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self._vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")

    def fit(self, documents: list[str]) -> np.ndarray:
        return _l2_normalize(self._vec.fit_transform(documents).toarray())

    def embed_query(self, query: str) -> np.ndarray:
        return _l2_normalize(self._vec.transform([query]).toarray())[0]


class GeminiEmbedder:
    """Semantic embeddings from the Gemini API, using asymmetric document/query task types."""

    def __init__(self, client, model: str = "gemini-embedding-001", batch_size: int = 100):
        self.client = client
        self.model = model
        self.batch_size = batch_size

    def _embed(self, texts: list[str], task_type: str) -> np.ndarray:
        from google.genai import types
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            resp = self.client.models.embed_content(
                model=self.model, contents=texts[i:i + self.batch_size],
                config=types.EmbedContentConfig(task_type=task_type))
            vectors.extend(e.values for e in resp.embeddings)
        return _l2_normalize(np.array(vectors, dtype=np.float32))

    def fit(self, documents: list[str]) -> np.ndarray:
        return self._embed(documents, "RETRIEVAL_DOCUMENT")

    def embed_query(self, query: str) -> np.ndarray:
        return self._embed([query], "RETRIEVAL_QUERY")[0]


def load_schema_docs(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"tables": {}, "hidden": []}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    data.setdefault("tables", {})
    data.setdefault("hidden", [])
    return data


def _humanize(name: str) -> str:
    """'fact_ads.amount_spent' -> 'fact ads amount spent' so keywords match questions."""
    return re.sub(r"[_\.]+", " ", name)


def build_table_docs(introspected: dict[str, dict], docs: dict) -> list[TableDoc]:
    described = docs.get("tables", {})
    out: list[TableDoc] = []
    for table, meta in introspected.items():
        tdoc = described.get(table, {}) or {}
        tdesc = (tdoc.get("description") or "").strip()
        col_docs = tdoc.get("columns", {}) or {}
        synonyms = ", ".join(tdoc.get("synonyms", []) or [])
        lines = [f"Table {table} ({_humanize(table)}). {tdesc}"]
        if synonyms:
            lines.append(f"Also called: {synonyms}.")
        for col in meta["columns"]:
            cdesc = (col_docs.get(col["name"]) or "").strip()
            lines.append(f"- {col['name']} ({_humanize(col['name'])}, {col['type']}): {cdesc}")
        out.append(TableDoc(table=table, description=tdesc, text="\n".join(lines)))
    return out


class SchemaIndex:
    def __init__(self, table_docs: list[TableDoc], embedder: Embedder):
        if not table_docs:
            raise ValueError("No tables found to index.")
        self.docs = table_docs
        self.embedder = embedder
        self.matrix = embedder.fit([d.text for d in table_docs])

    def search(self, question: str, top_k: int = 3) -> list[dict]:
        """Cosine similarity (vectors are L2-normalised, so a dot product)."""
        scores = self.matrix @ self.embedder.embed_query(question)
        order = np.argsort(-scores)[: max(1, top_k)]
        return [{"table": self.docs[i].table, "score": round(float(scores[i]), 4),
                 "description": self.docs[i].description} for i in order]
