"""Profile Match page - match discovered jobs against your profile."""

import streamlit as st

from job_agent_dashboard.helpers import get_api, post_api, load_profile


def render():
    st.header("🎯 Profile Match")
    st.caption("Match discovered jobs against your resume profile and see detailed scoring")

    # --- Profile Preview ---
    profile = load_profile()

    if not profile or not profile.get("name"):
        st.warning("⚠️ No user profile found. Create `data/profile.json` with your resume data for accurate matching.")
        st.stop()

    with st.expander("👤 Your Profile", expanded=False):
        col1, col2, col3 = st.columns(3)
        col1.metric("Name", profile.get("name", "N/A"))
        col2.metric("Title", profile.get("title", "N/A"))
        col3.metric("Experience", f"{profile.get('experience_years', 0)} years")
        skills = profile.get("skills", [])
        if skills:
            st.write("**Skills:**", ", ".join(skills[:20]), f"... (+{len(skills)-20} more)" if len(skills) > 20 else "")
        certs = profile.get("certifications", [])
        if certs:
            st.write("**Certifications:**", ", ".join(certs))

    st.divider()

    # --- Match Controls ---
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        batch_size = st.slider("Jobs to match", min_value=1, max_value=50, value=10, step=1)
    with col2:
        min_score = st.number_input("Min score threshold", min_value=0.0, max_value=1.0, value=0.6, step=0.05)
    with col3:
        st.write("")  # spacer
        st.write("")
        run_match = st.button("🚀 Run Matching", type="primary", use_container_width=True)

    # --- Single Job Match ---
    with st.expander("🔍 Match a Specific Job by ID"):
        job_id = st.text_input("Job ID", placeholder="e.g. linkedin_29ce721b")
        match_single = st.button("Match This Job")
        if match_single and job_id:
            with st.spinner(f"Matching {job_id}..."):
                r = post_api(f"/match/test/{job_id}", timeout=120)
                if "error" in r:
                    st.error(f"Matching failed: {r['error']}")
                else:
                    score = r.get("overall_score", 0)
                    icon = "✅" if score >= min_score else "❌"
                    st.subheader(f"{icon} {r['title']} at {r['company']} — {score:.0%}")
                    _render_match_detail(r, min_score)

    st.divider()

    # --- Batch Match Results ---
    if run_match:
        st.subheader(f"Matching {batch_size} discovered jobs...")
        progress = st.progress(0, text="Starting...")
        status_area = st.empty()

        data = post_api(f"/match/test-batch?limit={batch_size}", timeout=batch_size * 90)
        progress.progress(100, text="Complete!")

        if "error" in data:
            st.error(f"Error: {data['error']}")
            return

        results = data.get("results", [])
        total = data.get("total", 0)
        matched_count = data.get("matched", 0)

        if not results:
            st.info("No discovered jobs to match. Run the pipeline first to search for jobs.")
            return

        # Summary metrics
        st.divider()
        rejected_count = total - matched_count
        error_count = len([r for r in results if "error" in r])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Tested", total)
        m2.metric("Matched (≥ {:.0%})".format(min_score), matched_count)
        m3.metric("Not Matched", rejected_count - error_count)
        m4.metric("Errors", error_count)

        # --- Matched Jobs ---
        matched = [r for r in results if r.get("score", 0) >= min_score and "error" not in r]
        not_matched = [r for r in results if r.get("score", 0) < min_score and "error" not in r]
        errors = [r for r in results if "error" in r]

        if matched:
            st.subheader(f"✅ Matched Jobs ({len(matched)})")
            for r in sorted(matched, key=lambda x: x.get("score", 0), reverse=True):
                score = r.get("score", 0)
                loc = f" · {r['location']}" if r.get("location") else ""
                src = f" [{r['source']}]" if r.get("source") else ""
                with st.expander(f"**{r['title']}** at {r['company']}{loc}{src} — **{score:.0%}**", expanded=True):
                    _render_match_detail(r, min_score)

        if not_matched:
            st.subheader(f"❌ Not Matched ({len(not_matched)})")
            for r in sorted(not_matched, key=lambda x: x.get("score", 0), reverse=True):
                score = r.get("score", 0)
                loc = f" · {r['location']}" if r.get("location") else ""
                src = f" [{r['source']}]" if r.get("source") else ""
                with st.expander(f"{r['title']} at {r['company']}{loc}{src} — {score:.0%}"):
                    _render_match_detail(r, min_score)

        if errors:
            st.subheader(f"⚠️ Errors ({len(errors)})")
            for r in errors:
                st.error(f"**{r.get('title', 'Unknown')}**: {r.get('error', 'Unknown error')}")

    # --- Previous Match Results from DB ---
    st.divider()
    st.subheader("📊 Previously Matched Jobs in Database")
    matched_jobs = get_api("/jobs?status=matched")
    if isinstance(matched_jobs, dict) and "error" in matched_jobs:
        st.info("Server not available.")
    elif matched_jobs:
        for job in matched_jobs:
            score = job.get("score", job.get("match_score", 0))
            url = job.get("url", "")
            title_text = f"**{job['title']}** at {job['company']}"
            if url:
                title_text = f"[**{job['title']}**]({url}) at {job['company']}"
            st.write(f"✅ {title_text} — {score:.0%}")
    else:
        st.info("No matched jobs in database yet. Run matching above to score jobs.")


