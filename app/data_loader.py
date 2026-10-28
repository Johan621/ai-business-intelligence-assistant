"""
CSV Ingestion and Data Quality Module for AI Business Intelligence Assistant.

Applies strict business policies for sales analytics:
- Parses DD-MM-YYYY dates into ISO YYYY-MM-DD format.
- Excludes non-completed / returned orders from completed sales revenue.
- Excludes records with zero or negative quantities.
- Excludes records with missing or invalid unit prices (never defaults to zero).
- Computes Net Revenue = (Quantity * Unit_price) - Discount_amount.
- Ensures idempotent imports to avoid duplicate records.
- Retains full audit log of excluded records and reasons.
"""

import csv
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.database import get_connection, init_db, DEFAULT_DB_PATH

DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "ai_bi_assistant_sales_data - GET.csv"
)

COLUMN_MAPPING = {
    "transaction_id": "transaction_id",
    "order_date": "order_date",
    "product": "product",
    "category": "category",
    "region": "region",
    "sales_channel": "sales_channel",
    "quantity": "quantity",
    "unit_price": "unit_price",
    "discount_amount": "discount_amount",
    "status": "status"
}


def normalize_column_name(col: str) -> str:
    """Normalize column header to snake_case."""
    return col.strip().lower().replace(" ", "_")


