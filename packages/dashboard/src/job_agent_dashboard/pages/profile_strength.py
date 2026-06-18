"""💪 Profile Strength — analyze profile against market demand."""

import pandas as pd
import streamlit as st

from job_agent_dashboard.helpers import get_api


def render():
    st.title("💪 Profile Strength Analysis")
    st.markdown("See how your profile stacks up against market demand.")

    if st.button("🔍 Analyze My Profile"):
        with st.spinner("Analyzing against job market data..."):
            report = get_api("/profile/strength")

        if isinstance(report, dict) and "error" in report:
            st.error(f"Analysis failed: {report['error']}")
        elif report:
            score = report.get("overall_score", 0)
            st.metric("Overall Strength", f"{score:.0%}")
            st.progress(score)

            c1, c2 = st.columns(2)
            with c1:
                st.subheader("✅ Strengths")
                for skill in report.get("strengths", []):
                    st.markdown(f"- {skill}")
            with c2:
                st.subheader("❌ Gaps")
                for skill in report.get("gaps", []):
                    st.markdown(f"- {skill}")

            st.divider()
            st.subheader("💡 Recommendations")
            for rec in report.get("recommendations", []):
                st.info(rec)

            st.divider()
            st.subheader("📊 Market Demand (Top Skills)")
            demand = report.get("market_demand_top_skills", {})
            if demand:
                df = pd.DataFrame([
                    {"Skill": k, "Mentions": v} for k, v in demand.items()
                ])
                st.bar_chart(df.set_index("Skill"))
