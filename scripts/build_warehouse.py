"""Load the Olist CSVs into DuckDB and materialise the staging and mart models.

    python scripts/build_warehouse.py            # real Olist data from data/raw/
    python scripts/build_warehouse.py --sample   # generated sample from data/sample/
"""

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nl2sql import config  # noqa: E402

# raw table name -> (Olist file name, columns the staging models rely on)
RAW_FILES = {
    "orders": ("olist_orders_dataset.csv", [
        "order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]),
    "order_items": ("olist_order_items_dataset.csv", [
        "order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value"]),
    "order_payments": ("olist_order_payments_dataset.csv", [
        "order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"]),
    "order_reviews": ("olist_order_reviews_dataset.csv", [
        "review_id", "order_id", "review_score", "review_creation_date"]),
    "products": ("olist_products_dataset.csv", [
        "product_id", "product_category_name", "product_weight_g"]),
    "customers": ("olist_customers_dataset.csv", [
        "customer_id", "customer_unique_id", "customer_city", "customer_state"]),
    "sellers": ("olist_sellers_dataset.csv", [
        "seller_id", "seller_city", "seller_state"]),
    "category_translation": ("product_category_name_translation.csv", [
        "product_category_name", "product_category_name_english"]),
}


def load_raw(con: duckdb.DuckDBPyConnection, source_dir: Path) -> None:
    missing = [f for f, _ in RAW_FILES.values() if not (source_dir / f).exists()]
    if missing:
        sys.exit(
            f"Missing files in {source_dir}:\n  " + "\n  ".join(missing)
            + "\nDownload the Olist dataset (see README) or run with --sample."
        )
    con.execute("create schema raw")
    for table, (filename, required) in RAW_FILES.items():
        # utf-8-sig strips the byte-order mark some Olist files carry in their header
        df = pd.read_csv(source_dir / filename, dtype=str, encoding="utf-8-sig")
        absent = [c for c in required if c not in df.columns]
        if absent:
            sys.exit(f"{filename} is missing columns {absent}; found {list(df.columns)}")
        con.register("df", df)
        con.execute(f"create table raw.{table} as select * from df")
        con.unregister("df")
        print(f"  raw.{table:<26} {len(df):>8,} rows")


def build_models(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("create schema staging")
    for layer, schema in (("staging", "staging"), ("marts", "main")):
        for path in sorted((config.MODELS_DIR / layer).glob("*.sql")):
            con.execute(f"create table {schema}.{path.stem} as {path.read_text()}")
            count = con.execute(f"select count(*) from {schema}.{path.stem}").fetchone()[0]
            print(f"  {schema}.{path.stem:<26} {count:>8,} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", action="store_true", help="build from data/sample/ instead of data/raw/")
    args = parser.parse_args()

    source_dir = config.SAMPLE_DIR if args.sample else config.RAW_DIR
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = config.DB_PATH.with_suffix(".building")
    tmp_path.unlink(missing_ok=True)

    print(f"Building {config.DB_PATH.name} from {source_dir}")
    con = duckdb.connect(str(tmp_path))
    try:
        load_raw(con, source_dir)
        build_models(con)
        con.execute(
            "create table main._build_info as select ? as source, now() as built_at",
            ["sample" if args.sample else "olist"],
        )
    finally:
        con.close()
    # swap in only after a successful build, so a failed build never leaves a half-built warehouse
    tmp_path.replace(config.DB_PATH)
    print("Done.")


if __name__ == "__main__":
    main()
