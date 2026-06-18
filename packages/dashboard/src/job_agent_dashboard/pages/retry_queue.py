"""🔄 Retry Queue — view pending retries, dead letters, and re-enqueue failed tasks."""

import pandas as pd
import streamlit as st

from job_agent_dashboard.helpers import get_api_live, post_api


def render():
    st.title("🔄 Retry Queue")
    st.caption("Failed operations are retried with exponential backoff. Dead letters need manual attention.")

    # ── Stats ──
    stats = get_api_live("/retry-queue/stats")
    if isinstance(stats, dict) and "error" in stats:
        st.error(f"Cannot load retry queue: {stats['error']}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⏳ Pending", stats.get("pending", 0))
    c2.metric("🔄 In Progress", stats.get("in_progress", 0))
    c3.metric("✅ Completed", stats.get("completed", 0))
    c4.metric("💀 Dead Letters", stats.get("dead", 0))

    st.divider()

    # ── Pending Tasks ──
    st.subheader("⏳ Pending Retries")
    pending = get_api_live("/retry-queue/pending")
    if isinstance(pending, dict) and "error" in pending:
        st.warning(f"Cannot load pending tasks: {pending['error']}")
    elif pending:
        rows = []
        for t in pending:
            payload = t.get("payload", {})
            rows.append({
                "ID": t.get("id", ""),
                "Type": t.get("task_type", ""),
                "Attempts": f"{t.get('attempts', 0)}/{t.get('max_attempts', 5)}",
                "Job ID": payload.get("job_id", "")[:8] if isinstance(payload, dict) else "",
                "Detail": str(payload)[:80] if payload else "",
                "Created": (t.get("created_at", "") or "")[:16],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.success("No pending retries.")

    st.divider()

    # ── Dead Letters ──
    st.subheader("💀 Dead Letters (Exhausted Retries)")
    dead = get_api_live("/retry-queue/dead-letters")
    if isinstance(dead, dict) and "error" in dead:
        st.warning(f"Cannot load dead letters: {dead['error']}")
    elif dead:
        for t in dead:
            payload = t.get("payload", {})
            task_id = t.get("id", "?")
            with st.expander(
                f"#{task_id} — {t.get('task_type', '?')} | {t.get('attempts', '?')} attempts",
                expanded=False,
            ):
                st.markdown(f"**Created:** {t.get('created_at', '—')}")
                st.markdown(f"**Last Error:**")
                st.error(t.get("last_error", "No error recorded"))
                st.markdown("**Payload:**")
                st.json(payload)

                if st.button(f"🔄 Re-enqueue", key=f"requeue_{task_id}"):
                    result = post_api(f"/retry-queue/{task_id}/retry", {})
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        st.success(f"Task #{task_id} re-enqueued for retry!")
                        st.rerun()
    else:
        st.success("No dead letters — all tasks completing successfully.")

    st.divider()

    # ── Scheduler Status ──
    st.subheader("⏰ Scheduler")
    sched = get_api_live("/scheduler/status")
    if isinstance(sched, dict) and "error" not in sched:
        status_emoji = "🟢" if sched.get("status") == "running" else "🔴"
        st.markdown(f"**Status:** {status_emoji} {sched.get('status', 'unknown')}")
        tasks = sched.get("tasks", {})
        if tasks:
            for name, info in tasks.items():
                running = "🟢" if info.get("running") else "⚫"
                interval = info.get("interval_secs", 0) / 60
                st.markdown(
                    f"- {running} **{name}** — every {interval:.0f}min | "
                    f"runs: {info.get('run_count', 0)} | errors: {info.get('error_count', 0)}"
                )
                if info.get("last_error"):
                    st.caption(f"  Last error: {info['last_error']}")
        else:
            st.info("No scheduled tasks configured.")
    else:
        st.info("Scheduler not active.")
