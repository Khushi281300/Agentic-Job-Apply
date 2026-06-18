"""📈 Analytics — success rate tracking and outcome recording."""

import pandas as pd
import streamlit as st

from job_agent_dashboard.helpers import get_api, post_api


def render():
    st.title("📈 Success Rate Analytics")
    st.markdown("Track which sources, roles, and score ranges lead to callbacks.")

    analytics = get_api("/analytics")
    if isinstance(analytics, dict) and "error" in analytics:
        st.warning(f"Analytics unavailable: {analytics['error']}")
        return
    if not analytics:
        st.info("No analytics data yet. Apply to some jobs first.")
        return

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
