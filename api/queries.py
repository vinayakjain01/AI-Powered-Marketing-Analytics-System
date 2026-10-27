"""Fixed, parameterised SQL behind the dashboard.

Why not let the LLM do this: dashboards need the same numbers every time. Rules enforced here:
dimensions come from a whitelist (never user text in SQL), filter values are bound parameters,
and every ratio is computed from SUMs (never from fact_ads.ctr/cpc/roi, which are averages).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ADS_METRICS = """
    COALESCE(SUM(f.amount_spent), 0)              AS spend,
    COALESCE(SUM(f.purchase_value), 0)            AS revenue,
    COALESCE(SUM(f.purchases), 0)                 AS purchases,
    COALESCE(SUM(f.impressions), 0)               AS impressions,
    COALESCE(SUM(f.clicks), 0)                    AS clicks,
    SUM(f.purchase_value) / NULLIF(SUM(f.amount_spent), 0)                          AS roas,
    (SUM(f.purchase_value) - SUM(f.amount_spent)) / NULLIF(SUM(f.amount_spent), 0)  AS roi,
    SUM(f.amount_spent) / NULLIF(SUM(f.clicks), 0)                                  AS cpc,
    CAST(SUM(f.clicks) AS FLOAT) / NULLIF(SUM(f.impressions), 0)                    AS ctr,
    SUM(f.amount_spent) * 1000.0 / NULLIF(SUM(f.impressions), 0)                    AS cpm
"""
STORE_METRICS = """
    COALESCE(SUM(o.net_sales), 0)    AS net_sales,
    COALESCE(SUM(o.gross_sales), 0)  AS gross_sales,
    COALESCE(SUM(o.discounts), 0)    AS discounts,
    COALESCE(SUM(o.returns), 0)      AS returns,
    COALESCE(SUM(o.orders), 0)       AS orders,
    COALESCE(SUM(o.items_sold), 0)   AS items_sold,
    SUM(o.net_sales) / NULLIF(SUM(o.orders), 0) AS aov
