import sys,io,uuid; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace'); sys.path.insert(0,'backend'); from fastapi.testclient import TestClient; from app.main import app
with TestClient(app) as c:
    cid=str(uuid.uuid4())
    r=c.post('/api/v1/chat',json={'question':'Which employees have taken leave in September 2026?','conversation_id':cid})
    b=r.json()
    print(b['intent'])
    print(b['answer'])

