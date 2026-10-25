# Leave requests, balances, policy and department-summary response schemas.
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Evidence


class LeaveRequestOut(BaseModel):
    request_id: str
    employee_id: str
    employee_name: str
    department: str
    leave_type: str
    start_date: date
    end_date: date
    days: int
    approval_status: str
    reason: str
    approver_id: str
    approver_name: str


class LeaveRequestListResponse(BaseModel):
    total_matches: int = Field(description="All requests matching the filters.")
    total_days: int = Field(description="Sum of 'Days' over ALL matching requests, any status.")
    returned: int
    truncated: bool = Field(description="True when `limit` cut the list short.")
    filters_applied: dict[str, str]
    requests: list[LeaveRequestOut]
    evidence: Evidence


class BalanceOut(BaseModel):
    leave_type: str
    year: int
    annual_entitlement: int
    approved_days_used: int
    remaining_days: int


class BalanceResponse(BaseModel):
    employee_id: str
    employee_name: str
    balances: list[BalanceOut]
    note: str | None = Field(default=None, description="Present when a leave type has no balance row.")
    evidence: Evidence


class AllBalancesResponse(BaseModel):
    scope: Literal["all"] = "all"
    total_employees: int = Field(description="Employees considered, including those with no balance rows.")
    results: list[BalanceResponse]
    note: str | None = Field(default=None, description="Present when some employees have no balance records.")
    evidence: Evidence


class DepartmentBalancesResponse(BaseModel):
    scope: Literal["department"] = "department"
    department: str
    total_employees: int = Field(description="Employees in the department, including those with no balance rows.")
    results: list[BalanceResponse]
    note: str | None = Field(default=None, description="Present when some employees have no balance records.")
    evidence: Evidence


class PolicyOut(BaseModel):
    leave_type: str
    annual_days: int
    accrual: str
    payment: str


class PolicyResponse(BaseModel):
    policies: list[PolicyOut]
    evidence: Evidence


class DepartmentSummaryOut(BaseModel):
    department: str
    total_employees: int
    active_employees: int
    inactive_employees: int
    total_requests: int = Field(description="Requests matching the optional filters.")
    requests_by_status: dict[str, int]
    approved_days: int = Field(description="Sum of 'Days' of Approved requests matching the filters.")


class DepartmentSummaryResponse(BaseModel):
    departments: list[DepartmentSummaryOut] = Field(description="Sorted by approved_days, descending.")
    top_departments_by_approved_days: list[str] = Field(description="All departments tied for the max.")
    filters_applied: dict[str, str]
    evidence: Evidence


class HealthResponse(BaseModel):
    status: str
    environment: str
    workbook_loaded: bool
    row_counts: dict[str, int]
    workbook_refresh: dict | None = None
