from fastapi import APIRouter, Depends, Query

from app.api.deps import get_employee_service
from app.schemas.employee import (
    EmployeeListResponse,
    EmployeeResponse,
    HeadcountResponse,
    ManagerResponse,
)
from app.services.employee_service import EmployeeService

router = APIRouter(prefix="/employees", tags=["Employees"])

DEPARTMENT = Query(None, description="Department name, e.g. Engineering (case-insensitive).")
STATUS = Query(None, description="Employment status, e.g. Active or Inactive.")


@router.get("", response_model=EmployeeListResponse, summary="List employees (filtered, capped)")
def list_employees(
    department: str | None = DEPARTMENT,
    employment_status: str | None = STATUS,
    limit: int = Query(25, ge=1, le=100),
    service: EmployeeService = Depends(get_employee_service),
) -> EmployeeListResponse:
    return service.list_employees(department, employment_status, limit)


@router.get("/headcount", response_model=HeadcountResponse, summary="Count employees")
def headcount(
    department: str | None = DEPARTMENT,
    employment_status: str | None = STATUS,
    service: EmployeeService = Depends(get_employee_service),
) -> HeadcountResponse:
    return service.headcount(department, employment_status)


@router.get("/by-name", response_model=EmployeeResponse, summary="Find one employee by name")
def find_by_name(
    name: str = Query(..., min_length=2, max_length=80, description="Full or partial name."),
    service: EmployeeService = Depends(get_employee_service),
) -> EmployeeResponse:
    return service.find_by_name(name)


@router.get("/{employee_id}", response_model=EmployeeResponse, summary="Employee details by ID")
def get_employee(employee_id: str, service: EmployeeService = Depends(get_employee_service)) -> EmployeeResponse:
    return service.get_employee(employee_id)


@router.get("/{employee_id}/manager", response_model=ManagerResponse, summary="Who manages this employee?")
def get_manager(employee_id: str, service: EmployeeService = Depends(get_employee_service)) -> ManagerResponse:
    return service.get_manager(employee_id)
