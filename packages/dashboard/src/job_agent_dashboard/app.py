"""Streamlit Dashboard - Web UI for the job application agent.

Thin router that delegates to individual page modules under pages/.
"""

import streamlit as st

from job_agent_dashboard.helpers import get_api
from job_agent_dashboard.pages import (
    analytics,
    cover_letters,
    dashboard,
    interview_prep,
    live_status,
    pipeline_graph,
    pipeline_results,
    profile_strength,
    review_queue,
    run_pipeline,
    salary_insights,
    search_jobs,
    settings,
    source_health,
    timeline,
)

st.set_page_config(page_title="Job Apply Agent", page_icon="🤖", layout="wide")

# --- Sidebar ---

st.sidebar.title("🤖 Job Agent")

PAGES = {
    "📊 Dashboard": dashboard,
    "🚀 Run Pipeline": run_pipeline,
    "📋 Pipeline Results": pipeline_results,
    "🔍 Search Jobs": search_jobs,
    "📋 Review Queue": review_queue,
    "📝 Cover Letters": cover_letters,
    "🎯 Interview Prep": interview_prep,
    "📈 Analytics": analytics,
    "🏥 Source Health": source_health,
    "💪 Profile Strength": profile_strength,
    "💰 Salary Insights": salary_insights,
    "📅 Timeline": timeline,
    "🗺️ Pipeline Graph": pipeline_graph,
    "📡 Live Status": live_status,
    "⚙️ Settings": settings,
}

page = st.sidebar.radio("Navigation", list(PAGES.keys()))

health = get_api("/health")
if "error" in health:
    st.sidebar.error(f"Agent offline: {health['error']}")
else:
    st.sidebar.success(f"Agent v{health.get('version', '?')} online")

# --- Route to page ---

PAGES[page].render()
