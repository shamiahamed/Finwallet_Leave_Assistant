from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_balance_service, get_leave_request_service, get_policy_service
from app.schemas.leave import BalanceResponse, LeaveRequestListResponse, PolicyResponse
from app.services.balance_service import BalanceService
from app.services.leave_request_service import LeaveRequestService
from app.services.policy_service import PolicyService

router = APIRouter(tags=["Leave"])


@router.get(
    "/leave-requests",
    response_model=LeaveRequestListResponse,
    summary="Leave requests with optional filters",
    description=(
        "Date filtering uses OVERLAP semantics (inclusive): a request matches when any of its "
        "days falls within start_date..end_date. Either bound may be omitted."
    ),
)
def list_leave_requests(
    employee_id: str | None = Query(None, description="e.g. EMP025"),
    leave_type: str | None = Query(None, description="e.g. 'Sick Leave' or 'sick'"),
    approval_status: str | None = Query(None, description="Approved, Pending, Rejected or Cancelled"),
    department: str | None = Query(None, description="Department of the requesting employee"),
    start_date: date | None = Query(None, description="ISO date YYYY-MM-DD"),
    end_date: date | None = Query(None, description="ISO date YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=200),
    service: LeaveRequestService = Depends(get_leave_request_service),
) -> LeaveRequestListResponse:
    return service.list_requests(
        employee_id, leave_type, approval_status, start_date, end_date, department, limit
    )


@router.get(
    "/leave-balances/{employee_id}",
    response_model=BalanceResponse,
    summary="Leave balances for an employee (2026 snapshot)",
)
def get_leave_balances(
    employee_id: str,
    leave_type: str | None = Query(None, description="e.g. Casual Leave"),
    service: BalanceService = Depends(get_balance_service),
) -> BalanceResponse:
    return service.get_balances(employee_id, leave_type)


@router.get("/leave-policy", response_model=PolicyResponse, summary="Company leave policy")
def get_leave_policy(
    leave_type: str | None = Query(None, description="e.g. Earned Leave"),
    service: PolicyService = Depends(get_policy_service),
) -> PolicyResponse:
    return service.get_policies(leave_type)
