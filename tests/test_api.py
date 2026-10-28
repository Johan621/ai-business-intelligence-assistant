"""
Integration tests for FastAPI REST API endpoints using TestClient.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.data_loader import ingest_sales_csv

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    """Ensure database has data for API tests."""
    ingest_sales_csv()


def test_health_endpoint():
    """Verify /health returns 200 and healthy database status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == "AI Business Intelligence Assistant"
    assert data["database_connected"] is True
    assert data["eligible_transactions"] > 0


def test_examples_endpoint():
    """Verify /examples returns pre-configured questions."""
    response = client.get("/examples")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 5
    categories = [item["category"] for item in data]
    assert "Total Revenue" in categories
    assert "Product Performance" in categories


def test_summary_endpoint():
    """Verify /summary returns data quality metrics and excluded records."""
    response = client.get("/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records_processed"] == 51
    assert data["eligible_completed_sales"] == 48
    assert data["excluded_records_count"] == 3
    assert len(data["excluded_records"]) == 3


def test_ask_total_revenue():
    """Test POST /ask with total revenue question."""
    payload = {"question": "What is the total revenue?"}
    response = client.post("/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["recognized_intent"] == "total_revenue"
    assert "supporting_figures" in data
    assert data["supporting_figures"]["total_net_revenue"] > 0
    assert len(data["data_quality_caveats"]) > 0


def test_ask_highest_revenue_product():
    """Test POST /ask with highest revenue product question."""
    payload = {"question": "Which product generated the highest revenue?"}
    response = client.post("/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["recognized_intent"] == "highest_revenue_product"
    assert "top_product" in data["supporting_figures"]


def test_ask_monthly_revenue_trend():
    """Test POST /ask with monthly revenue trend question."""
    payload = {"question": "What is the monthly revenue trend?"}
    response = client.post("/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["recognized_intent"] == "monthly_revenue_trend"
    assert "peak_month" in data["supporting_figures"]


def test_ask_highest_revenue_region():
    """Test POST /ask with highest revenue region question."""
    payload = {"question": "Which region generated the highest sales?"}
    response = client.post("/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["recognized_intent"] == "highest_revenue_region"
    assert "top_region" in data["supporting_figures"]


def test_ask_month_to_month_comparison():
    """Test POST /ask with period comparison question."""
    payload = {"question": "How did revenue change between January and February 2026?"}
    response = client.post("/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["recognized_intent"] == "month_to_month_comparison"
    figs = data["supporting_figures"]
    assert "absolute_change" in figs
    assert "percentage_change" in figs
    assert figs["month1"] == "2026-01"
    assert figs["month2"] == "2026-02"


def test_ask_empty_question_returns_400():
    """Verify empty query string returns 400 Bad Request."""
    response = client.post("/ask", json={"question": "   "})
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_ask_sql_injection_returns_400():
    """Verify SQL injection attempt returns 400 Bad Request with explanation."""
    response = client.post("/ask", json={"question": "DROP TABLE sales_transactions;"})
    assert response.status_code == 400
    assert "Destructive operations" in response.json()["detail"]


def test_ask_unknown_question():
    """Verify unknown business question returns structured explanation."""
    response = client.post("/ask", json={"question": "What is the capital of France?"})
    assert response.status_code == 200
    data = response.json()
    assert data["recognized_intent"] == "unknown"
    assert "couldn't identify a supported sales analytics question" in data["human_readable_answer"].lower()


def test_ask_destructive_requests_rejected():
    """Regression test: verify destructive requests return 400 Bad Request."""
    destructive_queries = [
        "Delete all sales records",
        "Drop the database",
        "Remove every transaction"
    ]
    for q in destructive_queries:
        response = client.post("/ask", json={"question": q})
        assert response.status_code == 400, f"Query '{q}' was not rejected with 400"
        assert "Destructive operations" in response.json()["detail"]


def test_rejected_requests_do_not_modify_database():
    """Regression test: verify rejected destructive requests make zero changes to database."""
    from app.database import get_connection

    conn = get_connection()
    count_before = conn.execute("SELECT COUNT(*) FROM sales_transactions;").fetchone()[0]
    tables_before = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    conn.close()

    # Attempt multiple destructive operations
    client.post("/ask", json={"question": "Delete all sales records"})
    client.post("/ask", json={"question": "Drop the database"})
    client.post("/ask", json={"question": "Remove every transaction"})
    client.post("/ask", json={"question": "DROP TABLE sales_transactions;"})
    client.post("/ask", json={"question": "DELETE FROM sales_transactions;"})

    conn = get_connection()
    count_after = conn.execute("SELECT COUNT(*) FROM sales_transactions;").fetchone()[0]
    tables_after = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    conn.close()

    assert count_after == count_before
    assert count_after > 0
    assert tables_after == tables_before
    assert "sales_transactions" in tables_after


def test_random_unrelated_text_does_not_return_total_revenue():
    """Regression test: verify random text never triggers total_revenue analytics."""
    queries = [
        "What is the weather in New York?",
        "Tell me a joke",
        "Who is the CEO?",
        "Car sales in Chicago"
    ]
    for q in queries:
        response = client.post("/ask", json={"question": q})
        assert response.status_code == 200
        data = response.json()
        assert data["recognized_intent"] == "unknown"
        assert data["recognized_intent"] != "total_revenue"

