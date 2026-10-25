import sys,uuid,io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0,'backend')
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    cid=str(uuid.uuid4())
    # simulate what group history does
    from app.api.v1.endpoints import chat
    from app.api.deps import get_employee_service, get_leave_request_service
    from app.main import app as main_app
    # easier way

