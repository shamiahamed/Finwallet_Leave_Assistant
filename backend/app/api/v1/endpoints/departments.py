from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_department_service
from app.schemas.leave import DepartmentSummaryResponse
from app.services.department_service import DepartmentService

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.get(
    "/summary",
    response_model=DepartmentSummaryResponse,
    summary="Department summaries (headcount, requests, approved leave days)",
)
def department_summary(
    department: str | None = Query(None, description="Limit to one department"),
    leave_type: str | None = Query(None, description="Only count this leave type"),
    start_date: date | None = Query(None, description="ISO date; overlap semantics"),
    end_date: date | None = Query(None, description="ISO date; overlap semantics"),
    service: DepartmentService = Depends(get_department_service),
) -> DepartmentSummaryResponse:
    return service.summary(department, leave_type, start_date, end_date)
