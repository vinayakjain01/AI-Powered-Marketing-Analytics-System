"""Clean the raw Meta Ads export (logic extracted from Campaign_Data_Cleaning.ipynb).

Returns the cleaned frame plus a step-by-step row-count report, so a reviewer can see
exactly how many rows each rule removed.
"""
from __future__ import annotations

import pandas as pd

from .common import (CAMPAIGN_CSV, clean_text, parse_mixed_date, safe_ratio,
                     snake_case_columns, to_number)

TEXT_COLS = ["data_source_name", "campaign_name", "campaign_effective_status", "ad_set_name",
             "ad_name", "country_funnel", "geo_location_segment"]
NON_NUMERIC = set(TEXT_COLS) | {"date"}
# Raw spellings -> canonical, applied after lowercasing. This is a no-op on the current data
# (the source column holds brand names, not platforms) but keeps a platform export working.
SOURCE_ALIASES = {"fb": "facebook", "meta": "facebook", "insta": "instagram"}


def load_raw_campaign(path=CAMPAIGN_CSV) -> pd.DataFrame:
    return pd.read_csv(path)


def clean_campaign(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    report: list[tuple[str, int]] = [("raw rows", len(raw))]
    df = snake_case_columns(raw)

    for col in TEXT_COLS:
        df[col] = clean_text(df[col])
    df["data_source_name"] = df["data_source_name"].replace(SOURCE_ALIASES)

    # Time-series needs a real date; the old notebook left text and TO_DATE'd it in SQL.
    df["date"] = parse_mixed_date(df["date"])
    df = df.dropna(subset=["date"])
    report.append(("after dropping rows with no valid date", len(df)))
    df = df.dropna(subset=["campaign_name"])
    report.append(("after dropping rows with no campaign name", len(df)))

    # Missing marketing events are zero occurrences; negatives are export glitches -> abs().
    for col in [c for c in df.columns if c not in NON_NUMERIC]:
        df[col] = to_number(df[col]).fillna(0).abs()

    df = df.drop_duplicates()
    report.append(("after removing exact duplicates", len(df)))

    # Per-row ratios recomputed from base columns. For row-level inspection only: aggregate
    # questions must recompute ratios from SUMs (an average of ratios is mathematically wrong).
    df["ctr"] = safe_ratio(df["link_clicks"], df["impressions"])
    df["cpm"] = safe_ratio(df["amount_spent_inr"], df["impressions"], 1000)
    df["cpc"] = safe_ratio(df["amount_spent_inr"], df["link_clicks"])
    df["roas"] = safe_ratio(df["purchases_conversion_value_inr"], df["amount_spent_inr"])
    return df.reset_index(drop=True), report
