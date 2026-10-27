"""Static safety checks for model-generated SQL (guard 1 of 2).

Why two guards: this one rejects anything that is not a single read-only query and caps the
rows; the database layer (db.py) then runs it in a READ ONLY transaction with a timeout. Either
alone can be fooled (a parser gap, or a function with side effects), both together are robust.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

_WRITE_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Drop, exp.Create,
    exp.Alter, exp.TruncateTable, exp.Command, exp.Grant,
)
# Read-only transactions do not stop these: they burn CPU, touch the server filesystem or
# reach other databases.
_BLOCKED_FUNCTIONS = {"pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "lo_import",
                      "lo_export", "dblink", "dblink_exec", "pg_terminate_backend",
                      "pg_cancel_backend", "set_config", "copy"}


class UnsafeSQLError(ValueError):
    """Raised when SQL is not a single read-only query."""


def validate_read_only(sql: str, dialect: str = "postgres", max_rows: int = 200) -> str:
    """Return a safe, row-capped version of `sql` or raise UnsafeSQLError.

    The returned query fetches at most max_rows + 1 rows so the caller can tell whether the
    result was truncated.
    """
    if not sql or not sql.strip():
        raise UnsafeSQLError("SQL is empty.")
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQLError(f"Could not parse SQL: {e}") from e

    if len(statements) != 1:
        raise UnsafeSQLError(f"Expected exactly one statement, got {len(statements)}.")
    stmt = statements[0]

    if not isinstance(stmt, exp.Query):
        raise UnsafeSQLError(f"Only SELECT queries are allowed, got {stmt.key.upper()}.")
    for node in stmt.walk():
        if isinstance(node, _WRITE_NODES):
            raise UnsafeSQLError(f"Write or DDL operation not allowed: {node.key.upper()}.")
        if isinstance(node, exp.Into):
            raise UnsafeSQLError("SELECT ... INTO is not allowed.")
        if isinstance(node, (exp.Anonymous, exp.Func)):
            name = (node.name or node.key or "").lower()
            if name in _BLOCKED_FUNCTIONS:
                raise UnsafeSQLError(f"Function not allowed: {name}.")

    cap = max_rows + 1
    limit = stmt.args.get("limit")
    current = None
    if limit is not None:
        try:
            current = int(limit.expression.name)
        except (AttributeError, ValueError):
            current = None
    if current is None or current > cap:
        stmt = stmt.limit(cap)
    return stmt.sql(dialect=dialect)
