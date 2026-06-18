"""🗺️ Pipeline Graph — LangGraph visualization and interrupt handler."""

import streamlit as st

from job_agent_dashboard.helpers import get_api, post_api


def render():
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
