"""Measure how often search_schema returns the tables a question needs (recall@k).

    python scripts/eval_retrieval.py                  # uses DATABASE_URL + schema_docs.yaml
    python scripts/eval_retrieval.py --demo           # offline: SQLite demo DB, no Postgres/key
    python scripts/eval_retrieval.py --k 3 --min-recall 0.8   # exits 1 below the threshold (CI)
Backend follows EMBEDDINGS / GEMINI_API_KEY (tfidf offline, gemini with a key).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from agent.config import Settings  # noqa: E402
from agent.db import Database  # noqa: E402
from agent.schema_rag import SchemaIndex, TfidfEmbedder, build_table_docs, load_schema_docs  # noqa: E402
from agent.tools import visible_schema  # noqa: E402


def evaluate(index: SchemaIndex, questions: list[dict], k: int) -> tuple[float, float, list[dict]]:
    rows, recalls = [], []
    for item in questions:
        got = [r["table"] for r in index.search(item["q"], top_k=k)]
        expected = set(item["expected"])
        recall = len(expected & set(got)) / len(expected)
        recalls.append(recall)
        rows.append({"q": item["q"], "expected": sorted(expected), "got": got, "recall": recall})
    full = sum(r == 1.0 for r in recalls) / len(recalls)
    return sum(recalls) / len(recalls), full, rows


def build_index(settings: Settings, demo: bool) -> tuple[SchemaIndex, str]:
    if demo:
        from seed_demo_db import build_sqlite_demo
        db = Database(engine=build_sqlite_demo())
    else:
        db = Database(settings.database_url, schema=settings.db_schema)
    docs = load_schema_docs(settings.schema_docs_path)
    docs_for_index = build_table_docs(visible_schema(db, docs), docs)
    backend = settings.embedding_backend
    if backend == "gemini":
        from google import genai
        from agent.schema_rag import GeminiEmbedder
        embedder = GeminiEmbedder(genai.Client(api_key=settings.gemini_api_key), settings.embed_model)
    else:
        embedder = TfidfEmbedder()
    return SchemaIndex(docs_for_index, embedder), backend


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--demo", action="store_true", help="Use the SQLite demo DB instead of DATABASE_URL.")
    ap.add_argument("--min-recall", type=float, default=0.0)
    ap.add_argument("--questions", default=str(ROOT / "eval_questions.yaml"))
    args = ap.parse_args()

    questions = yaml.safe_load(Path(args.questions).read_text(encoding="utf-8"))["questions"]
    index, backend = build_index(Settings(), args.demo)
    recall, full, rows = evaluate(index, questions, args.k)

    for r in rows:
        mark = "ok " if r["recall"] == 1.0 else "MISS"
        print(f"[{mark}] {r['q']}\n       expected={r['expected']} got={r['got']}")
    print(f"\nbackend={backend}  questions={len(rows)}  recall@{args.k}={recall:.3f}  "
          f"all-expected-tables-found={full:.3f}")
    return 1 if recall < args.min_recall else 0


if __name__ == "__main__":
    sys.exit(main())
