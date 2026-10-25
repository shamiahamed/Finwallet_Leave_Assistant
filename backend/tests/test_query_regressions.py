"""Focused regressions for chat routing and structured-data filtering."""

import sys
from datetime import date
from pathlib import Path

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.api.v1.endpoints import chat
from app.core.config import get_settings
from app.exceptions.errors import AmbiguousEmployeeError
from app.llm.response_formatter import format_response
from app.repositories.workbook_repository import WorkbookRepository
from app.schemas.intent import QueryIntent
from app.services.balance_service import BalanceService
from app.services.department_service import DepartmentService
from app.services.employee_service import EmployeeService
from app.services.leave_request_service import LeaveRequestService
from app.services.policy_service import PolicyService
from app.utils.dates import (
    asks_submission_date,
    detect_leave_date_range,
)
from app.utils.scope_resolver import (
    detect_balance_threshold,
    is_department_breakdown_question,
)

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  OK   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}")


def build_services(repo: WorkbookRepository):
    employees = EmployeeService(repo)
    requests = LeaveRequestService(repo, employees)
    balances = BalanceService(repo, employees)
    policies = PolicyService(repo)
    departments = DepartmentService(repo, requests)
    return employees, requests, balances, policies, departments


def run_question(
    question: str,
    intent: QueryIntent,
    services,
    conversation_id: str,
    setup=None,
):
    employees, requests, balances, policies, departments = services
    context = chat.conversation_service.get_or_create(conversation_id)
    if setup:
        setup(context)

    original = chat.parse_intent
    chat.parse_intent = lambda _question, context=None: (intent, None)
    try:
        prepared = chat._prepare_answer(
            question,
            conversation_id,
            employees,
            requests,
            balances,
            policies,
            departments,
        )
        chat._commit_answer(prepared)
        return prepared
    finally:
        chat.parse_intent = original


def run_greeting(question: str, services, conversation_id: str, setup=None):
    employees, requests, balances, policies, departments = services
    context = chat.conversation_service.get_or_create(conversation_id)
    if setup:
        setup(context)

    original = chat.parse_intent

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Greeting must not invoke the LLM parser.")

    chat.parse_intent = fail_if_called
    try:
        prepared = chat._prepare_answer(
            question,
            conversation_id,
            employees,
            requests,
            balances,
            policies,
            departments,
        )
        chat._commit_answer(prepared)
        return prepared
    finally:
        chat.parse_intent = original


def synthetic_repo() -> WorkbookRepository:
    repo = WorkbookRepository.load(Path(get_settings().workbook_path))
    sheets = {name: frame.copy() for name, frame in repo._sheets.items()}
    balances = sheets["Leave Balances"]

    balances.loc[
        (balances["Employee ID"] == "EMP001")
        & (balances["Leave Type"] == "Sick Leave"),
        "Remaining Days",
    ] = 0
    balances.loc[
        (balances["Employee ID"] == "EMP002")
        & (balances["Leave Type"] == "Sick Leave"),
        "Remaining Days",
    ] = 5
    balances.loc[
        (balances["Employee ID"] == "EMP003")
        & (balances["Leave Type"] == "Sick Leave"),
        "Remaining Days",
    ] = 6
    sheets["Leave Balances"] = balances[
        ~(
            (balances["Employee ID"] == "EMP004")
            & (balances["Leave Type"] == "Sick Leave")
        )
    ]
    return WorkbookRepository(sheets)


def test_date_filters(services):
    print("=== Date filters ===")
    prepared = run_question(
        "Show leave requests between January 31, 2026 and February 2, 2026",
        QueryIntent(intent="leave_requests"),
        services,
        "reg-date-range",
    )
    request_ids = {request["request_id"] for request in prepared.data["requests"]}

    check("requested date range is applied", prepared.intent.start_date == date(2026, 1, 31))
    check("requested end date is applied", prepared.intent.end_date == date(2026, 2, 2))
    check("overlapping request is included", "LR0027" in request_ids)
    check("fully contained request is included", "LR0150" in request_ids)

    this_month = detect_leave_date_range(
        "Show leave requests this month",
        today=date(2026, 3, 15),
    )
    check(
        "this month uses the application date",
        this_month == (date(2026, 3, 1), date(2026, 3, 31)),
    )
    check(
        "submission wording is detected",
        asks_submission_date("Show leave requests submitted this month"),
    )
    check(
        "modal may is not treated as a month",
        detect_leave_date_range(
            "Show leave requests for employees who may have pending leave",
            today=date(2026, 3, 15),
        )
        is None,
    )
    check(
        "May is still treated as a month",
        detect_leave_date_range(
            "Show leave requests in May",
            today=date(2026, 3, 15),
        )
        == (date(2026, 5, 1), date(2026, 5, 31)),
    )


