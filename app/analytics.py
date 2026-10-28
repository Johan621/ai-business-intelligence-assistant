"""
Analytics engine for AI Business Intelligence Assistant.

All calculations use parameterized SQL against SQLite to ensure accurate,
reproducible, and safe data aggregation without hardcoding numbers.
"""

from calendar import month_name
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.database import get_connection


def format_amount(amount: float) -> str:
    """Format floating point number as standard two-decimal number (currency unspecified)."""
    return f"{amount:,.2f}"


# Alias for backward compatibility
format_currency = format_amount


def format_date_human(iso_date: str) -> str:
    """Convert 'YYYY-MM-DD' to human readable date, e.g. 'Jan 3, 2026'."""
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    except (ValueError, TypeError):
        return iso_date


def get_month_display_name(iso_month: str) -> str:
    """Convert 'YYYY-MM' into 'Month YYYY' (e.g. '2026-01' -> 'January 2026')."""
    try:
        dt = datetime.strptime(iso_month, "%Y-%m")
        return dt.strftime("%B %Y")
    except ValueError:
        return iso_month


def get_total_revenue(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate total net revenue, gross sales, discounts, and transaction metrics.
    """
    conn = get_connection(db_path)
    try:
        row = conn.execute("""
            SELECT 
                COUNT(*) AS transaction_count,
                COALESCE(SUM(quantity), 0) AS total_units_sold,
                COALESCE(SUM(quantity * unit_price), 0.0) AS gross_revenue,
                COALESCE(SUM(discount_amount), 0.0) AS total_discounts,
                COALESCE(SUM(net_revenue), 0.0) AS total_net_revenue,
                COALESCE(AVG(net_revenue), 0.0) AS average_order_value
            FROM sales_transactions;
        """).fetchone()

        tx_count = row["transaction_count"]
        net_rev = round(float(row["total_net_revenue"]), 2)
        gross_rev = round(float(row["gross_revenue"]), 2)
        discounts = round(float(row["total_discounts"]), 2)
        units_sold = int(row["total_units_sold"])
        aov = round(float(row["average_order_value"]), 2)

        if tx_count == 0:
            human_text = "The database currently contains no eligible sales transactions."
        else:
            human_text = (
                f"Total net revenue is {format_amount(net_rev)} (currency unspecified) across {tx_count} completed "
                f"transactions ({units_sold} total units sold), with an average order value of {format_amount(aov)}."
            )

        return {
            "metric": "total_revenue",
            "human_readable_answer": human_text,
            "supporting_figures": {
                "total_net_revenue": net_rev,
                "gross_revenue": gross_rev,
                "total_discounts": discounts,
                "total_units_sold": units_sold,
                "transaction_count": tx_count,
                "average_order_value": aov
            },
            "supporting_table": [
                {"Metric": "Total Net Revenue (currency unspecified)", "Value": format_amount(net_rev)},
                {"Metric": "Gross Revenue", "Value": format_amount(gross_rev)},
                {"Metric": "Total Discounts Applied", "Value": format_amount(discounts)},
                {"Metric": "Total Units Sold", "Value": f"{units_sold:,}"},
                {"Metric": "Completed Transactions", "Value": f"{tx_count:,}"},
                {"Metric": "Average Order Value", "Value": format_amount(aov)}
            ]
        }
    finally:
        conn.close()


def get_highest_revenue_product(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Identify the product that generated the highest revenue, including full ranking.
    Handles empty tables and tied top spots.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT 
                product,
                category,
                COUNT(*) AS transaction_count,
                COALESCE(SUM(quantity), 0) AS units_sold,
                ROUND(COALESCE(SUM(net_revenue), 0.0), 2) AS total_revenue
            FROM sales_transactions
            GROUP BY product
            ORDER BY total_revenue DESC, units_sold DESC;
        """).fetchall()

        if not rows:
            return {
                "metric": "highest_revenue_product",
                "human_readable_answer": "No product sales data is available.",
                "supporting_figures": {"top_product": None, "top_revenue": 0.0},
                "supporting_table": []
            }

        total_rev_row = conn.execute("SELECT COALESCE(SUM(net_revenue), 0.0) AS total FROM sales_transactions;").fetchone()
        overall_rev = float(total_rev_row["total"]) or 1.0

        ranking = []
        for idx, r in enumerate(rows, start=1):
            rev = float(r["total_revenue"])
            pct = round((rev / overall_rev) * 100, 2)
            ranking.append({
                "rank": idx,
                "product": r["product"],
                "category": r["category"],
                "units_sold": int(r["units_sold"]),
                "transaction_count": int(r["transaction_count"]),
                "total_revenue": rev,
                "formatted_revenue": format_currency(rev),
                "revenue_share_pct": pct
            })

        top = ranking[0]
        # Check for ties
        tied_products = [p for p in ranking if p["total_revenue"] == top["total_revenue"]]
        is_tie = len(tied_products) > 1

        if is_tie:
            names = ", ".join(p["product"] for p in tied_products)
            human_text = (
                f"There is a tie for highest revenue between {names}, each generating "
                f"{top['formatted_revenue']} (currency unspecified) ({top['revenue_share_pct']}% of total sales)."
            )
        else:
            human_text = (
                f"{top['product']} generated the highest revenue at {top['formatted_revenue']} (currency unspecified), "
                f"accounting for {top['revenue_share_pct']}% of total sales ({top['units_sold']} units sold across {top['transaction_count']} transactions)."
            )

        return {
            "metric": "highest_revenue_product",
            "human_readable_answer": human_text,
            "supporting_figures": {
                "top_product": top["product"],
                "top_revenue": top["total_revenue"],
                "top_units_sold": top["units_sold"],
                "top_transaction_count": top["transaction_count"],
                "is_tie": is_tie,
                "tied_count": len(tied_products)
            },
            "supporting_table": ranking
        }
    finally:
        conn.close()


