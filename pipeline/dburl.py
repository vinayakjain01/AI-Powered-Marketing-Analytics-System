"""DATABASE_URL handling shared by the pipeline, the agent and the scripts."""
from __future__ import annotations

import os

from dotenv import load_dotenv

from .common import ROOT

load_dotenv(ROOT / ".env")

SCHEMA = "campaign_data"


def normalize_database_url(url: str) -> str:
    """Accept the spellings hosted providers hand out and return a SQLAlchemy+psycopg2 URL.

    Supabase / Neon / Heroku give 'postgres://' or 'postgresql://'; SQLAlchemy 2 rejects the
    first and would pick whichever driver is installed for the second, so we pin psycopg2.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    return normalize_database_url(url)
