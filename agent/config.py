"""Runtime settings, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.dburl import normalize_database_url  # also loads .env

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _project_path(value: str) -> str:
    """Relative paths resolve against the repo root so the app works from any cwd (e.g. Claude Desktop)."""
    p = Path(value)
    return str(p if p.is_absolute() else ROOT / p)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: normalize_database_url(_env("DATABASE_URL")))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.5-flash"))
    embed_model: str = field(default_factory=lambda: _env("GEMINI_EMBED_MODEL", "gemini-embedding-001"))
    embeddings: str = field(default_factory=lambda: _env("EMBEDDINGS"))
    schema_docs_path: str = field(default_factory=lambda: _project_path(_env("SCHEMA_DOCS", "schema_docs.yaml")))
    db_schema: str = field(default_factory=lambda: _env("DB_SCHEMA", "campaign_data"))
    max_rows: int = field(default_factory=lambda: int(_env("MAX_ROWS", "200")))
    preview_rows: int = field(default_factory=lambda: int(_env("PREVIEW_ROWS", "50")))
    query_timeout_ms: int = field(default_factory=lambda: int(_env("QUERY_TIMEOUT_MS", "10000")))
    max_steps: int = field(default_factory=lambda: int(_env("AGENT_MAX_STEPS", "8")))
    max_sql_attempts: int = field(default_factory=lambda: int(_env("AGENT_MAX_SQL_ATTEMPTS", "3")))

    @property
    def embedding_backend(self) -> str:
        """'gemini' needs a key; 'tfidf' is the offline fallback. Explicit EMBEDDINGS wins."""
        if self.embeddings:
            return self.embeddings.lower()
        return "gemini" if self.gemini_api_key else "tfidf"