def _render_match_detail(r: dict, min_score: float):
    """Render detailed match result for a single job."""
    score = r.get("score", r.get("overall_score", 0))

    # --- Job Info Header ---
    url = r.get("url", "")
    location = r.get("location", "")
    source = r.get("source", "")
    description = r.get("description", "")
    discovered_at = r.get("discovered_at", "")

    info_cols = st.columns([2, 1, 1])
    with info_cols[0]:
        if url:
            st.markdown(f"🔗 [**Open Original Job Page**]({url})")
        if location:
            st.write(f"📍 **Location:** {location}")
    with info_cols[1]:
        if source:
            st.write(f"🌐 **Source:** {source}")
    with info_cols[2]:
        if discovered_at:
            date_str = discovered_at[:10] if len(discovered_at) >= 10 else discovered_at
            st.write(f"📅 **Found:** {date_str}")

    # Score bar
    st.progress(min(score, 1.0), text=f"Overall: {score:.0%}")

    # Sub-scores (if available from single match endpoint)
    sub_scores = {}
    for key in ["skill_match", "experience_match", "location_match", "salary_match"]:
        if key in r and r[key] is not None:
            sub_scores[key] = r[key]
    if sub_scores:
        cols = st.columns(len(sub_scores))
        for col, (key, val) in zip(cols, sub_scores.items()):
            label = key.replace("_", " ").title()
            col.metric(label, f"{val:.0%}")

    # Reasoning
    reasoning = r.get("reasoning", "")
    if reasoning:
        if score >= min_score:
            st.success(f"**Why matched:** {reasoning}")
        else:
            st.warning(f"**Why not matched:** {reasoning}")

    # Skills
    col1, col2 = st.columns(2)
    matched_skills = r.get("matched_skills", [])
    missing_skills = r.get("missing_skills", [])
    with col1:
        if matched_skills:
            st.write("**✅ Matched Skills:**")
            st.write(", ".join(matched_skills[:15]))
            if len(matched_skills) > 15:
                st.caption(f"+{len(matched_skills)-15} more")
    with col2:
        if missing_skills:
            st.write("**❌ Missing Skills:**")
            st.write(", ".join(missing_skills))

    # Job Description
    if description:
        with st.expander("📄 Job Description"):
            st.write(description[:2000])
            if len(description) > 2000:
                st.caption(f"... ({len(description) - 2000} more characters)")