def test_submission_date(services):
    print("=== Submission date ===")
    prepared = run_question(
        "Show leave requests submitted in March 2026",
        QueryIntent(intent="leave_requests"),
        services,
        "reg-submission",
    )
    check(
        "submission date limitation is explained",
        "does not store a submission" in prepared.answer,
    )
    check("submission answer lists no sample requests", "\u2022" not in prepared.answer)


def test_greetings(services):
    print("=== Greetings ===")
    standalone = [
        "Hi",
        "Hello",
        "Hey",
        "Good morning",
        "Good afternoon",
        "Good evening",
    ]
    with_name = [
        "Hi Finwallet",
        "Hello, Finwallet!",
        "Hey there Finwallet.",
        "Good morning, Finwallet",
        "Good evening Finwallet!",
    ]

    for greeting in standalone + with_name:
        prepared = run_greeting(
            greeting,
            services,
            "reg-greeting",
        )
        check(
            f"greeting '{greeting}' returns the deterministic response",
            prepared.intent.intent == "greeting"
            and prepared.answer == chat._GREETING_RESPONSE
            and prepared.data is None
            and prepared.evidence is None
            and prepared.metrics is None,
        )

    for question in [
        "Hi, what is my leave balance?",
        "Hi Finwallet, show my leave balance",
        "Good morning, what is EMP001's balance?",
    ]:
        check(
            f"greeting plus question '{question}' is not a greeting",
            not chat._is_greeting(question),
        )

    prepared = run_question(
        "Hi, what is EMP001's leave balance?",
        QueryIntent(
            intent="leave_balance",
            scope="single",
            employee_id="EMP001",
            leave_type="Sick Leave",
        ),
        services,
        "reg-greeting-question",
    )
    check(
        "greeting plus real question follows normal balance routing",
        prepared.intent.intent == "leave_balance"
        and "EMP001" in prepared.answer
        and prepared.answer != chat._GREETING_RESPONSE,
    )

    prepared = run_question(
        "Hi, what is my leave balance?",
        QueryIntent(intent="greeting"),
        services,
        "reg-greeting-misclassified",
    )
    check(
        "misclassified greeting cannot swallow a real question",
        prepared.intent.intent != "greeting"
        and prepared.answer != chat._GREETING_RESPONSE,
    )

    def setup(context):
        context.last_employee_id = "EMP001"
        context.last_employee_name = "Arun Kumar"
        context.last_intent = "leave_balance"
        context.last_document_name = "Policy.pdf"

    run_greeting(
        "Hello",
        services,
        "reg-greeting-context",
        setup=setup,
    )
    context = chat.conversation_service.get_or_create("reg-greeting-context")
    check(
        "greeting preserves active employee and document context",
        context.last_employee_id == "EMP001"
        and context.last_employee_name == "Arun Kumar"
        and context.last_intent == "leave_balance"
        and context.last_document_name == "Policy.pdf",
    )


def test_count_only(services):
    print("=== Count-only requests ===")
    prepared = run_question(
        "How many leave requests does EMP001 have?",
        QueryIntent(intent="leave_requests"),
        services,
        "reg-count",
    )
    check("count-only answer reports the total", "2 leave requests" in prepared.answer)
    check("count-only answer omits the sample list", "\u2022" not in prepared.answer)


