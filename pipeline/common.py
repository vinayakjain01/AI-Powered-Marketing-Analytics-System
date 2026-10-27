"""Helpers shared by the campaign and Shopify cleaners."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Data"
CAMPAIGN_CSV = DATA_DIR / "Campaign_Raw - Campaign_Raw.csv.csv"
SHOPIFY_CSV = DATA_DIR / "Raw_Shopify_Sales - Raw_Shopify_Sales.csv.csv"

# Strings that mean "no value" in the raw exports (the CSVs contain 'NAN' in several casings).
NULL_TOKENS = {"nan", "unknown", "none", "null", ""}


def snake_case_columns(df: pd.DataFrame) -> pd.DataFrame:
    """'Amount Spent (INR)' -> 'amount_spent_inr'. Done once so every later step uses stable names."""
    out = df.copy()
    out.columns = [re.sub(r"_+", "_", re.sub(r"[()\-]", "", c.strip().lower().replace(" ", "_")))
                   for c in out.columns]
    return out


def clean_text(series: pd.Series) -> pd.Series:
    """Trim, lowercase, collapse non-breaking spaces; map null-like tokens to real NULLs.

    Why: the raw data mixes 'Brand B', 'BRAND B' and 'brand b', and uses the literal text 'NAN',
    so group-bys would otherwise split one brand into several.
    """
    s = series.astype("string").str.replace(" ", " ", regex=False).str.strip().str.lower()
    return s.mask(s.isin(NULL_TOKENS))


def parse_mixed_date(series: pd.Series) -> pd.Series:
    """Parse the export's 'DD/MM/YYYY' text, undoing a spreadsheet-locale mix-up.

    The raw files were passed through a US-locale spreadsheet: any date whose day is <= 12 was
    re-read as MM/DD, while dates with day > 12 stayed as DD/MM text. So the rule is:
    first part > 12 -> DD/MM/YYYY, otherwise -> MM/DD/YYYY.
    Evidence: with this rule campaign dates span 2026-01-01..2026-03-28 (plain DD/MM spreads them
    over 12 months) and Shopify dates match the order timestamp ~90% of the time (the rest are
    1-day UTC offsets). Unparseable values (e.g. the text 'NAN') become NaT.
    """
    parts = series.astype("string").str.strip().str.extract(r"^(\d{1,2})/(\d{1,2})/(\d{4})$").astype("float")
    first_is_day = parts[0] > 12
    day = parts[0].where(first_is_day, parts[1])
    month = parts[1].where(first_is_day, parts[0])

    def two(v: pd.Series) -> pd.Series:
        return v.astype("Int64").astype("string").str.zfill(2)

    iso = parts[2].astype("Int64").astype("string") + "-" + two(month) + "-" + two(day)
    return pd.to_datetime(iso, format="%Y-%m-%d", errors="coerce")


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def safe_ratio(num: pd.Series, den: pd.Series, scale: float = 1.0) -> pd.Series:
    """num/den*scale, 0 where den is 0 (matches the notebook's np.where convention)."""
    safe_den = den.where(den > 0, 1)
    return pd.Series(np.where(den > 0, num / safe_den * scale, 0.0), index=num.index)
