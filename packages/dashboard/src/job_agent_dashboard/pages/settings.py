"""⚙️ Settings — configuration viewer, resume upload, and MCP tools list."""

from pathlib import Path

import streamlit as st

from job_agent_dashboard.helpers import post_api, get_api, upload_file


def render():
    st.title("⚙️ Configuration")

    # ─── Resume Upload ───────────────────────────────────────────────────────
    st.subheader("📄 Resume Upload")
    uploaded = st.file_uploader(
        "Upload your resume (PDF) to seed profile and RAG store",
        type=["pdf"],
        key="resume_upload",
    )
    if uploaded is not None:
        if st.button("⬆️ Upload & Parse Resume"):
            with st.spinner("Uploading and parsing resume..."):
                result = upload_file("/profile/upload", uploaded.name, uploaded.getvalue())
                if "error" not in result:
                    if result.get("status") == "uploaded":
                        st.success(f"Resume uploaded and parsed! Saved to `{result.get('path')}`")
                        if result.get("profile"):
                            st.json(result["profile"])
                    else:
                        st.warning(f"Uploaded but parsing failed: {result.get('error', 'unknown')}")
                else:
                    st.error(f"Upload failed: {result['error']}")

    # Show current profile
    profile = get_api("/profile")
    if "error" not in profile:
        with st.expander("👤 Current Profile", expanded=False):
            st.json(profile)
    else:
        st.info("No profile found. Upload a resume to get started.")

    st.divider()

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
