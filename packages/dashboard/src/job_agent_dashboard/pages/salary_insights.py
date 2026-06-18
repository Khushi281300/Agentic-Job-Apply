"""💰 Salary Insights — aggregated compensation data."""

import streamlit as st

from job_agent_dashboard.helpers import get_api


def render():
    st.title("💰 Salary Market Insights")
    st.markdown("Aggregated compensation data from scraped job listings.")

    insights = get_api("/salary-insights")
    if isinstance(insights, dict) and "error" in insights:
        st.error(f"Cannot fetch salary data: {insights['error']}")
        return
    if not insights:
        st.info("No data available.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Jobs Analyzed", insights.get("total_jobs_analyzed", 0))
    c2.metric("With Salary Info", insights.get("jobs_with_salary", 0))
    c3.metric("Coverage", f"{insights.get('coverage_pct', 0)}%")

    st.divider()
    ranges = insights.get("ranges_by_role", {})
    if ranges:
        for role, data in ranges.items():
            with st.expander(f"**{role}** ({data['count']} jobs)"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Min", f"${data['min']:,}")
                c2.metric("Median Range", f"${data['median_low']:,} - ${data['median_high']:,}")
                c3.metric("Max", f"${data['max']:,}")
    else:
        st.info("No salary data yet. Run searches to collect market data.")
