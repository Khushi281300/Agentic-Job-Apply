import httpx
import time

time.sleep(90)

s = httpx.get("http://localhost:8000/status").json()
print("Phase:", s["pipeline"]["phase"])
print("Stats:", s["pipeline"]["stats"])
print("IO count:", len(s.get("recent_io", [])))
print()

logs = httpx.get("http://localhost:8000/pipeline/logs").json().get("logs", [])
print(f"DB logs: {len(logs)}")
for log in logs:
    print(f"  [{log['direction']}] {log['node']}: {log['message']}")
