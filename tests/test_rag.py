from pathlib import Path

import pytest
import yaml

from scripts.eval_retrieval import evaluate

QUESTIONS = yaml.safe_load((Path(__file__).resolve().parents[1] / "eval_questions.yaml").read_text(encoding="utf-8"))["questions"]


@pytest.mark.parametrize("question, expected_top", [
    ("Which campaign had the worst CPC in March?", "fact_ads"),
    ("Top 5 campaigns by ROI", "fact_ads"),
    ("Which sales channel brings the most store revenue?", "fact_order_lines"),
    ("How many returning customers ordered?", "fact_order_lines"),
])
def test_top_table_for_representative_questions(tools, question, expected_top):
    assert tools.search_schema(question, top_k=3)["tables"][0]["table"] == expected_top


def test_questions_naming_two_concepts_surface_both_tables(tools):
    tables = [h["table"] for h in tools.search_schema("net sales by product type", top_k=2)["tables"]]
    assert set(tables) == {"fact_order_lines", "dim_product"}


def test_synonyms_route_manager_vocabulary(tools):
    # "GMV" never appears in a column name; only the docs' synonyms connect it to the store table.
    assert tools.search_schema("what is our GMV", top_k=1)["tables"][0]["table"] == "fact_order_lines"


def test_search_respects_top_k_and_sorts_by_score(tools):
    hits = tools.search_schema("ad spend", top_k=2)["tables"]
    assert len(hits) == 2 and hits[0]["score"] >= hits[1]["score"]


def test_recall_at_3_meets_threshold_on_eval_set(tools):
    recall, _full, rows = evaluate(tools.index, QUESTIONS, k=3)
    misses = [r["q"] for r in rows if r["recall"] < 1.0]
    assert len(QUESTIONS) >= 19
    assert recall >= 0.85, f"recall@3={recall:.3f}; misses: {misses}"
