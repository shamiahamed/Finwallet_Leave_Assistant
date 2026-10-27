# Department-level summaries: headcount, request counts and approved leave days
from datetime import date

from app.repositories.workbook_repository import (
    APPROVED_STATUS,
    SHEET_EMPLOYEES,
    SHEET_REQUESTS,
    WorkbookRepository,
)
from app.schemas.common import Evidence
from app.schemas.leave import DepartmentSummaryOut, DepartmentSummaryResponse
from app.services.leave_request_service import LeaveRequestService


class DepartmentService:
    def __init__(self, repository: WorkbookRepository, requests: LeaveRequestService) -> None:
        self._repo = repository
        self._requests = requests

    def summary(
        self,
        department: str | None = None,
        leave_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> DepartmentSummaryResponse:

        reqs, applied = self._requests.filtered_frame(
            leave_type=leave_type, start_date=start_date, end_date=end_date, department=department
        )
        emp = self._repo.employees
        if "department" in applied:
            emp = emp[emp["Department"] == applied["department"]]
        statuses = sorted(self._repo.leave_requests["Approval Status"].unique())

        rows: list[DepartmentSummaryOut] = []
        for dept, people in emp.groupby("Department"):
            dept_reqs = reqs[reqs["Department"] == dept]
            approved = dept_reqs[dept_reqs["Approval Status"] == APPROVED_STATUS]
            counts = dept_reqs["Approval Status"].value_counts()
            rows.append(
                DepartmentSummaryOut(
                    department=dept,
                    total_employees=len(people),
                    active_employees=int((people["Employment Status"] == "Active").sum()),
                    inactive_employees=int((people["Employment Status"] != "Active").sum()),
                    total_requests=len(dept_reqs),
                    requests_by_status={s: int(counts.get(s, 0)) for s in statuses},
                    approved_days=int(approved["Days"].sum()),
                )
            )
        rows.sort(key=lambda r: (-r.approved_days, r.department))
        top_days = rows[0].approved_days if rows else 0
        top = [r.department for r in rows if r.approved_days == top_days] if top_days > 0 else []
        bottom_days = rows[-1].approved_days if rows else 0
        bottom = [r.department for r in rows if r.approved_days == bottom_days] if rows else []
        approved_ids = reqs[reqs["Approval Status"] == APPROVED_STATUS]["Request ID"].tolist()

        return DepartmentSummaryResponse(
            departments=rows,
            top_departments_by_approved_days=top,
            bottom_departments_by_approved_days=bottom,
            filters_applied=applied,
            evidence=Evidence(worksheets=[SHEET_EMPLOYEES, SHEET_REQUESTS], request_ids=approved_ids),
        )