def test_unknown_employee(services):
    print("=== Unknown employee ===")
    prepared = run_question(
        "Show leave requests for John Doe",
        QueryIntent(intent="leave_requests"),
        services,
        "reg-unknown-name",
    )
    check("unknown name is not treated as an all-employee query", "couldn't find" in prepared.answer)
    check("unknown name response has no request list", "\u2022" not in prepared.answer)
    check("unknown name response has no data payload", prepared.data is None)

    prepared = run_question(
        "Show leave requests for an unknown employee",
        QueryIntent(intent="leave_requests"),
        services,
        "reg-unknown-literal",
    )
    check("literal unknown employee is not treated as all requests", "couldn't find" in prepared.answer)

    try:
        run_question(
            "Show leave requests for Arun",
            QueryIntent(intent="leave_requests"),
            services,
            "reg-ambiguous-partial",
        )
        check("partial ambiguous name still reaches ambiguity handling", False)
    except AmbiguousEmployeeError:
        check("partial ambiguous name still reaches ambiguity handling", True)


def test_leave_taken_followup(services):
    print("=== Leave-taken follow-up ===")

    def setup(context):
        context.last_employee_id = "EMP001"
        context.last_employee_name = "Arun Kumar"
        context.last_intent = "leave_balance"

    prepared = run_question(
        "How much leave was taken?",
        QueryIntent(intent="leave_balance", scope="single"),
        services,
        "reg-history-context",
        setup=setup,
    )
    check("history follow-up routes to leave requests", prepared.intent.intent == "leave_requests")
    check("history follow-up reuses the active employee", prepared.intent.employee_id == "EMP001")
    check("history follow-up is not a balance summary", "Leave balances" not in prepared.answer)
    check("history follow-up reports leave totals", "leave request" in prepared.answer)

    prepared = run_question(
        "How much leave was taken?",
        QueryIntent(intent="leave_balance", scope="single"),
        services,
        "reg-history-no-context",
    )
    check("history without context asks for an employee", "which employee" in prepared.answer)
    check("history without context does not guess an employee", prepared.intent.intent == "clarify")


def test_invalid_inputs(services):
    print("=== Invalid inputs ===")
    try:
        run_question(
            "Show leave requests between February 2, 2026 and January 31, 2026",
            QueryIntent(intent="leave_requests"),
            services,
            "reg-invalid-range",
        )
        check("reversed date range is rejected", False)
    except HTTPException as exc:
        check("reversed date range is rejected", exc.status_code == 422)

    try:
        run_question(
            "Show leave requests for vacation leave",
            QueryIntent(intent="leave_requests"),
            services,
            "reg-invalid-type",
        )
        check("unsupported leave type is rejected", False)
    except HTTPException as exc:
        check("unsupported leave type is rejected", exc.status_code == 422)
        check("unsupported leave type names the input", "vacation" in str(exc.detail).lower())


def test_threshold_filters(services):
    print("=== Balance thresholds ===")
    employees, requests, balances, policies, departments = services

    zero = balances.filter_remaining_balances(
        threshold=0,
        leave_type="Sick Leave",
    )
    check("zero threshold uses the actual remaining balance", zero["total_matching"] == 1)
    check("zero threshold result is EMP001", zero["results"][0]["employee_id"] == "EMP001")
    check("missing balance records are counted separately", zero["missing_employee_ids"] == ["EMP004"])
    check("missing records are not treated as zero", zero["total_matching"] == 1)

    five = balances.filter_remaining_balances(
        threshold=5,
        leave_type="Sick Leave",
    )
    five_ids = {result["employee_id"] for result in five["results"]}
    check("<= threshold includes the boundary value", five_ids == {"EMP001", "EMP002"})
    check("<= threshold excludes higher balances", "EMP003" not in five_ids)

    by_department = balances.filter_remaining_balances(
        threshold=0,
        leave_type="Sick Leave",
        by_department=True,
    )
    department_counts = {
        item["department"]: item for item in by_department["departments"]
    }
    check("department breakdown returns every department", len(department_counts) == 7)
    check("department breakdown counts zero-balance employees", department_counts["Engineering"]["count"] == 1)
    check("department breakdown keeps missing records separate", department_counts["Sales"]["missing_balance_records"] == 1)
    check("department breakdown returns zero counts", department_counts["Finance"]["count"] == 0)

    data = dict(zero)
    data["count_only"] = True
    answer, _, _ = format_response("leave_balance", data)
    check("threshold count-only answer reports a total", "1 employee" in answer)
    check("threshold count-only answer has no sample list", "\u2022" not in answer)
    check("threshold answer explains missing records", "no matching Sick Leave balance record" in answer)

    prepared = run_question(
        "How many employees in each department have zero remaining Sick Leave?",
        QueryIntent(intent="leave_balance", scope="all"),
        (employees, requests, balances, policies, departments),
        "reg-department-threshold",
    )
    check(
        "department threshold question returns per-department counts",
        "Engineering: 1" in prepared.answer and "Finance: 0" in prepared.answer,
    )
    check(
        "department threshold question reports missing records",
        "Sales: 0 (1 with no balance record)" in prepared.answer,
    )

    prepared = run_question(
        "Does EMP001 have zero remaining Sick Leave?",
        QueryIntent(
            intent="leave_balance",
            scope="single",
            employee_id="EMP001",
            leave_type="Sick Leave",
        ),
        (employees, requests, balances, policies, departments),
        "reg-employee-threshold",
    )
    check(
        "employee-specific threshold stays a single balance lookup",
        prepared.intent.intent == "leave_balance"
        and prepared.intent.employee_id == "EMP001"
        and "EMP001" in prepared.answer
        and "0 remaining" in prepared.answer
        and "Engineering" not in prepared.answer,
    )


