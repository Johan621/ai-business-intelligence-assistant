"""
Unit tests for analytics calculations using isolated temporary databases.
Tests calculations against controlled fixtures rather than hardcoded production totals.
"""

import os
import sqlite3
import tempfile
import pytest

from app.database import init_db
from app.analytics import (
    get_total_revenue,
    get_highest_revenue_product,
    get_monthly_revenue_trend,
    get_highest_revenue_region,
    get_month_to_month_comparison
)


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database initialized with schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def populated_temp_db(temp_db):
    """
    Populate temporary database with known, controlled records:
    - 2026-01-10: TXN1, Laptop, Electronics, North, Online, Qty: 2, Price: 1000, Disc: 100 -> Net: 1900
    - 2026-01-15: TXN2, Mouse, Accessories, South, Retail, Qty: 5, Price: 200, Disc: 0   -> Net: 1000
    - 2026-02-10: TXN3, Laptop, Electronics, North, Retail, Qty: 3, Price: 1000, Disc: 0 -> Net: 3000
    - 2026-02-20: TXN4, Chair, Furniture, South, Online, Qty: 1, Price: 500, Disc: 50   -> Net: 450
    """
    conn = sqlite3.connect(temp_db)
    records = [
        ("TXN1", "2026-01-10", "Laptop", "Electronics", "North", "Online", 2, 1000.0, 100.0, 1900.0, "Completed"),
        ("TXN2", "2026-01-15", "Mouse", "Accessories", "South", "Retail", 5, 200.0, 0.0, 1000.0, "Completed"),
        ("TXN3", "2026-02-10", "Laptop", "Electronics", "North", "Retail", 3, 1000.0, 0.0, 3000.0, "Completed"),
        ("TXN4", "2026-02-20", "Chair", "Furniture", "South", "Online", 1, 500.0, 50.0, 450.0, "Completed"),
    ]
    with conn:
        conn.executemany("""
            INSERT INTO sales_transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, records)
    conn.close()
    return temp_db


def test_total_revenue_calculation(populated_temp_db):
    """Verify total revenue matches exact sum of net revenues in test fixture."""
    res = get_total_revenue(populated_temp_db)
    figs = res["supporting_figures"]

    # 1900 + 1000 + 3000 + 450 = 6350.0
    assert figs["total_net_revenue"] == 6350.0
    # Gross: 2000 + 1000 + 3000 + 500 = 6500.0
    assert figs["gross_revenue"] == 6500.0
    # Discounts: 100 + 50 = 150.0
    assert figs["total_discounts"] == 150.0
    # Units: 2 + 5 + 3 + 1 = 11
    assert figs["total_units_sold"] == 11
    assert figs["transaction_count"] == 4
    assert figs["average_order_value"] == round(6350.0 / 4, 2)


def test_highest_revenue_product(populated_temp_db):
    """Verify product ranking and identification of top performer."""
    res = get_highest_revenue_product(populated_temp_db)
    figs = res["supporting_figures"]

    # Laptop revenue: 1900 + 3000 = 4900
    assert figs["top_product"] == "Laptop"
    assert figs["top_revenue"] == 4900.0
    assert figs["is_tie"] is False

    table = res["supporting_table"]
    assert len(table) == 3
    assert table[0]["product"] == "Laptop"
    assert table[1]["product"] == "Mouse"
    assert table[2]["product"] == "Chair"


def test_highest_revenue_product_tie(temp_db):
    """Verify handling when two top products generate identical revenue."""
    conn = sqlite3.connect(temp_db)
    with conn:
        conn.execute("INSERT INTO sales_transactions VALUES ('T1', '2026-01-01', 'A', 'Cat', 'Reg', 'On', 1, 100, 0, 100, 'Completed');")
        conn.execute("INSERT INTO sales_transactions VALUES ('T2', '2026-01-02', 'B', 'Cat', 'Reg', 'On', 1, 100, 0, 100, 'Completed');")
    conn.close()

    res = get_highest_revenue_product(temp_db)
    assert res["supporting_figures"]["is_tie"] is True
    assert "tie" in res["human_readable_answer"].lower()


def test_monthly_revenue_trend(populated_temp_db):
    """Verify monthly aggregation groups by YYYY-MM correctly."""
    res = get_monthly_revenue_trend(populated_temp_db)
    figs = res["supporting_figures"]
    table = res["supporting_table"]

    # Jan 2026: 1900 + 1000 = 2900.0
    # Feb 2026: 3000 + 450 = 3450.0
    assert figs["months_count"] == 2
    assert figs["peak_revenue"] == 3450.0
    assert figs["lowest_revenue"] == 2900.0
    assert table[0]["month"] == "2026-01"
    assert table[0]["total_revenue"] == 2900.0
    assert table[1]["month"] == "2026-02"
    assert table[1]["total_revenue"] == 3450.0


def test_highest_revenue_region(populated_temp_db):
    """Verify regional aggregation identifies top region."""
    res = get_highest_revenue_region(populated_temp_db)
    figs = res["supporting_figures"]

    # North: 1900 + 3000 = 4900
    # South: 1000 + 450 = 1450
    assert figs["top_region"] == "North"
    assert figs["top_revenue"] == 4900.0
    assert figs["top_transaction_count"] == 2


def test_month_to_month_comparison_growth(populated_temp_db):
    """Verify comparison with positive growth."""
    res = get_month_to_month_comparison("2026-01", "2026-02", populated_temp_db)
    figs = res["supporting_figures"]

    # Jan: 2900, Feb: 3450 -> Diff: +550
    assert figs["month1_revenue"] == 2900.0
    assert figs["month2_revenue"] == 3450.0
    assert figs["absolute_change"] == 550.0
    assert figs["percentage_change"] == round((550.0 / 2900.0) * 100, 2)
    assert figs["direction"] == "increased"


def test_month_to_month_comparison_zero_base(temp_db):
    """Verify safe division when base month has 0 revenue."""
    conn = sqlite3.connect(temp_db)
    with conn:
        conn.execute("INSERT INTO sales_transactions VALUES ('T1', '2026-02-01', 'A', 'C', 'R', 'O', 1, 500, 0, 500, 'Completed');")
    conn.close()

    res = get_month_to_month_comparison("2026-01", "2026-02", temp_db)
    figs = res["supporting_figures"]
    assert figs["month1_revenue"] == 0.0
    assert figs["month2_revenue"] == 500.0
    assert figs["absolute_change"] == 500.0
    assert figs["percentage_change"] == 100.0


def test_empty_database_analytics(temp_db):
    """Verify graceful handling when database has zero records."""
    total = get_total_revenue(temp_db)
    assert total["supporting_figures"]["total_net_revenue"] == 0.0
    assert total["supporting_figures"]["transaction_count"] == 0

    product = get_highest_revenue_product(temp_db)
    assert product["supporting_figures"]["top_product"] is None

    trend = get_monthly_revenue_trend(temp_db)
    assert trend["supporting_figures"]["trend"] == []

    region = get_highest_revenue_region(temp_db)
    assert region["supporting_figures"]["top_region"] is None

