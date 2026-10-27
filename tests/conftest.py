"""Shared fixtures. Everything runs offline: SQLite demo DB, TF-IDF embeddings, scripted fake Gemini."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from agent.config import Settings  # noqa: E402
from agent.db import Database  # noqa: E402
from agent.tools import build_tools  # noqa: E402
from seed_demo_db import build_sqlite_demo  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    return build_sqlite_demo()


@pytest.fixture
def settings():
    return Settings(database_url="sqlite://", gemini_api_key="", embeddings="tfidf",
                    max_rows=20, preview_rows=5)


@pytest.fixture
def tools(engine, settings):
    return build_tools(settings, db=Database(engine=engine))