def test_threshold_detection():
    print("=== Threshold detection ===")
    spec = detect_balance_threshold("Who has zero remaining leave?")
    check("zero threshold detected", spec == {"value": 0, "operator": "zero"})
    spec = detect_balance_threshold("Who has 0 days left?")
    check("numeric zero detected", spec == {"value": 0, "operator": "zero"})
    spec = detect_balance_threshold("Who has 5 or fewer days left?")
    check("or-fewer threshold detected", spec == {"value": 5, "operator": "at_most"})
    spec = detect_balance_threshold("Who has fewer than 5 days left?")
    check("less-than threshold is strict", spec == {"value": 5, "operator": "less_than"})
    spec = detect_balance_threshold("Who has exactly 5 days remaining?")
    check("exactly threshold detected", spec == {"value": 5, "operator": "exactly"})
    spec = detect_balance_threshold("Who has less than 0 days remaining?")
    check("negative less-than threshold", spec == {"value": 0, "operator": "less_than"})
    check(
        "department breakdown detected",
        is_department_breakdown_question(
            "How many employees in each department have zero remaining leave?"
        ),
    )


def test_september_group_history(services):
    """Issue 1: September group-history returns correct distinct-employee count."""
    print("=== September group-history ===")
    employees, requests, balances, policies, departments = services

    prepared = run_question(
        "Which employees have taken leave in September 2026?",
        QueryIntent(intent="leave_requests"),
        services,
        "reg-sept-history",
    )
    check(
        "September 2026 routes to group leave history",
        prepared.intent.intent == "leave_requests"
        and prepared.intent.scope == "all",
    )
    check(
        "September 2026 date range detected",
        prepared.intent.start_date is not None
        and prepared.intent.end_date is not None,
    )
    check(
        "September 2026 start date is Sep 1",
        prepared.intent.start_date == date(2026, 9, 1),
    )
    check(
        "September 2026 end date is Sep 30",
        prepared.intent.end_date == date(2026, 9, 30),
    )

    # Verify distinct employee count against the workbook.
    data = prepared.data
    check(
        "group history returns employee list",
        data is not None and "employees" in data,
    )
    if data and "employees" in data:
        employee_ids = {emp["employee_id"] for emp in data["employees"]}
        check(
            "September 2026 distinct employee count is 16",
            len(employee_ids) == 16,
        )
        check(
            "group history total_employees is 16",
            data.get("total_employees") == 16,
        )

    # Consistency: list_requests returns the same distinct employees.
    list_result = requests.list_requests(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )
    list_employee_ids = {r.employee_id for r in list_result.requests}
    check(
        "list_requests distinct employees matches group history",
        list_employee_ids == employee_ids,
    )
    check(
        "list_requests truncated flag is correct",
        list_result.truncated == (list_result.total_matches > list_result.returned),
    )


