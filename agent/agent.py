"""Gemini tool-calling agent loop.

Automatic function calling is disabled on purpose: running the loop by hand lets us log every
tool call, cap the number of steps, cap SQL retries, and keep the SQL guard between the model
and the database.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .tools import TOOL_SPECS, SchemaTools

SYSTEM_PROMPT = """You are a senior marketing analyst agent working on a PostgreSQL warehouse of Meta Ads
campaign data and Shopify order data. Answer business questions using ONLY the tools.

Workflow:
1. Call search_schema with the user's question to find relevant tables.
2. Call get_schema for those tables. Only use tables and columns that get_schema returned.
   Use sample_values to match text filters exactly (values are lowercase, e.g. 'brand b', 'usa').
3. Write ONE read-only SELECT and call run_sql. If it returns an error, read it, fix the SQL and
   retry (at most 3 attempts in total).
4. Call explain_result, then answer.

SQL rules:
- dim_date.month is an INTEGER 1-12: convert month names to numbers (March = 3). Include the time
  columns (year, month) in the SELECT when you filter by time.
- Compute ratios from SUMs, never from the stored per-row ratio columns (fact_ads.ctr/cpm/cpc/roi
  are averages of ratios and wrong for aggregates). Guard every division with NULLIF or CASE:
    CTR  = SUM(clicks) / NULLIF(SUM(impressions), 0)
    CPC  = SUM(amount_spent) / NULLIF(SUM(clicks), 0)
    CPM  = SUM(amount_spent) / NULLIF(SUM(impressions), 0) * 1000
    ROAS = SUM(purchase_value) / NULLIF(SUM(amount_spent), 0)            -- revenue per rupee spent
    ROI  = (SUM(purchase_value) - SUM(amount_spent)) / NULLIF(SUM(amount_spent), 0)
  If a user says "ROI" use the ROI formula; mention ROAS when it helps. Treat NULL metrics as 0
  (COALESCE) and always GROUP BY the relevant dimension (campaign_name, geo_location_segment, ...).
- Ranking by a ratio: a ratio is undefined (NULL) when its denominator is 0, and in PostgreSQL
  ORDER BY ... DESC puts NULLs FIRST. So when ranking, exclude undefined ratios with
  HAVING SUM(clicks) > 0 (or the relevant denominator) and add NULLS LAST. A NULL is never the
  "worst" or "best" - for CPC the worst is the highest value among campaigns that had clicks.
  Ignore trivially small samples when it matters (e.g. HAVING SUM(amount_spent) > 1000) and say so.
- Shopify rows are pre-aggregated lines: use SUM(orders), never COUNT(*), for order counts.
- Never infer dates or facts from campaign names. Amounts are in INR.
- Prefer top-N results (LIMIT 5 or 10) for ranking questions and include spend, revenue and
  conversions so the answer is checkable.

