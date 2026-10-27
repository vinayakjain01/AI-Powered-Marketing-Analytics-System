"""Load cleaned data into Postgres staging tables and build the star schema from SQL/schema.sql."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.types import Date

from .clean_campaign import clean_campaign, load_raw_campaign
from .clean_shopify import clean_shopify, load_raw_shopify
from .common import ROOT
from .dburl import SCHEMA, get_database_url

SCHEMA_SQL = ROOT / "SQL" / "schema.sql"
TABLES = ["staging_ads", "staging_shopify", "dim_date", "dim_campaign", "fact_ads",
          "dim_product", "fact_order_lines"]


def load_staging(engine: Engine, ads: pd.DataFrame, shopify: pd.DataFrame) -> None:
    """Replace the staging tables. The date column is written as a real DATE (the old notebook
    wrote text, which is why the SQL needed a fragile TO_DATE)."""
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    for name, df in (("staging_ads", ads), ("staging_shopify", shopify)):
        df.to_sql(name, engine, schema=SCHEMA, if_exists="replace", index=False,
                  dtype={"date": Date()}, chunksize=1000, method="multi")


def run_schema(engine: Engine, sql_path: Path = SCHEMA_SQL) -> None:
    """Execute the whole build script in a single transaction (all-or-nothing)."""
    script = sql_path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(script)


def row_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT COUNT(*) FROM {SCHEMA}.{t}")).scalar_one() for t in TABLES}


def build_warehouse(database_url: str | None = None, campaign_csv=None, shopify_csv=None) -> dict:
    """Clean both CSVs -> staging -> star schema. Returns the cleaning reports and row counts."""
    engine = create_engine(database_url or get_database_url())
    ads, ads_report = clean_campaign(load_raw_campaign(campaign_csv) if campaign_csv else load_raw_campaign())
    shop, shop_report = clean_shopify(load_raw_shopify(shopify_csv) if shopify_csv else load_raw_shopify())
    load_staging(engine, ads, shop)
    run_schema(engine)
    return {"campaign_cleaning": ads_report, "shopify_cleaning": shop_report, "row_counts": row_counts(engine)}
