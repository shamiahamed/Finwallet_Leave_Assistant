"""Test all fixes against the running backend."""
import json
import urllib.request

BASE = "http://localhost:8000/api/v1"


def ask(question, conv_id="test-fixes-1"):
    body = json.dumps({"question": question, "conversation_id": conv_id}).encode()
    req = urllib.request.Request(
        f"{BASE}/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": True, "status": e.code, "detail": e.read().decode()}


print("=== Issue 1: Show EMP029's leave request after pagination ===")
# First: show pending (creates pagination offset)
r1 = ask("Show pending leave requests.")
print(f"  Show pending: {len((r1.get('data') or {}).get('requests') or [])} requests")

# Then: show EMP029's leave request (should NOT use stale offset)
r2 = ask("Show EMP029's leave request.")
reqs2 = (r2.get('data') or {}).get('requests') or []
print(f"  Show EMP029's leave request: {len(reqs2)} requests")
if reqs2:
    print(f"    First: {reqs2[0].get('request_id')} ({reqs2[0].get('employee_name')})")
print(f"  PASS: EMP029 request shows records" if len(reqs2) > 0 else "  FAIL: EMP029 request shows 0 records")

print("\n=== Issue 2: 'his pending leave request' after EMP029 query ===")
r3 = ask("his pending leave request.")
reqs3 = (r3.get('data') or {}).get('requests') or []
print(f"  his pending leave request: {len(reqs3)} requests")
# EMP029 has 0 Pending requests, so empty is correct
print(f"  PASS: EMP029 has no pending requests (correct empty)" if len(reqs3) == 0 else f"  INFO: got {len(reqs3)} pending requests")

print("\n=== Issue 3: Show employees currently on approved leave ===")
r4 = ask("Show employees currently on approved leave.")
print(f"  Answer: {r4.get('answer', '')[:200]}")
# Should filter by today's date, not return all 72 Approved
data4 = r4.get('data') or {}
total4 = data4.get('total_matches', 0)
print(f"  Total matches: {total4}")
print(f"  PASS: filters by today's date" if total4 < 72 else "  FAIL: returns all Approved requests")

print("\n=== Issue 4: Show more after exhaustion ===")
# First: show pending
r5 = ask("Show pending leave requests.", "test-exhaust-1")
# Show more 4 times (36 pending / 10 per page = 4 pages)
for i in range(4):
    r5 = ask("Show more.", "test-exhaust-1")
    reqs5 = (r5.get('data') or {}).get('requests') or []
    print(f"  Show more #{i+1}: {len(reqs5)} requests, answer: {r5.get('answer', '')[:80]}")

print("\n=== Issue 5: 'Show pending leave requests for Engineering' ===")
r6 = ask("Show pending leave requests for the Engineering department.")
reqs6 = (r6.get('data') or {}).get('requests') or []
print(f"  Engineering pending: {len(reqs6)} requests")
all_eng = all(r.get('department') == 'Engineering' for r in reqs6)
print(f"  PASS: all Engineering" if all_eng else "  FAIL: non-Engineering records returned")

print("\n=== Issue 6: 'Who is the manager of LR0025?' ===")
r7 = ask("Who is the manager of LR0025?")
print(f"  Answer: {r7.get('answer', '')[:200]}")
print(f"  PASS: resolves LR first" if 'manager' in r7.get('answer', '').lower() else "  INFO: check answer")

print("\n=== All tests complete ===")