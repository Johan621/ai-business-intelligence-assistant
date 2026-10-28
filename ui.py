"""
Streamlit User Interface for AI Business Intelligence Assistant.

Provides an interactive dashboard to:
- Ask natural-language business questions.
- View verified SQL answers, KPI metrics, and charts.
- Audit data quality rules and excluded records.
- Explore monthly trends, product rankings, and regional breakdowns.
"""

import os
from typing import Any, Dict, List, Optional
import pandas as pd
import requests
import streamlit as st

# Configure page metadata
st.set_page_config(
    page_title="AI Business Intelligence Assistant",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Endpoint configuration (allows environment override)
API_BASE_URL = os.getenv("API_URL", "http://127.0.0.1:8000")


# --- Helper Functions for Backend Communication ---

@st.cache_data(ttl=10)
def check_backend_health() -> Optional[Dict[str, Any]]:
    """Check connectivity to FastAPI service."""
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=3)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


@st.cache_data(ttl=30)
def fetch_dataset_summary() -> Optional[Dict[str, Any]]:
    """Fetch dataset summary and data-quality metrics."""
    try:
        resp = requests.get(f"{API_BASE_URL}/summary", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


@st.cache_data(ttl=30)
def fetch_example_questions() -> List[Dict[str, Any]]:
    """Fetch pre-configured approved example queries."""
    try:
        resp = requests.get(f"{API_BASE_URL}/examples", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return [
        {"id": 1, "category": "Total Revenue", "question": "What is the total revenue?"},
        {"id": 2, "category": "Product Performance", "question": "Which product generated the highest revenue?"},
        {"id": 3, "category": "Revenue Trends", "question": "What is the monthly revenue trend?"},
        {"id": 4, "category": "Regional Performance", "question": "Which region generated the highest sales?"},
        {"id": 5, "category": "Period Comparison", "question": "How did revenue change between January and February 2026?"}
    ]


def query_assistant(question: str) -> Dict[str, Any]:
    """Send natural-language question to backend /ask endpoint."""
    try:
        resp = requests.post(
            f"{API_BASE_URL}/ask",
            json={"question": question},
            timeout=10
        )
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        else:
            detail = resp.json().get("detail", resp.text)
            return {"success": False, "error": f"API Error ({resp.status_code}): {detail}"}
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to backend server at {API_BASE_URL}. Ensure FastAPI is running on port 8000."
        }
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


# --- Sidebar Navigation and Status ---

with st.sidebar:
    st.title("📊 BI Assistant")
    st.markdown("**Sales Intelligence & Analytics**")
    st.markdown("---")

    health = check_backend_health()
    if health and health.get("status") == "ok":
        st.success("🟢 Backend Connected (FastAPI)")
        st.caption(f"App: {health.get('app_name')} v{health.get('version')}")
        st.caption(f"Eligible Records in DB: **{health.get('eligible_transactions', 0)}**")
    else:
        st.error("🔴 Backend Disconnected")
        st.caption(f"Target: `{API_BASE_URL}`")
        st.info("Start the backend with:\n```powershell\nuvicorn app.main:app --port 8000\n```")

    st.markdown("---")
    st.subheader("💡 Approved Questions")
    st.caption("Click any question to evaluate immediately:")

    examples = fetch_example_questions()
    for eg in examples:
        btn_label = f"👉 {eg['question']}"
        if st.button(btn_label, key=f"sidebar_btn_{eg['id']}"):
            st.session_state["submitted_question"] = eg["question"]
            st.rerun()

    st.markdown("---")
    st.caption("AI Business Intelligence Assistant • Safe Parameterized SQL Engine")


# --- Main Dashboard Header ---

st.title("AI Business Intelligence Assistant")
st.markdown(
    "Ask natural-language business questions and receive accurate answers "
    "calculated directly against verified SQLite database records."
)

# Fetch dataset summary metrics
summary = fetch_dataset_summary()

if summary:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="Total Net Revenue",
            value=f"{summary['total_net_revenue']:,.2f}",
            help="Net revenue = (Quantity * Unit Price) - Discount across all completed sales."
        )
    with col2:
        st.metric(
            label="Eligible Transactions",
            value=summary["eligible_completed_sales"],
            help="Completed transactions meeting strict quality criteria."
        )
    with col3:
        st.metric(
            label="Excluded Records",
            value=f"{summary['excluded_records_count']} records",
            delta=f"-{summary['excluded_records_count']} flagged",
            delta_color="inverse",
            help="Records excluded due to returns, zero quantity, or missing unit price."
        )
    with col4:
        st.metric(
            label="Date Coverage",
            value=f"{summary.get('earliest_date', '')} to {summary.get('latest_date', '')}",
            help="Temporal range of ingested transactions."
        )

    # Collapsible alert for data quality exclusions
    if summary["excluded_records_count"] > 0:
        with st.expander(f"⚠️ Data Quality Notice: {summary['excluded_records_count']} records excluded under revenue rules"):
            st.markdown(
                "Per business policy, non-completed sales, invalid quantities, and missing prices are excluded "
                "from sales revenue calculations to maintain reporting integrity:"
            )
            exc_df = pd.DataFrame(summary["excluded_records"])
            st.dataframe(exc_df, use_container_width=True)
            st.info(f"**Policy Standard:** {summary.get('policy_summary')}")
