"""🎯 Interview Prep — generate interview questions for applied jobs."""

import streamlit as st

from job_agent_dashboard.helpers import get_api, post_api


def render():
    st.title("🎯 Interview Preparation")
    st.markdown("Generate likely interview questions for any applied job.")

    jobs_data = get_api("/jobs?status=applied")
    if isinstance(jobs_data, dict) and "error" in jobs_data:
        st.error(f"Cannot load jobs: {jobs_data['error']}")
        return
    if not jobs_data:
        st.info("No applied jobs yet. Run the pipeline first.")
        return

    job_options = {f"{j['title']} @ {j['company']}": j['id'] for j in jobs_data}
    selected = st.selectbox("Select a job to prepare for", list(job_options.keys()))

    if selected and st.button("🎯 Generate Interview Questions", type="primary"):
        job_id = job_options[selected]
        with st.spinner("Generating interview prep using AI..."):
            result = post_api(f"/interview-prep/{job_id}")

        if "error" not in result:
            tech = result.get("technical", [])
            if tech:
                st.subheader("💻 Technical Questions")
                for i, qa in enumerate(tech, 1):
                    with st.expander(f"Q{i}: {qa.get('question', '')}"):
                        st.markdown(f"**Suggested Answer:** {qa.get('answer', '')}")

            behavioral = result.get("behavioral", [])
            if behavioral:
                st.subheader("🧠 Behavioral Questions")
                for i, qa in enumerate(behavioral, 1):
                    with st.expander(f"Q{i}: {qa.get('question', '')}"):
                        st.markdown(f"**Suggested Answer (STAR):** {qa.get('answer', '')}")

            company_q = result.get("company_specific", [])
            if company_q:
                st.subheader("🏢 Company-Specific Questions")
                for i, qa in enumerate(company_q, 1):
                    with st.expander(f"Q{i}: {qa.get('question', '')}"):
                        st.markdown(f"**Suggested Answer:** {qa.get('answer', '')}")
        else:
            st.error(f"Failed: {result.get('error', 'Unknown error')}")
