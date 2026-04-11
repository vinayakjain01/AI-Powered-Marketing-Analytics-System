-- SCHEMA: MARKETING ANALYTICS (META ADS DATA)
-- PURPOSE: Single Source of Truth for Power BI & AI Tool
CREATE SCHEMA IF NOT EXISTS campaign_data;
SET search_path TO campaign_data;


-- 1. STAGING TABLE (CLEAN DATA FROM PYTHON)

CREATE TABLE IF NOT EXISTS staging_ads (
data_source_name VARCHAR(100),
date DATE,
campaign_name VARCHAR(200),
campaign_effective_status VARCHAR(50),
ad_set_name VARCHAR(200),
ad_name VARCHAR(200),
country_funnel VARCHAR(50),
geo_location_segment VARCHAR(50),
fb_spent_funnel_inr NUMERIC,
amount_spent_inr NUMERIC,
clicks_all INT,
impressions INT,
page_likes INT,
landing_page_views INT,
link_clicks INT,
adds_to_cart INT,
checkouts_initiated INT,
adds_of_payment_info INT,
purchases INT,
purchases_conversion_value_inr NUMERIC,
website_contacts INT,
messaging_conversations_started INT,
adds_to_cart_conversion_value_inr NUMERIC,
checkouts_initiated_conversion_value_inr NUMERIC,
adds_of_payment_info_conversion_value_inr NUMERIC,
row_count INT,
ctr NUMERIC,
cpm NUMERIC,
cpc NUMERIC,
roi NUMERIC
);

select * from staging_ads;

-- 2. DATE DIMENSION TABLE

CREATE TABLE IF NOT EXISTS dim_date (
date_id DATE PRIMARY KEY,
day INT,
week INT,
month INT,
quarter INT,
year INT,
day_name VARCHAR(10),
month_name VARCHAR(10)
);

-- Populate date dimension
INSERT INTO dim_date
SELECT
d::DATE,
EXTRACT(DAY FROM d),
EXTRACT(WEEK FROM d),
EXTRACT(MONTH FROM d),
EXTRACT(QUARTER FROM d),
EXTRACT(YEAR FROM d),
TO_CHAR(d, 'Day'),
TO_CHAR(d, 'Month')
FROM generate_series(
'2023-01-01'::DATE,
'2026-12-31'::DATE,
INTERVAL '1 day'
) AS d
ON CONFLICT (date_id) DO NOTHING;

select * from dim_date;

-- 3. CAMPAIGN DIMENSION TABLE

CREATE TABLE IF NOT EXISTS dim_campaign (
campaign_id SERIAL PRIMARY KEY,
campaign_name VARCHAR(200),
campaign_status VARCHAR(50),
ad_set_name VARCHAR(200),
ad_name VARCHAR(200),
sales_platform VARCHAR(50),
country_funnel VARCHAR(50),
geo_location_segment VARCHAR(50)
);

-- Populate campaign dimension
INSERT INTO dim_campaign (
campaign_name,
campaign_status,
ad_set_name,
ad_name,
sales_platform,
country_funnel,
geo_location_segment
)
SELECT DISTINCT
s.campaign_name,
s.campaign_effective_status,
s.ad_set_name,
s.ad_name,
s.data_source_name,
s.country_funnel,
s.geo_location_segment
FROM staging_ads s
WHERE s.campaign_name IS NOT NULL;

select * from dim_campaign;



-- 4. FACT TABLE (ADS PERFORMANCE)

CREATE TABLE IF NOT EXISTS fact_ads (
date_id DATE,
campaign_id INT,
amount_spent NUMERIC,
fb_spent_funnel NUMERIC,
impressions INT,
clicks INT,
link_clicks INT,
landing_page_views INT,
adds_to_cart INT,
checkouts_initiated INT,
adds_payment_info INT,
purchases INT,
purchase_value NUMERIC,
ctr NUMERIC,
cpm NUMERIC,
cpc NUMERIC,
roi NUMERIC,
PRIMARY KEY (date_id, campaign_id),
FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
FOREIGN KEY (campaign_id) REFERENCES dim_campaign(campaign_id)
);


-- 5. LOAD FACT TABLE
INSERT INTO fact_ads (
    date_id,
    campaign_id,
    amount_spent,
    fb_spent_funnel,
    impressions,
    clicks,
    link_clicks,
    landing_page_views,
    adds_to_cart,
    checkouts_initiated,
    adds_payment_info,
    purchases,
    purchase_value,
    ctr,
    cpm,
    cpc,
    roi
)
SELECT
    TO_DATE(s.date,'DD/MM/YYYY'),
    c.campaign_id,
    SUM(s.amount_spent_inr),
    SUM(s.fb_spent_funnel_inr),
    SUM(s.impressions),
    SUM(s.clicks_all),
    SUM(s.link_clicks),
    SUM(s.landing_page_views),
    SUM(s.adds_to_cart),
    SUM(s.checkouts_initiated),
    SUM(s.adds_of_payment_info),
    SUM(s.purchases),
    SUM(s.purchases_conversion_value_inr),
    AVG(s.ctr),
    AVG(s.cpm),
    AVG(s.cpc),
    AVG(s.roas)
