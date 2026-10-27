"""Builds the real star schema on a THROWAWAY Postgres and checks the data-quality fixes.

Skipped unless TEST_DATABASE_URL is set. WARNING: build_warehouse drops and recreates the
campaign_data tables, so point this at an empty scratch database, never at your real warehouse.
"""
import os

import pytest
from sqlalchemy import create_engine, text

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set (Postgres-only test)")


@pytest.fixture(scope="module")
def engine():
    from pipeline.dburl import normalize_database_url
    from pipeline.warehouse import build_warehouse
    build_warehouse(normalize_database_url(URL))
    return create_engine(normalize_database_url(URL))


def scalar(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar_one()


def test_fact_ads_reconciles_with_staging_no_fan_out(engine):
    staging = scalar(engine, "SELECT SUM(amount_spent_inr) FROM campaign_data.staging_ads")
    fact = scalar(engine, "SELECT SUM(amount_spent) FROM campaign_data.fact_ads")
    assert float(fact) == pytest.approx(float(staging), rel=1e-9)
    assert scalar(engine, "SELECT COUNT(*) FROM campaign_data.fact_ads") <= \
        scalar(engine, "SELECT COUNT(*) FROM campaign_data.staging_ads")


def test_dim_campaign_grain_is_unique(engine):
    assert scalar(engine, """SELECT COUNT(*) FROM (SELECT 1 FROM campaign_data.dim_campaign
        GROUP BY COALESCE(campaign_name,''), COALESCE(ad_set_name,''), COALESCE(ad_name,''),
                 COALESCE(geo_location_segment,''), COALESCE(sales_platform,'') HAVING COUNT(*) > 1) d""") == 0


def test_month_name_is_trimmed_so_filters_work(engine):
    assert scalar(engine, "SELECT COUNT(*) FROM campaign_data.dim_date WHERE month_name = 'March'") == 31 * 5


def test_data_is_in_q1_2026_after_date_fix(engine):
    assert scalar(engine, "SELECT COUNT(DISTINCT d.month) FROM campaign_data.fact_ads f "
                          "JOIN campaign_data.dim_date d USING (date_id)") == 3


def test_shopify_loaded_and_no_orphans(engine):
    assert scalar(engine, "SELECT COUNT(*) FROM campaign_data.fact_order_lines") > 0
    assert scalar(engine, "SELECT COUNT(*) FROM campaign_data.fact_order_lines o "
                          "LEFT JOIN campaign_data.dim_product p USING (product_key) WHERE p.product_key IS NULL") == 0


def test_power_bi_view_survives_the_rebuild(engine):
    assert scalar(engine, "SELECT COUNT(*) FROM campaign_data.vw_marketing_performance") > 0
