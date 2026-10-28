# AI Business Intelligence Assistant

**AI Business Intelligence Assistant** is a production-grade, local business analytics application that enables business stakeholders to ask natural-language questions about sales transactions and receive verified, accurate answers backed by parameterized SQLite database queries.

Built from scratch with **Python**, **FastAPI**, **SQLite**, and **Streamlit**, the application operates 100% locally without external API keys, cloud dependencies, or LLM account charges.

---

## Key Features

- **Conversational Business Intelligence**: Ask natural-language questions regarding sales, products, trends, and regions.
- **Deterministic & Safe Question Interpretation**: Maps natural-language queries to approved analytics functions with parameter extraction (month names, years) and SQL injection filtering.
- **Strict Data Quality & Governance**:
  - Excludes returned orders (`Status = 'Returned'`) from completed sales.
  - Excludes zero or negative quantity orders (`Quantity <= 0`).
  - Excludes transactions with missing unit prices (**never silently replaced with zero**).
  - Explicitly calculates Net Revenue: `(Quantity × Unit_Price) - Discount_Amount`.
  - Maintains a full audit log of excluded records.
- **Parametric SQL Analytics Engine**: Zero hardcoded totals. All answers, metrics, rankings, and charts are calculated on-the-fly via parameterized SQL against SQLite.
- **Interactive Web Interface**: Streamlit dashboard featuring KPI metrics, visual charts, clickable example queries, data tables, and data governance audit views.
- **FastAPI REST Backend**: Clean endpoints (`/ask`, `/health`, `/summary`, `/examples`) with JSON error handling that never exposes raw stack traces.
- **Automated Test Suite**: 40 automated unit, security, and integration tests covering calculations, data rules, idempotency, API routes, and question parsing.

---

