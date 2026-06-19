"""Debug: test matching a single job from the DB."""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

async def main():
    from job_agent_agents.container import build_container
    from job_agent_contracts.models import JobListing, JobStatus

    container = build_container()
    await container.startup()

    # Check user profile
    from job_agent_services.profile.manager import ProfileManager
    pm = ProfileManager(llm=container.llm, rag=container.rag)
    profile = pm.get_profile()
    print(f"User profile: {profile if profile else 'EMPTY (no profile.json)'}")
    print()

    # Get a job from DB
    jobs = await container.db.get_all_jobs_detailed()
    jobs = jobs[:3]
    if not jobs:
        print("No jobs in DB!")
        return

    print(f"Got {len(jobs)} jobs from DB")
    job = jobs[0]
    print(f"Testing match on: {job['title']} at {job['company']}")

    # Build a JobListing from the DB record
    listing = JobListing(
        id=job["id"],
        title=job["title"],
        company=job["company"],
        location=job.get("location", ""),
        url=job.get("url", ""),
        source=job.get("source", "other"),
        status=JobStatus.DISCOVERED,
    )

    # Try matching
    try:
        result = await container.orchestrator.matcher_agent.run(job=listing)
        print(f"\nMatch result:")
        print(f"  Score: {result.overall_score}")
        print(f"  Reasoning: {result.reasoning}")
        print(f"  Matched skills: {result.matched_skills}")
        print(f"  Missing skills: {result.missing_skills}")
    except Exception as e:
        print(f"\nMatch FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(main())
