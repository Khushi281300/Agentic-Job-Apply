"""📋 Review Queue — approve or reject matched jobs before application."""

import streamlit as st

from job_agent_dashboard.helpers import get_api_live, post_api


def render():
    st.title("📋 Review Queue")
    st.caption("Jobs that matched your profile and await your approval before applying.")

    jobs = get_api_live("/jobs/review-queue")
    if isinstance(jobs, dict) and "error" in jobs:
        st.error(f"Cannot load review queue: {jobs['error']}")
        return

    if not jobs:
        st.success("🎉 Review queue is empty — no jobs pending approval.")
        return

    st.metric("Pending Review", len(jobs))
    st.divider()

    for idx, job in enumerate(jobs):
        score = job.get("score", 0) or job.get("match_score", 0) or 0
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        job_id = job.get("id", "")

        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 1, 2])
            with col1:
                st.markdown(f"**{title}**")
                st.caption(f"@ {company}")
            with col2:
                st.metric("Match Score", f"{score:.0%}" if score else "—")
            with col3:
                if job.get("url"):
                    st.markdown(f"[🔗 Link]({job['url']})")
            with col4:
                c_approve, c_reject = st.columns(2)
                with c_approve:
                    if st.button("✅ Approve", key=f"approve_{idx}_{job_id}"):
                        result = post_api(f"/jobs/{job_id}/decision", {"action": "approve"})
                        if "error" in result:
                            st.error(result["error"])
                        else:
                            st.success("Approved!")
                            st.rerun()
                with c_reject:
                    if st.button("❌ Reject", key=f"reject_{idx}_{job_id}"):
                        result = post_api(f"/jobs/{job_id}/decision", {"action": "reject"})
                        if "error" in result:
                            st.error(result["error"])
                        else:
                            st.warning("Rejected")
                            st.rerun()

            st.divider()

    # Bulk actions
    st.subheader("⚡ Bulk Actions")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("✅ Approve All", key="approve_all"):
            for job in jobs:
                post_api(f"/jobs/{job['id']}/decision", {"action": "approve"})
            st.success(f"Approved all {len(jobs)} jobs")
            st.rerun()
    with b2:
        if st.button("❌ Reject All", key="reject_all"):
            for job in jobs:
                post_api(f"/jobs/{job['id']}/decision", {"action": "reject"})
            st.warning(f"Rejected all {len(jobs)} jobs")
            st.rerun()
