"""
FastAPI Backend Application for AI Business Intelligence Assistant.

Exposes RESTful endpoints:
- POST /ask: Answers natural-language business questions with verified database figures.
- GET /health: Service and database health monitoring.
- GET /examples: Pre-defined supported example queries.
- GET /summary: Dataset health, governance metrics, and excluded records audit.
"""

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import analytics
from app.data_loader import ingest_sales_csv, DEFAULT_CSV_PATH
from app.database import get_connection, init_db
from app.question_interpreter import Intent, interpret_question


# --- Pydantic Models ---

class AskRequest(BaseModel):
    question: str = Field(
        ...,
        description="Natural-language question about business sales analytics.",
        examples=["What is the total revenue?"]
    )


class AskResponse(BaseModel):
    original_question: str
    recognized_intent: str
    human_readable_answer: str
    supporting_figures: Dict[str, Any]
    supporting_table: Optional[List[Dict[str, Any]]] = None
    currency: Optional[str] = "unspecified"
    data_quality_caveats: List[str]


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    database_connected: bool
    eligible_transactions: int


class ExampleQuestion(BaseModel):
    id: int
    category: str
    question: str
    description: str


# --- Application Lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    On startup, ensure database is initialized and data is ingested if empty.
    """
    init_db()
    try:
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) AS c FROM sales_transactions;").fetchone()["c"]
        conn.close()
        if count == 0:
            ingest_sales_csv(overwrite=True)
    except Exception:
        # If ingestion fails during startup, application still starts and allows manual reload
        pass
    yield


app = FastAPI(
    title="AI Business Intelligence Assistant",
    description="Business analytics API answering natural-language questions backed by parameterized SQL.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local Streamlit and web access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Global Exception Handler (Prevent Raw Stack Trace Leakage) ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred while processing your request. Please try again or rephrase your question."
        }
    )


# --- API Routes ---

@app.get("/health", response_model=HealthResponse, summary="Service Health Check")
def health_check():
    """Verify backend health, database connectivity, and record counts."""
    db_connected = False
    tx_count = 0
    try:
        conn = get_connection()
        row = conn.execute("SELECT COUNT(*) AS c FROM sales_transactions;").fetchone()
        tx_count = int(row["c"]) if row else 0
        db_connected = True
        conn.close()
    except Exception:
        db_connected = False

    return HealthResponse(
        status="ok" if db_connected else "degraded",
        app_name="AI Business Intelligence Assistant",
        version="1.0.0",
        database_connected=db_connected,
        eligible_transactions=tx_count
    )


@app.get("/examples", response_model=List[ExampleQuestion], summary="Example Business Questions")
def get_example_questions():
    """Return pre-approved representative questions showcasing capabilities."""
    return [
        {
            "id": 1,
            "category": "Total Revenue",
            "question": "What is the total revenue?",
            "description": "Calculates overall net sales, discounts, units sold, and average order value."
        },
        {
            "id": 2,
            "category": "Product Performance",
            "question": "Which product generated the highest revenue?",
            "description": "Ranks products by total net revenue and identifies the top performer."
        },
        {
            "id": 3,
            "category": "Revenue Trends",
            "question": "What is the monthly revenue trend?",
            "description": "Visualizes month-over-month revenue, peak periods, and low points."
        },
        {
            "id": 4,
            "category": "Regional Performance",
            "question": "Which region generated the highest sales?",
            "description": "Breaks down company revenue by geographic region and identifies the top market."
        },
        {
            "id": 5,
            "category": "Period Comparison",
            "question": "How did revenue change between January and February 2026?",
            "description": "Calculates absolute and percentage variance between two specific months."
        }
    ]


@app.get("/summary", summary="Dataset and Data Quality Summary")
def get_summary():
    """Return summary statistics, policy documentation, and list of excluded records."""
    try:
        return analytics.get_dataset_and_quality_summary()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to retrieve dataset summary: {str(e)}"
        )


@app.post("/ask", response_model=AskResponse, summary="Ask Natural-Language Question")
def ask_question(request: AskRequest):
    """
    Interpret user's natural language question, execute parameterized analytics,
    and return structured metrics with clear explanation.
    """
    q_str = request.question.strip()
    if not q_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The question field must not be empty. Please ask a business sales question."
        )

    # 1. Interpret question safely
    plan = interpret_question(q_str)
    intent = plan["intent"]

    if intent == Intent.UNSAFE_QUERY.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=plan["clarification_message"]
        )

    # Standard data quality caveats applied to all business analytics
    caveats = [
        "Figures exclude returned orders (e.g. TXN0033), orders with zero quantity (e.g. TXN0034), "
        "and transactions with missing unit prices (e.g. TXN0051) per company revenue policy."
    ]

    # 2. Dispatch to approved analytics function
    if intent == Intent.TOTAL_REVENUE.value:
        data = analytics.get_total_revenue()
        return AskResponse(
            original_question=q_str,
            recognized_intent=intent,
            human_readable_answer=data["human_readable_answer"],
            supporting_figures=data["supporting_figures"],
            supporting_table=data.get("supporting_table"),
            currency="unspecified",
            data_quality_caveats=caveats
        )

    elif intent == Intent.HIGHEST_REVENUE_PRODUCT.value:
        data = analytics.get_highest_revenue_product()
        return AskResponse(
            original_question=q_str,
            recognized_intent=intent,
            human_readable_answer=data["human_readable_answer"],
            supporting_figures=data["supporting_figures"],
            supporting_table=data.get("supporting_table"),
            currency="unspecified",
            data_quality_caveats=caveats
        )

    elif intent == Intent.MONTHLY_REVENUE_TREND.value:
        data = analytics.get_monthly_revenue_trend()
        return AskResponse(
            original_question=q_str,
            recognized_intent=intent,
            human_readable_answer=data["human_readable_answer"],
            supporting_figures=data["supporting_figures"],
            supporting_table=data.get("supporting_table"),
            currency="unspecified",
            data_quality_caveats=caveats
        )

    elif intent == Intent.HIGHEST_REVENUE_REGION.value:
        data = analytics.get_highest_revenue_region()
        return AskResponse(
            original_question=q_str,
            recognized_intent=intent,
            human_readable_answer=data["human_readable_answer"],
            supporting_figures=data["supporting_figures"],
            supporting_table=data.get("supporting_table"),
            currency="unspecified",
            data_quality_caveats=caveats
        )

    elif intent == Intent.MONTH_TO_MONTH_COMPARISON.value:
        params = plan.get("parameters", {})
        if not plan.get("is_supported") or "month1" not in params or "month2" not in params:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=plan.get("clarification_message", "Please specify two valid months to compare.")
            )
        data = analytics.get_month_to_month_comparison(params["month1"], params["month2"])
        clarification = plan.get("clarification_message")
        if clarification:
            caveats.append(clarification)

        return AskResponse(
            original_question=q_str,
            recognized_intent=intent,
            human_readable_answer=data["human_readable_answer"],
            supporting_figures=data["supporting_figures"],
            supporting_table=data.get("supporting_table"),
            currency="unspecified",
            data_quality_caveats=caveats
        )

    elif intent == Intent.DATASET_SUMMARY.value:
        data = analytics.get_dataset_and_quality_summary()
        human_text = (
            f"The dataset contains {data['total_records_processed']} total rows. "
            f"{data['eligible_completed_sales']} records are eligible completed sales representing "
            f"{data['total_net_revenue']:,.2f} in net revenue (currency unspecified). {data['excluded_records_count']} records "
            f"were excluded under data quality rules."
        )
        return AskResponse(
            original_question=q_str,
            recognized_intent=intent,
            human_readable_answer=human_text,
            supporting_figures={
                "total_records": data["total_records_processed"],
                "eligible_sales": data["eligible_completed_sales"],
                "excluded_records": data["excluded_records_count"],
                "total_net_revenue": data["total_net_revenue"]
            },
            supporting_table=data.get("excluded_records"),
            currency="unspecified",
            data_quality_caveats=[data["policy_summary"]]
        )

    else:
        # Intent.UNKNOWN or unsupported
        return AskResponse(
            original_question=q_str,
            recognized_intent="unknown",
            human_readable_answer=plan["clarification_message"],
            supporting_figures={},
            supporting_table=[],
            currency="unspecified",
            data_quality_caveats=[
                "Tip: Click one of the example queries or ask about total revenue, product performance, monthly trends, regional sales, or period comparisons."
            ]
        )

