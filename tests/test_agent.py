import json

from agent.agent import Text2SQLAgent
from tests.fake_gemini import FakeGemini, call, text

GOOD_SQL = ("SELECT c.brand, SUM(f.amount_spent) AS spend FROM fact_ads f "
            "JOIN dim_campaign c ON c.campaign_id = f.campaign_id GROUP BY c.brand")
ANSWER = "1. Final Answer\nbrand b spent more.\n```sql\n" + GOOD_SQL + "\n```"


def make(tools, script, **kw):
    client = FakeGemini(script)
    return Text2SQLAgent(tools, client, "fake-model", **kw), client


def test_full_loop_with_self_correction(tools):
    agent, client = make(tools, [
        call("search_schema", question="spend by brand"),
        call("get_schema", tables=["fact_ads", "dim_campaign"]),
        call("run_sql", sql="SELECT brand, SUM(spend) FROM fact_ads GROUP BY brand"),  # wrong: no such columns
        call("run_sql", sql=GOOD_SQL),                                                  # corrected
        call("explain_result"),
        text(ANSWER),
    ])
    res = agent.ask("How much did each brand spend?")

    assert [t["tool"] for t in res.trace] == ["search_schema", "get_schema", "run_sql", "run_sql", "explain_result"]
    assert [t["ok"] for t in res.trace] == [True, True, False, True, True]
    assert all({"step", "tool", "args", "ok", "summary", "ms"} <= set(t) for t in res.trace)
    assert res.stopped_reason == "answered" and res.steps == 6
    assert res.columns == ["brand", "spend"] and len(res.rows) == 2  # data for the UI table
    assert "SUM(f.amount_spent)" in res.sql
    assert "brand b spent more" in res.answer
    # The DB error was fed back to the model as a function response, which is what enables the fix.
    fed_back = json.dumps([str(c) for c in client.models.requests[3]])
    assert "Database error" in fed_back


def test_step_limit_stops_the_loop(tools):
    agent, _ = make(tools, [call("get_schema", tables=["fact_ads"])] * 5, max_steps=3)
    res = agent.ask("loop forever")
    assert res.stopped_reason == "max_steps" and res.steps == 3 and len(res.trace) == 3
    assert "step limit" in res.answer


def test_gives_up_after_three_failed_sql_attempts(tools):
    agent, _ = make(tools, [call("run_sql", sql="SELECT nope FROM fact_ads")] * 5, max_sql_attempts=3, max_steps=8)
    res = agent.ask("break it")
    assert res.stopped_reason == "sql_failed" and sum(not t["ok"] for t in res.trace) == 3


def test_blocked_sql_counts_as_a_failure_and_never_touches_data(tools):
    agent, _ = make(tools, [call("run_sql", sql="DELETE FROM fact_ads"), text("I cannot do that.")])
    res = agent.ask("delete everything")
    assert res.trace[0]["ok"] is False and "guard" in res.trace[0]["summary"].lower()
    assert tools.run_sql("SELECT COUNT(*) FROM fact_ads")["rows"][0][0] > 0


def test_answer_without_tools_still_returns(tools):
    agent, _ = make(tools, [text("Hello!")])
    res = agent.ask("hi there")
    assert res.answer == "Hello!" and res.trace == [] and res.sql is None


def test_concurrent_asks_do_not_share_results(tools):
    a1, _ = make(tools, [call("run_sql", sql="SELECT 1 AS one"), text("a")])
    a2, _ = make(tools, [call("run_sql", sql="SELECT 2 AS two"), text("b")])
    assert a1.ask("q1").columns == ["one"] and a2.ask("q2").columns == ["two"]
    assert tools.last_result is None


def test_rate_limit_429_is_waited_out_not_fatal(tools, monkeypatch):
    import agent.agent as agent_mod

    class Quota(Exception):
        code = 429
    client = FakeGemini([text("done")])
    real, state = client.models.generate_content, {"n": 0}

    def flaky(**kw):
        state["n"] += 1
        if state["n"] <= 2:
            raise Quota("429 RESOURCE_EXHAUSTED. Please retry in 0.5s.")
        return real(**kw)
    client.models.generate_content = flaky
    monkeypatch.setattr(agent_mod.time, "sleep", lambda s: None)
    res = Text2SQLAgent(tools, client, "fake").ask("hello there")
    assert res.answer == "done" and state["n"] == 3


def test_persistent_rate_limit_raises_a_clear_error(tools, monkeypatch):
    import pytest
    import agent.agent as agent_mod

    class Quota(Exception):
        code = 429
    client = FakeGemini([])
    client.models.generate_content = lambda **kw: (_ for _ in ()).throw(Quota("RESOURCE_EXHAUSTED"))
    monkeypatch.setattr(agent_mod.time, "sleep", lambda s: None)
    with pytest.raises(agent_mod.RateLimitedError):
        Text2SQLAgent(tools, client, "fake").ask("hello there")


def test_transient_503_is_retried(tools, monkeypatch):
    import agent.agent as agent_mod

    class Unavailable(Exception):
        code = 503
    client = FakeGemini([text("recovered")])
    real, state = client.models.generate_content, {"n": 0}

    def flaky(**kw):
        state["n"] += 1
        if state["n"] == 1:
            raise Unavailable("503 UNAVAILABLE")
        return real(**kw)
    client.models.generate_content = flaky
    monkeypatch.setattr(agent_mod.time, "sleep", lambda s: None)
    assert Text2SQLAgent(tools, client, "fake").ask("hello there").answer == "recovered"
