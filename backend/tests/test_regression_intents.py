"""Regression checks for the other intents routed by the dispatcher.

Run: backend/.venv/Scripts/python.exe backend/tests/test_regression_intents.py
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
from app.services.department_service import DepartmentService
from app.services.employee_service import EmployeeService
from app.services.leave_request_service import LeaveRequestService
from app.services.policy_service import PolicyService

PASS = 0
FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


repo = WorkbookRepository.load(Path(get_settings().workbook_path))
employees = EmployeeService(repo)
requests = LeaveRequestService(repo, employees)
balances = BalanceService(repo, employees)
policies = PolicyService(repo)
departments = DepartmentService(repo, requests)


def run(intent):
    result = dispatch_query(intent, employees, requests, balances, policies, departments)
    return format_response(intent.intent, result)


print("=== Employee lookup ===")
a, d, e = run(QueryIntent(intent="employee_lookup", employee_id="EMP002"))
check("EMP002 lookup names employee", "Priya Kumar" in a and "EMP002" in a)

print("=== Headcount (all) ===")
a, d, e = run(QueryIntent(intent="employee_headcount"))
check("total headcount is 100", "100" in a)

print("=== Leave requests ===")
a, d, e = run(QueryIntent(intent="leave_requests", employee_id="EMP001"))
check("EMP001 requests answered", "leave" in a.lower())

print("=== Leave policy ===")
a, d, e = run(QueryIntent(intent="leave_policy", leave_type="Sick Leave"))
check("sick policy present", "Sick Leave" in a)

print("=== Department summary ===")
a, d, e = run(QueryIntent(intent="department_summary", department="Engineering"))
check("engineering summary present", "Engineering" in a)

print("=== Documents unavailable fallback ===")
a, d, e = run(QueryIntent(intent="document_question"))
check("no document store -> message", "not available" in a.lower() or "no document" in a.lower())

print()
print(f"PASS={PASS} FAIL={FAIL}")
raise SystemExit(1 if FAIL else 0)
