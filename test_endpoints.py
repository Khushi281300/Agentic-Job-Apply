"""Test all API endpoints."""
import httpx
import json
import sys

base = "http://localhost:8000"
passed = 0
failed = 0
issues = []


def test(label, method, url, expected_code=200, json_data=None):
    global passed, failed
    try:
        if method == "GET":
            r = httpx.get(url, timeout=15)
        elif method == "POST":
            r = httpx.post(url, json=json_data or {}, timeout=15)
        elif method == "PUT":
            r = httpx.put(url, json=json_data or {}, timeout=15)
        else:
            raise ValueError(f"Unknown method: {method}")

        if r.status_code == expected_code:
            passed += 1
            print(f"  OK  {label} -> {r.status_code}")
            return r
        else:
            failed += 1
            detail = r.text[:200]
            print(f"  FAIL {label} -> {r.status_code} (expected {expected_code}): {detail}")
            issues.append(f"{label}: got {r.status_code}, expected {expected_code} - {detail}")
            return r
    except Exception as e:
        failed += 1
        print(f"  ERR  {label} -> {e}")
        issues.append(f"{label}: {e}")
        return None


print("=" * 60)
print("TESTING ALL API ENDPOINTS")
print("=" * 60)

# ── Core ──
print("\n--- Core ---")
test("Health", "GET", f"{base}/health")
r = test("Readiness", "GET", f"{base}/ready")
if r and r.status_code == 200:
    data = r.json()
    print(f"         checks: {data.get('checks', {})}")

# ── Jobs ──
print("\n--- Jobs ---")
r = test("Jobs list", "GET", f"{base}/jobs")
if r and r.status_code == 200:
    data = r.json()
    if isinstance(data, list):
        print(f"         {len(data)} jobs returned")
    elif isinstance(data, dict):
        print(f"         total={data.get('total', '?')}")
test("Jobs stats", "GET", f"{base}/jobs/stats")
test("Jobs by status", "GET", f"{base}/jobs?status=discovered")
test("Review queue", "GET", f"{base}/jobs/review-queue")
test("Job decision (bad action)", "POST", f"{base}/jobs/fakeid/decision", expected_code=400, json_data={
    "action": "invalid",
})
test("Outcome (bad job)", "POST", f"{base}/jobs/fakeid/outcome", json_data={
    "outcome": "no_response",
})

# ── Status ──
print("\n--- Status ---")
test("Status full", "GET", f"{base}/status")
test("Status state", "GET", f"{base}/status/state")
test("Status errors", "GET", f"{base}/status/errors")
r = test("Status IO", "GET", f"{base}/status/io")

# ── Export ──
print("\n--- Export ---")
r = test("Export CSV", "GET", f"{base}/export/csv")
if r and r.status_code == 200:
    print(f"         CSV content-type: {r.headers.get('content-type', '?')}")
r = test("Export JSON", "GET", f"{base}/export/json")
if r and r.status_code == 200:
    print(f"         JSON records: {len(r.json())}")
r = test("Export PDF", "GET", f"{base}/export/pdf")
if r and r.status_code == 200:
    print(f"         PDF size: {len(r.content)} bytes, valid: {r.content[:5] == b'%PDF-'}")

# ── Profile ──
print("\n--- Profile ---")
test("Get profile", "GET", f"{base}/profile", expected_code=404)

# ── Config ──
print("\n--- Config ---")
r = test("Get search config", "GET", f"{base}/config/search")
if r and r.status_code == 200:
    data = r.json()
    print(f"         titles={data.get('titles')}, locations={data.get('locations')}")
r = test("Get app config", "GET", f"{base}/config/application")
if r and r.status_code == 200:
    data = r.json()
    print(f"         min_score={data.get('min_match_score')}, max_apps={data.get('max_applications_per_day')}")
r = test("Update search config", "PUT", f"{base}/config/search", json_data={
    "titles": ["Backend Engineer", "Python Developer"],
    "locations": ["Remote", "New York"],
})
if r and r.status_code == 200:
    print(f"         updated: {r.json()}")
