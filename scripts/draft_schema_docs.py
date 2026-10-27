"""Add TODO entries to schema_docs.yaml for tables/columns that exist in the DB but are undocumented.

Existing descriptions are never overwritten. Run after changing the warehouse:
    python scripts/draft_schema_docs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.config import Settings  # noqa: E402
from agent.db import Database  # noqa: E402


def main() -> None:
    settings = Settings()
    path = Path(settings.schema_docs_path)
    docs = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    docs = docs or {}
    docs.setdefault("hidden", [])
    tables = docs.setdefault("tables", {})
    added = []
    for table, meta in Database(settings.database_url, schema=settings.db_schema).introspect().items():
        if table in docs["hidden"]:
            continue
        entry = tables.setdefault(table, {"description": f"TODO describe table {table}", "columns": {}})
        columns = entry.setdefault("columns", {})
        for col in meta["columns"]:
            if col["name"] not in columns:
                columns[col["name"]] = f"TODO describe {table}.{col['name']}"
                added.append(f"{table}.{col['name']}")
    # NOTE: rewriting loses YAML comments/folding; review the diff before committing.
    path.write_text(yaml.safe_dump(docs, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    print(f"Added {len(added)} TODO entries." + ("".join(f"\n  {a}" for a in added) if added else ""))


if __name__ == "__main__":
    main()
