"""⏰ Deadlines — track and manage application closing dates."""

from datetime import date

import pandas as pd
import streamlit as st

from job_agent_dashboard.helpers import get_api, get_api_live, post_api, AGENT_API_URL

import httpx


def _put_api(endpoint: str, data: dict):
    try:
        resp = httpx.put(f"{AGENT_API_URL}{endpoint}", json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def render():
    st.title("⏰ Application Deadlines")

    # ── Upcoming Deadlines ──
    days = st.slider("Show deadlines within (days)", 1, 90, 14, key="dl_days")
    upcoming = get_api_live(f"/deadlines/upcoming?days={days}")

    if isinstance(upcoming, dict) and "error" in upcoming:
        st.error(f"Cannot load deadlines: {upcoming['error']}")
        return

    if upcoming:
        st.subheader(f"🔔 Upcoming Deadlines ({len(upcoming)} jobs)")
        rows = []
        for j in upcoming:
            days_left = j.get("days_left", "?")
            urgency = "🔴" if isinstance(days_left, int) and days_left <= 2 else (
                "🟡" if isinstance(days_left, int) and days_left <= 5 else "🟢"
            )
            rows.append({
                "Urgency": urgency,
                "Days Left": days_left,
                "Company": j.get("company", ""),
                "Title": j.get("title", ""),
                "Deadline": j.get("deadline", "")[:10],
                "Score": f"{j.get('match_score', 0):.0%}" if j.get("match_score") else "—",
                "Status": j.get("status", "").upper(),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No upcoming deadlines. Set deadlines on tracked jobs below.")

    st.divider()

    # ── Expired Deadlines ──
    expired = get_api_live("/deadlines/expired")
    if isinstance(expired, list) and expired:
        st.subheader(f"⚠️ Expired Deadlines ({len(expired)} missed)")
        exp_rows = []
        for j in expired:
            exp_rows.append({
                "Company": j.get("company", ""),
                "Title": j.get("title", ""),
                "Deadline": j.get("deadline", "")[:10],
                "Status": j.get("status", "").upper(),
            })
        st.dataframe(pd.DataFrame(exp_rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── Set Deadline ──
    st.subheader("📅 Set a Deadline")

    jobs_data = get_api("/jobs")
    if isinstance(jobs_data, dict) and "error" in jobs_data:
        st.warning("Cannot load jobs list")
        return

    if isinstance(jobs_data, dict):
        all_jobs = jobs_data.get("jobs", [])
    else:
        all_jobs = jobs_data or []

    if not all_jobs:
        st.info("No jobs tracked yet. Run the pipeline first.")
        return

    job_options = {
        f"{j.get('company', '?')} — {j.get('title', '?')} ({j.get('id', '')[:8]})": j.get("id", "")
        for j in all_jobs
    }
    selected_label = st.selectbox("Select Job", list(job_options.keys()), key="dl_job")
    deadline_date = st.date_input("Deadline Date", value=None, min_value=date.today(), key="dl_date")

    if st.button("📅 Set Deadline", key="dl_set"):
        if not deadline_date:
            st.warning("Please select a deadline date.")
        else:
            job_id = job_options[selected_label]
            result = post_api("/deadlines", {
                "job_id": job_id,
                "deadline": deadline_date.isoformat(),
            })
            if "error" in result:
                st.error(f"Failed: {result['error']}")
            else:
                st.success(f"Deadline set for {deadline_date.isoformat()}!")
                st.rerun()
