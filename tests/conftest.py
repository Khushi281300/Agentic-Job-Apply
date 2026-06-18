"""Pytest configuration."""

import pytest

# Import shared fixtures so they are automatically available in all tests.
from tests.fixtures import (  # noqa: F401
    mock_source_infra,
    mock_remoteok_http,
    mock_remotive_http,
    mock_llm,
    mock_database,
    mock_rag,
)