def parse_date(date_val: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse DD-MM-YYYY date into ISO format (YYYY-MM-DD).
    Returns (iso_date_string, error_message).
    """
    if date_val is None or (isinstance(date_val, float) and pd.isna(date_val)):
        return None, "Missing order date"
    date_str = str(date_val).strip()
    if not date_str:
        return None, "Missing order date"

    # Try common formats, strictly expecting DD-MM-YYYY first
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d"), None
        except ValueError:
            continue
    return None, f"Invalid date format '{date_str}', expected DD-MM-YYYY"


def clean_and_validate_record(
    raw_row: Dict[str, Any],
    seen_ids: set
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Validate a single transaction record against business and revenue rules.
    
    Returns:
        (valid_record_dict, None) if eligible, or
        (None, excluded_record_dict) with exclusion reasons.
    """
    reasons = []

    # 1. Normalize keys
    normalized = {}
    for k, v in raw_row.items():
        normalized[normalize_column_name(k)] = v

    raw_tid = normalized.get("transaction_id")
    tid = str(raw_tid).strip() if raw_tid is not None and not pd.isna(raw_tid) else ""

    if not tid:
        reasons.append("Missing transaction ID")
    elif tid in seen_ids:
        reasons.append(f"Duplicate transaction ID '{tid}'")

    # 2. Date validation
    iso_date, date_err = parse_date(normalized.get("order_date"))
    if date_err:
        reasons.append(date_err)

    # 3. Product & Category & Region
    product = str(normalized.get("product", "") or "").strip()
    if not product or product.lower() in ("nan", "none", ""):
        reasons.append("Missing product name")

    category = str(normalized.get("category", "") or "").strip()
    region = str(normalized.get("region", "") or "").strip()
    sales_channel = str(normalized.get("sales_channel", "") or "").strip()

    # 4. Status validation
    status = str(normalized.get("status", "") or "").strip()
    if status.lower() == "returned":
        reasons.append("Status is 'Returned' (returned orders are excluded from completed sales revenue)")
    elif status.lower() != "completed":
        reasons.append(f"Invalid status '{status}' (only 'Completed' transactions are eligible)")

    # 5. Quantity validation
    raw_qty = normalized.get("quantity")
    qty = None
    if raw_qty is None or (isinstance(raw_qty, float) and pd.isna(raw_qty)) or str(raw_qty).strip() == "":
        reasons.append("Missing quantity")
    else:
        try:
            qty = int(float(str(raw_qty).strip()))
            if qty <= 0:
                reasons.append(f"Quantity must be greater than zero (found: {qty})")
        except (ValueError, TypeError):
            reasons.append(f"Invalid quantity value '{raw_qty}'")

    # 6. Unit price validation (CRITICAL: Never replace with 0)
    raw_price = normalized.get("unit_price")
    price = None
    if raw_price is None or (isinstance(raw_price, float) and pd.isna(raw_price)) or str(raw_price).strip() == "":
        reasons.append("Missing unit price (cannot determine revenue; price cannot be assumed)")
    else:
        try:
            price = float(str(raw_price).strip())
            if price <= 0:
                reasons.append(f"Unit price must be strictly positive (found: {price})")
        except (ValueError, TypeError):
            reasons.append(f"Invalid unit price value '{raw_price}'")

    # 7. Discount amount validation
    raw_disc = normalized.get("discount_amount")
    disc = 0.0
    if raw_disc is not None and not (isinstance(raw_disc, float) and pd.isna(raw_disc)) and str(raw_disc).strip() != "":
        try:
            disc = float(str(raw_disc).strip())
            if disc < 0:
                reasons.append(f"Discount amount cannot be negative (found: {disc})")
        except (ValueError, TypeError):
            reasons.append(f"Invalid discount amount '{raw_disc}'")

    # If any exclusion reasons exist, return exclusion record
    if reasons:
        excluded = {
            "transaction_id": tid or f"UNKNOWN_{len(seen_ids)+1}",
            "order_date": iso_date or str(normalized.get("order_date")),
            "product": product or "Unknown",
            "exclusion_reason": "; ".join(reasons),
            "raw_data": json.dumps(raw_row, default=str)
        }
        return None, excluded

    # Track seen transaction ID for duplicate detection
    seen_ids.add(tid)

    # Calculate net revenue
    net_revenue = round((qty * price) - disc, 2)

    valid_record = {
        "transaction_id": tid,
        "order_date": iso_date,
        "product": product,
        "category": category,
        "region": region,
        "sales_channel": sales_channel,
        "quantity": qty,
        "unit_price": round(price, 2),
        "discount_amount": round(disc, 2),
        "net_revenue": net_revenue,
        "status": status
    }
    return valid_record, None


def ingest_sales_csv(
    csv_path: Optional[str] = None,
    db_path: Optional[str] = None,
    overwrite: bool = True
) -> Dict[str, Any]:
    """
    Ingest sales CSV into SQLite, applying data quality rules and idempotency.

    Args:
        csv_path: Path to the sales CSV. Defaults to dataset in data/.
        db_path: Target SQLite database path.
        overwrite: When True, cleanly refreshes tables to ensure idempotent state.

    Returns:
        Summary dict containing ingestion metrics and exclusion details.
    """
    target_csv = csv_path or DEFAULT_CSV_PATH
    if not os.path.exists(target_csv):
        raise FileNotFoundError(f"Sales data CSV not found at: {target_csv}")

    init_db(db_path)
    conn = get_connection(db_path)

    seen_ids = set()
    valid_records: List[Dict[str, Any]] = []
    excluded_records: List[Dict[str, Any]] = []

    # Read CSV without altering source
    with open(target_csv, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            valid, excluded = clean_and_validate_record(row, seen_ids)
            if valid:
                valid_records.append(valid)
            else:
                excluded_records.append(excluded)

    total_rows = len(valid_records) + len(excluded_records)

    with conn:
        if overwrite:
            conn.execute("DELETE FROM sales_transactions;")
            conn.execute("DELETE FROM excluded_transactions;")

        # Insert valid records idempotently
        conn.executemany("""
            INSERT OR REPLACE INTO sales_transactions (
                transaction_id, order_date, product, category, region,
                sales_channel, quantity, unit_price, discount_amount,
                net_revenue, status
            ) VALUES (
                :transaction_id, :order_date, :product, :category, :region,
                :sales_channel, :quantity, :unit_price, :discount_amount,
                :net_revenue, :status
            );
        """, valid_records)

        # Insert excluded records idempotently
        conn.executemany("""
            INSERT OR REPLACE INTO excluded_transactions (
                transaction_id, order_date, product, exclusion_reason, raw_data
            ) VALUES (
                :transaction_id, :order_date, :product, :exclusion_reason, :raw_data
            );
        """, excluded_records)

        # Record audit log
        conn.execute("""
            INSERT INTO ingestion_metadata (
                imported_at, source_file, total_rows, valid_rows, excluded_rows
            ) VALUES (
                datetime('now'), ?, ?, ?, ?
            );
        """, (os.path.basename(target_csv), total_rows, len(valid_records), len(excluded_records)))

    conn.close()

    return {
        "status": "success",
        "source_file": os.path.basename(target_csv),
        "total_rows": total_rows,
        "valid_rows_count": len(valid_records),
        "excluded_rows_count": len(excluded_records),
        "excluded_records": excluded_records
    }


if __name__ == "__main__":
    result = ingest_sales_csv()
    print("CSV Ingestion Summary:")
    print(f"Total Rows Processed: {result['total_rows']}")
    print(f"Valid Transactions Stored: {result['valid_rows_count']}")
    print(f"Excluded Records: {result['excluded_rows_count']}")
    for exc in result["excluded_records"]:
        print(f" - {exc['transaction_id']}: {exc['exclusion_reason']}")

