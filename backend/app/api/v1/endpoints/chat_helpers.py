"""Regex patterns and helper functions for the chat endpoint.

These deterministic helpers detect greetings, capabilities questions,
employee-list questions, and other high-confidence routing signals
without calling the LLM. They are kept separate from the endpoint
definition and the intent router so they can be tested in isolation.
"""

import re

# Maximum allowed question length.
MAX_QUESTION_LENGTH = 1000

# --- Static response messages -------------------------------------------------

GREETING_RESPONSE = (
    "Hi! I'm Finwallet, your Employee Leave Management Assistant. "
    "How may I help you today? You can ask me about leave balances, leave "
    "requests, leave policies, employees, departments, or uploaded leave "
    "policy documents."
)

CAPABILITIES_RESPONSE = (
    "I can help with:\n"
    "  - Employee lookups, employee lists, and headcounts by department or status.\n"
    "  - Leave balances, including balances by employee, department, or leave type.\n"
    "  - Leave requests and leave history, filtered by employee, department, "
    "status, leave type, or date range.\n"
    "  - Leave policies and department-level leave summaries.\n"
    "  - Questions about uploaded policy documents.\n\n"
    "Try: \"Show employees in Finance\", \"What is EMP001's leave balance?\", "
    "\"Show pending leave requests\", or \"What is the Sick Leave policy?\""
)

BALANCE_VS_HISTORY_RESPONSE = (
    "Leave balance and leave history are different things:\n"
    "  - Leave balance is your entitlement: how many days you are allowed "
    "to take, how many you have used, and how many remain.\n"
    "  - Leave history is your record of leave requests: each request you "
    "have submitted, its dates, leave type, and approval status.\n\n"
    "Ask me about your balance (e.g. \"What is EMP001's leave balance?\") "
    "or your history (e.g. \"Show leave history for EMP001\")."
)

HISTORY_EMPLOYEE_REQUIRED = (
    "I can check leave history, but I need to know which employee. "
    "Please provide an employee ID or full name."
)

SUBMISSION_DATE_UNAVAILABLE = (
    "The Leave Requests worksheet does not store a submission or application "
    "date. It only contains each request's start date, end date, days, and "
    "status. I can filter by the leave-date range instead."
)

POLICY_DETAIL_UNAVAILABLE = (
    "The Leave Policy worksheet contains only annual days, accrual, and "
    "payment, so it does not include that detail. Upload a relevant policy "
    "document to answer this question."
)

# --- Compiled regex patterns --------------------------------------------------

GREETING_RE = re.compile(
    r"(?:(?:hi|hello|hey)(?:\s+there)?|"
    r"good\s+(?:morning|afternoon|evening))"
    r"(?:\s*,?\s*finwallet)?"
    r"\s*[!.?,]*",
    re.IGNORECASE,
)

CAPABILITIES_RE = re.compile(
    r"(?:please\s+)?(?:"
    r"what\s+can\s+(?:you|finwallet)\s+do(?:\s+for\s+me)?|"
    r"what\s+do\s+you\s+do|"
    r"what\s+can\s+you\s+help\s+(?:me\s+)?with|"
    r"what\s+are\s+your\s+(?:capabilities|skills)|"
    r"how\s+can\s+you\s+help(?:\s+me)?|"
    r"what\s+(?:questions|things)\s+can\s+i\s+ask(?:\s+you)?|"
    r"what\s+(?:can|may)\s+i\s+ask(?:\s+you)?|"
    r"help(?:\s+me)?|"
    r"show\s+(?:me\s+)?examples?"
    r")[\s?.!]*",
    re.IGNORECASE,
)

# Questions asking for the difference between leave balance and leave history.
BALANCE_VS_HISTORY_RE = re.compile(
    r"\b(?:difference|distinction|vs\.?|versus|compare)\b[^?]{0,80}\b(?:leave\s+)?balances?\b[^?]{0,80}\b(?:leave\s+)?history\b|"
    r"\b(?:leave\s+)?history\b[^?]{0,80}\b(?:difference|distinction|vs\.?|versus|compare)\b[^?]{0,80}\b(?:leave\s+)?balances?\b",
    re.IGNORECASE,
)

EMPLOYEE_LIST_RE = re.compile(
    r"\b(?:list|show|display|find|get|view|see|give\s+me)\b"
    r"[^?]{0,60}\b(?:employees|staff)\b",
    re.IGNORECASE,
)

EMPLOYEE_LIST_EXCLUDE_RE = re.compile(
    r"\b(?:leave|leaves|request|requests|balance|balances|policy|policies|"
    r"history|taken|used|took|headcount|how\s+many|count)\b",
    re.IGNORECASE,
)

# "Compare X balances by department" routes to department balance aggregation.
DEPT_BALANCE_COMPARE_RE = re.compile(
    r"\bcompar\w*\b[^?]{0,80}\b(?:sick|casual|earned|unpaid|maternity|paternity|"
    r"leave)\s+balances?\b[^?]{0,40}\bby\s+departments?\b",
    re.IGNORECASE,
)

# Extracts a candidate department name from employee-list questions.
DEPARTMENT_CANDIDATE_RE = re.compile(
    r"\b(?:in|for|of|within|from)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)",
    re.IGNORECASE,
)

START_DATE_RE = re.compile(r"\bstarting\s+in\b", re.IGNORECASE)
END_DATE_RE = re.compile(r"\bending\s+in\b", re.IGNORECASE)


def is_greeting(question: str) -> bool:
    """Return True when the question is a simple greeting."""
    return bool(GREETING_RE.fullmatch(question.strip()))


def is_capabilities_question(question: str) -> bool:
    """Return True when the question asks what the assistant can do."""
    return bool(CAPABILITIES_RE.fullmatch(question.strip()))


def is_employee_list_question(question: str) -> bool:
    """Return True when the question asks to list or show employees."""
    text = question.strip()
    return bool(EMPLOYEE_LIST_RE.search(text)) and not bool(
        EMPLOYEE_LIST_EXCLUDE_RE.search(text)
    )


def detect_employment_status(question: str) -> str | None:
    """Detect "active" or "inactive" employment status from a question."""
    lowered = question.lower()
    if re.search(r"\binactive\b", lowered):
        return "Inactive"
    if re.search(r"\bactive\b", lowered):
        return "Active"
    return None


def is_balance_vs_history_question(question: str) -> bool:
    """Return True when the question asks about balance vs history distinction."""
    return bool(BALANCE_VS_HISTORY_RE.search(question))