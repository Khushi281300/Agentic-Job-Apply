"""Tests for plugin registry."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from job_agent_services.registry import ServiceRegistry
from job_agent_contracts.interfaces import JobSource


class MockJobSource(JobSource):
    @property
    def name(self) -> str:
        return "mock_source"

    async def search(self, title, location, **kwargs):
        return []

    async def fetch_details(self, url):
        return ""


class TestPluginRegistry:
    def setup_method(self):
        """Clear registry between tests."""
        ServiceRegistry._registry = {}

    def test_register_job_source(self):
        ServiceRegistry.register("job_source", "mock_source", MockJobSource)
        assert ServiceRegistry.get("job_source", "mock_source") is MockJobSource

    def test_get_nonexistent_source(self):
        with pytest.raises(KeyError):
            ServiceRegistry.get("job_source", "nope")

    def test_list_sources(self):
        ServiceRegistry.register("job_source", "mock_source", MockJobSource)
        assert "mock_source" in ServiceRegistry.list_category("job_source")

    def test_register_multiple_sources(self):
        class AnotherSource(JobSource):
            @property
            def name(self):
                return "another"
            async def search(self, title, location, **kwargs):
                return []
            async def fetch_details(self, url):
                return ""

        ServiceRegistry.register("job_source", "mock_source", MockJobSource)
        ServiceRegistry.register("job_source", "another", AnotherSource)
        assert len(ServiceRegistry.list_category("job_source")) == 2
