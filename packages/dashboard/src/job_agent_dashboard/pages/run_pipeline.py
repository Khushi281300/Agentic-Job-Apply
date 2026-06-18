"""🚀 Run Pipeline — start/stop the job application pipeline."""

import json

import streamlit as st

from job_agent_dashboard.helpers import get_api, post_api, safe_json


def render():
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
            data = safe_json(content[0].get("text", "{}"))
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
