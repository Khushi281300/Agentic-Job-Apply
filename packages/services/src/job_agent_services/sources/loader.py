"""YAML config loader — reads job_sources.yaml and creates source instances.

Merges YAML-defined sources with hardcoded Python sources (remoteok, remotive,
remoterocketship). YAML sources use generic ApiJsonSource, HtmlScrapeSource,
or RssSource classes. Hardcoded sources take priority if names overlap.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from job_agent_contracts.interfaces import JobSource
from job_agent_services.sources.generic import ApiJsonSource, BrowserScrapeSource, HtmlScrapeSource, RssSource

logger = logging.getLogger(__name__)

# Sources with dedicated Python implementations — skip YAML config for these
_HARDCODED_SOURCES = {"remoteok", "remotive", "remoterocketship"}

_SOURCE_BUILDERS: dict[str, type] = {
    "api_json": ApiJsonSource,
    "html_scrape": HtmlScrapeSource,
    "browser_scrape": BrowserScrapeSource,
    "rss": RssSource,
}


def load_sources_from_yaml(
    config_path: str | Path = "config/job_sources.yaml",
) -> list[JobSource]:
    """Load enabled job sources from YAML config.

    Returns a list of generic source instances. Skips sources that have
    dedicated Python implementations (remoteok, remotive, remoterocketship)
    since those are added separately by the container.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        List of instantiated JobSource objects.
    """
    path = Path(config_path)
    if not path.exists():
        logger.warning("Job sources config not found: %s", path)
        return []

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to parse %s: %s", path, e)
        return []

    if not raw or "sources" not in raw:
        logger.warning("No 'sources' key in %s", path)
        return []

    sources: list[JobSource] = []
    for entry in raw["sources"]:
        source = _build_source(entry)
        if source is not None:
            sources.append(source)

    logger.info(
        "Loaded %d YAML sources: %s",
        len(sources),
        [s.name for s in sources],
    )
    return sources


def _build_source(entry: dict[str, Any]) -> JobSource | None:
    """Build one source instance from a YAML entry, or None to skip."""
    name = entry.get("name", "")
    if not name:
        logger.warning("Skipping source with no name")
        return None

    if not entry.get("enabled", True):
        logger.debug("Skipping disabled source: %s", name)
        return None

    if name in _HARDCODED_SOURCES:
        logger.debug("Skipping %s — has dedicated Python implementation", name)
        return None

    source_type = entry.get("type", "")
    builder = _SOURCE_BUILDERS.get(source_type)
    if builder is None:
        logger.warning(
            "Unknown source type '%s' for '%s' (expected: %s)",
            source_type, name, list(_SOURCE_BUILDERS.keys()),
        )
        return None

    if "search_url" not in entry:
        logger.warning("Skipping %s — no search_url defined", name)
        return None

    try:
        return builder(entry)
    except Exception as e:
        logger.error("Failed to create source '%s': %s", name, e)
        return None


def get_rate_limits_from_yaml(
    config_path: str | Path = "config/job_sources.yaml",
) -> dict[str, tuple[int, float]]:
    """Extract rate limit config from YAML for the rate limiter.

    Returns:
        Dict of {source_name: (max_requests_per_window, window_seconds)}.
        Window is always 60s; max_requests comes from the YAML rate_limit field.
    """
    path = Path(config_path)
    if not path.exists():
        return {}

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    limits: dict[str, tuple[int, float]] = {}
    for entry in raw.get("sources", []):
        name = entry.get("name", "")
        rate = entry.get("rate_limit")
        if name and rate:
            limits[name] = (int(rate), 60.0)

    return limits
