"""One command to (re)build the warehouse: clean CSVs -> staging -> star schema -> row counts.

    python scripts/build_warehouse.py                      # uses DATABASE_URL from .env
    python scripts/build_warehouse.py --database-url ...   # any Postgres (local, Supabase, Neon)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.warehouse import build_warehouse  # noqa: E402
from pipeline.dburl import normalize_database_url  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", help="Overrides DATABASE_URL.")
    args = ap.parse_args()
    url = normalize_database_url(args.database_url) if args.database_url else None

    result = build_warehouse(url)
    for title, key in (("Campaign cleaning", "campaign_cleaning"), ("Shopify cleaning", "shopify_cleaning")):
        print(f"\n{title}")
        for label, n in result[key]:
            print(f"  {label:<45}{n:>8,}")
    print("\nWarehouse row counts")
    for table, n in result["row_counts"].items():
        print(f"  {table:<45}{n:>8,}")


if __name__ == "__main__":
    main()
