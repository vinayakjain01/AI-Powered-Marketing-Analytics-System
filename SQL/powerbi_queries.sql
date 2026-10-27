-- Reference queries behind the Power BI visuals (not part of the build). Moved out of schema.sql.
SET search_path TO campaign_data;

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
