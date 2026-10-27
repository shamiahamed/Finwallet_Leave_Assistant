from datetime import date
from app.repositories.workbook_repository import WorkbookRepository
from app.services.employee_service import EmployeeService
from app.services.leave_request_service import LeaveRequestService

repo = WorkbookRepository.load('data/AI_Engineer_Leave_Management_Dataset.xlsx')
emp = EmployeeService(repo)
reqs = LeaveRequestService(repo, emp)

today = date.today()
result = reqs.list_requesting_employees(
    department='Engineering',
    start_date=today,
    end_date=today,
    date_mode='overlap',
)
print('Total matching requests:', result['total_matching_requests'])
print('Total days:', result['total_days'])
print('Total employees:', result['total_employees'])
for e in result['employees']:
    print(f"  {e['employee_id']} {e['employee_name']} - {e['request_count']} requests, {e['total_days']} days")