"""End-to-end test: show more preserves filters after commit_answer."""
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


def build_services():
    repo = WorkbookRepository.load(Path(get_settings().workbook_path))
    employees = EmployeeService(repo)
    requests = LeaveRequestService(repo, employees)
    balances = BalanceService(repo, employees)
    policies = PolicyService(repo)
    departments = DepartmentService(repo, requests)
    return employees, requests, balances, policies, departments


def test_show_more_preserves_filters():
    services = build_services()
    employees, requests, balances, policies, departments = services
    conv_id = "test-show-more-1"

    call_count = 0

    def mock_parse(question, context=None):
        nonlocal call_count
        call_count += 1
        from app.schemas.intent import QueryIntent
        return QueryIntent(intent="leave_requests", scope="all"), {"latency_ms": 100}

    # Step 1: Show pending leave requests
    with patch.object(chat, "parse_intent", side_effect=mock_parse):
        p1 = chat._prepare_answer(
            "Show pending leave requests.",
            conv_id,
            employees, requests, balances, policies, departments,
            documents=None, settings=get_settings(),
        )
        chat._commit_answer(p1)

    ctx = chat.conversation_service.get_or_create(conv_id)
    print(f"After 'Show pending': last_request_filters={ctx.last_request_filters}")

    # Step 2: Show more
    call_count = 0
    with patch.object(chat, "parse_intent", side_effect=mock_parse):
        p2 = chat._prepare_answer(
            "Show more.",
            conv_id,
            employees, requests, balances, policies, departments,
            documents=None, settings=get_settings(),
        )
        chat._commit_answer(p2)

    ctx = chat.conversation_service.get_or_create(conv_id)
    print(f"After 'Show more.': intent={p2.intent.intent}, status={p2.intent.approval_status}")
    print(f"  last_request_filters={ctx.last_request_filters}")
    print(f"  Groq calls for 'show more': {call_count}")

    if p2.intent.approval_status == "Pending":
        print("PASS: 'show more' preserved Pending filter")
    else:
        print(f"FAIL: 'show more' lost Pending filter (got {p2.intent.approval_status})")


def test_no_double_groq_call():
    services = build_services()
    employees, requests, balances, policies, departments = services
    call_count = 0

    def mock_parse(question, context=None):
        nonlocal call_count
        call_count += 1
        from app.schemas.intent import QueryIntent
        return QueryIntent(intent="leave_requests", scope="all"), {"latency_ms": 100}

    with patch.object(chat, "parse_intent", side_effect=mock_parse):
        chat._prepare_answer(
            "Show pending leave requests.",
            "test-double-1",
            employees, requests, balances, policies, departments,
            documents=None, settings=get_settings(),
        )

    print(f"\nGroq calls for 'Show pending leave requests': {call_count}")
    if call_count == 1:
        print("PASS: only 1 Groq call")
    else:
        print(f"FAIL: {call_count} Groq calls (expected 1)")


if __name__ == "__main__":
    print("=== Test: Show more preserves filters ===")
    test_show_more_preserves_filters()
    print("\n=== Test: No double Groq call ===")
    test_no_double_groq_call()