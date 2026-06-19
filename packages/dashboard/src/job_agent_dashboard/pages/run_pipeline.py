"""🚀 Run Pipeline — start the pipeline and watch real-time logs."""

import time

import streamlit as st

from job_agent_dashboard.helpers import get_api, get_api_live, post_api, safe_json, format_activity_message


def render():
    st.title("🚀 Run Pipeline")

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

    # ── Start Button ──
    col_start, col_stop = st.columns([1, 1])
    with col_start:
        if st.button("▶️ Start Pipeline", type="primary", use_container_width=True):
            titles_list = [t.strip() for t in run_titles.split(",") if t.strip()]
            locations_list = [l.strip() for l in run_locations.split(",") if l.strip()]
            result = post_api("/webhooks/trigger/search", {
                "titles": titles_list,
                "locations": locations_list,
                "auto_apply": auto_apply,
            })
            if "error" not in result:
                st.session_state["pipeline_run_id"] = result.get("task_id")
                st.session_state["pipeline_running"] = True
                st.rerun()
            else:
                st.error(f"Failed to start: {result['error']}")

    with col_stop:
        if st.button("⏹️ Stop Watching", use_container_width=True):
            st.session_state["pipeline_running"] = False

    st.divider()

    # ── Live Status Section ──
    status_data = get_api_live("/status")
    if "error" in status_data:
        st.warning("Server offline")
        return

    pipeline = status_data.get("pipeline", {})
    phase = pipeline.get("phase", "idle")
    run_id = status_data.get("run_id")

    # Progress bar
    steps = ["idle", "searching", "matching", "tailoring", "applying", "completed"]
    current_idx = steps.index(phase) if phase in steps else 0
    if phase == "failed":
        current_idx = -1

    cols = st.columns(len(steps))
    for i, step in enumerate(steps):
        with cols[i]:
            if phase == "failed":
                st.markdown(f"<div style='text-align:center;color:red'>❌<br><small>{step.title()}</small></div>", unsafe_allow_html=True)
            elif i < current_idx:
                st.markdown(f"<div style='text-align:center;color:green'>✅<br><small>{step.title()}</small></div>", unsafe_allow_html=True)
            elif i == current_idx:
                st.markdown(f"<div style='text-align:center;color:orange;font-weight:bold'>⏳<br><small><b>{step.title()}</b></small></div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align:center;color:gray'>⬜<br><small>{step.title()}</small></div>", unsafe_allow_html=True)

    if phase == "completed":
        st.progress(1.0, text="Pipeline completed!")
    elif phase == "failed":
        st.progress(0.0, text="Pipeline failed")
    elif current_idx > 0:
        st.progress(current_idx / (len(steps) - 1), text=f"Step {current_idx}/{len(steps) - 1}: {phase.title()}")

    # Live stats
    stats = pipeline.get("stats", {})
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🔍 Searched", stats.get("searched", 0))
    c2.metric("📊 Matched", stats.get("matched", 0))
    c3.metric("🚀 Applied", stats.get("applied", 0))
    c4.metric("📧 Emailed", stats.get("emailed", 0))
    c5.metric("❌ Errors", stats.get("errors", 0))

    st.divider()

    # ── Real-Time Activity Log ──
    st.subheader("📜 Live Activity Log")

    records = status_data.get("recent_io", [])
    if records:
        log_container = st.container()
        with log_container:
            for r in reversed(records[-40:]):
                node = r.get("node", "")
                direction = r.get("direction", "")
                data = r.get("data", {})
                ts = r.get("timestamp", "")[11:19]
                duration = r.get("duration_ms", 0)
                duration_str = f" `{duration:.0f}ms`" if duration else ""
                msg = format_activity_message(node, direction, data)

                if direction == "error":
                    st.error(f"🔴 `{ts}` {msg}{duration_str}")
                elif direction == "output":
                    st.success(f"✅ `{ts}` {msg}{duration_str}")
                else:
                    st.info(f"▶️ `{ts}` {msg}")
    else:
        st.caption("No activity yet. Start the pipeline above.")

    # ── Errors ──
    errors = status_data.get("errors", [])
    if errors:
        st.divider()
        st.subheader("🔴 Errors")
        for err in reversed(errors):
            st.error(f"`{err['timestamp'][11:19]}` **{err['node']}** — {err['data']}")

    # ── Past Runs (from DB) ──
    with st.expander("📂 Past Pipeline Runs"):
        runs_data = get_api("/pipeline/runs?limit=10")
        if "error" not in runs_data:
            runs = runs_data.get("runs", [])
            if runs:
                for run in runs:
                    rid = run.get("run_id", "?")
                    started = run.get("started_at", "")[:19]
                    count = run.get("log_count", 0)
                    if st.button(f"📋 {rid} — {started} ({count} entries)", key=f"run_{rid}"):
                        st.session_state["view_run_id"] = rid

                # Show selected run logs
                view_rid = st.session_state.get("view_run_id")
                if view_rid:
                    logs_data = get_api(f"/pipeline/logs?run_id={view_rid}&limit=200")
                    if "error" not in logs_data:
                        for log in logs_data.get("logs", []):
                            ts = log.get("timestamp", "")[11:19]
                            msg = log.get("message", "")
                            d = log.get("direction", "")
                            dur = log.get("duration_ms", 0)
                            dur_str = f" ({dur:.0f}ms)" if dur else ""
                            if d == "error":
                                st.error(f"🔴 `{ts}` {msg}{dur_str}")
                            elif d == "output":
                                st.success(f"✅ `{ts}` {msg}{dur_str}")
                            else:
                                st.info(f"▶️ `{ts}` {msg}")
            else:
                st.caption("No past runs recorded yet.")

    # ── Auto-refresh when pipeline is active ──
    is_active = phase not in ("idle", "completed", "failed")
    is_watching = st.session_state.get("pipeline_running", False)
    if is_active or is_watching:
        time.sleep(3)
        st.rerun()
