-- ============================================================================
-- MARKETING ANALYTICS WAREHOUSE (star schema, PostgreSQL)
-- Single source of truth for Power BI and the AI agent.
--
-- Run via:  python scripts/build_warehouse.py      (loads staging, then runs this file)
-- Safe to re-run: the star-schema tables are dropped and rebuilt from staging.
--
-- Prerequisite: pipeline has written staging_ads and staging_shopify
--   (cleaned, typed; written by pipeline/warehouse.py - not defined here).
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS campaign_data;
SET search_path TO campaign_data;

DROP VIEW  IF EXISTS vw_marketing_performance;
DROP TABLE IF EXISTS fact_order_lines CASCADE;
DROP TABLE IF EXISTS dim_product      CASCADE;
DROP TABLE IF EXISTS fact_ads         CASCADE;
DROP TABLE IF EXISTS dim_campaign     CASCADE;
DROP TABLE IF EXISTS dim_date         CASCADE;

-- 1. DATE DIMENSION ---------------------------------------------------------
CREATE TABLE dim_date (
    date_id    DATE PRIMARY KEY,
    day        INT,
    week       INT,
    month      INT,
    quarter    INT,
    year       INT,
    day_name   VARCHAR(10),
    month_name VARCHAR(10)
);

-- TRIM: TO_CHAR(..., 'Month') pads to 9 chars, which would break month_name = 'March'.
INSERT INTO dim_date
SELECT d::DATE,
       EXTRACT(DAY     FROM d),
       EXTRACT(WEEK    FROM d),
       EXTRACT(MONTH   FROM d),
       EXTRACT(QUARTER FROM d),
       EXTRACT(YEAR    FROM d),
       TRIM(TO_CHAR(d, 'Day')),
       TRIM(TO_CHAR(d, 'Month'))
FROM generate_series('2023-01-01'::DATE, '2027-12-31'::DATE, INTERVAL '1 day') AS d;

-- 2. CAMPAIGN DIMENSION -----------------------------------------------------
-- Grain: one row per (campaign, ad set, ad, region, brand). Status and country_funnel can change
-- over time, so they are taken from the most recent staging row; otherwise one ad would appear
-- twice and the fact join below would double-count its metrics.
CREATE TABLE dim_campaign (
    campaign_id          SERIAL PRIMARY KEY,
    campaign_name        VARCHAR(200),
    campaign_status      VARCHAR(50),
    ad_set_name          VARCHAR(200),
    ad_name              VARCHAR(200),
    sales_platform       VARCHAR(50),   -- legacy name kept for Power BI; holds the BRAND (see brand)
    brand                VARCHAR(50),   -- same value as sales_platform; the correct business name
    country_funnel       VARCHAR(50),
    geo_location_segment VARCHAR(50)
);

INSERT INTO dim_campaign (campaign_name, campaign_status, ad_set_name, ad_name, sales_platform,
                          brand, country_funnel, geo_location_segment)
SELECT DISTINCT ON (s.campaign_name, s.ad_set_name, s.ad_name, s.geo_location_segment, s.data_source_name)
       s.campaign_name, s.campaign_effective_status, s.ad_set_name, s.ad_name,
       s.data_source_name, s.data_source_name, s.country_funnel, s.geo_location_segment
FROM staging_ads s
WHERE s.campaign_name IS NOT NULL
ORDER BY s.campaign_name, s.ad_set_name, s.ad_name, s.geo_location_segment, s.data_source_name,
         s.date DESC;

-- Enforces the grain above (COALESCE so NULLs participate in uniqueness).
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_campaign_key ON dim_campaign (
    COALESCE(campaign_name, ''), COALESCE(ad_set_name, ''), COALESCE(ad_name, ''),
    COALESCE(geo_location_segment, ''), COALESCE(sales_platform, ''));

