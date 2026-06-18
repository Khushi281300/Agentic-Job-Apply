"""Streamlit Dashboard - Web UI for the job application agent."""

import json
import os
from pathlib import Path

import httpx
import streamlit as st
import pandas as pd

AGENT_API_URL = os.getenv("AGENT_API_URL", "http://localhost:8000")

st.set_page_config(page_title="Job Apply Agent", page_icon="🤖", layout="wide")


@st.cache_data(ttl=30)
def get_api(endpoint: str):
    try:
        resp = httpx.get(f"{AGENT_API_URL}{endpoint}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def post_api(endpoint: str, data: dict = {}):
    try:
        resp = httpx.post(f"{AGENT_API_URL}{endpoint}", json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ─── Sidebar ─────────────────────────────────────────────────────────────────

st.sidebar.title("🤖 Job Agent")
page = st.sidebar.radio("Navigation", [
    "📊 Dashboard",
    "🚀 Run Pipeline",
    "📋 Pipeline Results",
    "🔍 Search Jobs",
    "📋 Review Queue",
    "📝 Cover Letters",
    "🎯 Interview Prep",
    "📈 Analytics",
    "🏥 Source Health",
    "� Profile Strength",
    "💰 Salary Insights",
    "📅 Timeline",
    "�🗺️ Pipeline Graph",
    "📡 Live Status",
    "⚙️ Settings",
])

health = get_api("/health")
if "error" in health:
    st.sidebar.error(f"Agent offline: {health['error']}")
else:
    st.sidebar.success(f"Agent v{health.get('version', '?')} online")


# ─── Dashboard Page ──────────────────────────────────────────────────────────

if page == "📊 Dashboard":
    st.title("📊 Application Dashboard")

    stats = post_api("/mcp/tools/call", {"name": "get_application_stats", "arguments": {}})
    if "error" not in stats:
        content = stats.get("content", [{}])
        if content:
            try:
                data = json.loads(content[0].get("text", "{}") or "{}")
            except (json.JSONDecodeError, TypeError):
                data = {}
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Discovered", data.get("total_discovered", 0))
            col2.metric("Applied", data.get("applied", 0))
            col3.metric("Matched", data.get("matched_pending", 0))
            col4.metric("Rejected", data.get("rejected", 0))

            total = data.get("total_discovered", 0)
            applied = data.get("applied", 0)
            if total > 0:
                st.progress(applied / total, text=f"Application rate: {applied}/{total}")
    else:
        st.warning("Could not fetch stats. Is the agent running?")

    st.divider()
    st.subheader("Agent Card (A2A)")
    card = get_api("/.well-known/agent.json")
    if "error" not in card:
        st.json(card)


# ─── Search Page ─────────────────────────────────────────────────────────────

elif page == "🚀 Run Pipeline":
    st.title("🚀 Run Full Pipeline")
    st.markdown(
        "Start the end-to-end job application pipeline: "
        "**Search → Match → Tailor Resume → Apply**"
    )

    st.divider()

    # ── Pipeline Configuration ──
    col1, col2 = st.columns(2)
    with col1:
        run_titles = st.text_input(
            "Job Titles", "Software Engineer, Python Developer",
            key="run_titles",
        )
        auto_apply = st.checkbox("Auto-apply (skip human review)", value=False)
    with col2:
        run_locations = st.text_input(
            "Locations", "Remote", key="run_locations",
        )
        search_only = st.checkbox("Search & match only (no applications)", value=False)

    st.divider()

    # ── Start / Stop Buttons ──
    col_start, col_stop, col_status = st.columns([1, 1, 2])

    with col_start:
        if st.button("▶️ Start Pipeline", type="primary", use_container_width=True):
            titles_list = [t.strip() for t in run_titles.split(",") if t.strip()]
            locations_list = [l.strip() for l in run_locations.split(",") if l.strip()]
            with st.spinner("Triggering pipeline..."):
                result = post_api("/webhooks/trigger/search", {
                    "titles": titles_list,
                    "locations": locations_list,
                    "auto_apply": auto_apply and not search_only,
                })
            if "error" not in result:
                st.success(f"Pipeline started! {result.get('message', '')}")
                st.balloons()
            else:
                st.error(f"Failed to start: {result['error']}")

    with col_stop:
        if st.button("⏹️ Stop Pipeline", use_container_width=True):
            st.warning("Pipeline runs in the background and will finish its current batch. "
                       "Restart the server to force-stop.")

    with col_status:
        # Live status indicator
        status_data = get_api("/status")
        if "error" not in status_data:
            pipeline = status_data.get("pipeline", {})
            phase = pipeline.get("phase", "idle")
            phase_icons = {
                "idle": "🔘", "searching": "🔍", "matching": "📊",
                "tailoring": "📝", "applying": "🚀", "emailing": "📧",
                "completed": "✅", "failed": "❌",
            }
            icon = phase_icons.get(phase, "⚙️")
            st.info(f"{icon} Current phase: **{phase.upper()}**")
        else:
            st.warning("Server offline")

    st.divider()

    # ── Recent Pipeline Results ──
    st.subheader("📊 Latest Results")
    stats = post_api("/mcp/tools/call", {"name": "get_application_stats", "arguments": {}})
    if "error" not in stats:
        content = stats.get("content", [{}])
        if content:
            try:
                data = json.loads(content[0].get("text", "{}") or "{}")
            except (json.JSONDecodeError, TypeError):
                data = {}
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Discovered", data.get("total_discovered", 0))
            c2.metric("Matched", data.get("matched_pending", 0))
            c3.metric("Applied", data.get("applied", 0))
            c4.metric("Rejected", data.get("rejected", 0))

    # ── Pipeline Activity Log ──
    st.subheader("📜 Activity Log")
    io_data = get_api("/status/io?limit=10")
    if "error" not in io_data:
        records = io_data.get("records", [])
        if records:
            for r in reversed(records):
                direction = "→" if r.get("direction") == "input" else "←"
                duration = f" ({r['duration_ms']}ms)" if r.get("duration_ms") else ""
                st.text(f"{r.get('timestamp', '')[:19]}  {direction} {r.get('node', '?')}{duration}")
        else:
            st.caption("No activity yet. Start the pipeline above.")
    else:
        st.caption("Activity log unavailable.")


# ─── Pipeline Results ────────────────────────────────────────────────────────

elif page == "📋 Pipeline Results":
    st.title("📋 Pipeline Results — Per-Job Breakdown")

    jobs_data = get_api("/jobs")
    if isinstance(jobs_data, dict) and "error" in jobs_data:
        st.error(f"Cannot load jobs: {jobs_data['error']}")
    elif not jobs_data:
        st.info("No jobs tracked yet. Run the pipeline first.")
    else:
        # ── Status filter ──
        all_statuses = sorted(set(j.get("status", "") for j in jobs_data))
        status_filter = st.multiselect(
            "Filter by status", all_statuses, default=all_statuses,
        )
        filtered = [j for j in jobs_data if j.get("status") in status_filter]

        st.caption(f"Showing {len(filtered)} of {len(jobs_data)} jobs")

        # ── Summary table ──
        if filtered:
            table_data = []
            for j in filtered:
                score = j.get("match_score", 0) or 0
                table_data.append({
                    "Company": j.get("company", ""),
                    "Title": j.get("title", ""),
                    "Score": f"{score:.0%}" if score else "—",
                    "Status": j.get("status", "").upper(),
                    "Source": j.get("source", ""),
                    "Discovered": j.get("discovered_at", "")[:10],
                    "Applied": j.get("applied_at", "")[:10] if j.get("applied_at") else "—",
                })
            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()

        # ── Per-job detail expanders ──
        for j in filtered:
            score = j.get("match_score", 0) or 0
            status = j.get("status", "").upper()
            status_icon = {
                "DISCOVERED": "🔵", "MATCHED": "🟢", "REJECTED": "🔴",
                "APPLYING": "🟡", "APPLIED": "✅", "FAILED": "❌",
            }.get(status, "⚪")

            label = f"{status_icon} {j.get('company', '?')} — {j.get('title', '?')}  ({score:.0%})"
            with st.expander(label, expanded=False):
                c1, c2, c3 = st.columns(3)
                c1.metric("Match Score", f"{score:.0%}")
                c2.metric("Status", status)
                c3.metric("Source", j.get("source", "—"))

                if j.get("url"):
                    st.markdown(f"[🔗 Job Link]({j['url']})")

                # ── Match Details ──
                match_raw = j.get("match_data", "{}")
                try:
                    match_data = json.loads(match_raw) if isinstance(match_raw, str) else match_raw
                except (json.JSONDecodeError, TypeError):
                    match_data = {}

                if match_data and match_data.get("job_id"):
                    st.subheader("📊 Match Analysis")
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    mc1.metric("Skill", f"{match_data.get('skill_match', 0):.0%}")
                    mc2.metric("Experience", f"{match_data.get('experience_match', 0):.0%}")
                    mc3.metric("Location", f"{match_data.get('location_match', 0):.0%}")
                    mc4.metric("Salary", f"{match_data.get('salary_match', 0):.0%}")

                    matched_skills = match_data.get("matched_skills", [])
                    missing_skills = match_data.get("missing_skills", [])
                    if matched_skills:
                        st.markdown("**✅ Matched Skills:** " + ", ".join(f"`{s}`" for s in matched_skills))
                    if missing_skills:
                        st.markdown("**❌ Missing Skills:** " + ", ".join(f"`{s}`" for s in missing_skills))

                    reasoning = match_data.get("reasoning", "")
                    if reasoning:
                        st.markdown("**💡 Reasoning:**")
                        st.info(reasoning)

                # ── Tailored Resume / Cover Letter ──
                tailored_raw = j.get("tailored_data", "{}")
                try:
                    tailored = json.loads(tailored_raw) if isinstance(tailored_raw, str) else tailored_raw
                except (json.JSONDecodeError, TypeError):
                    tailored = {}

                if tailored and tailored.get("job_id"):
                    st.subheader("📝 Tailored Resume & Cover Letter")

                    summary = tailored.get("summary", "")
                    if summary:
                        st.markdown("**Resume Summary:**")
                        st.success(summary)

                    highlighted = tailored.get("highlighted_skills", [])
                    if highlighted:
                        st.markdown("**Highlighted Skills:** " + ", ".join(f"`{s}`" for s in highlighted))

                    cover_letter = tailored.get("cover_letter", "")
                    if cover_letter:
                        st.markdown("**Cover Letter:**")
                        st.text_area(
                            "Cover Letter", cover_letter, height=300,
                            key=f"cl_{j['id']}", disabled=True,
                        )

                # ── Error (if any) ──
                error = j.get("error", "")
                if error:
                    st.error(f"Error: {error}")


# ─── Search Page ─────────────────────────────────────────────────────────────

elif page == "🔍 Search Jobs":
    st.title("🔍 Search for Jobs")

    col1, col2 = st.columns(2)
    with col1:
        titles = st.text_input("Job Titles (comma separated)", "Software Engineer, Python Developer")
    with col2:
        locations = st.text_input("Locations (comma separated)", "Remote, New York")

    if st.button("🔍 Search Now", type="primary"):
        with st.spinner("Searching job boards..."):
            result = post_api("/mcp/tools/call", {
                "name": "search_jobs",
                "arguments": {
                    "titles": [t.strip() for t in titles.split(",")],
                    "locations": [l.strip() for l in locations.split(",")],
                },
            })

        if "error" not in result:
            content = result.get("content", [{}])
            if content:
                raw_text = content[0].get("text", "{}") or "{}"
                try:
                    data = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    data = {}
                st.success(f"Found {data.get('jobs_found', 0)} jobs!")
                jobs = data.get("jobs", [])
                if jobs:
                    df = pd.DataFrame(jobs)
                    st.dataframe(df, use_container_width=True)
        else:
            st.error(f"Search failed: {result['error']}")


# ─── Review Queue ────────────────────────────────────────────────────────────

elif page == "📋 Review Queue":
    st.title("📋 Review Matched Jobs")
    st.info("Jobs that matched your profile but haven't been applied to yet.")
    st.warning("Review queue requires the agent to be running with matched jobs.")


# ─── Cover Letters ───────────────────────────────────────────────────────────

elif page == "📝 Cover Letters":
    st.title("📝 Generated Cover Letters")

    cover_dir = Path("data/cover_letters")
    if cover_dir.exists():
        files = list(cover_dir.glob("*.txt"))
        if files:
            selected = st.selectbox("Select cover letter", [f.stem for f in files])
            if selected:
                content = (cover_dir / f"{selected}.txt").read_text()
                st.text_area("Cover Letter", content, height=400)
        else:
            st.info("No cover letters generated yet.")
    else:
        st.info("Cover letter directory not found.")

    st.divider()
    st.subheader("Generate New Cover Letter")
    col1, col2 = st.columns(2)
    with col1:
        job_title = st.text_input("Job Title")
        company = st.text_input("Company")
    with col2:
        description = st.text_area("Job Description", height=200)

    if st.button("Generate Cover Letter") and job_title and company and description:
        with st.spinner("Generating..."):
            result = post_api("/mcp/tools/call", {
                "name": "generate_cover_letter",
                "arguments": {
                    "job_title": job_title,
                    "company": company,
                    "description": description,
                },
            })
        if "error" not in result:
            content = result.get("content", [{}])
            if content:
                try:
                    data = json.loads(content[0].get("text", "{}") or "{}")
                except (json.JSONDecodeError, TypeError):
                    data = {}
                st.success("Generated!")
                st.text_area("Result", data.get("cover_letter", ""), height=300)


# ─── Pipeline Graph ──────────────────────────────────────────────────────────

elif page == "🗺️ Pipeline Graph":
    st.title("🗺️ LangGraph Pipeline")

    graph_data = get_api("/graph")
    if "error" not in graph_data:
        mermaid_code = graph_data.get("mermaid", "")
        if mermaid_code:
            st.subheader("Workflow Graph")
            st.markdown(f"```mermaid\n{mermaid_code}\n```")
    else:
        st.warning("Could not fetch graph. Is the agent running?")

    st.divider()

    # ─── Human-in-the-Loop: Interrupt Handler ────────────────────────────────
    st.subheader("🖐️ Human Review (Interrupt Handler)")

    interrupted = get_api("/graph/interrupted")
    if "error" not in interrupted and interrupted.get("interrupted"):
        paused_at = interrupted.get("paused_at", [])
        values = interrupted.get("values", {})

        st.warning(f"⏸️ Pipeline paused at: **{', '.join(paused_at)}**")
        st.info(f"Jobs waiting for review: **{values.get('jobs_to_apply', 0)}** | "
                f"Matched: **{values.get('matched_jobs', 0)}**")

        st.markdown("---")
        st.markdown("**Approve or reject jobs before submission:**")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Approve All", type="primary"):
                # Approve all by passing empty approved (defaults to all)
                result = post_api("/graph/resume", {
                    "thread_id": "pipeline-run",
                    "approved": list(range(values.get("jobs_to_apply", 0))),
                    "rejected": [],
                })
                if "error" not in result:
                    st.success(f"Resumed! Applied: {result.get('applied_count', 0)}")
                else:
                    st.error(f"Resume failed: {result['error']}")

        with col2:
            if st.button("❌ Reject All"):
                result = post_api("/graph/resume", {
                    "thread_id": "pipeline-run",
                    "approved": [],
                    "rejected": list(range(values.get("jobs_to_apply", 0))),
                })
                if "error" not in result:
                    st.info("All jobs rejected, pipeline ended.")
                else:
                    st.error(f"Resume failed: {result['error']}")
    else:
        st.success("No interrupted pipeline. The graph is idle or running automatically.")


# ─── Live Status ─────────────────────────────────────────────────────────────

elif page == "📡 Live Status":
    st.title("📡 Pipeline Live Status")

    status_data = get_api("/status")
    if "error" in status_data:
        st.error(f"Cannot fetch status: {status_data['error']}")
    else:
        pipeline = status_data.get("pipeline", {})

        # Phase indicator
        phase = pipeline.get("phase", "idle")
        phase_colors = {
            "idle": "🔘", "searching": "🔍", "matching": "📊",
            "tailoring": "📝", "applying": "🚀", "emailing": "📧",
            "completed": "✅", "failed": "❌",
        }
        st.markdown(f"### {phase_colors.get(phase, '⚙️')} Phase: **{phase.upper()}**")

        if pipeline.get("current_job"):
            job = pipeline["current_job"]
            st.info(f"Current: **{job.get('title', '?')}** @ {job.get('company', '?')}")

        # Stats
        stats = pipeline.get("stats", {})
        cols = st.columns(5)
        cols[0].metric("Searched", stats.get("searched", 0))
        cols[1].metric("Matched", stats.get("matched", 0))
        cols[2].metric("Applied", stats.get("applied", 0))
        cols[3].metric("Emailed", stats.get("emailed", 0))
        cols[4].metric("Errors", stats.get("errors", 0))

        st.divider()

        # Recent I/O
        st.subheader("Recent Activity (Raw I/O)")
        records = status_data.get("recent_io", [])
        if records:
            for r in reversed(records[-20:]):
                direction_icon = {"input": "➡️", "output": "⬅️", "error": "🔴"}.get(r["direction"], "•")
                duration_str = f" ({r['duration_ms']:.0f}ms)" if r.get("duration_ms") else ""
                with st.expander(
                    f"{direction_icon} [{r['timestamp'][11:19]}] **{r['node']}** {r['direction']}{duration_str}"
                ):
                    st.json(r["data"])
        else:
            st.info("No activity recorded yet.")

        st.divider()

        # Errors
        st.subheader("🔴 Errors")
        errors = status_data.get("errors", [])
        if errors:
            for err in reversed(errors):
                st.error(f"[{err['timestamp'][11:19]}] **{err['node']}**: {err['data']}")
        else:
            st.success("No errors.")

    # Auto-refresh
    if st.button("🔄 Refresh"):
        st.rerun()


# ─── Interview Prep ──────────────────────────────────────────────────────────

elif page == "🎯 Interview Prep":
    st.title("🎯 Interview Preparation")
    st.markdown("Generate likely interview questions for any applied job.")

    # Get applied jobs
    jobs_data = get_api("/jobs?status=applied")
    if isinstance(jobs_data, dict) and "error" in jobs_data:
        st.error(f"Cannot load jobs: {jobs_data['error']}")
    elif not jobs_data:
        st.info("No applied jobs yet. Run the pipeline first.")
    else:
        job_options = {f"{j['title']} @ {j['company']}": j['id'] for j in jobs_data}
        selected = st.selectbox("Select a job to prepare for", list(job_options.keys()))

        if selected and st.button("🎯 Generate Interview Questions", type="primary"):
            job_id = job_options[selected]
            with st.spinner("Generating interview prep using AI..."):
                result = post_api(f"/interview-prep/{job_id}")

            if "error" not in result:
                # Technical Questions
                tech = result.get("technical", [])
                if tech:
                    st.subheader("💻 Technical Questions")
                    for i, qa in enumerate(tech, 1):
                        with st.expander(f"Q{i}: {qa.get('question', '')}"):
                            st.markdown(f"**Suggested Answer:** {qa.get('answer', '')}")

                # Behavioral Questions
                behavioral = result.get("behavioral", [])
                if behavioral:
                    st.subheader("🧠 Behavioral Questions")
                    for i, qa in enumerate(behavioral, 1):
                        with st.expander(f"Q{i}: {qa.get('question', '')}"):
                            st.markdown(f"**Suggested Answer (STAR):** {qa.get('answer', '')}")

                # Company-Specific
                company_q = result.get("company_specific", [])
                if company_q:
                    st.subheader("🏢 Company-Specific Questions")
                    for i, qa in enumerate(company_q, 1):
                        with st.expander(f"Q{i}: {qa.get('question', '')}"):
                            st.markdown(f"**Suggested Answer:** {qa.get('answer', '')}")
            else:
                st.error(f"Failed: {result.get('error', 'Unknown error')}")


# ─── Analytics ───────────────────────────────────────────────────────────────

elif page == "📈 Analytics":
    st.title("📈 Success Rate Analytics")
    st.markdown("Track which sources, roles, and score ranges lead to callbacks.")

    analytics = get_api("/analytics")
    if isinstance(analytics, dict) and "error" in analytics:
        st.warning(f"Analytics unavailable: {analytics['error']}")
    elif analytics:
        # Overview metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Applied", analytics.get("total_applied", 0))
        c2.metric("Success Rate", f"{analytics.get('overall_success_rate', 0):.1%}")
        positive = sum(
            v for k, v in analytics.get("outcomes", {}).items()
            if k in ("callback", "interview", "offer")
        )
        c3.metric("Positive Responses", positive)

        st.divider()

        # Outcome breakdown
        st.subheader("📊 Outcome Breakdown")
        outcomes = analytics.get("outcomes", {})
        if outcomes:
            df = pd.DataFrame([
                {"Outcome": k.replace("_", " ").title(), "Count": v}
                for k, v in outcomes.items()
            ])
            st.bar_chart(df.set_index("Outcome"))

        # By Source
        st.subheader("📡 Success by Source")
        by_source = analytics.get("by_source", {})
        if by_source:
            source_df = pd.DataFrame([
                {"Source": k, "Total": v["total"], "Positive": v["positive"],
                 "Rate": f"{v['success_rate']:.1%}"}
                for k, v in by_source.items()
            ])
            st.dataframe(source_df, use_container_width=True, hide_index=True)

        # By Score Range
        st.subheader("🎯 Success by Match Score")
        by_score = analytics.get("by_score_range", {})
        if by_score:
            score_df = pd.DataFrame([
                {"Score Range": k, "Total": v["total"], "Positive": v["positive"],
                 "Rate": f"{v['success_rate']:.1%}"}
                for k, v in by_score.items()
            ])
            st.dataframe(score_df, use_container_width=True, hide_index=True)

        st.divider()

        # Record outcome form
        st.subheader("✏️ Record Application Outcome")
        all_jobs = get_api("/jobs?status=applied")
        if isinstance(all_jobs, list) and all_jobs:
            job_opts = {f"{j['title']} @ {j['company']}": j['id'] for j in all_jobs}
            sel_job = st.selectbox("Job", list(job_opts.keys()), key="outcome_job")
            outcome = st.selectbox("Outcome", [
                "callback", "interview", "offer", "rejected", "no_response"
            ])
            if st.button("Record Outcome"):
                result = post_api(f"/jobs/{job_opts[sel_job]}/outcome", {"outcome": outcome})
                if "error" not in result:
                    st.success(f"Recorded: {outcome}")
                else:
                    st.error(result["error"])

        # Follow-ups due
        st.divider()
        st.subheader("⏰ Follow-ups Due")
        follow_ups = get_api("/follow-ups")
        if isinstance(follow_ups, list) and follow_ups:
            for fu in follow_ups:
                st.warning(f"📧 Follow up: **{fu['title']}** @ {fu['company']} (applied {fu['applied_at'][:10]})")
        else:
            st.success("No follow-ups due right now.")
    else:
        st.info("No analytics data yet. Apply to some jobs first.")


# ─── Source Health Monitor ───────────────────────────────────────────────────

elif page == "🏥 Source Health":
    st.title("🏥 Source Health Monitor")
    st.markdown("Real-time status of all job board scrapers.")

    health_data = get_api("/sources/health")
    if isinstance(health_data, dict) and "error" in health_data:
        st.error(f"Cannot fetch health: {health_data['error']}")
    elif health_data:
        for source_name, metrics in health_data.items():
            usage = metrics.get("current_usage", 0)
            max_req = metrics.get("max_requests", 0)
            pct = usage / max_req if max_req else 0

            # Status indicator
            if metrics.get("last_error") and not metrics.get("last_success_ago_secs"):
                icon = "🔴"
            elif pct >= 0.8:
                icon = "🟡"
            else:
                icon = "🟢"

            with st.expander(f"{icon} **{source_name}** — {usage}/{max_req} requests used"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Requests", f"{metrics.get('total_requests', 0)}")
                c2.metric("Blocked", f"{metrics.get('total_blocked', 0)}")
                c3.metric("Avg Latency", f"{metrics.get('avg_latency_ms', 0):.0f}ms")

                st.progress(pct, text=f"Rate limit: {usage}/{max_req} (window: {metrics.get('window_secs', 60)}s)")

                if metrics.get("last_success_ago_secs") is not None:
                    st.caption(f"Last success: {metrics['last_success_ago_secs']:.0f}s ago")

                if metrics.get("last_error"):
                    st.error(f"Last error ({metrics.get('last_error_ago_secs', '?'):.0f}s ago): {metrics['last_error']}")
    else:
        st.info("No source data yet. Run a search first.")

    if st.button("🔄 Refresh", key="health_refresh"):
        st.rerun()

    # Export section
    st.divider()
    st.subheader("📤 Export Data")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📥 Download CSV"):
            st.markdown(f"[Download CSV]({AGENT_API_URL}/export/csv)")
    with c2:
        if st.button("📥 Download JSON"):
            st.markdown(f"[Download JSON]({AGENT_API_URL}/export/json)")


# ─── Profile Strength ────────────────────────────────────────────────────────

elif page == "💪 Profile Strength":
    st.title("💪 Profile Strength Analysis")
    st.markdown("See how your profile stacks up against market demand.")

    if st.button("🔍 Analyze My Profile"):
        with st.spinner("Analyzing against job market data..."):
            report = get_api("/profile/strength")

        if isinstance(report, dict) and "error" in report:
            st.error(f"Analysis failed: {report['error']}")
        elif report:
            score = report.get("overall_score", 0)
            st.metric("Overall Strength", f"{score:.0%}")
            st.progress(score)

            c1, c2 = st.columns(2)
            with c1:
                st.subheader("✅ Strengths")
                for skill in report.get("strengths", []):
                    st.markdown(f"- {skill}")
            with c2:
                st.subheader("❌ Gaps")
                for skill in report.get("gaps", []):
                    st.markdown(f"- {skill}")

            st.divider()
            st.subheader("💡 Recommendations")
            for rec in report.get("recommendations", []):
                st.info(rec)

            st.divider()
            st.subheader("📊 Market Demand (Top Skills)")
            demand = report.get("market_demand_top_skills", {})
            if demand:
                df = pd.DataFrame([
                    {"Skill": k, "Mentions": v} for k, v in demand.items()
                ])
                st.bar_chart(df.set_index("Skill"))

# ─── Salary Insights ─────────────────────────────────────────────────────────

elif page == "💰 Salary Insights":
    st.title("💰 Salary Market Insights")
    st.markdown("Aggregated compensation data from scraped job listings.")

    insights = get_api("/salary-insights")
    if isinstance(insights, dict) and "error" in insights:
        st.error(f"Cannot fetch salary data: {insights['error']}")
    elif insights:
        c1, c2, c3 = st.columns(3)
        c1.metric("Jobs Analyzed", insights.get("total_jobs_analyzed", 0))
        c2.metric("With Salary Info", insights.get("jobs_with_salary", 0))
        c3.metric("Coverage", f"{insights.get('coverage_pct', 0)}%")

        st.divider()
        ranges = insights.get("ranges_by_role", {})
        if ranges:
            for role, data in ranges.items():
                with st.expander(f"**{role}** ({data['count']} jobs)"):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Min", f"${data['min']:,}")
                    c2.metric("Median Range", f"${data['median_low']:,} - ${data['median_high']:,}")
                    c3.metric("Max", f"${data['max']:,}")
        else:
            st.info("No salary data yet. Run searches to collect market data.")
    else:
        st.info("No data available.")

# ─── Application Timeline ────────────────────────────────────────────────────

elif page == "📅 Timeline":
    st.title("📅 Application Timeline")
    st.markdown("Track the journey of each application.")

    timeline = get_api("/timeline")
    if isinstance(timeline, dict) and "error" in timeline:
        st.error(f"Cannot fetch timeline: {timeline['error']}")
    elif timeline:
        for item in timeline[:20]:
            events = item.get("events", [])
            stages = " → ".join(
                f"**{e['stage'].title()}**" for e in events
            )
            with st.expander(f"📌 {item['title']} @ {item['company']} — {item['current_status']}"):
                st.markdown(f"Journey: {stages}")
                for e in events:
                    col = "🟢" if e["stage"] in ("offer", "interview") else "🔵"
                    st.markdown(f"{col} **{e['stage'].title()}** — {e.get('at', 'N/A')}")
    else:
        st.info("No applications tracked yet.")

# ─── Settings ────────────────────────────────────────────────────────────────

elif page == "⚙️ Settings":
    st.title("⚙️ Configuration")

    env_path = Path(".env")
    if env_path.exists():
        env_content = env_path.read_text()
        st.code(env_content, language="ini")
    else:
        st.warning("No .env file found.")

    st.divider()
    st.subheader("MCP Tools Available")
    tools = post_api("/mcp/tools/list")
    if "error" not in tools:
        for tool in tools.get("tools", []):
            with st.expander(f"🔧 {tool['name']}"):
                st.write(tool["description"])
                st.json(tool.get("inputSchema", {}))
