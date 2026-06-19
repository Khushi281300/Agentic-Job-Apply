"""End-to-end pipeline flow test - exercises all agents in sequence."""
import httpx
import json
import sys

base = "http://localhost:8000"

print("=" * 60)
print("END-TO-END PIPELINE FLOW")
print("=" * 60)

# Step 1: Check current state
print("\n[1] CURRENT STATE")
r = httpx.get(f"{base}/jobs/stats", timeout=10)
stats = r.json()
print(f"    Total discovered: {stats.get('total_discovered', 0)}")
print(f"    Applied: {stats.get('applied', 0)}")
print(f"    Matched pending: {stats.get('matched_pending', 0)}")

# Step 2: Get graph info
print("\n[2] PIPELINE GRAPH")
r = httpx.get(f"{base}/graph/nodes", timeout=10)
nodes = r.json()
node_ids = [n["id"] for n in nodes.get("nodes", [])]
edges = [(e["source"], e["target"]) for e in nodes.get("edges", [])]
print(f"    Nodes: {node_ids}")
print(f"    Edges: {edges}")

# Step 3: Run search via MCP tool
print("\n[3] SEARCH JOBS (via MCP tool - JobSearchAgent)")
r = httpx.post(f"{base}/mcp/tools/call", json={
    "name": "search_jobs",
    "arguments": {"titles": ["Python Developer"], "locations": ["Remote"]}
}, timeout=120)
if r.status_code == 200:
    data = r.json()
    content = json.loads(data["content"][0]["text"])
    print(f"    Jobs found: {content.get('jobs_found', 0)}")
    for j in content.get("jobs", [])[:5]:
        print(f"      - {j['title']} @ {j['company']} ({j['location']})")
else:
    print(f"    ERROR: {r.status_code} - {r.text[:200]}")

# Step 4: Match a job via MCP tool (uses LLM)
print("\n[4] MATCH JOB (via MCP tool - ProfileMatcherAgent + Ollama LLM)")
r = httpx.post(f"{base}/mcp/tools/call", json={
    "name": "match_job",
    "arguments": {
        "job_title": "Senior Python Backend Engineer",
        "company": "DataFlow Inc",
        "description": (
            "We are looking for a Senior Python Backend Engineer with 5+ years "
            "experience in FastAPI, SQLAlchemy, async programming, and microservices. "
            "Experience with LLM integration, Docker, and Kubernetes is a plus. "
            "Remote-first company."
        ),
        "requirements": [
            "Python 5+ years", "FastAPI", "SQLAlchemy",
            "Docker", "async programming", "microservices"
        ],
    }
}, timeout=180)
if r.status_code == 200:
    data = r.json()
    match_data = json.loads(data["content"][0]["text"])
    print(f"    Overall score: {match_data.get('overall_score', '?')}")
    print(f"    Skill match: {match_data.get('skill_match', '?')}")
    print(f"    Experience match: {match_data.get('experience_match', '?')}")
    print(f"    Location match: {match_data.get('location_match', '?')}")
    print(f"    Salary match: {match_data.get('salary_match', '?')}")
    print(f"    Matched skills: {match_data.get('matched_skills', [])}")
    print(f"    Missing skills: {match_data.get('missing_skills', [])}")
    reasoning = match_data.get("reasoning", "")
    if reasoning:
        print(f"    Reasoning: {reasoning[:300]}")
else:
    print(f"    ERROR: {r.status_code} - {r.text[:300]}")

# Step 5: Generate cover letter (uses LLM via both MatcherAgent + ResumeTailorAgent)
print("\n[5] GENERATE COVER LETTER (ProfileMatcherAgent + ResumeTailorAgent + Ollama)")
r = httpx.post(f"{base}/mcp/tools/call", json={
    "name": "generate_cover_letter",
    "arguments": {
        "job_title": "Senior Python Backend Engineer",
        "company": "DataFlow Inc",
        "description": (
            "We are looking for a Senior Python Backend Engineer with 5+ years "
            "experience in FastAPI, SQLAlchemy, async programming, and microservices."
        ),
        "requirements": ["Python 5+ years", "FastAPI", "SQLAlchemy", "Docker"],
    }
}, timeout=300)
if r.status_code == 200:
    data = r.json()
    result = json.loads(data["content"][0]["text"])
    summary = result.get("summary", "")
    cover = result.get("cover_letter", "")
    print(f"    Summary ({len(summary)} chars):")
    print(f"      {summary[:200]}")
    print(f"    Cover Letter ({len(cover)} chars):")
    lines = cover.split("\n")
    for line in lines[:10]:
        print(f"      {line}")
    if len(lines) > 10:
        print(f"      ... ({len(lines)} total lines)")
else:
    print(f"    ERROR: {r.status_code} - {r.text[:300]}")

# Step 6: Get application stats (MCP)
print("\n[6] APPLICATION STATS (via MCP)")
r = httpx.post(f"{base}/mcp/tools/call", json={
    "name": "get_application_stats",
    "arguments": {}
}, timeout=10)
if r.status_code == 200:
    data = r.json()
    result = json.loads(data["content"][0]["text"])
    print(f"    {json.dumps(result, indent=6)}")

# Step 7: Analytics
print("\n[7] ANALYTICS")
r = httpx.get(f"{base}/analytics", timeout=10)
if r.status_code == 200:
    analytics = r.json()
    print(f"    Success rate: {analytics.get('success_rate', 'N/A')}")
    print(f"    By source: {analytics.get('by_source', {})}")

# Step 8: Status tracker
print("\n[8] STATUS TRACKER")
r = httpx.get(f"{base}/status", timeout=10)
status = r.json()
print(f"    Phase: {status.get('current_phase', '?')}")
print(f"    Is running: {status.get('is_running', '?')}")
io_log = status.get("io_log", [])
if io_log:
    print(f"    Recent IO ({len(io_log)} entries):")
    for entry in io_log[-5:]:
        print(f"      {entry}")

# Step 9: Check graph mermaid
print("\n[9] GRAPH VISUALIZATION")
r = httpx.get(f"{base}/graph", timeout=10)
if r.status_code == 200:
    graph_data = r.json()
    mermaid = graph_data.get("mermaid", graph_data.get("graph", ""))
    if mermaid:
        print(f"    Mermaid diagram ({len(mermaid)} chars):")
        for line in str(mermaid).split("\n")[:15]:
            print(f"      {line}")

print("\n" + "=" * 60)
print("PIPELINE E2E FLOW COMPLETE")
print("=" * 60)
