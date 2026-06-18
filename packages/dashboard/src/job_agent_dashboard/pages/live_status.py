"""📡 Live Status — real-time pipeline progress with step-by-step log."""

import time

import streamlit as st

from job_agent_dashboard.helpers import get_api_live, format_activity_message


def render():
    st.title("📡 Pipeline Live Status")

    auto_refresh = st.toggle("🔄 Auto-refresh (every 3s)", value=True)

    status_data = get_api_live("/status")
    if "error" in status_data:
        st.error(f"Cannot fetch status: {status_data['error']}")
    else:
        pipeline = status_data.get("pipeline", {})

        # ── Step Progress Bar ──
        phase = pipeline.get("phase", "idle")
        steps = ["idle", "searching", "matching", "tailoring", "applying", "completed"]

        current_idx = steps.index(phase) if phase in steps else 0
        if phase == "failed":
            current_idx = -1

        st.markdown("### Pipeline Progress")
        cols = st.columns(len(steps))
        for i, step in enumerate(steps):
            with cols[i]:
                if phase == "failed":
                    st.markdown(f"<div style='text-align:center;color:red'>❌<br><small>{step.title()}</small></div>", unsafe_allow_html=True)
                elif i < current_idx:
                    st.markdown(f"<div style='text-align:center;color:green'>✅<br><small>{step.title()}</small></div>", unsafe_allow_html=True)
                elif i == current_idx:
                    st.markdown(f"<div style='text-align:center;color:orange;font-weight:bold'>⏳<br><small><b>{step.title()}</b></small></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='text-align:center;color:gray'>⬜<br><small>{step.title()}</small></div>", unsafe_allow_html=True)

        if phase == "completed":
            st.progress(1.0, text="Pipeline completed!")
        elif phase == "failed":
            st.progress(0.0, text="Pipeline failed")
        elif current_idx > 0:
            st.progress(current_idx / (len(steps) - 1), text=f"Step {current_idx}/{len(steps) - 1}: {phase.title()}")

        st.divider()

        # ── Current Job ──
        if pipeline.get("current_job"):
            job = pipeline["current_job"]
            st.info(f"🎯 Currently processing: **{job.get('title', '?')}** @ {job.get('company', '?')}")

        # ── Live Stats ──
        stats = pipeline.get("stats", {})
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("🔍 Searched", stats.get("searched", 0))
        c2.metric("📊 Matched", stats.get("matched", 0))
        c3.metric("🚀 Applied", stats.get("applied", 0))
        c4.metric("📧 Emailed", stats.get("emailed", 0))
        c5.metric("❌ Errors", stats.get("errors", 0))

        st.divider()

        # ── Detailed Step-by-Step Log ──
        st.subheader("📜 Step-by-Step Activity Log")

        records = status_data.get("recent_io", [])
        if records:
            for r in reversed(records[-30:]):
                node = r.get("node", "")
                direction = r.get("direction", "")
                data = r.get("data", {})
                ts = r.get("timestamp", "")[11:19]
                duration = r.get("duration_ms", 0)
                duration_str = f" `{duration:.0f}ms`" if duration else ""

                msg = format_activity_message(node, direction, data)

                if direction == "error":
                    st.error(f"🔴 `{ts}` {msg}{duration_str}")
                elif direction == "output":
                    st.success(f"✅ `{ts}` {msg}{duration_str}")
                else:
                    st.info(f"▶️ `{ts}` {msg}")
        else:
            st.info("No activity yet. Start the pipeline from **🚀 Run Pipeline**.")

        st.divider()

        # ── Errors ──
        errors = status_data.get("errors", [])
        if errors:
            st.subheader("🔴 Errors")
            for err in reversed(errors):
                st.error(f"`{err['timestamp'][11:19]}` **{err['node']}** — {err['data']}")

    if auto_refresh:
        time.sleep(3)
        st.rerun()