"""
FUNNEL_STAGE = """CASE WHEN LOWER(c.campaign_name) LIKE '%retarget%' THEN 'retargeting'
    WHEN LOWER(c.campaign_name) LIKE '%tof%' THEN 'tof'
    WHEN LOWER(c.campaign_name) LIKE '%mof%' THEN 'mof'
    WHEN LOWER(c.campaign_name) LIKE '%bof%' THEN 'bof' ELSE 'other' END"""

# whitelist: public name -> SQL expression (ads fact joined to dim_campaign c and dim_date d)
ADS_DIMENSIONS = {
    "brand": "c.brand", "region": "c.geo_location_segment", "country": "c.country_funnel",
    "status": "c.campaign_status", "funnel_stage": FUNNEL_STAGE, "ad_set": "c.ad_set_name",
    "weekday": "d.day_name",
}
STORE_DIMENSIONS = {
    "channel": "o.sales_channel", "country": "o.country", "region": "o.geo_location_segment",
    "brand": "o.brand", "customer_type": "o.customer_sale_type", "product_type": "p.product_type",
}
# Real aggregate expressions (Postgres does not allow output aliases inside HAVING).
RANK_METRICS = {
    "spend": "SUM(f.amount_spent)", "revenue": "SUM(f.purchase_value)", "purchases": "SUM(f.purchases)",
    "roas": "SUM(f.purchase_value) / NULLIF(SUM(f.amount_spent), 0)",
    "roi": "(SUM(f.purchase_value) - SUM(f.amount_spent)) / NULLIF(SUM(f.amount_spent), 0)",
    "cpc": "SUM(f.amount_spent) / NULLIF(SUM(f.clicks), 0)",
    "ctr": "CAST(SUM(f.clicks) AS FLOAT) / NULLIF(SUM(f.impressions), 0)",
}
TREND_GRAINS = {
    "day": ("CAST(d.date_id AS TEXT)", "d.date_id"),
    "week": ("CAST(d.year AS TEXT) || '-W' || CAST(d.week AS TEXT)", "d.year, d.week"),
    "month": ("CAST(d.year AS TEXT) || '-' || CAST(d.month AS TEXT)", "d.year, d.month"),
}


@dataclass
class Filters:
    brand: str | None = None
    region: str | None = None
    start: str | None = None
    end: str | None = None


def _where(f: Filters, brand_col: str, region_col: str, date_col: str) -> tuple[str, dict[str, Any]]:
    clauses, params = [], {}
    for key, col, val in (("brand", brand_col, f.brand), ("region", region_col, f.region),
                          ("start", date_col, f.start), ("end", date_col, f.end)):
        if val:
            op = ">=" if key == "start" else "<=" if key == "end" else "="
            clauses.append(f"{col} {op} :{key}")
            params[key] = val
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


_ADS_FROM = ("FROM fact_ads f JOIN dim_campaign c ON c.campaign_id = f.campaign_id "
             "JOIN dim_date d ON d.date_id = f.date_id")
_STORE_FROM = ("FROM fact_order_lines o JOIN dim_date d ON d.date_id = o.date_id "
               "LEFT JOIN dim_product p ON p.product_key = o.product_key")


def ads_kpis(f: Filters) -> tuple[str, dict]:
    where, params = _where(f, "c.brand", "c.geo_location_segment", "d.date_id")
    return f"SELECT {ADS_METRICS} {_ADS_FROM} {where}", params


def store_kpis(f: Filters) -> tuple[str, dict]:
    where, params = _where(f, "o.brand", "o.geo_location_segment", "d.date_id")
    return f"SELECT {STORE_METRICS} {_STORE_FROM} {where}", params


def ads_trend(f: Filters, grain: str) -> tuple[str, dict]:
    label, order = TREND_GRAINS[grain]
    where, params = _where(f, "c.brand", "c.geo_location_segment", "d.date_id")
    return (f"SELECT {label} AS period, {ADS_METRICS} {_ADS_FROM} {where} "
            f"GROUP BY {order} ORDER BY {order}"), params


def store_trend(f: Filters, grain: str) -> tuple[str, dict]:
    label, order = TREND_GRAINS[grain]
    where, params = _where(f, "o.brand", "o.geo_location_segment", "d.date_id")
    return (f"SELECT {label} AS period, {STORE_METRICS} {_STORE_FROM} {where} "
            f"GROUP BY {order} ORDER BY {order}"), params


def ads_breakdown(f: Filters, by: str) -> tuple[str, dict]:
    expr = ADS_DIMENSIONS[by]
    where, params = _where(f, "c.brand", "c.geo_location_segment", "d.date_id")
    return (f"SELECT COALESCE({expr}, 'unknown') AS label, {ADS_METRICS} {_ADS_FROM} {where} "
            f"GROUP BY 1 ORDER BY spend DESC"), params


def store_breakdown(f: Filters, by: str) -> tuple[str, dict]:
    expr = STORE_DIMENSIONS[by]
    where, params = _where(f, "o.brand", "o.geo_location_segment", "d.date_id")
    return (f"SELECT COALESCE({expr}, 'unknown') AS label, {STORE_METRICS} {_STORE_FROM} {where} "
            f"GROUP BY 1 ORDER BY net_sales DESC"), params


def top_campaigns(f: Filters, metric: str, descending: bool, limit: int, min_spend: float) -> tuple[str, dict]:
    where, params = _where(f, "c.brand", "c.geo_location_segment", "d.date_id")
    params["min_spend"] = min_spend
    direction = "DESC" if descending else "ASC"
    col = RANK_METRICS[metric]
    # NULL ratios (zero denominators) are excluded from rankings so they never look "best".
    return (f"SELECT c.campaign_name AS label, {ADS_METRICS} {_ADS_FROM} {where} "
            f"GROUP BY c.campaign_name HAVING COALESCE(SUM(f.amount_spent), 0) >= :min_spend "
            f"AND {col} IS NOT NULL ORDER BY {col} {direction} LIMIT {int(limit)}"), params


FILTER_QUERIES = {
    "brands": "SELECT DISTINCT brand FROM dim_campaign WHERE brand IS NOT NULL ORDER BY brand",
    "regions": ("SELECT DISTINCT geo_location_segment FROM dim_campaign "
                "WHERE geo_location_segment IS NOT NULL ORDER BY geo_location_segment"),
    "dates": "SELECT MIN(date_id), MAX(date_id) FROM fact_ads",
}
