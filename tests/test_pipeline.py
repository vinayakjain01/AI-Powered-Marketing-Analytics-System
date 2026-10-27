import pandas as pd
import pytest

from pipeline.clean_campaign import clean_campaign
from pipeline.clean_shopify import clean_shopify
from pipeline.common import clean_text, parse_mixed_date, safe_ratio, snake_case_columns
from pipeline.dburl import normalize_database_url


def test_snake_case_columns():
    df = pd.DataFrame(columns=["Amount Spent (INR)", "Clicks (all)", "Data Source name"])
    assert list(snake_case_columns(df).columns) == ["amount_spent_inr", "clicks_all", "data_source_name"]


def test_clean_text_unifies_case_whitespace_and_null_tokens():
    out = clean_text(pd.Series(["Brand B", "BRAND B", " brand b ", "NAN", "nan", "", None, "United States"]))
    assert out.tolist()[:3] == ["brand b"] * 3
    assert out.isna().tolist()[3:7] == [True] * 4
    assert out.iloc[7] == "united states"


def test_parse_mixed_date_undoes_the_locale_swap():
    # day > 12 is genuine DD/MM; day <= 12 was re-read as MM/DD by a US-locale spreadsheet.
    s = pd.Series(["19/01/2026", "01/08/2026", "02/07/2026", "NAN", None, "garbage", "31/12/2026"])
    got = parse_mixed_date(s)
    assert got.iloc[0] == pd.Timestamp("2026-01-19")
    assert got.iloc[1] == pd.Timestamp("2026-01-08")   # matched the order timestamp in the real data
    assert got.iloc[2] == pd.Timestamp("2026-02-07")
    assert got.iloc[3:6].isna().all()
    assert got.iloc[6] == pd.Timestamp("2026-12-31")


def test_safe_ratio_returns_zero_for_zero_denominator():
    out = safe_ratio(pd.Series([10.0, 5.0]), pd.Series([0.0, 2.0]), scale=1000)
    assert out.tolist() == [0.0, 2500.0]


RAW_CAMPAIGN = pd.DataFrame({
    "Data Source name": ["Brand A", "BRAND A", "Brand B", "Brand B"],
    "Date": ["19/01/2026", "19/01/2026", "NAN", "02/03/2026"],
    "Campaign Name": ["C1", "c1", "C2", None],
    "Amount Spent (INR)": [100, 100, 50, 10],
    "Impressions": [1000, 1000, 500, 100],
    "Link Clicks": [10, 10, 5, 1],
    "Purchases Conversion Value (INR)": [400, 400, 0, 0],
    "Campaign Effective Status": ["ACTIVE", "active", "paused", "paused"],
    "Ad Set Name": ["s", "s", "s", "s"], "Ad Name": ["a", "a", "a", "a"],
    "Country Funnel": ["India"] * 4, "Geo Location Segment": ["India"] * 4,
})


def test_clean_campaign_rules_and_report():
    df, report = clean_campaign(RAW_CAMPAIGN)
    labels = dict(report)
    assert labels["raw rows"] == 4
    assert labels["after dropping rows with no valid date"] == 3      # 'NAN' date dropped
    assert labels["after dropping rows with no campaign name"] == 2
    assert len(df) == 1 and labels["after removing exact duplicates"] == 1  # 'Brand A'/'BRAND A' collapse
    row = df.iloc[0]
    assert row["data_source_name"] == "brand a" and row["date"] == pd.Timestamp("2026-01-19")
    assert row["ctr"] == pytest.approx(0.01) and row["cpc"] == pytest.approx(10) and row["roas"] == pytest.approx(4)
    assert row["cpm"] == pytest.approx(100)


def test_clean_campaign_takes_absolute_values_and_fills_nulls():
    raw = RAW_CAMPAIGN.iloc[[0]].copy()
    raw["Amount Spent (INR)"] = -100
    raw["Link Clicks"] = None
    df, _ = clean_campaign(raw)
    assert df.iloc[0]["amount_spent_inr"] == 100 and df.iloc[0]["link_clicks"] == 0 and df.iloc[0]["cpc"] == 0


def test_clean_shopify_rules():
    raw = pd.DataFrame({
        "Data Source name": ["Brand A", "Brand A", "Brand A", "Brand A"],
        "Date": ["19/01/2026", "NAN", "NAN", "19/01/2026"],
        "Order Created At": ["2026-01-19T10:00:00Z", "2026-02-03T10:00:00Z", "NAN", "2026-01-19T10:00:00Z"],
        "Order ID": [1.0, 2.0, 3.0, None],
        "Product Title": ["Kurta", None, "Dress", "Kurta"],
        "Net Sales (INR)": [1000, 500, 300, 100],
        "Orders": [1, 1, 1, 1],
    })
    for col in ["Currency", "Sales Channel", "Order Name", "Country Funnel", "Geo Location Segment",
                "Product ID", "Product Type", "Customer Sale Type", "Gross Sales (INR)", "Total Sales (INR)",
                "Returns (INR)", "Items Sold", "Items Returned", "New Customer Orders",
                "Returning Customer Orders", "Discounts (INR)"]:
        raw[col] = None
    df, report = clean_shopify(raw)
    assert dict(report)["after dropping rows with no order id"] == 3
    assert len(df) == 2                                              # row 3 has no date and no timestamp
    assert df["date"].tolist() == [pd.Timestamp("2026-01-19"), pd.Timestamp("2026-02-03")]  # fallback used
    assert df["product_title"].tolist() == ["kurta", "unknown"]
    assert df["order_id"].dtype == "int64"


@pytest.mark.parametrize("raw, expected", [
    ("postgres://u:p@h:5432/db", "postgresql+psycopg2://u:p@h:5432/db"),
    ("postgresql://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
    ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
    ("sqlite:///x.db", "sqlite:///x.db"),
])
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected
