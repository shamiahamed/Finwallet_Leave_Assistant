# Employee-related response schemas
from datetime import date

from pydantic import BaseModel

from app.schemas.common import Evidence


class EmployeeOut(BaseModel):
    employee_id: str
    full_name: str
    department: str
    designation: str
    join_date: date
    manager_id: str | None = None
    manager_name: str | None = None
    office: str
    employment_status: str


class EmployeeResponse(BaseModel):
    employee: EmployeeOut
    evidence: Evidence


class EmployeeListResponse(BaseModel):
    total_matches: int
    returned: int
    employees: list[EmployeeOut]
    evidence: Evidence


class ManagerResponse(BaseModel):
    employee_id: str
    employee_name: str
    has_manager: bool
    manager: EmployeeOut | None = None
    evidence: Evidence


class HeadcountResponse(BaseModel):
    department: str | None = None
    employment_status: str | None = None
    count: int
    evidence: Evidence
