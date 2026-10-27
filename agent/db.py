"""Database access: schema introspection and read-only query execution (guard 2 of 2)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine


def to_jsonable(value: Any) -> Any:
    """Decimal/date/bytes are not JSON-safe; the API, MCP and Gemini all need plain values."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return str(value)


class Database:
    def __init__(self, url: str = "", schema: str | None = None, engine: Engine | None = None):
        self.engine = engine or create_engine(url, pool_pre_ping=True)
        name = self.engine.dialect.name
        self.dialect = "postgres" if name.startswith("postgres") else name  # sqlglot dialect name
        self.schema = schema if self.dialect == "postgres" else None
        if self.schema and engine is None:
            # Set per connection (not via the startup `options` parameter) so it also works behind
            # hosted poolers such as Supabase's, which reject startup options.
            @event.listens_for(self.engine, "connect")
            def _set_search_path(dbapi_conn, _record):  # pragma: no cover - needs Postgres
                with dbapi_conn.cursor() as cur:
                    cur.execute(f'SET search_path TO "{self.schema}"')
                dbapi_conn.commit()

    def quote(self, identifier: str) -> str:
        return self.engine.dialect.identifier_preparer.quote(identifier)

    def introspect(self) -> dict[str, dict]:
        """Return {table: {columns, primary_key, foreign_keys}} for every table and view."""
        insp = inspect(self.engine)
        names = insp.get_table_names(schema=self.schema) + insp.get_view_names(schema=self.schema)
        out: dict[str, dict] = {}
        for table in sorted(names):
            cols = [{"name": c["name"], "type": str(c["type"]), "nullable": bool(c.get("nullable", True))}
                    for c in insp.get_columns(table, schema=self.schema)]
            try:
                pk = insp.get_pk_constraint(table, schema=self.schema).get("constrained_columns") or []
                fks = [{"columns": fk["constrained_columns"], "ref_table": fk["referred_table"],
                        "ref_columns": fk["referred_columns"]}
                       for fk in insp.get_foreign_keys(table, schema=self.schema)]
            except NotImplementedError:  # views
                pk, fks = [], []
            out[table] = {"columns": cols, "primary_key": pk, "foreign_keys": fks}
        return out

    def run_read_only(self, sql: str, timeout_ms: int = 10000, params: dict | None = None) -> tuple[list[str], list[list[Any]]]:
        """Run a query inside a READ ONLY transaction with a timeout, and always roll back."""
        with self.engine.connect() as conn:
            if self.dialect == "postgres":
                conn.execute(text("SET TRANSACTION READ ONLY"))
                conn.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
            elif self.dialect == "sqlite":
                conn.execute(text("PRAGMA query_only = ON"))
            try:
                result = conn.execute(text(sql), params or {})
                columns = list(result.keys())
                rows = [[to_jsonable(v) for v in row] for row in result.fetchall()]
            finally:
                if self.dialect == "sqlite":
                    conn.execute(text("PRAGMA query_only = OFF"))
                conn.rollback()
        return columns, rows

    def sample_values(self, table: str, column: str, limit: int = 5) -> list[Any]:
        """Distinct example values, so the model can filter on exact spellings ('brand b', 'usa')."""
        sql = (f"SELECT DISTINCT {self.quote(column)} FROM {self.quote(table)} "
               f"WHERE {self.quote(column)} IS NOT NULL LIMIT {int(limit)}")
        _, rows = self.run_read_only(sql)
        return [r[0] for r in rows]
