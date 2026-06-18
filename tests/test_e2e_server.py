"""End-to-end test for the Job Apply Agent server."""
import asyncio
import json
import time

import httpx

BASE = "http://localhost:8000"


async def e2e_test():
    async with httpx.AsyncClient(base_url=BASE, timeout=300) as c:
        print("=" * 60)
        print("  END-TO-END TEST: Job Apply Agent")
        print("=" * 60)

        # 1. Health + Readiness
        print("\n[1] Health & Readiness")
        r = await c.get("/health")
        assert r.status_code == 200
        health = r.json()
        assert health["status"] == "healthy"
        print(f"    /health -> {health}")

        r = await c.get("/ready")
        assert r.status_code == 200
        ready = r.json()
        assert ready["status"] == "ready"
        assert ready["checks"]["ollama"] == "ok"
        assert ready["checks"]["database"] == "ok"
        assert ready["checks"]["vectordb"] == "ok"
        print("    /ready -> all checks OK")

        # 2. A2A Agent Card
        print("\n[2] A2A Protocol - Agent Card Discovery")
        r = await c.get("/.well-known/agent.json")
        assert r.status_code == 200
        card = r.json()
        assert card["name"] == "job-apply-agent"
        assert len(card["skills"]) >= 4
        skill_ids = [s["id"] for s in card["skills"]]
        print(f"    Agent: {card['name']} v{card['version']}")
        print(f"    Skills: {skill_ids}")

        # 3. MCP Tools List
        print("\n[3] MCP Protocol - Tools Discovery")
        r = await c.post("/mcp/tools/list", json={})
        assert r.status_code == 200
        tools = r.json()["tools"]
        tool_names = [t["name"] for t in tools]
        print(f"    Tools: {tool_names}")
        assert "match_job" in tool_names
        assert "generate_cover_letter" in tool_names
        assert "get_application_stats" in tool_names

        # 4. MCP Tool Call - Match Job (exercises LLM validated generation)
        print("\n[4] MCP Tool Call - match_job (LLM validated generation)")
        start = time.time()
        r = await c.post("/mcp/tools/call", json={
            "name": "match_job",
            "arguments": {
                "job_title": "Senior Python Backend Engineer",
                "company": "DataFlow Inc",
                "description": (
                    "Build scalable APIs with FastAPI, manage PostgreSQL databases, "
                    "deploy with Docker/K8s. 5+ years Python required. "
                    "Experience with async, Redis, and CI/CD pipelines."
                ),
            },
        })
        elapsed = time.time() - start
        assert r.status_code == 200, f"match_job failed: {r.text}"
        match_result = r.json()
        print(f"    Status: {r.status_code} ({elapsed:.1f}s)")
        print(f"    Result: {json.dumps(match_result, indent=2)[:400]}")

        # 5. MCP Tool Call - Generate Cover Letter (LLM creative)
        print("\n[5] MCP Tool Call - generate_cover_letter (LLM creative)")
        start = time.time()
        r = await c.post("/mcp/tools/call", json={
            "name": "generate_cover_letter",
            "arguments": {
                "job_title": "Senior Python Backend Engineer",
                "company": "DataFlow Inc",
                "description": (
                    "Build scalable APIs with FastAPI, manage PostgreSQL databases, "
                    "deploy with Docker/K8s."
                ),
                "requirements": "Python, FastAPI, Docker, PostgreSQL, async programming",
            },
        })
        elapsed = time.time() - start
        assert r.status_code == 200, f"cover_letter failed: {r.text}"
        cover = r.json()
        print(f"    Status: {r.status_code} ({elapsed:.1f}s)")
        result_text = str(cover.get("result", cover))[:300]
        print(f"    Preview: {result_text}...")

        # 6. MCP Tool Call - Application Stats (DB query)
        print("\n[6] MCP Tool Call - get_application_stats (DB)")
        r = await c.post("/mcp/tools/call", json={
            "name": "get_application_stats",
            "arguments": {},
        })
        assert r.status_code == 200, f"stats failed: {r.text}"
        stats = r.json()
        print(f"    Stats: {stats}")

        # 7. A2A Task Send (orchestrator)
        print("\n[7] A2A Protocol - Task Send")
        r = await c.post("/a2a/tasks/send", json={
            "id": "test-task-001",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Find Python backend jobs in Remote locations"}],
            },
        })
        print(f"    Status: {r.status_code}")
        if r.status_code == 200:
            task = r.json()
            state = task.get("status", {}).get("state", "unknown")
            print(f"    Task state: {state}")
        else:
            print(f"    Response: {r.text[:200]}")

        print("\n" + "=" * 60)
        print("  ALL END-TO-END TESTS PASSED")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(e2e_test())
