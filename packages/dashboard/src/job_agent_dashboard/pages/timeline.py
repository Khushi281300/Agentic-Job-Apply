"""📅 Timeline — application journey tracking."""

import streamlit as st

from job_agent_dashboard.helpers import get_api


def render():
    st.title("📅 Application Timeline")
    st.markdown("Track the journey of each application.")

    timeline = get_api("/timeline")
    if isinstance(timeline, dict) and "error" in timeline:
        st.error(f"Cannot fetch timeline: {timeline['error']}")
        return
    if not timeline:
        st.info("No applications tracked yet.")
        return

    for item in timeline[:20]:
        events = item.get("events", [])
        stages = " → ".join(
            f"**{e['stage'].title()}**" for e in events
        )
        with st.expander(f"📌 {item['title']} @ {item['company']} — {item['current_status']}"):
            st.markdown(f"Journey: {stages}")
            for e in events:
                col = "🟢" if e["stage"] in ("offer", "interview") else "🔵"
                st.markdown(f"{col} **{e['stage'].title()}** — {e.get('at', 'N/A')}")
