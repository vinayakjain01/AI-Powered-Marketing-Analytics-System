"""Clean the raw Shopify export (logic from Shopify_Data_Cleaning.ipynb) so it can be loaded.

Grain of the cleaned data: one row per (date, order, product line) as exported by Shopify's
analytics report. Rows are pre-aggregated, so `orders` can be > 1 on a single row.
"""
from __future__ import annotations

import pandas as pd

from .common import SHOPIFY_CSV, clean_text, parse_mixed_date, snake_case_columns, to_number

TEXT_COLS = ["data_source_name", "currency", "sales_channel", "order_name", "country_funnel",
             "geo_location_segment", "product_title", "product_type", "customer_sale_type"]
MEASURES = ["gross_sales_inr", "net_sales_inr", "total_sales_inr", "orders", "returns_inr",
            "items_sold", "items_returned", "new_customer_orders", "returning_customer_orders",
            "discounts_inr"]
OUTPUT_COLS = ["date", "brand", "sales_channel", "currency", "order_id", "order_name",
               "country_funnel", "geo_location_segment", "product_id", "product_title",
               "product_type", "customer_sale_type", *MEASURES]


def load_raw_shopify(path=SHOPIFY_CSV) -> pd.DataFrame:
    return pd.read_csv(path)


def clean_shopify(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    report: list[tuple[str, int]] = [("raw rows", len(raw))]
    df = snake_case_columns(raw).drop_duplicates()
    report.append(("after removing exact duplicates", len(df)))

    for col in TEXT_COLS:
        df[col] = clean_text(df[col])
    for col in ["order_id", "product_id", *MEASURES]:
        df[col] = to_number(df[col])

    # Order ID is the tracking key; rows without it cannot be traced (same rule as the notebook).
    df = df.dropna(subset=["order_id"])
    report.append(("after dropping rows with no order id", len(df)))

    # 'Date' is DD/MM/YYYY text (often the literal 'NAN'); fall back to the order-created timestamp.
    created = pd.to_datetime(df["order_created_at"].replace("NAN", pd.NA), errors="coerce", utc=True)
    df["date"] = parse_mixed_date(df["date"]).fillna(created.dt.tz_localize(None).dt.normalize())
    df = df.dropna(subset=["date"])
    report.append(("after dropping rows with no usable date", len(df)))

    df[MEASURES] = df[MEASURES].fillna(0)
    df["order_id"] = df["order_id"].astype("int64")
    df["product_title"] = df["product_title"].fillna("unknown")
    df["brand"] = df["data_source_name"]
    return df[OUTPUT_COLS].reset_index(drop=True), report
