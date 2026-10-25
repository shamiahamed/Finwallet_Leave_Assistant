from fastapi import Depends, Request

from app.repositories.workbook_repository import WorkbookRepository
from app.services.balance_service import BalanceService
from app.services.department_service import DepartmentService
from app.services.employee_service import EmployeeService
from app.services.leave_request_service import LeaveRequestService
from app.services.policy_service import PolicyService


def get_repository(request: Request) -> WorkbookRepository:
    # Optional per-request dataset selection. Absent -> configured workbook.
    # Both regular and streaming chat resolve through this same function.
    dataset_id = request.headers.get("X-Dataset-Id")
    refresher = getattr(request.app.state, "workbook_refresh", None)
    registry = getattr(request.app.state, "dataset_registry", None)

    # Default selection keeps the existing hot-refresh behavior for the workbook.
    # Use the requested dataset when provided, otherwise use the configured default.
    if not dataset_id or dataset_id == "default":
        if refresher is not None:
            return refresher.maybe_refresh()
        return request.app.state.repository

    if registry is not None:
        return registry.resolve_repository(dataset_id)

    # Unknown dataset id with no registry available.
    from app.exceptions.errors import DatasetNotFoundError

    raise DatasetNotFoundError(f"No dataset found with ID '{dataset_id}'.")


def get_employee_service(repo: WorkbookRepository = Depends(get_repository)) -> EmployeeService:
    return EmployeeService(repo)


def get_leave_request_service(
    repo: WorkbookRepository = Depends(get_repository),
    employees: EmployeeService = Depends(get_employee_service),
) -> LeaveRequestService:
    return LeaveRequestService(repo, employees)


def get_balance_service(
    repo: WorkbookRepository = Depends(get_repository),
    employees: EmployeeService = Depends(get_employee_service),
) -> BalanceService:
    return BalanceService(repo, employees)


def get_policy_service(repo: WorkbookRepository = Depends(get_repository)) -> PolicyService:
    return PolicyService(repo)


def get_department_service(
    repo: WorkbookRepository = Depends(get_repository),
    requests: LeaveRequestService = Depends(get_leave_request_service),
) -> DepartmentService:
    return DepartmentService(repo, requests)
