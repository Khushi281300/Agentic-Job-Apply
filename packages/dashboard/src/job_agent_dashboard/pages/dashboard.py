"""📊 Dashboard — overview metrics and agent card."""

import json

import streamlit as st

from job_agent_dashboard.helpers import get_api, post_api, safe_json


def render():
    st.title("📊 Application Dashboard")

    stats = post_api("/mcp/tools/call", {"name": "get_application_stats", "arguments": {}})
    if "error" not in stats:
        content = stats.get("content", [{}])
        if content:
            data = safe_json(content[0].get("text", "{}"))
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
