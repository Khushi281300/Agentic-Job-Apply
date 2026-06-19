"""Shared helpers for all dashboard pages."""

import json
import os

import httpx
import streamlit as st

AGENT_API_URL = os.getenv("AGENT_API_URL", "http://localhost:8000")


@st.cache_data(ttl=30)
def get_api(endpoint: str):
    """Cached API GET call (30s TTL)."""
    try:
        resp = httpx.get(f"{AGENT_API_URL}{endpoint}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def get_api_live(endpoint: str):
    """Uncached API GET call for live-updating pages."""
    try:
        resp = httpx.get(f"{AGENT_API_URL}{endpoint}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def post_api(endpoint: str, data: dict = {}, timeout: int = 30):
    """API POST call."""
    try:
        resp = httpx.post(f"{AGENT_API_URL}{endpoint}", json=data, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def put_api(endpoint: str, data: dict = {}):
    """API PUT call."""
    try:
        resp = httpx.put(f"{AGENT_API_URL}{endpoint}", json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def upload_file(endpoint: str, filename: str, content: bytes, mime: str = "application/pdf"):
    """Upload a file via multipart POST."""
    try:
        resp = httpx.post(
            f"{AGENT_API_URL}{endpoint}",
            files={"file": (filename, content, mime)},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def download_bytes(endpoint: str, timeout: int = 15) -> httpx.Response | None:
    """Download raw bytes from an endpoint. Returns Response or None on error."""
    try:
        resp = httpx.get(f"{AGENT_API_URL}{endpoint}", timeout=timeout)
        if resp.status_code == 200:
            return resp
    except Exception:
        pass
    return None


def safe_json(text: str) -> dict:
    """Parse JSON safely, returning {} on failure."""
    try:
        return json.loads(text or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def format_activity_message(node: str, direction: str, data: dict) -> str:
    """Turn raw node I/O records into human-readable messages."""
    if direction == "error":
        return f"**{node.title()}** failed — {data}" if isinstance(data, str) else f"**{node.title()}** encountered an error"

    if node == "search":
        if direction == "input":
            return "🔍 **Started searching** for jobs across all configured sources…"
        count = data.get("job_count", 0)
        return f"🔍 **Search complete** — found **{count} job{'s' if count != 1 else ''}** from remote boards"

    if node == "fetch_details":
        if direction == "input":
            return "📄 **Fetching full job descriptions** for each discovered listing…"
        return "📄 **Job details enriched** — descriptions, requirements & salary data loaded"

    if node == "match":
        if direction == "input":
            return "📊 **Started matching** jobs against your profile & resume…"
        matched = data.get("matched", 0)
        rejected = data.get("rejected", 0)
        total = matched + rejected
        return f"📊 **Matching complete** — **{matched}/{total}** jobs passed the score threshold ({rejected} rejected)"

    if node == "tailor":
        if direction == "input":
            return "📝 **Tailoring resumes** for each matched position…"
        return "📝 **Tailoring done** — custom resumes & cover letters generated for each match"

    if node == "human_review":
        if direction == "input":
            return "👀 **Waiting for your review** — check the Review Queue to approve/reject applications"
        return "👀 **Review completed** — approved applications moving to apply step"

    if node == "apply":
        if direction == "input":
            return "🚀 **Submitting applications** to company career portals…"
        applied = data.get("applied", 0)
        failed = data.get("failed", 0)
        if failed:
            return f"🚀 **Applications submitted** — **{applied} succeeded**, {failed} failed"
        return f"🚀 **Applications submitted** — **{applied}** application{'s' if applied != 1 else ''} sent successfully!"

    if node == "email":
        if direction == "input":
            return "📧 **Sending application emails** with tailored cover letters…"
        return "📧 **Emails sent** — cover letters delivered to hiring contacts"

    return f"⚙️ **{node.title()}** — {direction}"


def load_profile() -> dict:
    """Load the user profile from data/profile.json. Returns {} if not found."""
    from pathlib import Path
    profile_path = Path(__file__).resolve().parents[4] / "data" / "profile.json"
    try:
        if profile_path.exists():
            return json.loads(profile_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {}
