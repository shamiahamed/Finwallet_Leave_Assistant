"""Comprehensive regression tests for all fixes."""
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.api.v1.endpoints import chat
from app.core.config import get_settings
from app.repositories.workbook_repository import WorkbookRepository
from app.services.balance_service import BalanceService
from app.services.department_service import DepartmentService
from app.services.employee_service import EmployeeService
from app.services.leave_request_service import LeaveRequestService
from app.services.policy_service import PolicyService


PASS = 0
FAIL = 0


def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  OK   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


def build_services():
    repo = WorkbookRepository.load(Path(get_settings().workbook_path))
    employees = EmployeeService(repo)
    requests = LeaveRequestService(repo, employees)
    balances = BalanceService(repo, employees)
    policies = PolicyService(repo)
    departments = DepartmentService(repo, requests)
    return employees, requests, balances, policies, departments


def call_chat(question, conv_id, services):
    employees, requests, balances, policies, departments = services
    call_count = 0

    def mock_parse(q, context=None):
        nonlocal call_count
        call_count += 1
        from app.schemas.intent import QueryIntent
        return QueryIntent(intent="leave_requests", scope="all"), {"latency_ms": 100}

    with patch.object(chat, "parse_intent", side_effect=mock_parse):
        prepared = chat._prepare_answer(
            question, conv_id,
            employees, requests, balances, policies, departments,
            documents=None, settings=get_settings(),
        )
        chat._commit_answer(prepared)
    return prepared, call_count


# === Test 1: Exact leave-request lookup ===
print("=== Test 1: Exact leave-request lookup ===")
services = build_services()
prepared, calls = call_chat("Is LR0025 approved?", "test-lr-1", services)
check("LR0025 lookup returned result", prepared.result is not None)
check("LR0025 lookup made 0 Groq calls", calls == 0)
check("LR0025 answer mentions LR0025", "LR0025" in prepared.answer)
check("LR0025 answer mentions status", "approved" in prepared.answer.lower())

# Test incomplete ID
try:
    prepared, calls = call_chat("Is LR005 approved?", "test-lr-2", services)
    check("LR005 incomplete ID raises HTTPException", False)
except Exception as e:
    check("LR005 incomplete ID raises HTTPException", "404" in str(e) or "not found" in str(e).lower())

# Test employee vs leave-request ID distinction
prepared, calls = call_chat("What is EMP029's leave balance?", "test-lr-3", services)
check("EMP029 is not treated as LR ID", "LR" not in str(prepared.intent.employee_id or ""))

# === Test 2: Status filters ===
print("\n=== Test 2: Status filters ===")
for status in ["Approved", "Pending", "Rejected", "Cancelled"]:
    prepared, calls = call_chat(f"Show all {status.lower()} leave requests.", f"test-status-{status}", services)
    result = prepared.result
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    actual_statuses = set()
    for r in result.get("requests", []):
        actual_statuses.add(r.get("approval_status"))
    check(f"{status} filter returns only {status}", actual_statuses == {status} or len(actual_statuses) == 0)

# === Test 3: Currently on leave ===
print("\n=== Test 3: Currently on leave ===")
prepared, calls = call_chat("Who is currently on leave in the Engineering department?", "test-current-1", services)
check("Currently on leave made 0 Groq calls", calls == 0)
check("Currently on leave intent is leave_requests", prepared.intent.intent == "leave_requests")
check("Currently on leave has approval_status=Approved", prepared.intent.approval_status == "Approved")

# === Test 4: Show more preserves filters ===
print("\n=== Test 4: Show more preserves filters ===")
prepared, calls = call_chat("Show pending leave requests.", "test-more-1", services)
ctx = chat.conversation_service.get_or_create("test-more-1")
check("After 'Show pending': filters stored", bool(ctx.last_request_filters))

prepared, calls = call_chat("Show more.", "test-more-1", services)
check("Show more preserved Pending filter", prepared.intent.approval_status == "Pending")
check("Show more made 0 Groq calls", calls == 0)

# === Test 5: No double Groq call ===
print("\n=== Test 5: No double Groq call ===")
prepared, calls = call_chat("Show pending leave requests.", "test-double-1", services)
check("Only 1 Groq call for normal query", calls == 1)

# === Test 6: Employee leave balance ===
print("\n=== Test 6: Employee leave balance ===")
prepared, calls = call_chat("What is EMP029's leave balance?", "test-balance-1", services)
check("EMP029 balance lookup made 0 Groq calls", calls == 0)
check("EMP029 balance intent is leave_balance", prepared.intent.intent == "leave_balance")

print(f"\n{'='*50}")
print(f"PASS={PASS} FAIL={FAIL}")
print(f"{'='*50}")