-- 3. ADS FACT ---------------------------------------------------------------
-- Grain: one row per (date, campaign_id).
-- ctr / cpm / cpc / roi here are AVERAGES of per-row ratios, kept only so existing Power BI
-- reports keep working. DO NOT use them for aggregates: recompute from SUM(...) instead.
-- (roi holds AVG of ROAS = revenue / spend, not (revenue - spend) / spend.)
CREATE TABLE fact_ads (
    date_id            DATE,
    campaign_id        INT,
    amount_spent       NUMERIC,
    fb_spent_funnel    NUMERIC,
    impressions        INT,
    clicks             INT,
    link_clicks        INT,
    landing_page_views INT,
    adds_to_cart       INT,
    checkouts_initiated INT,
    adds_payment_info  INT,
    purchases          INT,
    purchase_value     NUMERIC,
    ctr                NUMERIC,
    cpm                NUMERIC,
    cpc                NUMERIC,
    roi                NUMERIC,
    PRIMARY KEY (date_id, campaign_id),
    FOREIGN KEY (date_id)     REFERENCES dim_date(date_id),
    FOREIGN KEY (campaign_id) REFERENCES dim_campaign(campaign_id)
);

COMMENT ON COLUMN fact_ads.ctr IS 'DO NOT USE FOR AGGREGATES: average of per-row ratios. Use SUM(link_clicks)/SUM(impressions).';
COMMENT ON COLUMN fact_ads.cpm IS 'DO NOT USE FOR AGGREGATES. Use SUM(amount_spent)/SUM(impressions)*1000.';
COMMENT ON COLUMN fact_ads.cpc IS 'DO NOT USE FOR AGGREGATES. Use SUM(amount_spent)/SUM(link_clicks).';
COMMENT ON COLUMN fact_ads.roi IS 'DO NOT USE FOR AGGREGATES: average of per-row ROAS. Use SUM(purchase_value)/SUM(amount_spent).';

-- NULL-safe join (IS NOT DISTINCT FROM): the old '=' join silently dropped every row where an
-- ad set / ad / region was NULL, and duplicated rows when dim_campaign had two statuses per ad.
INSERT INTO fact_ads
SELECT s.date, c.campaign_id,
       SUM(s.amount_spent_inr), SUM(s.fb_spent_funnel_inr),
       SUM(s.impressions), SUM(s.clicks_all), SUM(s.link_clicks), SUM(s.landing_page_views),
       SUM(s.adds_to_cart), SUM(s.checkouts_initiated), SUM(s.adds_of_payment_info),
       SUM(s.purchases), SUM(s.purchases_conversion_value_inr),
       AVG(s.ctr), AVG(s.cpm), AVG(s.cpc), AVG(s.roas)
FROM staging_ads s
JOIN dim_campaign c
  ON  s.campaign_name        =                    c.campaign_name
  AND s.ad_set_name          IS NOT DISTINCT FROM c.ad_set_name
  AND s.ad_name              IS NOT DISTINCT FROM c.ad_name
  AND s.geo_location_segment IS NOT DISTINCT FROM c.geo_location_segment
  AND s.data_source_name     IS NOT DISTINCT FROM c.sales_platform
WHERE s.date IS NOT NULL
GROUP BY s.date, c.campaign_id;

-- 4. PRODUCT DIMENSION + ORDER-LINE FACT (Shopify) ----------------------------------------------
-- Product ID is null on ~half of the export, so a product is identified by title + type.
CREATE TABLE dim_product (
    product_key        SERIAL PRIMARY KEY,
    product_title      VARCHAR(300),
    product_type       VARCHAR(100),
    shopify_product_id BIGINT
);

INSERT INTO dim_product (product_title, product_type, shopify_product_id)
SELECT product_title, product_type, MAX(product_id)::BIGINT
FROM staging_shopify
GROUP BY product_title, product_type
ORDER BY product_title, product_type;

CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_product_key
    ON dim_product (product_title, COALESCE(product_type, ''));

