"""The four agent tools. Plain Python, so Gemini, the REST API and the MCP server share them."""
from __future__ import annotations

import time
from statistics import mean
from typing import Any

from .config import Settings
from .db import Database
from .schema_rag import SchemaIndex, build_table_docs, load_schema_docs
from .sql_guard import UnsafeSQLError, validate_read_only

# JSON-schema declarations sent to Gemini for function calling.
TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "search_schema",
     "description": "Semantic search over table and column descriptions. Call this FIRST with the "
                    "user's question to find which tables are relevant.",
     "parameters": {"type": "object", "properties": {
         "question": {"type": "string", "description": "The user's question, verbatim."},
         "top_k": {"type": "integer", "description": "How many tables to return (default 3)."}},
         "required": ["question"]}},
    {"name": "get_schema",
     "description": "Get columns, types, keys, descriptions and sample values for specific tables. "
                    "Only use tables and columns returned here.",
     "parameters": {"type": "object", "properties": {
         "tables": {"type": "array", "items": {"type": "string"},
                    "description": "Table names from search_schema."}},
         "required": ["tables"]}},
    {"name": "run_sql",
     "description": "Run ONE read-only SELECT query. Returns columns and rows, or an error message "
                    "you should use to fix the query and retry.",
     "parameters": {"type": "object", "properties": {
         "sql": {"type": "string", "description": "A single SELECT statement."}}, "required": ["sql"]}},
    {"name": "explain_result",
     "description": "Profile the most recent run_sql result (row count, min/max/mean/sum of numeric "
                    "columns, top values of text columns) to ground the final answer in facts.",
     "parameters": {"type": "object", "properties": {}}},
]


class SchemaTools:
    def __init__(self, db: Database, index: SchemaIndex, docs: dict, settings: Settings,
                 schema: dict[str, dict]):
        self.db = db
        self.index = index
        self.docs = docs
        self.settings = settings
        self.schema = schema  # only the tables the agent may see (hidden ones already removed)
        self.last_result: dict[str, Any] | None = None

    @property
    def last_sql(self) -> str | None:
        return self.last_result["sql"] if self.last_result else None

    # ---- tools -------------------------------------------------------------
    def search_schema(self, question: str, top_k: int = 3) -> dict:
        return {"tables": self.index.search(question, top_k=int(top_k or 3))}

    def get_schema(self, tables: list[str]) -> dict:
        described = self.docs.get("tables", {})
        found, unknown = {}, []
        for t in tables or []:
            if t not in self.schema:
                unknown.append(t)
                continue
            meta = self.schema[t]
            tdoc = described.get(t, {}) or {}
            col_docs = tdoc.get("columns", {}) or {}
            cols = []
            for c in meta["columns"]:
                entry = {"name": c["name"], "type": c["type"], "description": col_docs.get(c["name"], "")}
                if self._is_text(c["type"]):
                    try:
                        entry["sample_values"] = self.db.sample_values(t, c["name"])
                    except Exception:  # samples are a nice-to-have
                        pass
                cols.append(entry)
            found[t] = {"description": tdoc.get("description", ""), "columns": cols,
                        "primary_key": meta["primary_key"], "foreign_keys": meta["foreign_keys"]}
        out: dict[str, Any] = {"tables": found}
        if unknown:
            out["unknown_tables"] = unknown
            out["available_tables"] = sorted(self.schema)
        return out

    def run_sql(self, sql: str) -> dict:
        """Never raises: guard and database errors are returned so the model can self-correct."""
        try:
            safe_sql = validate_read_only(sql, self.db.dialect, self.settings.max_rows)
        except UnsafeSQLError as e:
            return {"ok": False, "error": f"Rejected by SQL guard: {e}"}
        start = time.perf_counter()
        try:
            columns, rows = self.db.run_read_only(safe_sql, self.settings.query_timeout_ms)
        except Exception as e:
            msg = str(getattr(e, "orig", e)).strip().splitlines()[0][:500]
            return {"ok": False, "error": f"Database error: {msg}", "sql": safe_sql}
        ms = round((time.perf_counter() - start) * 1000, 1)
        truncated = len(rows) > self.settings.max_rows
        rows = rows[: self.settings.max_rows]
        self.last_result = {"sql": safe_sql, "columns": columns, "rows": rows, "truncated": truncated}
        preview = rows[: self.settings.preview_rows]
        return {"ok": True, "sql": safe_sql, "columns": columns, "rows": preview,
                "row_count": len(rows), "truncated": truncated,
                "rows_shown": len(preview), "elapsed_ms": ms}

    def explain_result(self) -> dict:
        if not self.last_result:
            return {"ok": False, "error": "No query has been run yet. Call run_sql first."}
        cols, rows = self.last_result["columns"], self.last_result["rows"]
        profile = []
        for i, name in enumerate(cols):
            values = [r[i] for r in rows]
            present = [v for v in values if v is not None]
            entry: dict[str, Any] = {"column": name, "nulls": len(values) - len(present)}
            if present and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in present):
                entry.update(kind="numeric", min=min(present), max=max(present),
                             mean=round(mean(present), 4), sum=round(sum(present), 4))
            else:
                counts: dict[str, int] = {}
                for v in present:
                    counts[str(v)] = counts.get(str(v), 0) + 1
                top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
                entry.update(kind="categorical", distinct=len(counts),
                             top_values=[{"value": k, "count": c} for k, c in top])
            profile.append(entry)
        return {"ok": True, "sql": self.last_result["sql"], "row_count": len(rows),
                "truncated": self.last_result["truncated"], "columns": profile}

    # ---- dispatch ----------------------------------------------------------
    def dispatch(self, name: str, args: dict[str, Any]) -> dict:
        handlers = {"search_schema": self.search_schema, "get_schema": self.get_schema,
                    "run_sql": self.run_sql, "explain_result": self.explain_result}
        if name not in handlers:
            return {"ok": False, "error": f"Unknown tool '{name}'."}
        try:
            return handlers[name](**args)
        except TypeError as e:
            return {"ok": False, "error": f"Bad arguments for {name}: {e}"}

    @staticmethod
    def _is_text(type_name: str) -> bool:
        t = type_name.upper()
        return any(k in t for k in ("CHAR", "TEXT", "STRING", "VARCHAR"))


def visible_schema(db: Database, docs: dict) -> dict[str, dict]:
    """Introspect, then drop tables listed under `hidden:` in schema_docs.yaml (staging, views)."""
    hidden = set(docs.get("hidden", []) or [])
    return {t: m for t, m in db.introspect().items() if t not in hidden}


def build_tools(settings: Settings | None = None, *, db: Database | None = None, embedder=None,
                genai_client=None) -> SchemaTools:
    """Wire DB + schema docs + RAG index from settings."""
    settings = settings or Settings()
    db = db or Database(settings.database_url, schema=settings.db_schema)
    docs = load_schema_docs(settings.schema_docs_path)
    schema = visible_schema(db, docs)
    if embedder is None:
        if settings.embedding_backend == "gemini":
            from .schema_rag import GeminiEmbedder
            if genai_client is None:
                from google import genai
                genai_client = genai.Client(api_key=settings.gemini_api_key)
            embedder = GeminiEmbedder(genai_client, settings.embed_model)
        else:
            from .schema_rag import TfidfEmbedder
            embedder = TfidfEmbedder()
    index = SchemaIndex(build_table_docs(schema, docs), embedder)
    return SchemaTools(db, index, docs, settings, schema)