Final answer format (plain text, no markdown tables):
1. Final Answer (one line)
2. Key Numbers (the important values, from the returned rows only)
3. Insight (what it means for the business)
4. Recommendation (what to do)
Then the final SQL in a ```sql block. If the data cannot answer the question, say so and say what
is missing. Never invent numbers."""


@dataclass
class AgentResult:
    answer: str
    sql: str | None
    trace: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0
    stopped_reason: str = "answered"
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"answer": self.answer, "sql": self.sql, "steps": self.steps,
                "stopped_reason": self.stopped_reason, "trace": self.trace,
                "columns": self.columns, "rows": self.rows, "truncated": self.truncated}


def _function_declarations():
    from google.genai import types
    return [types.FunctionDeclaration(name=s["name"], description=s["description"],
                                      parameters_json_schema=s["parameters"]) for s in TOOL_SPECS]


def _summarize(result: dict) -> str:
    if not result.get("ok", True):
        return result.get("error", "error")[:160]
    if "row_count" in result:
        return f"{result['row_count']} rows"
    if "tables" in result:
        t = result["tables"]
        return ", ".join(x["table"] for x in t) if isinstance(t, list) else ", ".join(t)
    return "ok"


def _extract_sql(text: str) -> str | None:
    m = re.search(r"```sql\s*(.+?)```", text or "", re.S | re.I)
    return m.group(1).strip() if m else None


class RateLimitedError(RuntimeError):
    """The model API kept returning 429 after retries (e.g. free-tier requests-per-minute quota)."""


def _retry_delay_s(exc: Exception, default: float = 12.0) -> float:
    """Gemini's 429 body says 'Please retry in 6.17s' / retryDelay '6s'; honour it (plus a margin)."""
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", str(exc))
    if not m:
        return default
    hours, minutes, seconds = (float(g or 0) for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds + 1.0


def generate_with_retry(client, *, retries: int = 5, max_wait_s: float = 65.0, **kwargs):
    """client.models.generate_content, riding out rate limits (429) and transient server errors."""
    for attempt in range(retries + 1):
        try:
            return client.models.generate_content(**kwargs)
        except Exception as e:  # google.genai.errors.APIError carries .code
            code = getattr(e, "code", None)
            quota = code == 429 or "RESOURCE_EXHAUSTED" in str(e)
            transient = code in (500, 502, 503, 504) or any(s in str(e) for s in ("UNAVAILABLE", "DEADLINE_EXCEEDED"))
            if not (quota or transient):
                raise
            delay = _retry_delay_s(e, default=12.0) if quota else min(2.0 * 2 ** attempt, 20.0)
            if quota and delay > max_wait_s:  # a long delay means a daily quota: do not wait
                raise RateLimitedError(
                    "The AI model's quota is used up (Gemini free tier). "
                    f"Retry in about {max(1, round(delay / 60))} min, or set GEMINI_MODEL to another model.") from e
            if attempt == retries:
                if quota:
                    raise RateLimitedError("The AI model's rate limit was hit. Please retry in a minute.") from e
                raise RateLimitedError("The AI model is temporarily unavailable. Please try again shortly.") from e
            time.sleep(delay)


class Text2SQLAgent:
    def __init__(self, tools: SchemaTools, client, model: str = "gemini-2.5-flash",
                 max_steps: int = 8, max_sql_attempts: int = 3):
        self.tools = tools
        self.client = client
        self.model = model
        self.max_steps = max_steps
        self.max_sql_attempts = max_sql_attempts

    @staticmethod
    def _result(tools: SchemaTools, answer: str, trace: list, steps: int,
                reason: str = "answered") -> AgentResult:
        last = tools.last_result or {}
        sql = last.get("sql") or _extract_sql(answer)
        return AgentResult(answer=answer, sql=sql, trace=trace, steps=steps, stopped_reason=reason,
                           columns=last.get("columns", []), rows=last.get("rows", []),
                           truncated=bool(last.get("truncated", False)))

    def ask(self, question: str) -> AgentResult:
        from google.genai import types

        tools = self.tools.fork()  # isolated session: safe under concurrent requests
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=_function_declarations())],
            temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents: list[Any] = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]
        trace: list[dict[str, Any]] = []
        sql_failures = 0

        for step in range(1, self.max_steps + 1):
            response = generate_with_retry(self.client, model=self.model, contents=contents, config=config)
            calls = response.function_calls or []
            if not calls:
                return self._result(tools, response.text or "", trace, step)

            contents.append(response.candidates[0].content)
            parts = []
            for call in calls:
                args = dict(call.args or {})
                t0 = time.perf_counter()
                result = tools.dispatch(call.name, args)
                ok = bool(result.get("ok", True))
                if call.name == "run_sql" and not ok:
                    sql_failures += 1
                trace.append({"step": step, "tool": call.name, "args": args, "ok": ok,
                              "summary": _summarize(result),
                              "ms": round((time.perf_counter() - t0) * 1000, 1)})
                parts.append(types.Part.from_function_response(name=call.name, response={"result": result}))
            contents.append(types.Content(role="user", parts=parts))

            if sql_failures >= self.max_sql_attempts:
                return self._result(
                    tools, f"I couldn't produce a working query after {self.max_sql_attempts} attempts. "
                    "Try rephrasing the question or narrowing it (a metric, a period, a region).",
                    trace, step, "sql_failed")

        return self._result(tools, "I couldn't finish within the step limit. Try a more specific question.",
                            trace, self.max_steps, "max_steps")


def build_agent(settings=None, tools: SchemaTools | None = None, client=None) -> Text2SQLAgent:
    from .config import Settings
    from .tools import build_tools
    settings = settings or Settings()
    if client is None:
        from google import genai
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        client = genai.Client(api_key=settings.gemini_api_key)
    tools = tools or build_tools(settings, genai_client=client)
    return Text2SQLAgent(tools, client, settings.model, settings.max_steps, settings.max_sql_attempts)


if __name__ == "__main__":  # python -m agent.agent "your question"
    import sys
    res = build_agent().ask(" ".join(sys.argv[1:]) or "Top 5 campaigns by ROI")
    for t in res.trace:
        print(f"  [{t['step']}] {t['tool']}({json.dumps(t['args'])[:80]}) -> {t['summary']}")
    print("\n" + res.answer)
