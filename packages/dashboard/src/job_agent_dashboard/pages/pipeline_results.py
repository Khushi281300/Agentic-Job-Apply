"""📋 Pipeline Results — per-job breakdown with match and resume details."""

import json

import pandas as pd
import streamlit as st

from job_agent_dashboard.helpers import get_api, safe_json, download_bytes


def render():
    st.title("📋 Pipeline Results — Per-Job Breakdown")

    # ── Export buttons ──
    exports = [
        ("📄 Download PDF Report", "/export/pdf", "job_applications.pdf", "application/pdf"),
        ("📊 Download CSV", "/export/csv", "job_applications.csv", "text/csv"),
        ("🗂️ Download JSON", "/export/json", "job_applications.json", "application/json"),
    ]
    exp_cols = st.columns(len(exports))
    for col, (label, endpoint, filename, mime) in zip(exp_cols, exports):
        with col:
            resp = download_bytes(endpoint)
            if resp:
                st.download_button(label, data=resp.content, file_name=filename, mime=mime)
            else:
                st.button(label, disabled=True, help="No data to export")

    st.divider()

    jobs_data = get_api("/jobs")
    if isinstance(jobs_data, dict) and "error" in jobs_data:
        st.error(f"Cannot load jobs: {jobs_data['error']}")
        return
    if not jobs_data:
        st.info("No jobs tracked yet. Run the pipeline first.")
        return

    # ── Status filter ──
    all_statuses = sorted(set(j.get("status", "") for j in jobs_data))
    status_filter = st.multiselect(
        "Filter by status", all_statuses, default=all_statuses,
    )
    filtered = [j for j in jobs_data if j.get("status") in status_filter]

    st.caption(f"Showing {len(filtered)} of {len(jobs_data)} jobs")

    # ── Summary table ──
    if filtered:
        table_data = []
        for j in filtered:
            score = j.get("match_score", 0) or 0
            table_data.append({
                "Company": j.get("company", ""),
                "Title": j.get("title", ""),
                "Score": f"{score:.0%}" if score else "—",
                "Status": j.get("status", "").upper(),
                "Source": j.get("source", ""),
                "Discovered": j.get("discovered_at", "")[:10],
                "Applied": j.get("applied_at", "")[:10] if j.get("applied_at") else "—",
            })
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Per-job detail expanders ──
    for j in filtered:
        score = j.get("match_score", 0) or 0
        status = j.get("status", "").upper()
        status_icon = {
            "DISCOVERED": "🔵", "MATCHED": "🟢", "REJECTED": "🔴",
            "APPLYING": "🟡", "APPLIED": "✅", "FAILED": "❌",
        }.get(status, "⚪")

        label = f"{status_icon} {j.get('company', '?')} — {j.get('title', '?')}  ({score:.0%})"
        with st.expander(label, expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("Match Score", f"{score:.0%}")
            c2.metric("Status", status)
            c3.metric("Source", j.get("source", "—"))

            if j.get("url"):
                st.markdown(f"[🔗 Job Link]({j['url']})")

            # ── Match Details ──
            match_raw = j.get("match_data", "{}")
            match_data = safe_json(match_raw) if isinstance(match_raw, str) else (match_raw or {})

            if match_data and match_data.get("job_id"):
                st.subheader("📊 Match Analysis")
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Skill", f"{match_data.get('skill_match', 0):.0%}")
                mc2.metric("Experience", f"{match_data.get('experience_match', 0):.0%}")
                mc3.metric("Location", f"{match_data.get('location_match', 0):.0%}")
                mc4.metric("Salary", f"{match_data.get('salary_match', 0):.0%}")

                matched_skills = match_data.get("matched_skills", [])
                missing_skills = match_data.get("missing_skills", [])
                if matched_skills:
                    st.markdown("**✅ Matched Skills:** " + ", ".join(f"`{s}`" for s in matched_skills))
                if missing_skills:
                    st.markdown("**❌ Missing Skills:** " + ", ".join(f"`{s}`" for s in missing_skills))

                reasoning = match_data.get("reasoning", "")
                if reasoning:
                    st.markdown("**💡 Reasoning:**")
                    st.info(reasoning)

            # ── Tailored Resume / Cover Letter ──
            tailored_raw = j.get("tailored_data", "{}")
            tailored = safe_json(tailored_raw) if isinstance(tailored_raw, str) else (tailored_raw or {})

            if tailored and tailored.get("job_id"):
                st.subheader("📝 Tailored Resume & Cover Letter")

                summary = tailored.get("summary", "")
                if summary:
                    st.markdown("**Resume Summary:**")
                    st.success(summary)

                highlighted = tailored.get("highlighted_skills", [])
                if highlighted:
                    st.markdown("**Highlighted Skills:** " + ", ".join(f"`{s}`" for s in highlighted))

                cover_letter = tailored.get("cover_letter", "")
                if cover_letter:
                    st.markdown("**Cover Letter:**")
                    st.text_area(
                        "Cover Letter", cover_letter, height=300,
                        key=f"cl_{j['id']}", disabled=True,
                    )

            # ── Error (if any) ──
            error = j.get("error", "")
            if error:
                st.error(f"Error: {error}")
