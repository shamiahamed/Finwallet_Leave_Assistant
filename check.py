from pathlib import Path
from app.core.config import get_settings
from app.repositories.workbook_repository import WorkbookRepository
from app.services.employee_service import EmployeeService
from app.services.leave_request_service import LeaveRequestService
from app.services.balance_service import BalanceService
from app.services.policy_service import PolicyService
from app.services.department_service import DepartmentService
from app.api.v1.endpoints import chat
repo=WorkbookRepository.load(Path(get_settings().workbook_path))
e=EmployeeService(repo); req=LeaveRequestService(repo,e); b=BalanceService(repo,e); p=PolicyService(repo); d=DepartmentService(repo,req)
q1='Show the leave history for EMP001'
prep1=chat._prepare_answer(q1,None,e,req,b,p,d)
chat._commit_answer(prep1)
cid=prep1.conversation_id
q2='what about his casual leave?'
prep2=chat._prepare_answer(q2,cid,e,req,b,p,d)
print(prep2.intent.intent)

