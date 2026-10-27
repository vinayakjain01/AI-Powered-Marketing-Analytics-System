import pytest

from agent.sql_guard import UnsafeSQLError, validate_read_only


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select campaign_id, SUM(amount_spent) FROM fact_ads GROUP BY 1",
    "WITH t AS (SELECT * FROM fact_ads) SELECT COUNT(*) FROM t",
    "SELECT a FROM x UNION ALL SELECT a FROM y",
    "SELECT * FROM fact_ads;",  # a trailing semicolon is still one statement
])
def test_allows_read_only_queries(sql):
    assert validate_read_only(sql)


@pytest.mark.parametrize("sql", [
    "INSERT INTO fact_ads VALUES (1)",
    "UPDATE fact_ads SET amount_spent = 0",
    "DELETE FROM fact_ads",
    "DROP TABLE fact_ads",
    "TRUNCATE fact_ads",
    "ALTER TABLE fact_ads ADD COLUMN x INT",
    "CREATE TABLE t (a INT)",
    "GRANT ALL ON fact_ads TO public",
    "SELECT * INTO new_table FROM fact_ads",
    "WITH d AS (DELETE FROM fact_ads RETURNING *) SELECT * FROM d",
    "COPY fact_ads TO '/tmp/x'",
])
def test_blocks_writes_and_ddl(sql):
    with pytest.raises(UnsafeSQLError):
        validate_read_only(sql)


@pytest.mark.parametrize("sql", ["SELECT pg_sleep(10)", "SELECT pg_read_file('/etc/passwd')"])
def test_blocks_dangerous_functions(sql):
    with pytest.raises(UnsafeSQLError, match="not allowed"):
        validate_read_only(sql)


def test_blocks_multiple_statements():
    with pytest.raises(UnsafeSQLError, match="exactly one"):
        validate_read_only("SELECT 1; DROP TABLE fact_ads")


@pytest.mark.parametrize("sql", ["", "   ", "SELEC nonsense FROM ((("])
def test_blocks_empty_and_unparseable(sql):
    with pytest.raises(UnsafeSQLError):
        validate_read_only(sql)


def test_adds_a_limit_of_cap_plus_one():
    # +1 so the caller can tell "exactly 200 rows" from "truncated".
    assert validate_read_only("SELECT * FROM t", max_rows=200).upper().endswith("LIMIT 201")


def test_lowers_an_oversized_limit_but_keeps_a_small_one():
    assert "LIMIT 201" in validate_read_only("SELECT * FROM t LIMIT 100000", max_rows=200).upper()
    assert "LIMIT 5" in validate_read_only("SELECT * FROM t LIMIT 5", max_rows=200).upper()


def test_limit_applies_to_unions():
    out = validate_read_only("SELECT a FROM x UNION SELECT a FROM y", max_rows=10).upper()
    assert "LIMIT 11" in out
