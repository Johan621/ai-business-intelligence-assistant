"""
Unit tests for CSV ingestion, data quality rules, and idempotency.
Tests business rules against controlled CSV fixtures.
"""

import os
import sqlite3
import tempfile
import pytest

from app.database import init_db
from app.data_loader import clean_and_validate_record, ingest_sales_csv


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_missing_unit_price_exclusion():
    """Verify that a row with missing unit price is excluded and NOT defaulted to zero."""
    seen_ids = set()
    raw = {
        "Transaction_Id": "TXN_TEST1",
        "Order_date": "10-01-2026",
        "Product": "Laptop",
        "Category": "Electronics",
        "Region": "North",
        "Sales_channel": "Online",
        "Quantity": "5",
        "Unit_price": "",  # missing!
        "Discount_amount": "0",
        "Status": "Completed"
    }
    valid, excluded = clean_and_validate_record(raw, seen_ids)
    assert valid is None
    assert excluded is not None
    assert excluded["transaction_id"] == "TXN_TEST1"
    assert "Missing unit price" in excluded["exclusion_reason"]


def test_zero_quantity_exclusion():
    """Verify transactions with quantity <= 0 are excluded."""
    seen_ids = set()
    raw_zero = {
        "Transaction_Id": "TXN_ZERO",
        "Order_date": "10-01-2026",
        "Product": "Laptop",
        "Category": "Electronics",
        "Region": "North",
        "Sales_channel": "Online",
        "Quantity": "0",
        "Unit_price": "1000",
        "Discount_amount": "0",
        "Status": "Completed"
    }
    valid, excluded = clean_and_validate_record(raw_zero, seen_ids)
    assert valid is None
    assert excluded is not None
    assert "Quantity must be greater than zero" in excluded["exclusion_reason"]


def test_returned_status_exclusion():
    """Verify returned transactions are excluded from completed sales."""
    seen_ids = set()
    raw_ret = {
        "Transaction_Id": "TXN_RET",
        "Order_date": "10-01-2026",
        "Product": "Monitor",
        "Category": "Electronics",
        "Region": "West",
        "Sales_channel": "Retail",
        "Quantity": "2",
        "Unit_price": "5000",
        "Discount_amount": "0",
        "Status": "Returned"
    }
    valid, excluded = clean_and_validate_record(raw_ret, seen_ids)
    assert valid is None
    assert excluded is not None
    assert "Returned" in excluded["exclusion_reason"]


def test_valid_record_net_revenue_calculation():
    """Verify Net Revenue = (Quantity * Unit_price) - Discount_amount."""
    seen_ids = set()
    raw_valid = {
        "Transaction_Id": "TXN_OK",
        "Order_date": "15-02-2026",
        "Product": "Chair",
        "Category": "Furniture",
        "Region": "South",
        "Sales_channel": "Online",
        "Quantity": "4",
        "Unit_price": "2500",
        "Discount_amount": "500",
        "Status": "Completed"
    }
    valid, excluded = clean_and_validate_record(raw_valid, seen_ids)
    assert excluded is None
    assert valid is not None
    # (4 * 2500) - 500 = 9500
    assert valid["net_revenue"] == 9500.0
    assert valid["order_date"] == "2026-02-15"
    assert valid["transaction_id"] == "TXN_OK"


def test_repeated_csv_ingestion_idempotence(temp_db):
    """Verify that multiple CSV ingestions do not duplicate transactions."""
    csv_content = """Transaction_Id,Order_date,Product,Category,Region,Sales_channel,Quantity,Unit_price,Discount_amount,Status
TXN1,01-01-2026,Laptop,Electronics,North,Online,1,1000,0,Completed
TXN2,02-01-2026,Mouse,Accessories,South,Retail,2,100,0,Completed
TXN3,03-01-2026,Bad,Electronics,West,Retail,1,,0,Completed
"""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as f:
        f.write(csv_content)
        temp_csv = f.name

    try:
        # First ingestion
        res1 = ingest_sales_csv(csv_path=temp_csv, db_path=temp_db)
        assert res1["valid_rows_count"] == 2
        assert res1["excluded_rows_count"] == 1

        conn = sqlite3.connect(temp_db)
        count1 = conn.execute("SELECT COUNT(*) FROM sales_transactions;").fetchone()[0]
        exc_count1 = conn.execute("SELECT COUNT(*) FROM excluded_transactions;").fetchone()[0]
        conn.close()

        assert count1 == 2
        assert exc_count1 == 1

        # Second ingestion (repeated import)
        res2 = ingest_sales_csv(csv_path=temp_csv, db_path=temp_db)
        assert res2["valid_rows_count"] == 2

        conn = sqlite3.connect(temp_db)
        count2 = conn.execute("SELECT COUNT(*) FROM sales_transactions;").fetchone()[0]
        exc_count2 = conn.execute("SELECT COUNT(*) FROM excluded_transactions;").fetchone()[0]
        conn.close()

        # Counts must be identical (no duplicates!)
        assert count2 == 2
        assert exc_count2 == 1

    finally:
        if os.path.exists(temp_csv):
            os.remove(temp_csv)

