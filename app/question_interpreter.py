"""
Question Interpreter for AI Business Intelligence Assistant.

Performs safe, deterministic natural language question-intent matching:
- Maps natural-language queries to approved analytics functions.
- Extracts and validates parameters (e.g. month names and years).
- Rejects SQL injection attempts and destructive payloads.
- Explains unsupported or ambiguous questions clearly.
- Requires no paid API keys or external LLM connections.
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class Intent(str, Enum):
    TOTAL_REVENUE = "total_revenue"
    HIGHEST_REVENUE_PRODUCT = "highest_revenue_product"
    MONTHLY_REVENUE_TREND = "monthly_revenue_trend"
    HIGHEST_REVENUE_REGION = "highest_revenue_region"
    MONTH_TO_MONTH_COMPARISON = "month_to_month_comparison"
    DATASET_SUMMARY = "dataset_summary"
    UNSAFE_QUERY = "unsafe_query"
    UNKNOWN = "unknown"


MONTH_NAME_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}

DESTRUCTIVE_PATTERN = re.compile(
    r"("
    r"\bdrop\s+(the\s+|our\s+|all\s+|every\s+)?(table|tables|database|schema|data|records?)\b|"
    r"\bdelete\s+(from\s+)?(all\s+|every\s+|the\s+|our\s+)?(\w+\s+)?(records?|transactions?|database|tables?|data|everything|\*)?|"
    r"\bdelete\s+from\b|"
    r"\bdelete\s+all\b|"
    r"\bremove\s+(the\s+|our\s+|all\s+|every\s+)?(transactions?|records?|sales|data|database|tables?|everything)\b|"
    r"\b(wipe|clear|erase|destroy|truncate)\s+(the\s+|our\s+|all\s+|every\s+)?(database|tables?|records?|transactions?|data|sales|everything)\b|"
    r"\b(truncate\s+table|alter\s+table|insert\s+into|update\s+\w+\s+set|union\s+select|select\s+.*\s+from|exec\(|execute\(|--|;)\b"
    r")",
    re.IGNORECASE
)


def contains_hostile_or_destructive_request(text: str) -> bool:
    """Detect potential SQL injection, hostile commands, or destructive requests."""
    return bool(DESTRUCTIVE_PATTERN.search(text))


def extract_months_from_query(text: str, default_year: int = 2026) -> List[str]:
    """
    Extract YYYY-MM strings from a natural language string.
    Supports month names (e.g. 'January 2026', 'Feb', 'March and April 2026')
    and ISO representations (e.g. '2026-01', '01-2026').
    """
    found_months: List[Tuple[int, str]] = []  # (position_in_text, "YYYY-MM")
    text_lower = text.lower()

    # Find general year if present in text
    year_match = re.search(r"\b(20[2-3][0-9])\b", text_lower)
    global_year = int(year_match.group(1)) if year_match else default_year

    # 1. Match numeric YYYY-MM or YYYY/MM
    for m in re.finditer(r"\b(20[2-3][0-9])[-/](0?[1-9]|1[0-2])\b", text_lower):
        yr = int(m.group(1))
        mo = int(m.group(2))
        found_months.append((m.start(), f"{yr:04d}-{mo:02d}"))

    # 2. Match numeric MM-YYYY or MM/YYYY
    for m in re.finditer(r"\b(0?[1-9]|1[0-2])[-/](20[2-3][0-9])\b", text_lower):
        mo = int(m.group(1))
        yr = int(m.group(2))
        found_months.append((m.start(), f"{yr:04d}-{mo:02d}"))

    # 3. Match month names with optional adjacent year
    month_regex = r"\b(" + "|".join(MONTH_NAME_MAP.keys()) + r")\b(?:\s+(20[2-3][0-9]))?"
    for m in re.finditer(month_regex, text_lower):
        m_name = m.group(1)
        m_year_str = m.group(2)
        mo_num = MONTH_NAME_MAP[m_name]
        yr_num = int(m_year_str) if m_year_str else global_year
        iso_str = f"{yr_num:04d}-{mo_num:02d}"
        found_months.append((m.start(), iso_str))

    # Sort by appearance in query and remove duplicates while preserving order
    found_months.sort(key=lambda x: x[0])
    ordered_unique: List[str] = []
    for _, iso in found_months:
        if iso not in ordered_unique:
            ordered_unique.append(iso)

    return ordered_unique


# Intent 1: Total Revenue patterns (using word boundaries)
TOTAL_REVENUE_PATTERNS = [
    re.compile(r"\b(what\s+is|what's|show|tell\s+me|calculate|get|find)\s+(the\s+|our\s+)?(total\s+|overall\s+|gross\s+|net\s+)?(revenue|sales|income|turnover)\b", re.I),
    re.compile(r"\b(total|overall|gross|net)\s+(revenue|sales|turnover|income)\b", re.I),
    re.compile(r"\b(sum\s+of\s+sales|sum\s+of\s+revenue)\b", re.I),
    re.compile(r"\bhow\s+much\s+(total\s+)?(revenue|sales|money)\b", re.I),
    re.compile(r"\bhow\s+much\s+did\s+we\s+make\b", re.I),
    re.compile(r"^(total\s+revenue|overall\s+revenue|net\s+revenue|total\s+sales|overall\s+sales)\??$", re.I),
]

# Intent 2: Highest Revenue Product patterns
PRODUCT_PATTERNS = [
    re.compile(r"\b(which|what)\s+(product|item|merchandise|sku)\b", re.I),
    re.compile(r"\b(top|best)\s+selling\s+(product|item|merchandise|sku)\b", re.I),
    re.compile(r"\b(top|best)\s+(product|item|sku)\b", re.I),
    re.compile(r"\b(product|item|sku|merchandise)\s+(with\s+|generating\s+|generated\s+)?(the\s+)?(highest|top|most|best|maximum|leading|greatest)\s+(revenue|sales)?\b", re.I),
    re.compile(r"\b(highest|top|most|best|maximum|leading)\s+(revenue|sales|selling)\s+(product|item|sku|merchandise)\b", re.I),
    re.compile(r"\b(product|item|sku)\s+(performed\s+best|ranking)\b", re.I),
]

# Intent 3: Monthly Revenue Trend patterns
TREND_PATTERNS = [
    re.compile(r"\b(month\s+by\s+month|month-by-month)\b", re.I),
    re.compile(r"\bmonthly\s+(revenue|sales|trend|breakdown)\b", re.I),
    re.compile(r"\b(revenue|sales)\s+(trend|by\s+month|over\s+time)\b", re.I),
    re.compile(r"\btrend\s+over\s+months\b", re.I),
    re.compile(r"\bmonthly\s+trend\b", re.I),
    re.compile(r"\bwhat\s+is\s+the\s+monthly\s+revenue\s+trend\b", re.I),
    re.compile(r"\bshow\s+sales\s+month\s+by\s+month\b", re.I),
]

# Intent 4: Highest Revenue Region patterns
REGION_PATTERNS = [
    re.compile(r"\b(which|what)\s+(region|territory|area|zone|location)\b", re.I),
    re.compile(r"\b(top|best)\s+(region|territory|area|zone|location)\b", re.I),
    re.compile(r"\b(region|territory|area|zone|location)\s+(with\s+|generating\s+|generated\s+)?(the\s+)?(highest|top|most|best|maximum|leading|greatest)\s+(revenue|sales)?\b", re.I),
    re.compile(r"\b(highest|top|most|best|maximum|leading)\s+(revenue|sales|selling)\s+(region|territory|area|zone|location)\b", re.I),
    re.compile(r"\b(region|territory|area|zone)\s+(performed\s+best|ranking)\b", re.I),
    re.compile(r"\bwhere\s+did\s+we\s+sell\s+the\s+most\b", re.I),
    re.compile(r"\bregional\s+(sales|revenue)\b", re.I),
]

# Summary patterns
SUMMARY_PATTERNS = [
    re.compile(r"\b(dataset\s+summary|data\s+quality|excluded\s+records?|excluded\s+transactions?|data\s+health|ingestion\s+audit)\b", re.I),
    re.compile(r"^summary\??$", re.I),
    re.compile(r"\bhow\s+many\s+(records|rows|transactions)\b", re.I),
]


def interpret_question(question: str) -> Dict[str, Any]:
    """
    Interpret a user's natural language question and map to an analytics execution plan.

    Returns:
        dict containing:
        - intent: Intent enum value
        - function_name: Corresponding analytics function name
        - parameters: Dictionary of parameters (e.g. month1, month2)
        - is_supported: bool
        - clarification_message: Helpful explanation if ambiguous or unsupported
        - original_question: The original user question
    """
    cleaned = question.strip() if question else ""
    if not cleaned:
        return {
            "intent": Intent.UNKNOWN.value,
            "function_name": None,
            "parameters": {},
            "is_supported": False,
            "clarification_message": "Please enter a business question to analyze.",
            "original_question": question
        }

    # Step 1: Detect destructive commands and hostile query attempts
    if contains_hostile_or_destructive_request(cleaned):
        return {
            "intent": Intent.UNSAFE_QUERY.value,
            "function_name": None,
            "parameters": {},
            "is_supported": False,
            "clarification_message": (
                "Destructive operations and direct database modifications are not permitted. "
                "Please ask questions in natural language, such as 'What is the total revenue?'."
            ),
            "original_question": question
        }

    q_lower = cleaned.lower()

    # Step 2: Intent 5 - Month-to-Month Comparison
    extracted_months = extract_months_from_query(cleaned)
    has_comparison_keyword = bool(re.search(
        r"\b(between\s+(two\s+)?months|month\s+to\s+month|month-to-month|month\s+over\s+month|mom|change\s+between|compare|difference\s+between|revenue\s+change\s+from|vs|versus)\b",
        q_lower
    ))

    if len(extracted_months) >= 2:
        return {
            "intent": Intent.MONTH_TO_MONTH_COMPARISON.value,
            "function_name": "get_month_to_month_comparison",
            "parameters": {"month1": extracted_months[0], "month2": extracted_months[1]},
            "is_supported": True,
            "clarification_message": None,
            "original_question": question
        }
    elif len(extracted_months) == 1 and has_comparison_keyword:
        return {
            "intent": Intent.MONTH_TO_MONTH_COMPARISON.value,
            "function_name": None,
            "parameters": {"month1": extracted_months[0]},
            "is_supported": False,
            "clarification_message": (
                f"You specified only one month ({extracted_months[0]}). "
                "Please provide two months to compare, for example: "
                "'Compare January 2026 and February 2026'."
            ),
            "original_question": question
        }
    elif len(extracted_months) == 0 and bool(re.search(r"\b(between\s+(two\s+)?months|month\s+to\s+month|month-to-month|month\s+over\s+month|compare\s+months)\b", q_lower)):
        return {
            "intent": Intent.MONTH_TO_MONTH_COMPARISON.value,
            "function_name": "get_month_to_month_comparison",
            "parameters": {"month1": "2026-01", "month2": "2026-02"},
            "is_supported": True,
            "clarification_message": (
                "Comparing the first two recorded months (January 2026 vs February 2026). "
                "You can also specify any two months, such as 'Compare April 2026 and May 2026'."
            ),
            "original_question": question
        }

    # Step 3: Intent 2 - Highest Revenue Product
    if any(p.search(cleaned) for p in PRODUCT_PATTERNS):
        return {
            "intent": Intent.HIGHEST_REVENUE_PRODUCT.value,
            "function_name": "get_highest_revenue_product",
            "parameters": {},
            "is_supported": True,
            "clarification_message": None,
            "original_question": question
        }

    # Step 4: Intent 4 - Highest Revenue Region
    if any(p.search(cleaned) for p in REGION_PATTERNS):
        return {
            "intent": Intent.HIGHEST_REVENUE_REGION.value,
            "function_name": "get_highest_revenue_region",
            "parameters": {},
            "is_supported": True,
            "clarification_message": None,
            "original_question": question
        }

    # Step 5: Intent 3 - Monthly Revenue Trend
    if any(p.search(cleaned) for p in TREND_PATTERNS):
        return {
            "intent": Intent.MONTHLY_REVENUE_TREND.value,
            "function_name": "get_monthly_revenue_trend",
            "parameters": {},
            "is_supported": True,
            "clarification_message": None,
            "original_question": question
        }

    # Step 6: Intent 1 - Total Revenue
    if any(p.search(cleaned) for p in TOTAL_REVENUE_PATTERNS):
        return {
            "intent": Intent.TOTAL_REVENUE.value,
            "function_name": "get_total_revenue",
            "parameters": {},
            "is_supported": True,
            "clarification_message": None,
            "original_question": question
        }

    # Step 7: Dataset Summary / Health
    if any(p.search(cleaned) for p in SUMMARY_PATTERNS):
        return {
            "intent": Intent.DATASET_SUMMARY.value,
            "function_name": "get_dataset_and_quality_summary",
            "parameters": {},
            "is_supported": True,
            "clarification_message": None,
            "original_question": question
        }

    # Step 8: Fallback - Explicit Unsupported / Unknown
    return {
        "intent": Intent.UNKNOWN.value,
        "function_name": None,
        "parameters": {},
        "is_supported": False,
        "clarification_message": (
            "I couldn't identify a supported sales analytics question. Please try one of the example questions:\n"
            "- What is the total revenue?\n"
            "- Which product generated the highest revenue?\n"
            "- What is the monthly revenue trend?\n"
            "- Which region generated the highest sales?\n"
            "- How did revenue change between January and February 2026?"
        ),
        "original_question": question
    }