FROM staging_ads s
JOIN dim_campaign c
ON s.campaign_name = c.campaign_name
AND s.ad_set_name = c.ad_set_name
AND s.ad_name = c.ad_name
AND s.geo_location_segment = c.geo_location_segment
WHERE s.date IS NOT NULL
GROUP BY s.date, c.campaign_id;

select * from fact_ads;

-- 5. INDEXES (PERFORMANCE OPTIMIZATION)
-- Fast time filtering (Power BI slicers)
CREATE INDEX idx_fact_date ON fact_ads(date_id);

-- Faster joins
CREATE INDEX idx_fact_campaign ON fact_ads(campaign_id);

-- Platform filtering
CREATE INDEX idx_campaign_platform ON dim_campaign(sales_platform);

-- Region filtering
CREATE INDEX idx_campaign_region ON dim_campaign(geo_location_segment);

-- Campaign filtering
CREATE INDEX idx_campaign_name ON dim_campaign(campaign_name);


--POWER BI QUERY (AGGREGATED PERFORMANCE)
-- 1. MAIN DASHBOARD VIEW (Overall Performance)
--for: KPI cards + trend charts
SELECT
    d.year,
    d.month,
    c.sales_platform AS platform,
    c.geo_location_segment AS region,
    round(SUM(f.amount_spent),2) AS total_spend,
    SUM(f.impressions) AS total_impressions,
    SUM(f.clicks) AS total_clicks,
    SUM(f.purchases) AS total_purchases,
    SUM(f.purchase_value) AS revenue
FROM fact_ads f
JOIN dim_date d ON f.date_id = d.date_id
JOIN dim_campaign c ON f.campaign_id = c.campaign_id
GROUP BY
    d.year,
    d.month,
    c.sales_platform,
    c.geo_location_segment
ORDER BY d.year, d.month;

--🔹 2. PLATFORM PERFORMANCE
SELECT
    c.sales_platform AS platform,
    SUM(f.amount_spent) AS spend,
    SUM(f.purchase_value) AS revenue,
    CASE 
        WHEN SUM(f.amount_spent) > 0 
        THEN round((SUM(f.purchase_value) - SUM(f.amount_spent)) / SUM(f.amount_spent),2)
        ELSE 0 
    END AS roi
FROM fact_ads f
JOIN dim_campaign c ON f.campaign_id = c.campaign_id
where  c.sales_platform is not null
GROUP BY c.sales_platform
ORDER BY roi DESC;

--3. CHANNEL PERFORMANCE (Ad Set Level)
SELECT
    c.ad_set_name AS channel,
    SUM(f.impressions) AS impressions,
    SUM(f.clicks) AS clicks,
    SUM(f.purchases) AS purchases,
    CASE 
        WHEN SUM(f.impressions) > 0 
        THEN round(SUM(f.clicks)::NUMERIC / SUM(f.impressions),2)
        ELSE 0 
    END AS ctr
FROM fact_ads f
JOIN dim_campaign c ON f.campaign_id = c.campaign_id
GROUP BY c.ad_set_name
ORDER BY ctr DESC;

--4. REGION PERFORMANCE
SELECT
    c.geo_location_segment AS region,
    round(SUM(f.amount_spent),2) AS spend,
    SUM(f.purchase_value) AS revenue,
    SUM(f.purchases) AS purchases
FROM fact_ads f
JOIN dim_campaign c ON f.campaign_id = c.campaign_id
GROUP BY c.geo_location_segment
ORDER BY revenue DESC;

--5. FULL COMBINATION (Platform + Channel + Region + Month)
SELECT
    d.year,
    d.month,
    c.sales_platform AS platform,
    c.ad_set_name AS channel,
    c.geo_location_segment AS region,
    round(SUM(f.amount_spent),2) AS total_spend,
    SUM(f.purchase_value) AS revenue,
    SUM(f.purchases) AS purchases
FROM fact_ads f
JOIN dim_date d ON f.date_id = d.date_id
JOIN dim_campaign c ON f.campaign_id = c.campaign_id
GROUP BY
    d.year,
    d.month,
    c.sales_platform,
    c.ad_set_name,
    c.geo_location_segment
ORDER BY d.year, d.month;
