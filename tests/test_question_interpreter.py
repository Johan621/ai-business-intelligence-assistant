"""
Unit tests for deterministic question interpretation and safety filters.
"""

import pytest
from app.question_interpreter import Intent, extract_months_from_query, interpret_question


def test_extract_months_various_formats():
    """Verify regex and month name extraction into ISO YYYY-MM."""
    assert extract_months_from_query("January and February 2026") == ["2026-01", "2026-02"]
    assert extract_months_from_query("compare 2026-03 with 2026-04") == ["2026-03", "2026-04"]
    assert extract_months_from_query("between Mar and Apr 2026") == ["2026-03", "2026-04"]
    assert extract_months_from_query("compare 05-2026 and 06-2026") == ["2026-05", "2026-06"]


def test_total_revenue_variations():
    """Verify total revenue intent recognition across phrasing variations."""
    queries = [
        "What is the total revenue?",
        "What is our total revenue?",
        "What is the overall revenue?",
        "How much total sales have we made?",
        "Show total net sales",
        "calculate overall revenue"
    ]
    for q in queries:
        plan = interpret_question(q)
        assert plan["intent"] == Intent.TOTAL_REVENUE.value
        assert plan["is_supported"] is True
        assert plan["function_name"] == "get_total_revenue"


def test_highest_revenue_product_variations():
    """Verify product ranking intent recognition."""
    queries = [
        "Which product generated the highest revenue?",
        "Which product performed best?",
        "Top selling product by revenue",
        "What is our best product?",
        "Which item generated the most revenue?"
    ]
    for q in queries:
        plan = interpret_question(q)
        assert plan["intent"] == Intent.HIGHEST_REVENUE_PRODUCT.value
        assert plan["is_supported"] is True
        assert plan["function_name"] == "get_highest_revenue_product"


def test_monthly_revenue_trend_variations():
    """Verify monthly trend intent recognition."""
    queries = [
        "What is the monthly revenue trend?",
        "Show sales month by month.",
        "Monthly revenue breakdown",
        "What is our monthly sales trend?",
        "Revenue over time"
    ]
    for q in queries:
        plan = interpret_question(q)
        assert plan["intent"] == Intent.MONTHLY_REVENUE_TREND.value
        assert plan["is_supported"] is True
        assert plan["function_name"] == "get_monthly_revenue_trend"


def test_highest_revenue_region_variations():
    """Verify regional performance intent recognition."""
    queries = [
        "Which region generated the highest sales?",
        "Which region performed best?",
        "Top region by revenue",
        "Which area had the highest sales?",
        "Where did we sell the most?"
    ]
    for q in queries:
        plan = interpret_question(q)
        assert plan["intent"] == Intent.HIGHEST_REVENUE_REGION.value
        assert plan["is_supported"] is True
        assert plan["function_name"] == "get_highest_revenue_region"


def test_month_to_month_comparison_variations():
    """Verify period comparison with explicit month extraction."""
    q1 = "How did revenue change between January and February 2026?"
    p1 = interpret_question(q1)
    assert p1["intent"] == Intent.MONTH_TO_MONTH_COMPARISON.value
    assert p1["is_supported"] is True
    assert p1["parameters"] == {"month1": "2026-01", "month2": "2026-02"}

    q2 = "Compare 2026-03 and 2026-04"
    p2 = interpret_question(q2)
    assert p2["intent"] == Intent.MONTH_TO_MONTH_COMPARISON.value
    assert p2["parameters"] == {"month1": "2026-03", "month2": "2026-04"}


def test_month_to_month_generic_question():
    """Verify question 5 literal wording matches and provides default months."""
    q = "How did revenue change between two months?"
    p = interpret_question(q)
    assert p["intent"] == Intent.MONTH_TO_MONTH_COMPARISON.value
    assert p["is_supported"] is True
    assert "month1" in p["parameters"]
    assert "month2" in p["parameters"]


def test_month_to_month_single_month_clarification():
    """Verify user is prompted for second month if only one month is given."""
    q = "Compare January 2026"
    p = interpret_question(q)
    assert p["intent"] == Intent.MONTH_TO_MONTH_COMPARISON.value
    assert p["is_supported"] is False
    assert "provide two months" in p["clarification_message"].lower()


def test_empty_question():
    """Verify empty or whitespace-only questions are rejected gracefully."""
    for empty_input in ["", "   ", "\t\n"]:
        res = interpret_question(empty_input)
        assert res["intent"] == Intent.UNKNOWN.value
        assert res["is_supported"] is False
        assert "enter a business question" in res["clarification_message"].lower()


def test_unsupported_question():
    """Verify out-of-scope questions return clear guidance."""
    res = interpret_question("What is the weather in Paris?")
    assert res["intent"] == Intent.UNKNOWN.value
    assert res["is_supported"] is False
    assert "couldn't identify a supported sales analytics question" in res["clarification_message"].lower()


def test_sql_injection_rejection():
    """Verify malicious SQL payloads are blocked without execution."""
    attacks = [
        "DROP TABLE sales_transactions;",
        "SELECT * FROM sales_transactions WHERE 1=1;",
        "DELETE FROM sales_transactions;",
        "'; UPDATE sales_transactions SET net_revenue=999999; --"
    ]
    for attack in attacks:
        res = interpret_question(attack)
        assert res["intent"] == Intent.UNSAFE_QUERY.value
        assert res["is_supported"] is False
        assert "Destructive operations" in res["clarification_message"]


def test_destructive_requests_rejected():
    """Regression test: verify destructive natural-language and SQL commands are rejected."""
    destructive_queries = [
        "Delete all sales records",
        "Drop the database",
        "Remove every transaction",
        "wipe all records",
        "clear all data",
        "destroy the database",
        "truncate table sales_transactions",
        "remove all transactions"
    ]
    for q in destructive_queries:
        plan = interpret_question(q)
        assert plan["intent"] == Intent.UNSAFE_QUERY.value
        assert plan["is_supported"] is False
        assert plan["function_name"] is None
        assert "Destructive operations" in plan["clarification_message"]


def test_unrelated_text_does_not_return_total_revenue():
    """Regression test: verify random text and destructive requests never return total_revenue."""
    non_revenue_queries = [
        "Delete all sales records",
        "Drop the database",
        "Remove every transaction",
        "Random unrelated text",
        "Who is the manager?",
        "Apples vs oranges",
        "Car sales in Chicago",
        "Tell me a joke"
    ]
    for q in non_revenue_queries:
        plan = interpret_question(q)
        assert plan["intent"] != Intent.TOTAL_REVENUE.value, f"Query '{q}' incorrectly matched total_revenue"

