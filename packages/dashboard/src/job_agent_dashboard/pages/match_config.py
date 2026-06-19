"""🎛️ Match Config — adjust search titles, locations, and match criteria at runtime."""

import streamlit as st

from job_agent_dashboard.helpers import get_api_live, put_api


def render():
    st.title("🎛️ Match Configuration")
    st.caption("Change search and matching settings without restarting the server.")

    # ── Search Config ──
    st.subheader("🔍 Search Settings")
    search_cfg = get_api_live("/config/search")
    if "error" in search_cfg:
        st.error(f"Cannot load search config: {search_cfg['error']}")
        return

    titles = st.text_area(
        "Job Titles (one per line)",
        value="\n".join(search_cfg.get("titles", [])),
        height=100,
        key="cfg_titles",
    )
    locations = st.text_area(
        "Locations (one per line)",
        value="\n".join(search_cfg.get("locations", [])),
        height=100,
        key="cfg_locations",
    )
    min_salary = st.number_input(
        "Minimum Salary ($)",
        value=search_cfg.get("min_salary", 0),
        min_value=0,
        step=5000,
        key="cfg_min_salary",
    )
    remote_only = st.checkbox(
        "Remote Only",
        value=search_cfg.get("remote_only", False),
        key="cfg_remote",
    )
    experience_level = st.selectbox(
        "Experience Level",
        options=["", "junior", "mid", "senior", "lead", "principal"],
        index=["", "junior", "mid", "senior", "lead", "principal"].index(
            search_cfg.get("experience_level", "")
        ) if search_cfg.get("experience_level", "") in ["", "junior", "mid", "senior", "lead", "principal"] else 0,
        key="cfg_exp",
    )

    if st.button("💾 Save Search Settings", key="save_search"):
        new_titles = [t.strip() for t in titles.split("\n") if t.strip()]
        new_locations = [l.strip() for l in locations.split("\n") if l.strip()]
        result = put_api("/config/search", {
            "titles": new_titles,
            "locations": new_locations,
            "min_salary": min_salary,
            "remote_only": remote_only,
            "experience_level": experience_level,
        })
        if "error" in result:
            st.error(f"Failed: {result['error']}")
        else:
            st.success("Search settings updated! Changes take effect on next pipeline run.")

    st.divider()

    # ── Application Config ──
    st.subheader("🎯 Application Settings")
    app_cfg = get_api_live("/config/application")
    if "error" in app_cfg:
        st.error(f"Cannot load application config: {app_cfg['error']}")
        return

    min_score = st.slider(
        "Minimum Match Score",
        min_value=0.0,
        max_value=1.0,
        value=float(app_cfg.get("min_match_score", 0.6)),
        step=0.05,
        format="%.0f%%" if False else "%.2f",
        help="Jobs below this score will be rejected during matching",
        key="cfg_min_score",
    )
    max_apps = st.number_input(
        "Max Applications Per Day",
        value=app_cfg.get("max_applications_per_day", 10),
        min_value=1,
        max_value=100,
        key="cfg_max_apps",
    )
    auto_submit = st.checkbox(
        "Auto-Submit Applications",
        value=app_cfg.get("auto_submit", False),
        help="When enabled, applications are submitted automatically without review",
        key="cfg_auto",
    )

    if st.button("💾 Save Application Settings", key="save_app"):
        result = put_api("/config/application", {
            "min_match_score": min_score,
            "max_applications_per_day": max_apps,
            "auto_submit": auto_submit,
        })
        if "error" in result:
            st.error(f"Failed: {result['error']}")
        else:
            st.success("Application settings updated!")
