# Development & Engineering Notes

This document records the actual development process, tools used, problems encountered, debugging steps taken, verification results, and identified future improvements during the construction of the **AI Business Intelligence Assistant**.

---

## 1. Development Environment & Tooling

- **Operating System**: Windows 11 (AMD64)
- **Primary Runtime**: Python 3.14.7
- **AI Coding Assistant**: Google DeepMind Antigravity Pair Programmer
- **Shell**: Windows PowerShell
- **Virtual Environment**: `.venv` using standard library `venv`
- **Core Libraries**:
  - `fastapi` (0.162.0)
  - `uvicorn` (0.54.0)
  - `pydantic` (2.14.1)
  - `pandas` (3.1.0)
  - `streamlit` (1.66.1)
  - `pytest` (9.2.0)
  - `requests` (2.34.2)
  - `httpx` (0.28.1)

---

## 2. Dataset Inspection & Verification

Before implementing code, the supplied file `data/ai_bi_assistant_sales_data - GET.csv` was inspected using Python's standard `csv` library.

### Findings from Actual CSV Data:
- **Total records**: 51 rows (51 distinct transaction IDs: `TXN0001` through `TXN0051`).
- **Columns**: `Transaction_Id, Order_date, Product, Category, Region, Sales_channel, Quantity, Unit_price, Discount_amount, Status`.
- **Date format**: `DD-MM-YYYY` (e.g. `03-01-2026`).
- **Target edge-case transactions verified**:
  1. `TXN0033`: `Status` is `'Returned'`, `Quantity=2`, `Unit_price=9500`. Verified present at row 34.
  2. `TXN0034`: `Quantity` is `0`, `Product='Keyboard'`, `Unit_price=900`. Verified present at row 35.
  3. `TXN0051`: `Unit_price` is missing (`""`), `Quantity=5`. Verified present at row 52.

### Mathematical Baseline Established from Verified Data:
- **Total CSV rows**: 51
- **Excluded records**: Exactly 3 (`TXN0033`, `TXN0034`, `TXN0051`)
- **Valid completed sales records**: 48
- **Total Net Revenue**: **$1,439,200.00**
  - Gross Revenue: $1,443,200.00
  - Discounts: $4,000.00
  - Units Sold: 633
  - Transactions: 48
- **Top Product**: Monitor ($473,000.00, 32.87% of revenue)
- **Top Region**: South ($411,200.00, 28.57% of revenue)
- **Date Range**: 2026-01-03 to 2026-06-28 (6 months)

---

## 3. Engineering Problems Encountered & Debugging Steps

### Problem 1: PowerShell Escape Syntax During Inline Script Execution
- **Symptom**: Running inline PowerShell commands containing nested double quotes and brackets (e.g., `python -c "..."`) threw a `SyntaxError: unterminated string literal`.
- **Root Cause**: PowerShell interprets double quotes inside double-quoted strings differently than bash/zsh.
- **Resolution**: Shifted from fragile inline shell scripts to dedicated standalone test scripts executed with `$env:PYTHONPATH="."`.

### Problem 2: Intent Matching Edge Case in Superlative Product Queries
- **Symptom**: During the first pytest run, 34 out of 35 tests passed. `test_highest_revenue_product_variations` failed on the input *"What is our best product?"*.
- **Root Cause**: The original interpreter required both a product keyword and a compound trigger like `"best selling"` or `"top selling"`. In *"What is our best product?"*, the adjective `"best"` was separated from `"product"`.
- **Resolution**: Refactored `app/question_interpreter.py` to decouple product entity detection from ranking superlative words (`"best"`, `"top"`, `"highest"`, `"leading"`). Re-running the test suite resulted in all 35 tests passing cleanly.

### Problem 3: Safe Division in Month-over-Month Variance
- **Symptom**: When comparing a month with sales against a month with zero sales, a naive percentage formula `(rev2 - rev1) / rev1` raised `ZeroDivisionError`.
- **Resolution**: Implemented guarded logic in `analytics.get_month_to_month_comparison`:
  - If both months have zero sales: 0.0% variance.
  - If base month has zero sales and target month has sales: returns +100.0% with a descriptive footnote explaining the $0 baseline.
  - Added dedicated unit test `test_month_to_month_comparison_zero_base` to prevent regression.

### Problem 4: Destructive Query Misclassification ("Delete all sales records" -> total_revenue)
- **Symptom**: In the Streamlit UI, entering *"Delete all sales records"* was erroneously classified as `total_revenue` and returned the total sales answer.
- **Root Cause**:
  1. The total revenue intent triggers included the broad phrase `"all sales"` without word boundaries. In `"delete all sales records"`, the substring `"all sales"` was present, triggering a false-positive match.
  2. Destructive natural-language commands (e.g. *"Delete all sales records"*, *"Drop the database"*, *"Remove every transaction"*) were not intercepted by the SQL injection regex, which only looked for strict SQL keywords like `delete from` or `drop table`.
- **Resolution**:
  1. Created a unified `DESTRUCTIVE_PATTERN` that intercepts both direct SQL commands and natural language destructive requests (`delete`, `drop`, `remove`, `wipe`, `clear`, `truncate`) targeting tables, databases, records, or transactions, rejecting them immediately with HTTP 400 Bad Request before any analytics function can run.
  2. Refactored all intent matchers to use compiled regex with word boundaries `\b` and intent-specific phrasing rather than loose substring checks.
  3. Removed `"all sales"` and loose single-word matches from `TOTAL_REVENUE_PATTERNS`.
  4. Standardized fallback response to return `Intent.UNKNOWN` with the friendly clarification: *"I couldn't identify a supported sales analytics question. Please try one of the example questions."*
  5. Added regression tests verifying that destructive commands are rejected, unrelated queries do not match total revenue, and rejected requests make zero modifications to the database.