-- Grain: one row per exported (date, order, product) line. Rows are pre-aggregated by Shopify's
-- report, so `orders` may be > 1 on a row: always SUM(orders) rather than COUNT(*).
CREATE TABLE fact_order_lines (
    order_line_id             SERIAL PRIMARY KEY,
    date_id                   DATE REFERENCES dim_date(date_id),
    product_key               INT  REFERENCES dim_product(product_key),
    brand                     VARCHAR(50),
    sales_channel             VARCHAR(100),
    country                   VARCHAR(100),
    geo_location_segment      VARCHAR(50),
    customer_sale_type        VARCHAR(30),
    order_id                  BIGINT,
    order_name                VARCHAR(50),
    gross_sales               NUMERIC,
    discounts                 NUMERIC,
    returns                   NUMERIC,
    net_sales                 NUMERIC,
    total_sales               NUMERIC,
    orders                    NUMERIC,
    items_sold                NUMERIC,
    items_returned            NUMERIC,
    new_customer_orders       NUMERIC,
    returning_customer_orders NUMERIC
);

INSERT INTO fact_order_lines (date_id, product_key, brand, sales_channel, country, geo_location_segment,
       customer_sale_type, order_id, order_name, gross_sales, discounts, returns, net_sales,
       total_sales, orders, items_sold, items_returned, new_customer_orders, returning_customer_orders)
SELECT s.date, p.product_key, s.brand, s.sales_channel, s.country_funnel, s.geo_location_segment,
       s.customer_sale_type, s.order_id, s.order_name, s.gross_sales_inr, s.discounts_inr,
       s.returns_inr, s.net_sales_inr, s.total_sales_inr, s.orders, s.items_sold,
       s.items_returned, s.new_customer_orders, s.returning_customer_orders
FROM staging_shopify s
JOIN dim_product p
  ON  s.product_title = p.product_title
  AND s.product_type  IS NOT DISTINCT FROM p.product_type
ORDER BY s.date, s.order_id;

-- 5. INDEXES ------------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_fact_date         ON fact_ads(date_id);
CREATE INDEX IF NOT EXISTS idx_fact_campaign     ON fact_ads(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_platform ON dim_campaign(sales_platform);
CREATE INDEX IF NOT EXISTS idx_campaign_region   ON dim_campaign(geo_location_segment);
CREATE INDEX IF NOT EXISTS idx_campaign_name     ON dim_campaign(campaign_name);
CREATE INDEX IF NOT EXISTS idx_orders_date       ON fact_order_lines(date_id);
CREATE INDEX IF NOT EXISTS idx_orders_product    ON fact_order_lines(product_key);

-- 6. POWER BI VIEW (kept as it was; ratios are correctly computed from SUMs) ----------------------
CREATE VIEW vw_marketing_performance AS
SELECT d.year, d.month, c.campaign_name, c.sales_platform, c.geo_location_segment, c.country_funnel,
       SUM(f.amount_spent)   AS spend,
       SUM(f.purchase_value) AS revenue,
       SUM(f.purchases)      AS conversions,
       CASE WHEN SUM(f.clicks) > 0 THEN SUM(f.amount_spent) / SUM(f.clicks)::NUMERIC ELSE 0::NUMERIC END AS cpc,
       CASE WHEN SUM(f.amount_spent) > 0 THEN SUM(f.purchase_value) / SUM(f.amount_spent) ELSE 0::NUMERIC END AS roas,
       CASE WHEN SUM(f.amount_spent) > 0
            THEN (SUM(f.purchase_value) - SUM(f.amount_spent)) / SUM(f.amount_spent) ELSE 0::NUMERIC END AS roi
FROM fact_ads f
JOIN dim_campaign c ON f.campaign_id = c.campaign_id
JOIN dim_date d     ON f.date_id = d.date_id
GROUP BY d.year, d.month, c.campaign_name, c.sales_platform, c.geo_location_segment, c.country_funnel;

ANALYZE;
