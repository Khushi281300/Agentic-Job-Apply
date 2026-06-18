"""📝 Cover Letters — view and generate cover letters."""

from pathlib import Path

import streamlit as st

from job_agent_dashboard.helpers import post_api, safe_json


def render():
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
                data = safe_json(content[0].get("text", "{}"))
                st.success("Generated!")
                st.text_area("Result", data.get("cover_letter", ""), height=300)
