"""📋 Review Queue — matched jobs pending review."""

import streamlit as st


def render():
    st.title("📋 Review Matched Jobs")
    st.info("Jobs that matched your profile but haven't been applied to yet.")
    st.warning("Review queue requires the agent to be running with matched jobs.")
