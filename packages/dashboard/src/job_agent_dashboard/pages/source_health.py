"""🏥 Source Health — real-time status of job board scrapers."""

import streamlit as st

from job_agent_dashboard.helpers import get_api, AGENT_API_URL


def render():
    st.title("🏥 Source Health Monitor")
    st.markdown("Real-time status of all job board scrapers.")

    health_data = get_api("/sources/health")
    if isinstance(health_data, dict) and "error" in health_data:
        st.error(f"Cannot fetch health: {health_data['error']}")
        return
    if not health_data:
        st.info("No source data yet. Run a search first.")
        return

    for source_name, metrics in health_data.items():
        usage = metrics.get("current_usage", 0)
        max_req = metrics.get("max_requests", 0)
        pct = usage / max_req if max_req else 0

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
