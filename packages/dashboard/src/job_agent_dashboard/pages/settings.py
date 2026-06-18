"""⚙️ Settings — configuration viewer and MCP tools list."""

from pathlib import Path

import streamlit as st

from job_agent_dashboard.helpers import post_api


def render():
    st.title("⚙️ Configuration")

    env_path = Path(".env")
    if env_path.exists():
        env_content = env_path.read_text()
        st.code(env_content, language="ini")
    else:
        st.warning("No .env file found.")

    st.divider()
    st.subheader("MCP Tools Available")
    tools = post_api("/mcp/tools/list")
    if "error" not in tools:
        for tool in tools.get("tools", []):
            with st.expander(f"🔧 {tool['name']}"):
                st.write(tool["description"])
                st.json(tool.get("inputSchema", {}))