---

## 4. Verification & Test Results

### Automated Test Execution
Automated tests were executed against the codebase:
```powershell
$env:PYTHONPATH="."
.venv\Scripts\pytest.exe -v
```

**Results**:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.2.0, pluggy-1.7.0
rootdir: D:\RSG
plugins: anyio-4.15.1
collected 40 items

tests/test_analytics.py::test_total_revenue_calculation PASSED           [  2%]
tests/test_analytics.py::test_highest_revenue_product PASSED             [  5%]
tests/test_analytics.py::test_highest_revenue_product_tie PASSED         [  7%]
tests/test_analytics.py::test_monthly_revenue_trend PASSED               [ 10%]
tests/test_analytics.py::test_highest_revenue_region PASSED              [ 12%]
tests/test_analytics.py::test_month_to_month_comparison_growth PASSED    [ 15%]
tests/test_analytics.py::test_month_to_month_comparison_zero_base PASSED [ 17%]
tests/test_analytics.py::test_empty_database_analytics PASSED            [ 20%]
tests/test_api.py::test_health_endpoint PASSED                           [ 22%]
tests/test_api.py::test_examples_endpoint PASSED                         [ 25%]
tests/test_api.py::test_summary_endpoint PASSED                          [ 27%]
tests/test_api.py::test_ask_total_revenue PASSED                         [ 30%]
tests/test_api.py::test_ask_highest_revenue_product PASSED               [ 32%]
tests/test_api.py::test_ask_monthly_revenue_trend PASSED                 [ 35%]
tests/test_api.py::test_ask_highest_revenue_region PASSED                [ 37%]
tests/test_api.py::test_ask_month_to_month_comparison PASSED             [ 40%]
tests/test_api.py::test_ask_empty_question_returns_400 PASSED            [ 42%]
tests/test_api.py::test_ask_sql_injection_returns_400 PASSED             [ 45%]
tests/test_api.py::test_ask_unknown_question PASSED                      [ 47%]
tests/test_api.py::test_ask_destructive_requests_rejected PASSED         [ 50%]
tests/test_api.py::test_rejected_requests_do_not_modify_database PASSED  [ 52%]
tests/test_api.py::test_random_unrelated_text_does_not_return_total_revenue PASSED [ 55%]
tests/test_data_loader.py::test_missing_unit_price_exclusion PASSED      [ 57%]
tests/test_data_loader.py::test_zero_quantity_exclusion PASSED           [ 60%]
tests/test_data_loader.py::test_returned_status_exclusion PASSED         [ 62%]
tests/test_data_loader.py::test_valid_record_net_revenue_calculation PASSED [ 65%]
tests/test_data_loader.py::test_repeated_csv_ingestion_idempotence PASSED [ 67%]
tests/test_question_interpreter.py::test_extract_months_various_formats PASSED [ 70%]
tests/test_question_interpreter.py::test_total_revenue_variations PASSED [ 72%]
tests/test_question_interpreter.py::test_highest_revenue_product_variations PASSED [ 75%]
tests/test_question_interpreter.py::test_monthly_revenue_trend_variations PASSED [ 77%]
tests/test_question_interpreter.py::test_highest_revenue_region_variations PASSED [ 80%]
tests/test_question_interpreter.py::test_month_to_month_comparison_variations PASSED [ 82%]
tests/test_question_interpreter.py::test_month_to_month_generic_question PASSED [ 85%]
tests/test_question_interpreter.py::test_month_to_month_single_month_clarification PASSED [ 87%]
tests/test_question_interpreter.py::test_empty_question PASSED           [ 90%]
tests/test_question_interpreter.py::test_unsupported_question PASSED     [ 92%]
tests/test_question_interpreter.py::test_sql_injection_rejection PASSED  [ 95%]
tests/test_question_interpreter.py::test_destructive_requests_rejected PASSED [ 97%]
tests/test_question_interpreter.py::test_unrelated_text_does_not_return_total_revenue PASSED [100%]

======================== 40 passed, 1 warning in 2.22s ========================
```

### Live HTTP Verification
- Started `uvicorn app.main:app --port 8000`
- Verified `GET /health` -> `200 OK`, `database_connected: True`, `eligible_transactions: 48`
- Verified `GET /summary` -> `200 OK`, 51 processed, 48 eligible, 3 excluded with exact reasons
- Verified `POST /ask` across all 5 questions -> Exact matching answers returned
- Verified SQL injection attempt `DROP TABLE sales_transactions;` -> `400 Bad Request` with security notice
- Verified Streamlit UI launched and responded with `200 OK` on port 8501

---

## 5. Limitations & Future Improvements

### Current Limitations
1. **Dataset Scope**: The current dataset contains 51 transactions covering H1 2026 (January to June 2026). Inquiries for July-December 2026 yield zero sales with explanatory notes.
2. **Deterministic Interpreter**: The question interpreter relies on linguistic heuristics, regex, and keyword dictionaries. While fast, safe, and cost-free, it only supports questions within the defined business analytics scope.

### Planned Improvements
1. **Optional LLM Intent Extractor**: Add an optional plug-in for Gemini or a local Ollama model to map complex multi-sentence queries to structured parameters, while maintaining the parameterized SQL execution firewall.
2. **Export Capabilities**: Add CSV / Excel download buttons in the Streamlit UI for user-queried breakdown tables.
3. **Multi-File Ingestion**: Extend the ingestion module to accept dynamic CSV file uploads via drag-and-drop in the UI.