test("Restore search config", "PUT", f"{base}/config/search", json_data={
    "titles": ["Software Engineer"],
    "locations": ["Remote"],
})
r = test("Update app config", "PUT", f"{base}/config/application", json_data={
    "min_match_score": 0.7,
})
if r and r.status_code == 200:
    print(f"         updated: {r.json()}")
test("Restore app config", "PUT", f"{base}/config/application", json_data={
    "min_match_score": 0.6,
})

# ── Deadlines ──
print("\n--- Deadlines ---")
test("Upcoming deadlines", "GET", f"{base}/deadlines/upcoming")
test("Expired deadlines", "GET", f"{base}/deadlines/expired")
test("Set deadline (bad job)", "POST", f"{base}/deadlines", expected_code=404, json_data={
    "job_id": "nonexistent", "deadline": "2026-07-01",
})
test("Set deadline (bad date)", "POST", f"{base}/deadlines", expected_code=400, json_data={
    "job_id": "test", "deadline": "not-a-date",
})

# ── Retry Queue ──
print("\n--- Retry Queue ---")
r = test("Retry queue stats", "GET", f"{base}/retry-queue/stats")
if r and r.status_code == 200:
    print(f"         {r.json()}")
test("Retry queue pending", "GET", f"{base}/retry-queue/pending")
test("Retry queue dead letters", "GET", f"{base}/retry-queue/dead-letters")
test("Requeue non-existent", "POST", f"{base}/retry-queue/99999/retry", expected_code=404)

# ── Scheduler ──
print("\n--- Scheduler ---")
r = test("Scheduler status", "GET", f"{base}/scheduler/status")
if r and r.status_code == 200:
    print(f"         {r.json()}")

# ── Analytics ──
print("\n--- Analytics ---")
test("Analytics", "GET", f"{base}/analytics")
test("Follow-ups", "GET", f"{base}/follow-ups")
test("Profile strength", "GET", f"{base}/profile/strength")
test("Salary insights", "GET", f"{base}/salary-insights")
test("Adaptive thresholds", "GET", f"{base}/adaptive-thresholds")
test("Timeline", "GET", f"{base}/timeline")

# ── Graph ──
print("\n--- Graph ---")
r = test("Graph mermaid", "GET", f"{base}/graph")
if r and r.status_code == 200:
    data = r.json()
    print(f"         source: {data.get('source', 'unknown')}, has mermaid: {'mermaid' in str(data)}")
test("Graph nodes", "GET", f"{base}/graph/nodes")
test("Graph interrupted", "GET", f"{base}/graph/interrupted")

# ── Scraper ──
print("\n--- Scraper ---")
r = test("Scrape sources", "GET", f"{base}/scrape/sources")
if r and r.status_code == 200:
    data = r.json()
    print(f"         {len(data.get('sources', []))} sources available")
test("Source health", "GET", f"{base}/sources/health")

# ── A2A ──
print("\n--- A2A ---")
r = test("Agent card", "GET", f"{base}/.well-known/agent.json")
if r and r.status_code == 200:
    data = r.json()
    skills = data.get("skills", [])
    print(f"         Agent: {data.get('name', '?')}, skills: {len(skills)}")
    for s in skills:
        print(f"           - {s.get('id', '?')}: {s.get('name', '?')}")

# ── MCP ──
print("\n--- MCP ---")
r = test("MCP list tools", "POST", f"{base}/mcp/tools/list")
if r and r.status_code == 200:
    tools = r.json().get("tools", [])
    print(f"         {len(tools)} tools:")
    for t in tools:
        print(f"           - {t['name']}: {t['description'][:60]}")

# Test MCP get_application_stats (lightweight, no LLM needed)
r = test("MCP call get_stats", "POST", f"{base}/mcp/tools/call", json_data={
    "name": "get_application_stats",
    "arguments": {},
})
if r and r.status_code == 200:
    data = r.json()
    content = data.get("content", [{}])
    if content:
        print(f"         stats result: {content[0].get('text', '')[:100]}")

# ── Summary ──
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed")
if issues:
    print("\nISSUES:")
    for issue in issues:
        print(f"  - {issue}")
print("=" * 60)
