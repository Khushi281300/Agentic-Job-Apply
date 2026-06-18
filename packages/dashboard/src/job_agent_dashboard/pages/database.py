"""🗄️ Database — view all tracked job records."""

import pandas as pd
import streamlit as st

from job_agent_dashboard.helpers import get_api_live, safe_json


def render():
    st.title("🗄️ Database Records")

    data = get_api_live("/export/json")
    if isinstance(data, dict) and "error" in data:
        st.error(f"Cannot load database: {data['error']}")
        return
    if not data:
        st.info("Database is empty. Run the pipeline to discover jobs.")
        return

    st.metric("Total Records", len(data))

    # ── Filters ──
    col1, col2, col3 = st.columns(3)
    with col1:
        statuses = sorted(set(j.get("status", "") for j in data))
        status_filter = st.multiselect("Status", statuses, default=statuses, key="db_status")
    with col2:
        sources = sorted(set(j.get("source", "") for j in data if j.get("source")))
        source_filter = st.multiselect("Source", sources, default=sources, key="db_source")
    with col3:
        search_text = st.text_input("Search (title/company)", key="db_search")

    filtered = data
    if status_filter:
        filtered = [j for j in filtered if j.get("status") in status_filter]
    if source_filter:
        filtered = [j for j in filtered if j.get("source") in source_filter]
    if search_text:
        q = search_text.lower()
        filtered = [
            j for j in filtered
            if q in (j.get("title", "") or "").lower()
            or q in (j.get("company", "") or "").lower()
        ]

    st.caption(f"Showing {len(filtered)} of {len(data)} records")

    # ── Table ──
    if filtered:
        rows = []
        for j in filtered:
            score = j.get("match_score", 0) or 0
            rows.append({
                "ID": (j.get("id", "") or "")[:8],
                "Title": j.get("title", ""),
                "Company": j.get("company", ""),
                "Location": j.get("location", ""),
                "Source": j.get("source", ""),
                "Status": (j.get("status", "") or "").upper(),
                "Score": f"{score:.0%}" if score else "—",
                "Discovered": (j.get("discovered_at", "") or "")[:10],
                "Applied": (j.get("applied_at", "") or "")[:10] or "—",
                "URL": j.get("url", ""),
                "Error": j.get("error", ""),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Detail view ──
    st.subheader("🔍 Record Details")
    if filtered:
        labels = [
            f"{j.get('company', '?')} — {j.get('title', '?')} ({(j.get('id','') or '')[:8]})"
            for j in filtered
        ]
        selected_idx = st.selectbox("Select a record", range(len(labels)), format_func=lambda i: labels[i], key="db_detail")
        job = filtered[selected_idx]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status", (job.get("status", "") or "").upper())
        c2.metric("Score", f"{(job.get('match_score', 0) or 0):.0%}")
        c3.metric("Source", job.get("source", "—"))
        c4.metric("Discovered", (job.get("discovered_at", "") or "")[:10])

        if job.get("url"):
            st.markdown(f"[🔗 Job Link]({job['url']})")

        # Match data
        match_raw = job.get("match_data", "{}")
        match_data = safe_json(match_raw) if isinstance(match_raw, str) else (match_raw or {})
        if match_data and match_data.get("job_id"):
            with st.expander("📊 Match Data", expanded=False):
                st.json(match_data)

        # Tailored data
        tailored_raw = job.get("tailored_data", "{}")
        tailored = safe_json(tailored_raw) if isinstance(tailored_raw, str) else (tailored_raw or {})
        if tailored and tailored.get("job_id"):
            with st.expander("📝 Tailored Resume Data", expanded=False):
                st.json(tailored)

        if job.get("error"):
            st.error(f"Error: {job['error']}")
