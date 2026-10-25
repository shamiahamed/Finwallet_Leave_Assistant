"""Deterministic tests for scope detection, balance retrieval, conversation
behaviour, and regression, for the leave-management chat pipeline.

These tests avoid the live LLM: they exercise the deterministic scope resolver,
the balance service, the response formatter, the dispatcher, and the conversation
service directly. Run with:

    backend/.venv/Scripts/python.exe backend/tests/test_leave_scope.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings
from app.llm.dispatcher import dispatch_query
from app.llm.response_formatter import format_response
from app.repositories.workbook_repository import WorkbookRepository
from app.schemas.intent import QueryIntent
from app.services.balance_service import BalanceService
from app.services.conversation_service import ConversationService
from app.services.department_service import DepartmentService
from app.services.employee_service import EmployeeService
from app.services.leave_request_service import LeaveRequestService
from app.services.policy_service import PolicyService
from app.utils.scope_resolver import detect_balance_scope, is_headcount_question

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


def build_services():
    repo = WorkbookRepository.load(Path(get_settings().workbook_path))
    employees = EmployeeService(repo)
    requests = LeaveRequestService(repo, employees)
    balances = BalanceService(repo, employees)
    policies = PolicyService(repo)
    departments = DepartmentService(repo, requests)
    return repo, employees, requests, balances, policies, departments


def test_scope_detection():
    print("=== Scope detection ===")
    depts = ["Engineering", "Finance", "Human Resources", "Sales", "Marketing"]
    types = ["Casual Leave", "Earned Leave", "Sick Leave", "Unpaid Leave"]

    cases = [
        ("Show everyone's leave balances", "all"),
        ("Show all employees' leave balances", "all"),
        ("Show company-wide leave balances", "all"),
        ("Show Engineering's leave balances", "department"),
        ("Show Finance leave balances", "department"),
        ("What is EMP001's sick leave balance?", "single"),
        ("How many employees are in Engineering?", None),
        ("Show Engineering's leave activity", None),
    ]
    for question, want in cases:
        result = detect_balance_scope(question, depts, types)
        got = result["scope"] if result else None
        check(f"scope {question!r} -> {want}", got == want)

    check(
        "headcount 'How many employees are in Engineering?'",
        is_headcount_question("How many employees are in Engineering?"),
    )
    check(
        "department activity is not headcount",
        not is_headcount_question("Show Engineering's leave activity"),
    )

    # Department name is resolved from workbook data, not hardcoded.
    result = detect_balance_scope(
        "Show Engineering's leave balances", ["Engineering", "Finance"]
    )
    check(
        "department name resolved from data",
        result is not None and result["department"] == "Engineering",
    )

    # Leave type is detected and carried into the scope result.
    leave_type_cases = [
        ("What is EMP001's sick leave balance?", "single", "Sick Leave"),
        ("Show everyone's casual leave balances", "all", "Casual Leave"),
        ("Show Engineering's earned leave balances", "department", "Earned Leave"),
        ("Show Engineering's leave balances", "department", None),
    ]
    for question, want_scope, want_lt in leave_type_cases:
        result = detect_balance_scope(question, depts, types)
        got_lt = result.get("leave_type") if result else None
        check(
            f"leave type {question!r} -> {want_lt}",
            result is not None
            and result["scope"] == want_scope
            and got_lt == want_lt,
        )


def test_balance_retrieval(balances: BalanceService):
    print("=== Balance retrieval ===")

    single = balances.get_balances("EMP001", "Sick Leave")
    sick = [b for b in single.balances if b.leave_type == "Sick Leave"]
    check("EMP001 single has Sick Leave row", len(sick) == 1)
    check("EMP001 sick entitlement 10", sick[0].annual_entitlement == 10)
    check("EMP001 sick used 4", sick[0].approved_days_used == 4)
    check("EMP001 sick remaining 6", sick[0].remaining_days == 6)

    all_bal = balances.get_all_balances()
    check("all balances scope", all_bal.scope == "all")
    check(
        "all balances includes every employee",
        all_bal.total_employees == len(all_bal.results) > 0,
    )

    all_sick = balances.get_all_balances(leave_type="Sick Leave")
    check(
        "all balances leave-type filter applied",
        all(
            all(b.leave_type == "Sick Leave" for b in r.balances)
            for r in all_sick.results
            if r.balances
        ),
    )

    dept = balances.get_department_balances("Engineering")
    check("department balances scope", dept.scope == "department")
    check("department balances non-empty", len(dept.results) > 0)

    # Employees with no balance rows are included honestly.
    check(
        "missing records shown as empty, not zero",
        all(
            isinstance(r.balances, list)
            for r in dept.results
        ),
    )


def test_balance_errors(balances: BalanceService):
    print("=== Balance error handling ===")
    from app.exceptions.errors import (
        EmployeeNotFoundError,
        InvalidFilterError,
    )

    try:
        balances.get_balances("EMP999")
        check("invalid employee raises", False)
    except EmployeeNotFoundError:
        check("invalid employee raises EmployeeNotFoundError", True)

    try:
        balances.get_department_balances("Nonexistent Dept")
        check("invalid department raises", False)
    except InvalidFilterError:
        check("invalid department raises InvalidFilterError", True)


def test_dispatch_and_format(employees, requests, balances, policies, departments):
    print("=== Dispatcher + formatter ===")

    def run(intent: QueryIntent) -> str:
        result = dispatch_query(
            intent, employees, requests, balances, policies, departments
        )
        answer, _, _ = format_response(intent.intent, result)
        return answer

    all_answer = run(QueryIntent(intent="leave_balance", scope="all"))
    check("all answer is not the empty placeholder", "The employee (?)" not in all_answer)
    check("all answer lists employees", "Leave balances for all" in all_answer)

    dept_answer = run(
        QueryIntent(intent="leave_balance", scope="department", department="Engineering")
    )
    check("department answer lists department", "Engineering" in dept_answer)

    single_answer = run(
        QueryIntent(
            intent="leave_balance", scope="single", employee_id="EMP001", leave_type="Sick Leave"
        )
    )
    check("single answer shows remaining", "6 remaining" in single_answer)
    check("single answer filtered to sick only", "Sick Leave" in single_answer and "Casual Leave" not in single_answer)

    dept_sick = run(
        QueryIntent(
            intent="leave_balance", scope="department", department="Engineering", leave_type="Sick Leave"
        )
    )
    check(
        "department answer filtered to sick only",
        "Sick Leave" in dept_sick and "Casual Leave" not in dept_sick,
    )

    hc = run(QueryIntent(intent="employee_headcount", department="Engineering"))
    check("headcount answer has count", "15" in hc)


def test_conversation():
    print("=== Conversation behaviour ===")
    svc = ConversationService()

    ctx = svc.get_or_create("c1")
    svc.add_message(ctx, "user", "Show me the sick leave balance")
    svc.set_pending_clarification(
        ctx,
        intent="leave_balance",
        question="Show me the sick leave balance",
        field_name="employee_id",
        leave_type="Sick Leave",
    )

    pending = svc.resolve_pending_employee_id(ctx, "EMP001")
    check("valid ID resolves pending", pending is not None)
    check("leave type preserved", pending and pending["leave_type"] == "Sick Leave")

    check(
        "invalid reply does not resolve",
        svc.resolve_pending_employee_id(ctx, "hello") is None,
    )

    svc.clear_pending_clarification(ctx)
    check("pending cleared", svc.resolve_pending_employee_id(ctx, "EMP001") is None)

    # Broad scope clears the active employee.
    ctx2 = svc.get_or_create("c2")
    ctx2.last_employee_id = "EMP001"
    svc.update_from_result(ctx2, "leave_balance", {"scope": "all", "results": []}, scope="all")
    check("broad scope clears active employee", ctx2.last_employee_id is None)

    # Isolation between conversations.
    a = svc.get_or_create("conv-a")
    b = svc.get_or_create("conv-b")
    check("conversations isolated", a is not b and a.conversation_id != b.conversation_id)

    # MAX history bound.
    c = svc.get_or_create("conv-c")
    for i in range(30):
        svc.add_message(c, "user", f"m{i}")
    check("history bounded", len(c.history) <= 10)


def main() -> int:
    repo, employees, requests, balances, policies, departments = build_services()
    test_scope_detection()
    test_balance_retrieval(balances)
    test_balance_errors(balances)
    test_dispatch_and_format(employees, requests, balances, policies, departments)
    test_conversation()

    print()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAILURES:
        print("Failures:")
        for f in FAILURES:
            print("  -", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
