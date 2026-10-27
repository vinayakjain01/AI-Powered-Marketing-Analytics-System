import json

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from agent.agent import Text2SQLAgent
from agent.mcp_server import create_server
from api import main as api_main
from tests.fake_gemini import FakeGemini, call, text


# ------------------------------------------------------------------ MCP
def run_mcp(tools, fn):
    async def go():
        async with Client(create_server(tools)) as client:
            return await fn(client)
    return anyio.run(go)


def payload(result):
    return json.loads(result.content[0].text)


def test_mcp_lists_the_four_tools(tools):
    names = run_mcp(tools, lambda c: _names(c))
    assert sorted(names) == ["explain_result", "get_schema", "run_sql", "search_schema"]


async def _names(client):
    return [t.name for t in (await client.list_tools()).tools]


def test_mcp_call_tool_runs_sql_and_blocks_writes(tools):
    async def scenario(client):
        ok = payload(await client.call_tool("run_sql", {"sql": "SELECT COUNT(*) AS n FROM fact_ads"}))
        bad = payload(await client.call_tool("run_sql", {"sql": "DROP TABLE fact_ads"}))
        found = payload(await client.call_tool("search_schema", {"question": "ad spend"}))
        return ok, bad, found

    ok, bad, found = run_mcp(tools, scenario)
    assert ok["ok"] and ok["rows"][0][0] > 0
    assert bad["ok"] is False and "guard" in bad["error"]
    assert found["tables"][0]["table"] == "fact_ads"


# ------------------------------------------------------------------ API
@pytest.fixture
def client(tools):
    agent = Text2SQLAgent(tools, FakeGemini([
        call("run_sql", sql="SELECT 1 AS one"), text("Answer text\n```sql\nSELECT 1\n```"),
    ]), "fake")
    api_main.app.dependency_overrides[api_main.get_tools] = lambda: tools
    api_main.app.dependency_overrides[api_main.get_agent] = lambda: agent
    api_main.ask_limiter.hits.clear()
    yield TestClient(api_main.app)
    api_main.app.dependency_overrides.clear()


def test_health_and_tables(client):
    assert client.get("/api/health").json()["status"] == "ok"
    names = [t["name"] for t in client.get("/api/tables").json()["tables"]]
    assert "fact_ads" in names and not any(n.startswith("staging") for n in names)
    fact = next(t for t in client.get("/api/tables").json()["tables"] if t["name"] == "fact_ads")
    assert any(c["name"] == "purchase_value" and c["description"] for c in fact["columns"])


def test_ask_returns_answer_sql_trace_and_rows(client):
    r = client.post("/api/ask", json={"question": "anything at all"})
    body = r.json()
    assert r.status_code == 200
    assert body["answer"].startswith("Answer text") and body["sql"]
    assert body["trace"][0]["tool"] == "run_sql" and body["rows"] == [[1]]


def test_ask_validates_input(client):
    assert client.post("/api/ask", json={"question": "x"}).status_code == 422
    assert client.post("/api/ask", json={}).status_code == 422


def test_ask_is_rate_limited(client):
    api_main.ask_limiter.limit = 1
    try:
        client.post("/api/ask", json={"question": "first question"})
        assert client.post("/api/ask", json={"question": "second question"}).status_code == 429
    finally:
        api_main.ask_limiter.limit = 20


def test_search_endpoint(client):
    r = client.get("/api/search", params={"q": "store net sales"})
    assert r.json()["tables"][0]["table"] == "fact_order_lines"


def test_dashboard_kpis_reconcile_with_raw_sums(client, tools):
    kpis = client.get("/api/kpis").json()["ads"]
    spend, revenue, clicks, imps = tools.db.run_read_only(
        "SELECT SUM(amount_spent), SUM(purchase_value), SUM(clicks), SUM(impressions) FROM fact_ads")[1][0]
    assert kpis["spend"] == pytest.approx(spend) and kpis["revenue"] == pytest.approx(revenue)
    assert kpis["roas"] == pytest.approx(revenue / spend)  # ratios come from SUMs
    assert kpis["ctr"] == pytest.approx(clicks / imps) and kpis["cpc"] == pytest.approx(spend / clicks)


def test_dashboard_filters_and_breakdowns(client):
    all_spend = client.get("/api/kpis").json()["ads"]["spend"]
    one = client.get("/api/kpis", params={"brand": "brand a"}).json()["ads"]["spend"]
    assert 0 < one < all_spend
    feb = client.get("/api/kpis", params={"start": "2026-02-01", "end": "2026-02-28"}).json()["ads"]["spend"]
    assert 0 < feb < all_spend
    rows = client.get("/api/breakdown", params={"by": "region"}).json()["rows"]
    assert sum(r["spend"] for r in rows) == pytest.approx(all_spend)
    assert client.get("/api/trend", params={"grain": "month"}).json()["ads"][0]["period"] == "2026-1"
    assert client.get("/api/store/breakdown", params={"by": "product_type"}).json()["rows"]
    top = client.get("/api/campaigns", params={"metric": "roas", "min_spend": 0}).json()["rows"]
    assert [r["roas"] for r in top] == sorted((r["roas"] for r in top), reverse=True)


def test_dashboard_rejects_unlisted_dimensions(client):
    # Dimensions are whitelisted, so SQL fragments can never reach the query.
    assert client.get("/api/breakdown", params={"by": "brand; DROP TABLE fact_ads"}).status_code == 422
    assert client.get("/api/campaigns", params={"metric": "spend DESC; --"}).status_code == 422


def test_agent_disabled_without_key(tools, settings, monkeypatch):
    monkeypatch.setattr(api_main, "get_settings", lambda: settings)  # keyless, whatever the dev's .env says
    api_main.get_agent.cache_clear()
    api_main.app.dependency_overrides[api_main.get_tools] = lambda: tools
    try:
        assert TestClient(api_main.app).post("/api/ask", json={"question": "hello there"}).status_code == 503
    finally:
        api_main.app.dependency_overrides.clear()