def get_monthly_revenue_trend(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate the month-by-month revenue progression and summary statistics.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT 
                strftime('%Y-%m', order_date) AS month,
                COUNT(*) AS transaction_count,
                COALESCE(SUM(quantity), 0) AS units_sold,
                ROUND(COALESCE(SUM(net_revenue), 0.0), 2) AS total_revenue
            FROM sales_transactions
            GROUP BY strftime('%Y-%m', order_date)
            ORDER BY month ASC;
        """).fetchall()

        if not rows:
            return {
                "metric": "monthly_revenue_trend",
                "human_readable_answer": "No monthly trend data is available.",
                "supporting_figures": {"trend": []},
                "supporting_table": []
            }

        trend = []
        for r in rows:
            m = r["month"]
            rev = float(r["total_revenue"])
            trend.append({
                "month": m,
                "month_name": get_month_display_name(m),
                "transaction_count": int(r["transaction_count"]),
                "units_sold": int(r["units_sold"]),
                "total_revenue": rev,
                "formatted_revenue": format_currency(rev)
            })

        best_month = max(trend, key=lambda x: x["total_revenue"])
        lowest_month = min(trend, key=lambda x: x["total_revenue"])
        avg_monthly = round(sum(x["total_revenue"] for x in trend) / len(trend), 2)

        human_text = (
            f"Monthly revenue spans {len(trend)} months (from {trend[0]['month_name']} to {trend[-1]['month_name']}) "
            f"averaging {format_amount(avg_monthly)} per month. The peak month was {best_month['month_name']} "
            f"at {best_month['formatted_revenue']}, while the lowest was {lowest_month['month_name']} at {lowest_month['formatted_revenue']} (currency unspecified)."
        )

        return {
            "metric": "monthly_revenue_trend",
            "human_readable_answer": human_text,
            "supporting_figures": {
                "months_count": len(trend),
                "peak_month": best_month["month_name"],
                "peak_revenue": best_month["total_revenue"],
                "lowest_month": lowest_month["month_name"],
                "lowest_revenue": lowest_month["total_revenue"],
                "average_monthly_revenue": avg_monthly
            },
            "supporting_table": trend
        }
    finally:
        conn.close()


def get_highest_revenue_region(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Identify the region that generated the highest sales revenue, with full regional ranking.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT 
                region,
                COUNT(*) AS transaction_count,
                COALESCE(SUM(quantity), 0) AS units_sold,
                ROUND(COALESCE(SUM(net_revenue), 0.0), 2) AS total_revenue
            FROM sales_transactions
            GROUP BY region
            ORDER BY total_revenue DESC, units_sold DESC;
        """).fetchall()

        if not rows:
            return {
                "metric": "highest_revenue_region",
                "human_readable_answer": "No regional sales data is available.",
                "supporting_figures": {"top_region": None, "top_revenue": 0.0},
                "supporting_table": []
            }

        total_rev_row = conn.execute("SELECT COALESCE(SUM(net_revenue), 0.0) AS total FROM sales_transactions;").fetchone()
        overall_rev = float(total_rev_row["total"]) or 1.0

        regional_ranking = []
        for idx, r in enumerate(rows, start=1):
            rev = float(r["total_revenue"])
            pct = round((rev / overall_rev) * 100, 2)
            regional_ranking.append({
                "rank": idx,
                "region": r["region"],
                "units_sold": int(r["units_sold"]),
                "transaction_count": int(r["transaction_count"]),
                "total_revenue": rev,
                "formatted_revenue": format_currency(rev),
                "revenue_share_pct": pct
            })

        top = regional_ranking[0]
        tied_regions = [r for r in regional_ranking if r["total_revenue"] == top["total_revenue"]]
        is_tie = len(tied_regions) > 1

        if is_tie:
            names = ", ".join(r["region"] for r in tied_regions)
            human_text = (
                f"There is a tie for top region between {names}, each generating "
                f"{top['formatted_revenue']} (currency unspecified) ({top['revenue_share_pct']}% of company sales)."
            )
        else:
            human_text = (
                f"The {top['region']} region generated the highest sales at {top['formatted_revenue']} (currency unspecified), "
                f"contributing {top['revenue_share_pct']}% of total revenue across {top['transaction_count']} transactions."
            )

        return {
            "metric": "highest_revenue_region",
            "human_readable_answer": human_text,
            "supporting_figures": {
                "top_region": top["region"],
                "top_revenue": top["total_revenue"],
                "top_units_sold": top["units_sold"],
                "top_transaction_count": top["transaction_count"],
                "revenue_share_pct": top["revenue_share_pct"],
                "is_tie": is_tie
            },
            "supporting_table": regional_ranking
        }
    finally:
        conn.close()


