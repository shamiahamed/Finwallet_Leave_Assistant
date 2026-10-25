import pandas as pd

from app.exceptions.errors import (
    AmbiguousEmployeeError,
    EmployeeNotFoundError,
    InvalidFilterError,
)
from app.repositories.workbook_repository import SHEET_EMPLOYEES, WorkbookRepository
from app.schemas.common import Evidence
from app.schemas.employee import (
    EmployeeListResponse,
    EmployeeOut,
    EmployeeResponse,
    HeadcountResponse,
    ManagerResponse,
)
from app.utils.choices import resolve_choice
from app.utils.ids import normalize_employee_id

MIN_NAME_LENGTH = 2


def _to_out(row: pd.Series, names: dict[str, str]) -> EmployeeOut:
    manager_id = None if pd.isna(row["Manager ID"]) else str(row["Manager ID"])
    return EmployeeOut(
        employee_id=row["Employee ID"],
        full_name=row["Full Name"],
        department=row["Department"],
        designation=row["Designation"],
        join_date=row["Join Date"].date(),
        manager_id=manager_id,
        manager_name=names.get(manager_id) if manager_id else None,
        office=row["Office"],
        employment_status=row["Employment Status"],
    )


class EmployeeService:
    def __init__(self, repository: WorkbookRepository) -> None:
        self._repo = repository

    def get_row(self, employee_id: str) -> pd.Series:
        # Return the raw employee row
        normalized = normalize_employee_id(employee_id)
        df = self._repo.employees
        match = df[df["Employee ID"] == normalized]
        if match.empty:
            raise EmployeeNotFoundError(f"No employee found with ID {normalized}.")
        return match.iloc[0]

    @staticmethod
    def _names(df: pd.DataFrame) -> dict[str, str]:
        return dict(zip(df["Employee ID"], df["Full Name"]))

    @staticmethod
    def _evidence(ids: list[str]) -> Evidence:
        return Evidence(worksheets=[SHEET_EMPLOYEES], employee_ids=ids)

    def _filtered(self, department: str | None, status: str | None) -> tuple[pd.DataFrame, str | None, str | None]:
        df = self._repo.employees
        if department:
            department = resolve_choice(department, df["Department"], "department")
            df = df[df["Department"] == department]
        if status:
            all_statuses = self._repo.employees["Employment Status"]
            status = resolve_choice(status, all_statuses, "employment status")
            df = df[df["Employment Status"] == status]
        return df, department, status

    # operations
    def get_employee(self, employee_id: str) -> EmployeeResponse:
        row = self.get_row(employee_id)
        names = self._names(self._repo.employees)
        return EmployeeResponse(employee=_to_out(row, names), evidence=self._evidence([row["Employee ID"]]))

    def find_by_name(self, name: str) -> EmployeeResponse:
       
        query = " ".join(name.lower().split())
        if len(query) < MIN_NAME_LENGTH:
            raise InvalidFilterError("Please provide at least two characters of the employee's name.")
        df = self._repo.employees
        lowered = df["Full Name"].str.lower()
        matches = df[lowered == query]
        if matches.empty:
            tokens = query.split()
            keep = lowered.apply(
                lambda full: all(any(w.startswith(t) for w in full.split()) for t in tokens)
            )
            matches = df[keep]
        if matches.empty:
            raise EmployeeNotFoundError("No employee matches that name.")
        if len(matches) > 1:
            candidates = [
                {"employee_id": r["Employee ID"], "full_name": r["Full Name"], "department": r["Department"]}
                for _, r in matches.iterrows()
            ]
            raise AmbiguousEmployeeError(
                f"{len(matches)} employees match that name. Please give an employee ID or full name.",
                details={"candidates": candidates},
            )
        row = matches.iloc[0]
        return EmployeeResponse(
            employee=_to_out(row, self._names(df)), evidence=self._evidence([row["Employee ID"]])
        )

    def get_manager(self, employee_id: str) -> ManagerResponse:
        row = self.get_row(employee_id)
        df = self._repo.employees
        names = self._names(df)
        ids = [row["Employee ID"]]
        manager = None
        if not pd.isna(row["Manager ID"]):
            manager_row = df[df["Employee ID"] == row["Manager ID"]].iloc[0]
            manager = _to_out(manager_row, names)
            ids.append(manager.employee_id)
        return ManagerResponse(
            employee_id=row["Employee ID"],
            employee_name=row["Full Name"],
            has_manager=manager is not None,
            manager=manager,
            evidence=self._evidence(ids),
        )

    def headcount(self, department: str | None = None, employment_status: str | None = None) -> HeadcountResponse:
        df, department, status = self._filtered(department, employment_status)
        return HeadcountResponse(
            department=department,
            employment_status=status,
            count=len(df),
            evidence=self._evidence(df["Employee ID"].tolist()),
        )

    def list_employees(
        self, department: str | None = None, employment_status: str | None = None, limit: int = 25
    ) -> EmployeeListResponse:
        df, _, _ = self._filtered(department, employment_status)
        names = self._names(self._repo.employees)
        page = df.head(limit)
        return EmployeeListResponse(
            total_matches=len(df),
            returned=len(page),
            employees=[_to_out(r, names) for _, r in page.iterrows()],
            evidence=self._evidence(page["Employee ID"].tolist()),
        )
