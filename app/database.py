"""
Database module for AI Business Intelligence Assistant.
Manages SQLite connection lifecycle, schemas, and table initialization.
"""

import os
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sales_bi.db")


def get_db_path() -> str:
    """Return the database path, allowing environment override."""
    return os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Open and return a SQLite database connection with row dictionary access.
    """
    path = db_path or get_db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize SQLite schema for eligible transactions, excluded records,
    and ingestion audit metadata.
    """
    conn = get_connection(db_path)
    try:
        with conn:
            # Table for eligible, completed sales transactions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sales_transactions (
                    transaction_id TEXT PRIMARY KEY,
                    order_date TEXT NOT NULL,
                    product TEXT NOT NULL,
                    category TEXT NOT NULL,
                    region TEXT NOT NULL,
                    sales_channel TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_price REAL NOT NULL,
                    discount_amount REAL NOT NULL DEFAULT 0.0,
                    net_revenue REAL NOT NULL,
                    status TEXT NOT NULL
                );
            """)

            # Table for tracking records excluded by business rules
            conn.execute("""
                CREATE TABLE IF NOT EXISTS excluded_transactions (
                    transaction_id TEXT PRIMARY KEY,
                    order_date TEXT,
                    product TEXT,
                    exclusion_reason TEXT NOT NULL,
                    raw_data TEXT
                );
            """)

            # Table for ingestion execution audit history
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    imported_at TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    total_rows INTEGER NOT NULL,
                    valid_rows INTEGER NOT NULL,
                    excluded_rows INTEGER NOT NULL
                );
            """)

            # Indexes to accelerate analytics queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_order_date ON sales_transactions(order_date);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_product ON sales_transactions(product);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_region ON sales_transactions(region);")
    finally:
        conn.close()

