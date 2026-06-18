"""Tests for the YAML job source loader."""

import textwrap
import pytest
from pathlib import Path

from job_agent_services.sources.loader import load_sources_from_yaml, get_rate_limits_from_yaml
from job_agent_services.sources.generic import ApiJsonSource, HtmlScrapeSource, RssSource


@pytest.fixture
def yaml_config(tmp_path: Path) -> Path:
    """Create a minimal test YAML config."""
    config = tmp_path / "sources.yaml"
    config.write_text(textwrap.dedent("""\
        sources:
          - name: test_api
            type: api_json
            enabled: true
            base_url: https://example.com
            search_url: https://example.com/api?q={title}&loc={location}
            rate_limit: 10
            json_mapping:
              title: name
              company: org
              url: link
              id_field: id
              id_prefix: "test_"

          - name: test_scraper
            type: html_scrape
            enabled: true
            base_url: https://example.com
            search_url: https://example.com/jobs?q={title}
            rate_limit: 5
            selectors:
              job_card: ".job"
              title: ".title"
              company: ".company"

          - name: test_rss
            type: rss
            enabled: true
            base_url: https://example.com
            search_url: https://example.com/feed.rss
            rate_limit: 8

          - name: disabled_source
            type: api_json
            enabled: false
            base_url: https://disabled.com
            search_url: https://disabled.com/api

          - name: remoteok
            type: api_json
            enabled: true
            base_url: https://remoteok.com
            search_url: https://remoteok.com/api
            rate_limit: 10
    """))
    return config


def test_loads_enabled_sources(yaml_config: Path):
    sources = load_sources_from_yaml(yaml_config)
    names = [s.name for s in sources]
    assert "test_api" in names
    assert "test_scraper" in names
    assert "test_rss" in names


def test_skips_disabled_sources(yaml_config: Path):
    sources = load_sources_from_yaml(yaml_config)
    names = [s.name for s in sources]
    assert "disabled_source" not in names


def test_skips_hardcoded_sources(yaml_config: Path):
    sources = load_sources_from_yaml(yaml_config)
    names = [s.name for s in sources]
    assert "remoteok" not in names


def test_correct_types(yaml_config: Path):
    sources = load_sources_from_yaml(yaml_config)
    type_map = {s.name: type(s) for s in sources}
    assert type_map["test_api"] is ApiJsonSource
    assert type_map["test_scraper"] is HtmlScrapeSource
    assert type_map["test_rss"] is RssSource


def test_rate_limits(yaml_config: Path):
    limits = get_rate_limits_from_yaml(yaml_config)
    assert limits["test_api"] == (10, 60.0)
    assert limits["test_scraper"] == (5, 60.0)
    assert limits["test_rss"] == (8, 60.0)


def test_missing_file():
    sources = load_sources_from_yaml("/nonexistent/path.yaml")
    assert sources == []


def test_loads_real_config():
    """Smoke test: the actual config/job_sources.yaml loads without errors."""
    sources = load_sources_from_yaml("config/job_sources.yaml")
    assert len(sources) >= 20  # We added 22+ YAML-driven sources
    names = [s.name for s in sources]
    assert "naukri" in names
    assert "naukrigulf" in names
    assert "arbeitnow" in names
