"""Build a small deterministic SQLite database with the same tables and columns as the warehouse.

Used by the tests, CI and the offline retrieval eval, so they run without Postgres or real data.
The data is synthetic and tiny - it exists to exercise queries, not to resemble real results.

    python scripts/seed_demo_db.py demo.db
"""
from __future__ import annotations

import datetime as dt
import random
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DDL = [
    """CREATE TABLE dim_date (date_id DATE PRIMARY KEY, day INT, week INT, month INT, quarter INT,
       year INT, day_name VARCHAR(10), month_name VARCHAR(10))""",
    """CREATE TABLE dim_campaign (campaign_id INTEGER PRIMARY KEY, campaign_name VARCHAR(200),
       campaign_status VARCHAR(50), ad_set_name VARCHAR(200), ad_name VARCHAR(200),
       sales_platform VARCHAR(50), brand VARCHAR(50), country_funnel VARCHAR(50),
       geo_location_segment VARCHAR(50))""",
    """CREATE TABLE fact_ads (date_id DATE, campaign_id INT, amount_spent NUMERIC, fb_spent_funnel NUMERIC,
       impressions INT, clicks INT, link_clicks INT, landing_page_views INT, adds_to_cart INT,
       checkouts_initiated INT, adds_payment_info INT, purchases INT, purchase_value NUMERIC,
       ctr NUMERIC, cpm NUMERIC, cpc NUMERIC, roi NUMERIC, PRIMARY KEY (date_id, campaign_id),
       FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
       FOREIGN KEY (campaign_id) REFERENCES dim_campaign(campaign_id))""",
    """CREATE TABLE dim_product (product_key INTEGER PRIMARY KEY, product_title VARCHAR(300),
       product_type VARCHAR(100), shopify_product_id BIGINT)""",
    """CREATE TABLE fact_order_lines (order_line_id INTEGER PRIMARY KEY, date_id DATE, product_key INT,
       brand VARCHAR(50), sales_channel VARCHAR(100), country VARCHAR(100),
       geo_location_segment VARCHAR(50), customer_sale_type VARCHAR(30), order_id BIGINT,
       order_name VARCHAR(50), gross_sales NUMERIC, discounts NUMERIC, returns NUMERIC,
       net_sales NUMERIC, total_sales NUMERIC, orders NUMERIC, items_sold NUMERIC,
       items_returned NUMERIC, new_customer_orders NUMERIC, returning_customer_orders NUMERIC,
       FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
       FOREIGN KEY (product_key) REFERENCES dim_product(product_key))""",
    # Staging tables exist in the real warehouse; the agent must never see them (schema_docs hidden:).
    "CREATE TABLE staging_ads (date DATE, campaign_name VARCHAR(200), amount_spent_inr NUMERIC)",
    "CREATE TABLE staging_shopify (date DATE, order_id BIGINT, net_sales_inr NUMERIC)",
]
CAMPAIGNS = [
    ("growify | tof | conversion | india", "active", "ecomm | women", "brand a", "india", "india"),
    ("growify | retarget | conversion | uk", "active", "ecomm | retargeting", "brand b", "united kingdom", "rest of the world"),
    ("growify | tof | conversion | us", "paused", "ecomm | online shoppers", "brand b", "united states", "usa"),
    ("growify | mof | messaging | uae", "active", "ecomm | cx data", "brand a", "united arab emirates", "middle east"),
]
PRODUCTS = [("heather kurta set", "kurta set"), ("lilian kaftan set", "co-ord"),
            ("primrose phiran set", "lehenga"), ("icecream dress", "dress")]


def build_sqlite_demo(url: str = "sqlite://") -> Engine:
    """Create and fill the demo schema. `url='sqlite://'` gives an in-memory DB (one shared connection)."""
    from sqlalchemy.pool import StaticPool
    kwargs = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}} if url == "sqlite://" else {}
    engine = create_engine(url, **kwargs)
    rng = random.Random(7)
    with engine.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))
        day = dt.date(2026, 1, 1)
        while day <= dt.date(2026, 3, 31):
            conn.execute(text("INSERT INTO dim_date VALUES (:d,:day,:wk,:m,:q,:y,:dn,:mn)"), {
                "d": day, "day": day.day, "wk": day.isocalendar()[1], "m": day.month,
                "q": (day.month - 1) // 3 + 1, "y": day.year, "dn": day.strftime("%A"),
                "mn": day.strftime("%B")})
            day += dt.timedelta(days=1)
        for i, (name, status, adset, brand, country, region) in enumerate(CAMPAIGNS, 1):
            conn.execute(text("INSERT INTO dim_campaign VALUES (:i,:n,:s,:a,NULL,:b,:b,:c,:r)"),
                         {"i": i, "n": name, "s": status, "a": adset, "b": brand, "c": country, "r": region})
        for i, (title, ptype) in enumerate(PRODUCTS, 1):
            conn.execute(text("INSERT INTO dim_product VALUES (:i,:t,:p,NULL)"), {"i": i, "t": title, "p": ptype})
        for month in (1, 2, 3):
            for d in range(1, 29, 3):
                date = dt.date(2026, month, d)
                for cid in range(1, len(CAMPAIGNS) + 1):
                    spend = round(rng.uniform(500, 5000), 2)
                    imps = rng.randint(5000, 60000)
                    clicks = rng.randint(50, 900)
                    purchases = rng.randint(0, 12)
                    conn.execute(text("INSERT INTO fact_ads VALUES (:d,:c,:sp,:sp,:im,:cl,:cl,:lp,:ac,:ci,:ap,:pu,:pv,0,0,0,0)"), {
                        "d": date, "c": cid, "sp": spend, "im": imps, "cl": clicks, "lp": clicks // 2,
                        "ac": purchases * 3, "ci": purchases * 2, "ap": purchases + 1, "pu": purchases,
                        "pv": round(purchases * rng.uniform(1500, 4000), 2)})
        line = 1
        for month in (1, 2, 3):
            for d in range(2, 28, 4):
                for pk in range(1, len(PRODUCTS) + 1):
                    net = round(rng.uniform(1500, 9000), 2)
                    camp = CAMPAIGNS[(line + pk) % len(CAMPAIGNS)]
                    conn.execute(text("INSERT INTO fact_order_lines VALUES (:l,:d,:p,:b,:ch,:co,:r,:t,:o,:on,:g,:di,:re,:n,:tt,1,:it,0,:nc,:rc)"), {
                        "l": line, "d": dt.date(2026, month, d), "p": pk, "b": camp[3],
                        "ch": rng.choice(["online store", "draft orders"]), "co": camp[4], "r": camp[5],
                        "t": rng.choice(["first-time", "returning"]), "o": 1000 + line, "on": f"#{1000 + line}",
                        "g": net + 300, "di": 200, "re": 100, "n": net, "tt": net + 50,
                        "it": rng.randint(1, 3), "nc": line % 2, "rc": 1 - line % 2})
                    line += 1
    return engine


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "demo.db")
    target.unlink(missing_ok=True)
    build_sqlite_demo(f"sqlite:///{target}")
    print(f"Wrote {target}")
