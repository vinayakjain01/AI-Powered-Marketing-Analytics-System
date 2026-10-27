"""REST API for the frontend: dashboard data, schema browser, and the AI agent.

    uvicorn api.main:app --reload        (dev)   |   serves frontend/dist at / when it exists
Everything under /api. The agent and the dashboard share one read-only Database.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.agent import RateLimitedError, Text2SQLAgent, build_agent
from agent.config import Settings
from agent.tools import SchemaTools, build_tools

from . import queries as q

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


# --------------------------------------------------------------------------- dependencies
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def get_tools() -> SchemaTools:
    """Schema tools (DB + RAG index). Works without a Gemini key (offline TF-IDF embeddings)."""
    return build_tools(get_settings())


@lru_cache(maxsize=1)
def get_agent() -> Text2SQLAgent:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="The AI agent is disabled: GEMINI_API_KEY is not set on the server.")
    return build_agent(settings, tools=get_tools())


class RateLimiter:
    """Tiny in-memory sliding window per client IP. Protects the Gemini quota on a public demo."""

    def __init__(self, limit: int = 20, window_s: int = 60):
        self.limit, self.window_s = limit, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self.lock:
            dq = self.hits[key]
            while dq and now - dq[0] > self.window_s:
                dq.popleft()
            if len(dq) >= self.limit:
                raise HTTPException(status_code=429, detail="Too many questions. Please wait a minute.")
            dq.append(now)


ask_limiter = RateLimiter(limit=int(os.getenv("ASK_RATE_LIMIT", "20")))


# --------------------------------------------------------------------------- models
class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class AskResponse(BaseModel):
    answer: str
    sql: str | None
    steps: int
    stopped_reason: str
    trace: list[dict]
    columns: list[str] = []
    rows: list[list[Any]] = []
    truncated: bool = False


class DashFilters:
    """Query-string filters shared by every dashboard endpoint."""

    def __init__(self, brand: str | None = None, region: str | None = None,
                 start: dt.date | None = None, end: dt.date | None = None):
        self.f = q.Filters(brand=brand or None, region=region or None, start=start, end=end)


def _rows(tools: SchemaTools, sql_params: tuple[str, dict]) -> list[dict]:
    sql, params = sql_params
    cols, rows = tools.db.run_read_only(sql, tools.settings.query_timeout_ms, params)
    return [dict(zip(cols, r)) for r in rows]


# --------------------------------------------------------------------------- app
app = FastAPI(title="Marketing Analytics API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    allow_methods=["GET", "POST"], allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "agent_enabled": bool(s.gemini_api_key), "embeddings": s.embedding_backend,
            "model": s.model}


@app.get("/api/tables")
def tables(tools: SchemaTools = Depends(get_tools)) -> dict:
    """Every agent-visible table with its business description and column docs."""
    docs = tools.docs.get("tables", {})
    out = []
    for name, meta in tools.schema.items():
        d = docs.get(name, {}) or {}
        cols = d.get("columns", {}) or {}
        out.append({"name": name, "description": " ".join((d.get("description") or "").split()),
                    "synonyms": d.get("synonyms", []), "primary_key": meta["primary_key"],
                    "foreign_keys": meta["foreign_keys"],
                    "columns": [{"name": c["name"], "type": c["type"], "description": cols.get(c["name"], "")}
                                for c in meta["columns"]]})
    return {"tables": out}


@app.get("/api/search")
def search(q: str = Query(min_length=2, max_length=300), top_k: int = Query(3, ge=1, le=10),
           tools: SchemaTools = Depends(get_tools)) -> dict:
    """The agent's first step on its own: which tables does RAG pick for this question?"""
    return tools.search_schema(q, top_k)


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request, agent: Text2SQLAgent = Depends(get_agent)) -> AskResponse:
    ask_limiter.check(request.client.host if request.client else "unknown")
    try:
        return AskResponse(**agent.ask(req.question).to_dict())
    except HTTPException:
        raise
    except RateLimitedError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except Exception as e:  # upstream (Gemini) or DB failure: surface a clean 502
        raise HTTPException(status_code=502, detail=f"Agent failed: {type(e).__name__}: {e}") from e


@app.get("/api/filters")
def filters(tools: SchemaTools = Depends(get_tools)) -> dict:
    run = tools.db.run_read_only
    lo, hi = run(q.FILTER_QUERIES["dates"])[1][0]
    return {"brands": [r[0] for r in run(q.FILTER_QUERIES["brands"])[1]],
            "regions": [r[0] for r in run(q.FILTER_QUERIES["regions"])[1]],
            "date_min": lo, "date_max": hi}


@app.get("/api/kpis")
def kpis(df: DashFilters = Depends(), tools: SchemaTools = Depends(get_tools)) -> dict:
    return {"ads": _rows(tools, q.ads_kpis(df.f))[0], "store": _rows(tools, q.store_kpis(df.f))[0]}


@app.get("/api/trend")
def trend(grain: Literal["day", "week", "month"] = "week", df: DashFilters = Depends(),
          tools: SchemaTools = Depends(get_tools)) -> dict:
    return {"ads": _rows(tools, q.ads_trend(df.f, grain)), "store": _rows(tools, q.store_trend(df.f, grain))}


@app.get("/api/breakdown")
def breakdown(by: Literal["brand", "region", "country", "status", "funnel_stage", "ad_set", "weekday"] = "region",
              df: DashFilters = Depends(), tools: SchemaTools = Depends(get_tools)) -> dict:
    return {"by": by, "rows": _rows(tools, q.ads_breakdown(df.f, by))}


@app.get("/api/store/breakdown")
def store_breakdown(by: Literal["channel", "country", "region", "brand", "customer_type", "product_type"] = "channel",
                    df: DashFilters = Depends(), tools: SchemaTools = Depends(get_tools)) -> dict:
    return {"by": by, "rows": _rows(tools, q.store_breakdown(df.f, by))}


@app.get("/api/campaigns")
def campaigns(metric: Literal["spend", "revenue", "roas", "roi", "cpc", "purchases", "ctr"] = "roas",
              order: Literal["desc", "asc"] = "desc", limit: int = Query(10, ge=1, le=50),
              min_spend: float = Query(1000, ge=0), df: DashFilters = Depends(),
              tools: SchemaTools = Depends(get_tools)) -> dict:
    return {"metric": metric, "order": order, "min_spend": min_spend,
            "rows": _rows(tools, q.top_campaigns(df.f, metric, order == "desc", limit, min_spend))}


# --------------------------------------------------------------------------- frontend (production)
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """Serve the built React app; unknown paths fall back to index.html (client-side routing)."""
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        target = (FRONTEND_DIST / path).resolve()
        if path and target.is_file() and FRONTEND_DIST in target.parents:
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
