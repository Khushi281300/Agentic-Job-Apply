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
test("Jobs list", "GET", f"{base}/jobs")
test("Jobs stats", "GET", f"{base}/jobs/stats")
test("Status state", "GET", f"{base}/status/state")
test("Status full", "GET", f"{base}/status")
test("Status errors", "GET", f"{base}/status/errors")

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
    print(f"         PDF size: {len(r.content)} bytes, starts with: {r.content[:5]}")

# ── Profile ──
print("\n--- Profile ---")
test("Get profile", "GET", f"{base}/profile", expected_code=404)  # no resume uploaded

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

# Test PUT config
r = test("Update search config", "PUT", f"{base}/config/search", json_data={
    "titles": ["Backend Engineer", "Python Developer"],
    "locations": ["Remote", "New York"],
})
if r and r.status_code == 200:
    data = r.json()
    print(f"         updated titles={data.get('titles')}")

# Restore original
test("Restore search config", "PUT", f"{base}/config/search", json_data={
    "titles": ["Software Engineer"],
    "locations": ["Remote"],
})

r = test("Update app config", "PUT", f"{base}/config/application", json_data={
    "min_match_score": 0.7,
    "max_applications_per_day": 15,
})
if r and r.status_code == 200:
    data = r.json()
    print(f"         updated min_score={data.get('min_match_score')}, max_apps={data.get('max_applications_per_day')}")

# Restore
test("Restore app config", "PUT", f"{base}/config/application", json_data={
    "min_match_score": 0.6,
    "max_applications_per_day": 10,
})

# ── Deadlines ──
print("\n--- Deadlines ---")
test("Upcoming deadlines", "GET", f"{base}/deadlines/upcoming")
test("Expired deadlines", "GET", f"{base}/deadlines/expired")
# Test set deadline with non-existent job (should 404)
test("Set deadline (bad job)", "POST", f"{base}/deadlines", expected_code=404, json_data={
    "job_id": "nonexistent", "deadline": "2026-07-01",
})
# Test bad date format
test("Set deadline (bad date)", "POST", f"{base}/deadlines", expected_code=400, json_data={
    "job_id": "test", "deadline": "not-a-date",
})

# ── Review Queue ──
print("\n--- Review Queue ---")
test("Review queue", "GET", f"{base}/jobs/review-queue")
# Test decision with non-existent job (should still return since update_status doesn't error)
test("Job decision (bad action)", "POST", f"{base}/jobs/fakeid/decision", expected_code=400, json_data={
    "action": "invalid",
})

# ── Retry Queue ──
print("\n--- Retry Queue ---")
test("Retry queue stats", "GET", f"{base}/retry-queue/stats")
test("Retry queue pending", "GET", f"{base}/retry-queue/pending")
test("Retry queue dead letters", "GET", f"{base}/retry-queue/dead-letters")
test("Requeue non-existent", "POST", f"{base}/retry-queue/99999/retry", expected_code=404)

# ── Scheduler ──
print("\n--- Scheduler ---")
test("Scheduler status", "GET", f"{base}/scheduler/status")

# ── Other ──
print("\n--- Other ---")
test("Scrape sources", "GET", f"{base}/scrape/sources")
test("Agent card", "GET", f"{base}/.well-known/agent.json")

# ── Summary ──
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed")
if issues:
    print("\nISSUES:")
    for issue in issues:
        print(f"  - {issue}")
print("=" * 60)