def get_month_to_month_comparison(
    month1: str,
    month2: str,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compare revenue between two specific months using parameterized SQL queries.

    Args:
        month1: Base month in 'YYYY-MM' format (e.g. '2026-01').
        month2: Comparison month in 'YYYY-MM' format (e.g. '2026-02').
        db_path: Optional SQLite database path.

    Returns:
        Structured analysis with absolute change, percentage change, and supporting figures.
    """
    conn = get_connection(db_path)
    try:
        # Fetch data for both months safely using parameterized query
        rows = conn.execute("""
            SELECT 
                strftime('%Y-%m', order_date) AS month,
                COUNT(*) AS transaction_count,
                COALESCE(SUM(quantity), 0) AS units_sold,
                COALESCE(SUM(net_revenue), 0.0) AS total_revenue
            FROM sales_transactions
            WHERE strftime('%Y-%m', order_date) IN (?, ?)
            GROUP BY strftime('%Y-%m', order_date);
        """, (month1, month2)).fetchall()

        month_map = {r["month"]: r for r in rows}

        m1_data = month_map.get(month1)
        m2_data = month_map.get(month2)

        rev1 = round(float(m1_data["total_revenue"]), 2) if m1_data else 0.0
        tx1 = int(m1_data["transaction_count"]) if m1_data else 0
        units1 = int(m1_data["units_sold"]) if m1_data else 0

        rev2 = round(float(m2_data["total_revenue"]), 2) if m2_data else 0.0
        tx2 = int(m2_data["transaction_count"]) if m2_data else 0
        units2 = int(m2_data["units_sold"]) if m2_data else 0

        name1 = get_month_display_name(month1)
        name2 = get_month_display_name(month2)

        abs_diff = round(rev2 - rev1, 2)

        # Handle percentage change edge cases (division by zero, missing base)
        if rev1 == 0.0 and rev2 == 0.0:
            pct_change = 0.0
            direction = "no change"
            pct_text = "0.0%"
        elif rev1 == 0.0 and rev2 > 0.0:
            pct_change = 100.0
            direction = "increased"
            pct_text = f"+100.0% (from 0.00 base in {name1})"
        elif rev1 > 0.0 and rev2 == 0.0:
            pct_change = -100.0
            direction = "decreased"
            pct_text = "-100.0%"
        else:
            pct_change = round(((rev2 - rev1) / rev1) * 100.0, 2)
            direction = "increased" if abs_diff > 0 else ("decreased" if abs_diff < 0 else "remained flat")
            pct_text = f"{'+' if pct_change > 0 else ''}{pct_change}%"

        # Build natural language narrative
        if abs_diff > 0:
            human_text = (
                f"Revenue increased by {format_amount(abs_diff)} ({pct_text}) "
                f"from {name1} ({format_amount(rev1)}) to {name2} ({format_amount(rev2)}) (currency unspecified)."
            )
        elif abs_diff < 0:
            human_text = (
                f"Revenue decreased by {format_amount(abs(abs_diff))} ({pct_text}) "
                f"from {name1} ({format_amount(rev1)}) to {name2} ({format_amount(rev2)}) (currency unspecified)."
            )
        else:
            human_text = (
                f"Revenue remained identical at {format_amount(rev1)} between {name1} and {name2} (currency unspecified)."
            )

        supporting_table = [
            {"Period": name1, "Transactions": tx1, "Units": units1, "Revenue (currency unspecified)": format_amount(rev1)},
            {"Period": name2, "Transactions": tx2, "Units": units2, "Revenue (currency unspecified)": format_amount(rev2)},
            {"Period": "Change (M2 - M1)", "Transactions": tx2 - tx1, "Units": units2 - units1, "Revenue (currency unspecified)": f"{'+' if abs_diff > 0 else ''}{format_amount(abs_diff)} ({pct_text})"}
        ]

        return {
            "metric": "month_to_month_comparison",
            "human_readable_answer": human_text,
            "supporting_figures": {
                "month1": month1,
                "month1_name": name1,
                "month1_revenue": rev1,
                "month1_transactions": tx1,
                "month2": month2,
                "month2_name": name2,
                "month2_revenue": rev2,
                "month2_transactions": tx2,
                "absolute_change": abs_diff,
                "percentage_change": pct_change,
                "direction": direction
            },
            "supporting_table": supporting_table
        }
    finally:
        conn.close()


def get_consecutive_mom_summary(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Generate month-over-month comparisons for all consecutive months in the database.
    """
    trend_data = get_monthly_revenue_trend(db_path)
    trend = trend_data.get("supporting_table", [])
    if len(trend) < 2:
        return []

    mom_list = []
    for i in range(1, len(trend)):
        prev_m = trend[i - 1]
        curr_m = trend[i]
        rev_prev = prev_m["total_revenue"]
        rev_curr = curr_m["total_revenue"]
        diff = round(rev_curr - rev_prev, 2)
        pct = round(((rev_curr - rev_prev) / rev_prev) * 100, 2) if rev_prev != 0 else 0.0

        mom_list.append({
            "from_month": prev_m["month_name"],
            "to_month": curr_m["month_name"],
            "previous_revenue": format_currency(rev_prev),
            "current_revenue": format_currency(rev_curr),
            "absolute_change": f"{'+' if diff > 0 else ''}{format_currency(diff)}",
            "percentage_change": f"{'+' if pct > 0 else ''}{pct}%",
            "direction": "Up" if diff > 0 else ("Down" if diff < 0 else "Flat")
        })
    return mom_list


def get_dataset_and_quality_summary(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve dataset summary metrics and details of excluded records.
    """
    conn = get_connection(db_path)
    try:
        # Check sales_transactions
        sales_stats = conn.execute("""
            SELECT 
                COUNT(*) AS count,
                MIN(order_date) AS min_date,
                MAX(order_date) AS max_date,
                COALESCE(SUM(net_revenue), 0.0) AS total_revenue
            FROM sales_transactions;
        """).fetchone()

        # Check excluded_transactions
        exclusions = conn.execute("""
            SELECT transaction_id, order_date, product, exclusion_reason
            FROM excluded_transactions
            ORDER BY transaction_id;
        """).fetchall()

        valid_count = sales_stats["count"] if sales_stats else 0
        excluded_count = len(exclusions)
        total_records = valid_count + excluded_count
        total_rev = round(float(sales_stats["total_revenue"]), 2) if sales_stats else 0.0

        excluded_list = [
            {
                "transaction_id": row["transaction_id"],
                "order_date": row["order_date"],
                "product": row["product"],
                "reason": row["exclusion_reason"]
            }
            for row in exclusions
        ]

        # Check complete date coverage across all transactions (including excluded rows)
        date_row = conn.execute("""
            SELECT MIN(order_date) AS min_d, MAX(order_date) AS max_d
            FROM (
                SELECT order_date FROM sales_transactions
                UNION ALL
                SELECT order_date FROM excluded_transactions
            );
        """).fetchone()

        min_d = date_row["min_d"] if date_row and date_row["min_d"] else (sales_stats["min_date"] if sales_stats else None)
        max_d = date_row["max_d"] if date_row and date_row["max_d"] else (sales_stats["max_date"] if sales_stats else None)

        # Build clean date coverage string (e.g. "Jan 3 – Jun 28, 2026")
        date_coverage_display = None
        if min_d and max_d:
            try:
                dt1 = datetime.strptime(min_d, "%Y-%m-%d")
                dt2 = datetime.strptime(max_d, "%Y-%m-%d")
                if dt1.year == dt2.year:
                    date_coverage_display = f"{dt1.strftime('%b')} {dt1.day} \u2013 {dt2.strftime('%b')} {dt2.day}, {dt1.year}"
                else:
                    date_coverage_display = f"{dt1.strftime('%b')} {dt1.day}, {dt1.year} \u2013 {dt2.strftime('%b')} {dt2.day}, {dt2.year}"
            except Exception:
                date_coverage_display = f"{min_d} to {max_d}"

        return {
            "total_records_processed": total_records,
            "eligible_completed_sales": valid_count,
            "excluded_records_count": excluded_count,
            "total_net_revenue": total_rev,
            "earliest_date": min_d,
            "latest_date": max_d,
            "date_coverage_display": date_coverage_display,
            "excluded_records": excluded_list,
            "policy_summary": (
                "Revenue Policy: Excludes returned orders, missing unit prices, and zero/negative quantities. "
                "Net revenue is calculated as (Quantity * Unit_price) - Discount_amount."
            )
        }
    finally:
        conn.close()