def test_casual_leave_followup_after_history(services):
    """Issue 2: 'what about his casual leave?' after leave history → clarify balance vs history."""
    print("=== Casual Leave follow-up after history ===")
    employees, requests, balances, policies, departments = services

    def setup(context):
        context.last_employee_id = "EMP001"
        context.last_employee_name = "Arun Kumar"
        context.last_intent = "leave_requests"

    prepared = run_question(
        "what about his casual leave?",
        QueryIntent(intent="leave_balance", scope="single"),
        services,
        "reg-casual-after-history",
        setup=setup,
    )
    check(
        "casual follow-up after history is clarify",
        prepared.intent.intent == "clarify",
    )
    check(
        "casual follow-up resolves employee from context",
        prepared.intent.employee_id == "EMP001",
    )
    check(
        "casual follow-up detects Casual Leave type",
        prepared.intent.leave_type == "Casual Leave",
    )
    check(
        "casual follow-up distinguishes balance from history",
        "balance" in prepared.answer.lower()
        and "history" in prepared.answer.lower(),
    )
    check(
        "casual follow-up is not an empty result",
        len(prepared.answer) > 0,
    )


def test_casual_leave_followup_after_balance(services):
    """Issue 2: 'what about his casual leave?' after leave balance → returns Casual Leave balance."""
    print("=== Casual Leave follow-up after balance ===")
    employees, requests, balances, policies, departments = services

    def setup(context):
        context.last_employee_id = "EMP001"
        context.last_employee_name = "Arun Kumar"
        context.last_intent = "leave_balance"

    prepared = run_question(
        "what about his casual leave?",
        QueryIntent(intent="leave_balance", scope="single"),
        services,
        "reg-casual-after-balance",
        setup=setup,
    )
    check(
        "casual follow-up after balance returns balance intent",
        prepared.intent.intent == "leave_balance",
    )
    check(
        "casual follow-up resolves employee from context",
        prepared.intent.employee_id == "EMP001",
    )
    check(
        "casual follow-up detects Casual Leave type",
        prepared.intent.leave_type == "Casual Leave",
    )
    check(
        "casual follow-up shows Casual Leave balance",
        "Casual Leave" in prepared.answer,
    )


def test_limit_pagination(services):
    """Issue 4: limit parameter restricts results without breaking contracts."""
    print("=== Limit pagination ===")
    employees, requests, balances, policies, departments = services

    # Default limit returns up to 50
    default_result = requests.list_requests()
    check(
        "default list_requests returns up to 50",
        default_result.returned <= 50,
    )
    check(
        "default list_requests reports truncation correctly",
        default_result.truncated == (default_result.total_matches > default_result.returned),
    )

    # Custom limit restricts results
    limited_result = requests.list_requests(limit=10)
    check(
        "limit=10 returns at most 10",
        limited_result.returned <= 10,
    )
    check(
        "limit=10 reports total_matches unchanged",
        limited_result.total_matches == default_result.total_matches,
    )
    check(
        "limit=10 reports truncation",
        limited_result.truncated == True,
    )

    # Full result set with limit=total
    full_result = requests.list_requests(limit=1000)
    check(
        "limit=1000 returns all results",
        full_result.returned == full_result.total_matches,
    )
    check(
        "limit=1000 reports no truncation",
        full_result.truncated == False,
    )


def main() -> int:
    repo = WorkbookRepository.load(Path(get_settings().workbook_path))
    services = build_services(repo)

    test_date_filters(services)
    test_submission_date(services)
    test_greetings(services)
    test_count_only(services)
    test_unknown_employee(services)
    test_leave_taken_followup(services)
    test_invalid_inputs(services)
    test_threshold_detection()
    test_september_group_history(services)
    test_casual_leave_followup_after_history(services)
    test_casual_leave_followup_after_balance(services)
    test_limit_pagination(services)

    threshold_services = build_services(synthetic_repo())
    test_threshold_filters(threshold_services)

    print()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAILURES:
        print("Failures:")
        for failure in FAILURES:
            print("  -", failure)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
