from agent.tools import TOOL_SPECS


def test_tool_specs_declare_the_four_tools():
    assert [t["name"] for t in TOOL_SPECS] == ["search_schema", "get_schema", "run_sql", "explain_result"]


def test_staging_and_views_are_hidden(tools):
    assert not any(t.startswith("staging_") for t in tools.schema)
    assert {"fact_ads", "dim_campaign", "dim_date", "fact_order_lines", "dim_product"} <= set(tools.schema)


def test_get_schema_returns_columns_descriptions_keys_and_samples(tools):
    out = tools.get_schema(["dim_campaign", "fact_ads"])
    cols = {c["name"]: c for c in out["tables"]["dim_campaign"]["columns"]}
    assert "brand a" in cols["brand"]["sample_values"]
    assert cols["brand"]["description"]  # from schema_docs.yaml
    assert out["tables"]["fact_ads"]["foreign_keys"]
    assert "DO NOT USE" in {c["name"]: c for c in out["tables"]["fact_ads"]["columns"]}["ctr"]["description"]


def test_get_schema_unknown_and_hidden_tables(tools):
    out = tools.get_schema(["nope", "staging_ads"])
    assert out["tables"] == {} and out["unknown_tables"] == ["nope", "staging_ads"]
    assert "fact_ads" in out["available_tables"]


def test_run_sql_returns_rows(tools):
    r = tools.run_sql("SELECT month, COUNT(*) AS n FROM dim_date GROUP BY month ORDER BY month")
    assert r["ok"] and r["columns"] == ["month", "n"] and r["rows"][0][0] == 1
    assert tools.last_sql == r["sql"]


def test_run_sql_errors_are_returned_not_raised(tools):
    bad_column = tools.run_sql("SELECT no_such_column FROM fact_ads")
    assert bad_column["ok"] is False and "Database error" in bad_column["error"]
    blocked = tools.run_sql("DELETE FROM fact_ads")
    assert blocked["ok"] is False and "SQL guard" in blocked["error"]


def test_blocked_write_leaves_data_intact(tools):
    before = tools.run_sql("SELECT COUNT(*) FROM fact_ads")["rows"][0][0]
    tools.run_sql("DELETE FROM fact_ads")
    assert tools.run_sql("SELECT COUNT(*) FROM fact_ads")["rows"][0][0] == before


def test_database_layer_blocks_writes_even_if_the_guard_is_bypassed(tools):
    """Second safety layer: the read-only transaction/PRAGMA, independent of sqlglot."""
    import pytest
    with pytest.raises(Exception):
        tools.db.run_read_only("DELETE FROM fact_ads")
    assert tools.run_sql("SELECT COUNT(*) FROM fact_ads")["rows"][0][0] > 0


def test_run_sql_truncates_and_flags(tools):  # fixture caps at 20 rows, preview 5
    r = tools.run_sql("SELECT date_id FROM dim_date")
    assert r["ok"] and r["truncated"] is True and r["row_count"] == 20 and r["rows_shown"] == 5
    assert len(tools.last_result["rows"]) == 20


def test_explain_result_profiles_numeric_and_text_columns(tools):
    assert tools.explain_result()["ok"] is False  # nothing run yet
    tools.run_sql("SELECT brand, SUM(amount_spent) AS spend FROM fact_ads f "
                  "JOIN dim_campaign c USING (campaign_id) GROUP BY brand")
    prof = tools.explain_result()
    by = {c["column"]: c for c in prof["columns"]}
    assert prof["row_count"] == 2
    assert by["spend"]["kind"] == "numeric" and by["spend"]["sum"] > by["spend"]["min"] > 0
    assert by["brand"]["kind"] == "categorical" and by["brand"]["distinct"] == 2


def test_dispatch_unknown_tool_and_bad_args(tools):
    assert tools.dispatch("drop_everything", {})["ok"] is False
    assert tools.dispatch("run_sql", {"query": "x"})["ok"] is False


def test_fork_isolates_results_between_sessions(tools):
    a, b = tools.fork(), tools.fork()
    a.run_sql("SELECT 1 AS a")
    b.run_sql("SELECT 2 AS b")
    assert a.last_result["columns"] == ["a"] and b.last_result["columns"] == ["b"]
    assert tools.last_result is None