else:
    st.warning("⚠️ Backend dataset summary is loading or backend is not running. Launch FastAPI backend to enable full metrics.")

st.markdown("---")

# --- Tabs: Question Assistant vs Analytics Dashboards ---

tab_ask, tab_charts, tab_audit = st.tabs([
    "💬 Ask Assistant",
    "📈 Visual Analytics",
    "📋 Data Quality & Policy Audit"
])


# --- TAB 1: ASK ASSISTANT ---

with tab_ask:
    st.subheader("Ask a Sales Question")

    # Question input form
    with st.form("ask_form", clear_on_submit=False):
        default_q = st.session_state.get("submitted_question", "")
        user_question = st.text_input(
            "Enter your business question:",
            value=default_q,
            placeholder="e.g., Which product generated the highest revenue?",
            help="Enter one of the 5 core business questions or its variations."
        )
        col_btn1, col_btn2 = st.columns([1, 5])
        with col_btn1:
            submit_pressed = st.form_submit_button("Ask Assistant", type="primary")

    # If submitted via button or sidebar example click
    active_question = user_question.strip() if submit_pressed else st.session_state.get("submitted_question")

    if active_question:
        with st.spinner("Analyzing question and executing database calculation..."):
            result = query_assistant(active_question)

        if not result["success"]:
            st.error(result["error"])
        else:
            resp_data = result["data"]
            intent = resp_data.get("recognized_intent")
            human_answer = resp_data.get("human_readable_answer")
            figures = resp_data.get("supporting_figures", {})
            table_data = resp_data.get("supporting_table")
            caveats = resp_data.get("data_quality_caveats", [])

            # Display Answer Card
            st.markdown("### Answer")
            if intent == "unknown":
                st.warning(human_answer)
            else:
                st.success(f"**{human_answer}**")

            # Intent Badge
            st.caption(f"🎯 Recognized Intent: `{intent}` | Original Question: *\"{active_question}\"*")

            # Supporting Visuals & Metrics
            if intent == "total_revenue" and figures:
                st.markdown("#### Key Metrics")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Gross Revenue", f"{figures.get('gross_revenue', 0):,.2f}")
                m2.metric("Total Discounts", f"{figures.get('total_discounts', 0):,.2f}")
                m3.metric("Net Revenue", f"{figures.get('total_net_revenue', 0):,.2f}")
                m4.metric("Avg Order Value", f"{figures.get('average_order_value', 0):,.2f}")

            elif intent == "highest_revenue_product" and table_data:
                st.markdown("#### Product Revenue Breakdown")
                df_prod = pd.DataFrame(table_data)
                chart_df = df_prod.set_index("product")["total_revenue"]
                st.bar_chart(chart_df)

            elif intent == "monthly_revenue_trend" and table_data:
                st.markdown("#### Monthly Trend Chart")
                df_trend = pd.DataFrame(table_data)
                chart_df = df_trend.set_index("month_name")["total_revenue"]
                st.line_chart(chart_df)

            elif intent == "highest_revenue_region" and table_data:
                st.markdown("#### Regional Sales Breakdown")
                df_reg = pd.DataFrame(table_data)
                chart_df = df_reg.set_index("region")["total_revenue"]
                st.bar_chart(chart_df)

            elif intent == "month_to_month_comparison" and figures:
                st.markdown("#### Variance Analysis")
                c1, c2, c3 = st.columns(3)
                c1.metric(f"{figures.get('month1_name')} Revenue", f"{figures.get('month1_revenue', 0):,.2f}")
                c2.metric(f"{figures.get('month2_name')} Revenue", f"{figures.get('month2_revenue', 0):,.2f}")
                c3.metric(
                    "Revenue Variance",
                    f"{figures.get('absolute_change', 0):,.2f}",
                    delta=f"{figures.get('percentage_change', 0)}%"
                )

            # Supporting Table Display
            if table_data:
                st.markdown("#### Supporting Database Figures")
                st.dataframe(pd.DataFrame(table_data), use_container_width=True)

            # Data Quality Caveats
            if caveats:
                st.markdown("---")
                st.caption("🛡️ **Data Quality & Reporting Notes:**")
                for c in caveats:
                    st.caption(f"• {c}")


