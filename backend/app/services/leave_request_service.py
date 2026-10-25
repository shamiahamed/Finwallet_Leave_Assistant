# Leave-request queries: history and filtering joined with employee names.
from datetime import date

import pandas as pd

from app.repositories.workbook_repository import (
    SHEET_EMPLOYEES,
    SHEET_REQUESTS,
    WorkbookRepository,
)
from app.schemas.common import Evidence
from app.schemas.leave import LeaveRequestListResponse, LeaveRequestOut
from app.services.employee_service import EmployeeService
from app.utils.choices import resolve_choice
from app.utils.dates import overlap_mask, validate_date_range

class LeaveRequestService:
    def __init__(self, repository: WorkbookRepository, employees: EmployeeService) -> None:
        self._repo = repository
        self._employees = employees

    def _joined(self) -> pd.DataFrame:

        emp = self._repo.employees
        requester = emp[["Employee ID", "Full Name", "Department"]].rename(
            columns={"Full Name": "Employee Name"}
        )
        approver = emp[["Employee ID", "Full Name"]].rename(
            columns={"Employee ID": "Approver ID", "Full Name": "Approver Name"}
        )
        return (
            self._repo.leave_requests.merge(requester, on="Employee ID", how="left")
            .merge(approver, on="Approver ID", how="left")
        )

    def filtered_frame(
        self,
        employee_id: str | None = None,
        leave_type: str | None = None,
        approval_status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        department: str | None = None,
        date_mode: str = "overlap",
    ) -> tuple[pd.DataFrame, dict[str, str]]:

        validate_date_range(start_date, end_date)
        df = self._joined()
        applied: dict[str, str] = {}

        if employee_id:
            row = self._employees.get_row(employee_id)  # 422 bad format / 404 unknown
            applied["employee_id"] = row["Employee ID"]
            df = df[df["Employee ID"] == row["Employee ID"]]
        if leave_type:
            applied["leave_type"] = resolve_choice(leave_type, df["Leave Type"].unique().tolist()
                                                   + self._repo.leave_policy["Leave Type"].tolist(), "leave type")
            df = df[df["Leave Type"] == applied["leave_type"]]
        if approval_status:
            statuses = self._repo.leave_requests["Approval Status"]
            applied["approval_status"] = resolve_choice(approval_status, statuses, "approval status")
            df = df[df["Approval Status"] == applied["approval_status"]]
        if department:
            departments = self._repo.employees["Department"]
            applied["department"] = resolve_choice(department, departments, "department")
            df = df[df["Department"] == applied["department"]]
        if start_date:
            applied["start_date"] = start_date.isoformat()
        if end_date:
            applied["end_date"] = end_date.isoformat()
        applied["date_mode"] = date_mode
        if date_mode == "start_date":
            if start_date:
                df = df[df["Start Date"] >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df["Start Date"] <= pd.Timestamp(end_date)]
        elif date_mode == "end_date":
            if start_date:
                df = df[df["End Date"] >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df["End Date"] <= pd.Timestamp(end_date)]
        else:
            df = df[overlap_mask(df["Start Date"], df["End Date"], start_date, end_date)]
        return df.sort_values(["Start Date", "Request ID"]), applied

    def list_requests(
        self,
        employee_id: str | None = None,
        leave_type: str | None = None,
        approval_status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        department: str | None = None,
        limit: int = 50,
        date_mode: str = "overlap",
    ) -> LeaveRequestListResponse:
        df, applied = self.filtered_frame(
            employee_id, leave_type, approval_status, start_date, end_date, department, date_mode
        )
        page = df.head(limit)
        items = [
            LeaveRequestOut(
                request_id=r["Request ID"],
                employee_id=r["Employee ID"],
                employee_name=r["Employee Name"],
                department=r["Department"],
                leave_type=r["Leave Type"],
                start_date=r["Start Date"].date(),
                end_date=r["End Date"].date(),
                days=int(r["Days"]),
                approval_status=r["Approval Status"],
                reason=r["Reason"],
                approver_id=r["Approver ID"],
                approver_name=r["Approver Name"],
            )
            for _, r in page.iterrows()
        ]
        return LeaveRequestListResponse(
            total_matches=len(df),
            total_days=int(df["Days"].sum()),
            returned=len(items),
            truncated=len(df) > len(items),
            filters_applied=applied,
            requests=items,
            evidence=Evidence(
                worksheets=[SHEET_REQUESTS, SHEET_EMPLOYEES],
                employee_ids=sorted(df["Employee ID"].unique().tolist()),
                request_ids=df["Request ID"].tolist(),
            ),
        )

    def list_requesting_employees(
        self,
        leave_type: str | None = None,
        approval_status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        department: str | None = None,
        date_mode: str = "overlap",
    ) -> dict:
        """Return distinct employees with leave requests in the filter range."""
        df, applied = self.filtered_frame(
            leave_type=leave_type,
            approval_status=approval_status,
            start_date=start_date,
            end_date=end_date,
            department=department,
            date_mode=date_mode,
        )

        employees: list[dict] = []
        if not df.empty:
            grouped = (
                df.groupby(
                    ["Employee ID", "Employee Name", "Department"],
                    dropna=False,
                )
                .agg(
                    request_count=("Request ID", "nunique"),
                    total_days=("Days", "sum"),
                )
                .reset_index()
                .sort_values(["Employee Name", "Employee ID"])
            )
            employees = [
                {
                    "employee_id": row["Employee ID"],
                    "employee_name": row["Employee Name"],
                    "department": row["Department"],
                    "request_count": int(row["request_count"]),
                    "total_days": int(row["total_days"]),
                }
                for _, row in grouped.iterrows()
            ]

        return {
            "group_history": True,
            "total_matching_requests": len(df),
            "total_days": int(df["Days"].sum()),
            "total_employees": len(employees),
            "employees": employees,
            "filters_applied": applied,
            "evidence": {
                "worksheets": [SHEET_REQUESTS, SHEET_EMPLOYEES],
                "employee_ids": sorted(df["Employee ID"].unique().tolist()),
                "request_ids": df["Request ID"].tolist(),
            },
        }
