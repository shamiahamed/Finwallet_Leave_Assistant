from app.repositories.workbook_repository import (
    SHEET_BALANCES,
    SHEET_EMPLOYEES,
    SHEET_POLICY,
    WorkbookRepository,
)
from app.schemas.common import Evidence
from app.schemas.leave import (
    AllBalancesResponse,
    BalanceOut,
    BalanceResponse,
    DepartmentBalancesResponse,
)
from app.services.employee_service import EmployeeService
from app.utils.choices import resolve_choice
import pandas as pd


class BalanceService:
    def __init__(self, repository: WorkbookRepository, employees: EmployeeService) -> None:
        self._repo = repository
        self._employees = employees

    def get_balances(self, employee_id: str, leave_type: str | None = None) -> BalanceResponse:
        employee = self.get_employee_row(employee_id)
        policy_types = self._repo.leave_policy["Leave Type"].tolist()
        wanted = [resolve_choice(leave_type, policy_types, "leave type")] if leave_type else policy_types

        df = self._repo.leave_balances
        df = df[(df["Employee ID"] == employee["Employee ID"]) & (df["Leave Type"].isin(wanted))]
        balances = [
            BalanceOut(
                leave_type=r["Leave Type"],
                year=int(r["Year"]),
                annual_entitlement=int(r["Annual Entitlement"]),
                approved_days_used=int(r["Approved Days Used"]),
                remaining_days=int(r["Remaining Days"]),
            )
            for _, r in df.iterrows()
        ]
        untracked = [t for t in wanted if t not in set(df["Leave Type"])]
        note = None
        sheets = [SHEET_BALANCES]
        if untracked:
            note = (
                f"The Leave Balances sheet has no balance record for {', '.join(untracked)}. "
                "See the Leave Policy sheet for its entitlement rules."
            )
            sheets.append(SHEET_POLICY)
        return BalanceResponse(
            employee_id=employee["Employee ID"],
            employee_name=employee["Full Name"],
            balances=balances,
            note=note,
            evidence=Evidence(worksheets=sheets, employee_ids=[employee["Employee ID"]]),
        )

    def get_employee_row(self, employee_id: str):
        return self._employees.get_row(employee_id)  

    
    def get_all_balances(self, leave_type: str | None = None) -> AllBalancesResponse:
        """Return leave balances for every employee.

        Employees are read from the Employees worksheet, so people with no
        matching Leave Balances rows are still included (with an empty balance
        list rather than an invented zero).
        """
        employees = self._employees.list_employees(limit=len(self._repo.employees)).employees

        results = [
            self.get_balances(
                employee_id=employee.employee_id,
                leave_type=leave_type,
            )
            for employee in employees
        ]

        missing = [r.employee_id for r in results if not r.balances]
        note = None
        if missing:
            note = (
                f"{len(missing)} employee(s) have no matching balance record: "
                f"{', '.join(missing)}."
            )

        return AllBalancesResponse(
            total_employees=len(employees),
            results=results,
            note=note,
            evidence=Evidence(
                worksheets=[SHEET_EMPLOYEES, SHEET_BALANCES],
                employee_ids=[e.employee_id for e in employees],
            ),
        )

    def filter_remaining_balances(
        self,
        *,
        threshold: int,
        threshold_operator: str = "at_most",
        leave_type: str | None = None,
        department: str | None = None,
        by_department: bool = False,
    ) -> dict:
        """Filter employees by their actual remaining balance.

        Employees without a matching Leave Balances row are reported as
        missing records and are never treated as having zero remaining days.
        """
        policy_types = self._repo.leave_policy["Leave Type"].tolist()
        if leave_type:
            leave_type = resolve_choice(leave_type, policy_types, "leave type")

        employees = self._repo.employees
        balances = self._repo.leave_balances
        if leave_type:
            balances = balances[balances["Leave Type"] == leave_type]

        def rows_for(employee_id: str):
            return balances[balances["Employee ID"] == employee_id]

        def matches_threshold(remaining: pd.Series) -> pd.Series:
            if threshold_operator == "exactly":
                return remaining == threshold
            if threshold_operator == "less_than":
                return remaining < threshold
            # "at_most" and "zero" both mean <=
            return remaining <= threshold

        if by_department:
            departments = []
            total_matching = 0
            total_missing = 0
            for name in sorted(employees["Department"].dropna().astype(str).unique()):
                group = employees[employees["Department"] == name]
                matched = 0
                missing = 0
                for _, employee in group.iterrows():
                    rows = rows_for(employee["Employee ID"])
                    if rows.empty:
                        missing += 1
                    elif matches_threshold(rows["Remaining Days"]).any():
                        matched += 1
                total_matching += matched
                total_missing += missing
                departments.append(
                    {
                        "department": name,
                        "count": matched,
                        "total_employees": len(group),
                        "missing_balance_records": missing,
                    }
                )

            return {
                "threshold_filter": True,
                "count_by_department": True,
                "count_only": True,
                "threshold": threshold,
                "threshold_operator": threshold_operator,
                "leave_type": leave_type,
                "department": None,
                "departments": departments,
                "total_matching": total_matching,
                "total_employees": len(employees),
                "missing_count": total_missing,
                "evidence": {
                    "worksheets": [SHEET_EMPLOYEES, SHEET_BALANCES],
                    "employee_ids": employees["Employee ID"].tolist(),
                },
            }

        if department:
            department = resolve_choice(department, employees["Department"], "department")
            employees = employees[employees["Department"] == department]

        results = []
        missing_ids = []
        for _, employee in employees.iterrows():
            rows = rows_for(employee["Employee ID"])
            if rows.empty:
                missing_ids.append(employee["Employee ID"])
                continue

            matched_rows = rows[matches_threshold(rows["Remaining Days"])]
            if matched_rows.empty:
                continue

            results.append(
                {
                    "employee_id": employee["Employee ID"],
                    "employee_name": employee["Full Name"],
                    "balances": [
                        {
                            "leave_type": row["Leave Type"],
                            "year": int(row["Year"]),
                            "annual_entitlement": int(row["Annual Entitlement"]),
                            "approved_days_used": int(row["Approved Days Used"]),
                            "remaining_days": int(row["Remaining Days"]),
                        }
                        for _, row in matched_rows.iterrows()
                    ],
                }
            )

        return {
            "threshold_filter": True,
            "count_by_department": False,
            "count_only": False,
            "threshold": threshold,
            "threshold_operator": threshold_operator,
            "leave_type": leave_type,
            "department": department,
            "scope": "department" if department else "all",
            "results": results,
            "total_matching": len(results),
            "total_employees": len(employees),
            "missing_count": len(missing_ids),
            "missing_employee_ids": missing_ids,
            "evidence": {
                "worksheets": [SHEET_EMPLOYEES, SHEET_BALANCES],
                "employee_ids": employees["Employee ID"].tolist(),
            },
        }

    def get_department_balance_summary(
        self, leave_type: str | None = None, year: int | None = None
    ) -> dict:
        employees = self._repo.employees
        balances = self._repo.leave_balances
        if leave_type:
            balances = balances[balances["Leave Type"] == leave_type]
        if year is not None:
            balances = balances[balances["Year"] == year]
        merged = balances.merge(
            employees[["Employee ID", "Department"]], on="Employee ID", how="left"
        )
        agg = (
            merged.groupby("Department")
            .agg(
                employee_count=("Employee ID", "nunique"),
                total_entitlement=("Annual Entitlement", "sum"),
                total_used=("Approved Days Used", "sum"),
                total_remaining=("Remaining Days", "sum"),
            )
            .reset_index()
        )
        rows = [
            {
                "department": r["Department"],
                "employee_count": int(r["employee_count"]),
                "total_entitlement": int(r["total_entitlement"]),
                "total_used": int(r["total_used"]),
                "total_remaining": int(r["total_remaining"]),
            }
            for _, r in agg.iterrows()
        ]
        return {"leave_type": leave_type, "year": year, "departments": rows}

    def get_department_balances(
        self,
        department: str,
        leave_type: str | None = None,
    ) -> DepartmentBalancesResponse:
        """Return leave balances for employees in one department.

        The department name is validated against the Employees worksheet.
        Employees with no matching balance rows are included with an empty
        balance list.
        """
        employees = self._employees.list_employees(
            department=department,
            limit=len(self._repo.employees),
        ).employees

        results = [
            self.get_balances(
                employee_id=employee.employee_id,
                leave_type=leave_type,
            )
            for employee in employees
        ]

        missing = [r.employee_id for r in results if not r.balances]
        note = None
        if missing:
            note = (
                f"{len(missing)} employee(s) have no matching balance record: "
                f"{', '.join(missing)}."
            )

        return DepartmentBalancesResponse(
            department=department,
            total_employees=len(employees),
            results=results,
            note=note,
            evidence=Evidence(
                worksheets=[SHEET_EMPLOYEES, SHEET_BALANCES],
                employee_ids=[e.employee_id for e in employees],
            ),
        )