## Technology Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend API** | [FastAPI](https://fastapi.tiangolo.com/) | RESTful API server with Pydantic validation |
| **Database** | [SQLite](https://www.sqlite.org/) | Local persistent storage with indexing |
| **User Interface** | [Streamlit](https://streamlit.io/) | Interactive web UI for query input and data visualization |
| **Data Ingestion** | [Pandas](https://pandas.pydata.org/) & `csv` | CSV parsing, cleaning, and schema normalization |
| **Calculations** | Parameterized SQL | Deterministic, audited revenue aggregations |
| **Testing** | [Pytest](https://docs.pytest.org/) | Automated unit, security, and integration testing |

---

## Project Structure

```text
ai-business-intelligence-assistant/
├── app/
│   ├── __init__.py               # Application package definition
│   ├── database.py               # SQLite connection, schema, and table initialization
│   ├── data_loader.py            # CSV ingestion, data cleaning, and audit logging
│   ├── analytics.py              # Parameterized SQL calculations for business queries
│   ├── question_interpreter.py   # Deterministic intent matching and safety guardrails
│   └── main.py                   # FastAPI REST backend with endpoints and error models
├── tests/
│   ├── __init__.py               # Test package definition
│   ├── test_analytics.py         # Unit tests for revenue and aggregation math
│   ├── test_data_loader.py       # Tests for exclusions, prices, and idempotency
│   ├── test_question_interpreter.py # Tests for query intent matching and SQLi blocking
│   └── test_api.py               # Integration tests for FastAPI endpoints
├── data/
│   ├── ai_bi_assistant_sales_data - GET.csv  # Original source sales dataset
│   └── sales_bi.db               # Generated persistent SQLite database (auto-created)
├── ui.py                         # Streamlit user interface
├── requirements.txt              # Production and development dependencies
├── .gitignore                    # Git exclusion rules
├── README.md                     # Comprehensive documentation and setup guide
├── ARCHITECTURE.md               # End-to-end architectural flow and design principles
└── DEVELOPMENT_NOTES.md          # Real engineering notes, debugging, and verification
```

---

## Prerequisites

- **Operating System**: Windows 10/11 (or macOS / Linux)
- **Python**: Version 3.10 to 3.14 (Verified on Python 3.14)
- **Git** (optional, for repository management)

---

## Windows Installation & Quickstart

Follow these exact steps in your terminal (PowerShell or Command Prompt):

### 1. Open Project Directory
```powershell
cd D:\RSG
```

### 2. Create and Activate Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment (PowerShell)
.venv\Scripts\Activate.ps1

# Or activate in Command Prompt (cmd.exe):
# .venv\Scripts\activate.bat
```

> *Note: If PowerShell displays an execution policy error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and re-run the activation script.*

### 3. Install Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Ingesting the Sales Dataset

The dataset is located at:
```text
data/ai_bi_assistant_sales_data - GET.csv
```

To initialize the SQLite database and ingest the dataset:
```powershell
python -m app.data_loader
```

**Expected output:**
```text
CSV Ingestion Summary:
Total Rows Processed: 51
Valid Transactions Stored: 48
Excluded Records: 3
 - TXN0033: Status is 'Returned' (returned orders are excluded from completed sales revenue)
 - TXN0034: Quantity must be greater than zero (found: 0)
 - TXN0051: Missing unit price (cannot determine revenue; price cannot be assumed)
```
*(Ingestion is idempotent: running it multiple times refreshes cleanly without duplicating records).*

---

## Running the Application

For the best experience, run the backend and frontend in two separate terminal windows.

### Terminal 1: Start FastAPI Backend
```powershell
.venv\Scripts\Activate.ps1
uvicorn app.main:app --port 8000 --reload
```
- Interactive API documentation (Swagger UI): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health check endpoint: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### Terminal 2: Start Streamlit Frontend
```powershell
.venv\Scripts\Activate.ps1
streamlit run ui.py
```
Streamlit will automatically open in your default browser at [http://localhost:8501](http://localhost:8501).

---

## Running Automated Tests

To run the complete test suite with verbose output:

```powershell
$env:PYTHONPATH="."
pytest -v
```

All 40 automated tests will execute:
```text
======================== 40 passed in 2.22s ========================
```

---

## Supported Questions & Capabilities

The assistant natively supports all five core business questions and their natural-language variations:

| # | Question Focus | Example Natural Language Query |
| :--- | :--- | :--- |
| **1** | **Total Revenue** | *"What is the total revenue?"*, *"What is our overall net revenue?"*, *"How much total sales have we made?"* |
| **2** | **Top Product** | *"Which product generated the highest revenue?"*, *"Which product performed best?"*, *"Top selling product by revenue"* |
| **3** | **Monthly Trend** | *"What is the monthly revenue trend?"*, *"Show sales month by month."*, *"Monthly revenue breakdown"* |
| **4** | **Top Region** | *"Which region generated the highest sales?"*, *"Which region performed best?"*, *"Where did we sell the most?"* |
| **5** | **Period Comparison** | *"How did revenue change between two months?"*, *"Compare January and February 2026."*, *"Compare sales between April and May 2026"* |

Clickable example buttons are integrated directly into the sidebar and main view of the Streamlit application for convenience.

---

## Data Cleaning & Revenue Policy

To ensure accurate, audit-compliant financial reporting, the application adheres to strict business rules:

1. **Eligible Transactions Only**: Only transactions with `Status = 'Completed'` are included.
2. **Returned Transactions Excluded**: Transaction `TXN0033` has `Status = 'Returned'` and is excluded from completed revenue totals.
3. **Invalid Quantities Excluded**: Transaction `TXN0034` has `Quantity = 0`. Transactions with zero or negative quantities are excluded from sales revenue.
4. **Missing Unit Prices Excluded**: Transaction `TXN0051` has an empty `Unit_price`. The policy **strictly forbids guessing or replacing missing unit prices with zero**, which would falsely distort sales volumes.
5. **Net Revenue Formula**:
   $$\text{Net Revenue} = (\text{Quantity} \times \text{Unit Price}) - \text{Discount Amount}$$
   `Discount_amount` is treated as a transaction-level monetary discount.
6. **Consistent Calculations**: All 5 analytics functions query the same cleaned `sales_transactions` table, guaranteeing identical totals and figures across questions.

---

## Troubleshooting & Known Limitations

### Common Issues
- **PowerShell Script Execution Error**:
  Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in your PowerShell window.
- **Port 8000 already in use**:
  Run uvicorn on another port (e.g. `uvicorn app.main:app --port 8080`) and set `$env:API_URL="http://127.0.0.1:8080"` before launching Streamlit.
- **Backend Disconnected in Streamlit**:
  Ensure the FastAPI server in Terminal 1 is running and shows `Uvicorn running on http://127.0.0.1:8000`.

### Known Limitations
- Current dataset covers the period January 2026 to June 2026. Comparing months outside this window returns $0 with an explanation.
- The intent matcher is deterministic and rule-based. Unrecognized questions (e.g., weather or general trivia) are rejected gracefully with helpful suggested queries.

