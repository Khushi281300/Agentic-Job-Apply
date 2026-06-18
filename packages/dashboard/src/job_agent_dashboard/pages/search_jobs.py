"""🔍 Search Jobs — ad-hoc job search."""

import json

import pandas as pd
import streamlit as st

from job_agent_dashboard.helpers import post_api, safe_json


def render():
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
                data = safe_json(content[0].get("text", "{}"))
                st.success(f"Found {data.get('jobs_found', 0)} jobs!")
                jobs = data.get("jobs", [])
                if jobs:
                    df = pd.DataFrame(jobs)
                    st.dataframe(df, use_container_width=True)
        else:
            st.error(f"Search failed: {result['error']}")