# --- TAB 2: VISUAL ANALYTICS ---

with tab_charts:
    st.subheader("Business Analytics Overview")
    st.markdown("Visual breakdowns computed live from the SQLite database.")

    # Product and Region side by side
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### Top Products by Revenue")
        prod_res = query_assistant("Which product generated the highest revenue?")
        if prod_res["success"] and prod_res["data"].get("supporting_table"):
            df_p = pd.DataFrame(prod_res["data"]["supporting_table"])
            st.bar_chart(df_p.set_index("product")["total_revenue"])
            st.dataframe(
                df_p[["rank", "product", "category", "formatted_revenue", "revenue_share_pct", "units_sold"]],
                use_container_width=True
            )

    with col_right:
        st.markdown("### Regional Revenue Distribution")
        reg_res = query_assistant("Which region generated the highest sales?")
        if reg_res["success"] and reg_res["data"].get("supporting_table"):
            df_r = pd.DataFrame(reg_res["data"]["supporting_table"])
            st.bar_chart(df_r.set_index("region")["total_revenue"])
            st.dataframe(
                df_r[["rank", "region", "formatted_revenue", "revenue_share_pct", "units_sold"]],
                use_container_width=True
            )

    st.markdown("---")
    st.markdown("### Monthly Revenue Progression")
    trend_res = query_assistant("What is the monthly revenue trend?")
    if trend_res["success"] and trend_res["data"].get("supporting_table"):
        df_t = pd.DataFrame(trend_res["data"]["supporting_table"])
        st.line_chart(df_t.set_index("month_name")["total_revenue"])
        st.dataframe(
            df_t[["month_name", "formatted_revenue", "units_sold", "transaction_count"]],
            use_container_width=True
        )


# --- TAB 3: DATA QUALITY & POLICY AUDIT ---

with tab_audit:
    st.subheader("Data Governance & Ingestion Audit")
    st.markdown(
        "To ensure business stakeholders can trust reports, the system strictly separates "
        "eligible completed sales from invalid records."
    )

    if summary:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Records Ingested", summary["total_records_processed"])
        m2.metric("Completed Sales Stored", summary["eligible_completed_sales"])
        m3.metric("Excluded Records Flagged", summary["excluded_records_count"])

        st.markdown("### Excluded Records Audit Log")
        st.caption("These records were filtered during ingestion and are never included in sales calculations:")
        exc_df = pd.DataFrame(summary["excluded_records"])
        st.dataframe(exc_df, use_container_width=True)

        st.markdown("### Revenue Policy Definitions")
        st.markdown("""
        1. **Completed Sales Only**: Orders marked as `Returned` are explicitly excluded from completed sales revenue.
        2. **Unit Price Integrity**: Missing or blank unit prices are strictly excluded. The system **never silently replaces missing unit prices with zero**.
        3. **Valid Quantities**: Orders with zero or negative quantities are excluded as non-sale records.
        4. **Net Revenue Formula**: `Net Revenue = (Quantity × Unit_Price) - Discount_Amount`. Discount amounts are treated as transaction-level reductions.
        5. **Idempotency**: Repeated CSV imports cleanly update or overwrite existing records without duplication.
        """)
    else:
        st.info("Start the FastAPI backend to view real-time data governance records.")

