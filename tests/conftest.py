"""Pytest configuration for VPS Manager tests."""
import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# Fixtures for pytest
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    import unittest.mock as mock
    from config import get_settings

    with mock.patch("config.get_settings") as mock_get:
        settings = mock_get.return_value
        settings.database_url = "postgresql+asyncpg://test:test@localhost/test_db"
        settings.git_repo_path = "/tmp/test_repo"
        settings.ssh_keys_path = "/tmp/test_keys"
        settings.encryption_key_path = "/tmp/test_key"
        settings.jwt_secret = "test_secret"
        settings.jwt_algorithm = "HS256"
        settings.jwt_expiration_hours = 24
        settings.api_host = "127.0.0.1"
        settings.api_port = 8000
        settings.cors_origins = ["http://localhost"]
        settings.log_level = "INFO"
        settings.log_format = "json"
        settings.rate_limit_enabled = True
        settings.rate_limit_requests = 100
        settings.rate_limit_period = 60
        yield settings


# Async client fixture for HTTP tests
@pytest.fixture
async def http_client():
    """Create async HTTP client for testing."""
    import httpx
    from main import app

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client


# Mark tests
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_marker(
        "unit",
        "Unit tests"
    )
    config.addinivalue_marker(
        "integration",
        "Integration tests"
    )
    config.addinivalue_marker(
        "slow",
        "Slow tests that run slowly"
    )
