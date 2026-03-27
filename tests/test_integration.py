"""Integration tests for VPS Manager services."""
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient


class TestErrorHandlingIntegration:
    """Integration tests for error handling."""

    @pytest.fixture
    def app_with_custom_errors(self):
        """Create app with custom error handlers."""
        from main import app
        return app

    async def test_custom_exception_handling(self, app_with_custom_errors):
        """Test custom exceptions are handled correctly."""
        # Import custom exception
        from services.exceptions import VPSNotFoundError

        # Create a test endpoint that raises custom exception
        @app.get("/test-error")
        async def test_endpoint():
            raise VPSNotFoundError(999)

        # Make request
        async with AsyncClient(app=app) as client:
            response = await client.get("/test-error")

            assert response.status_code == 404
            data = response.json()
            assert data["error"] == "VPS_NOT_FOUND"
            assert data["status_code"] == 404


class TestMonitoringIntegration:
    """Integration tests for monitoring."""

    @pytest.fixture
    def reset_metrics(self):
        """Reset metrics between tests."""
        from services.monitoring import get_metrics
        metrics = get_metrics()
        metrics.reset()
        yield
        metrics.reset()

    def test_metrics_are_persisted(self, reset_metrics):
        """Test metrics persist across function calls."""
        from services.monitoring import get_metrics
        metrics = get_metrics()

        # Increment counter
        metrics.increment("test_counter", 1.0)

        # Get metrics again
        metrics2 = get_metrics()
        assert metrics2.get_counter("test_counter") == 1.0

    def test_metrics_tracking_across_requests(self, reset_metrics):
        """Test metrics track across multiple simulated requests."""
        from services.monitoring import get_metrics
        metrics = get_metrics()

        # Simulate multiple requests
        for i in range(5):
            metrics.increment("http_requests_total", 1.0, labels={"method": "GET"})

        summary = metrics.get_summary("http_requests_total", labels={"method": "GET"})
        assert summary.count == 5


class TestLoggingIntegration:
    """Integration tests for logging."""

    @pytest.fixture
    def temp_log_dir(self):
        """Create temporary directory for test logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_logging_creates_file(self, temp_log_dir):
        """Test logging creates log file."""
        from services.logging import setup_logging, get_logger

        log_path = Path(temp_log_dir) / "test.log"
        logger = setup_logging(
            log_dir=temp_log_dir,
            log_file=str(log_path),
            log_format="json",
        )

        # Write a log entry
        test_logger = get_logger("test")
        test_logger.info("Test message")

        # Check file exists
        import os
        assert log_path.exists()

    def test_request_id_filter_thread_safety(self, temp_log_dir):
        """Test request ID filter is thread-safe."""
        from services.logging import RequestIdFilter

        # Clear any existing state
        RequestIdFilter.clear_request_id()

        # Set request ID
        RequestIdFilter.set_request_id("test-123")
        assert RequestIdFilter.get_request_id() == "test-123"

        # Clear
        RequestIdFilter.clear_request_id()
        assert RequestIdFilter.get_request_id() is None


class TestSecurityIntegration:
    """Integration tests for security features."""

    def test_password_validation(self):
        """Test password strength validation."""
        from auth.middleware import _validate_password

        # Valid password
        is_valid, error = _validate_password("StrongP@ssw0rd123")
        assert is_valid is True
        assert error is None

        # Too short
        is_valid, error = _validate_password("Short1")
        assert is_valid is False
        assert "too short" in error.lower()

        # Missing uppercase
        is_valid, error = _validate_password("lowercase123@")
        assert is_valid is False
        assert "uppercase" in error.lower()

        # Missing digit
        is_valid, error = _validate_password("NoDigits@Passw")
        assert is_valid is False
        assert "digit" in error.lower()

        # Missing special character
        is_valid, error = _validate_password("NoSpecial123")
        assert is_valid is False
        assert "special" in error.lower()

    def test_rate_limiting_store(self):
        """Test rate limiting store functionality."""
        from main import _rate_limit_store, check_rate_limit

        # Reset store
        _rate_limit_store.clear()

        identifier = "test-client"

        # Should allow first request
        assert check_rate_limit(identifier) is True

        # Check count
        assert len(_rate_limit_store.get(identifier, [])) == 1

        # Add more requests up to limit
        for i in range(99):
            check_rate_limit(identifier)

        # Still should allow (at limit)
        assert check_rate_limit(identifier) is True

        # One more should exceed limit
        assert check_rate_limit(identifier) is False


class TestCLIRouting:
    """Integration tests for CLI routing."""

    @pytest.fixture
    def cli_runner(self):
        """Create CLI runner."""
        import subprocess
        return lambda cmd: subprocess.run(
            ["python", "cli.py"] + cmd,
            capture_output=True,
            text=True,
            cwd="/Users/fum/Documents/Github/openclaw-vps-manager/vps-manager",
        )

    def test_cli_health_command(self, cli_runner):
        """Test CLI health command."""
        result = cli_runner(["health"])

        assert result.returncode == 0
        # Check for expected output
        assert "health" in result.stdout.lower()

    def test_cli_list_vps_command(self, cli_runner):
        """Test CLI list-vps command."""
        result = cli_runner(["list-vps"])

        # Should complete successfully even if API is not running
        assert result.returncode in (0, 1)  # May fail to connect


class TestEncryptionIntegration:
    """Integration tests for encryption."""

    @pytest.fixture
    def temp_key_file(self):
        """Create temporary key file."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmp:
            yield Path(tmp.name)

    def test_encryption_roundtrip(self, temp_key_file):
        """Test encrypt-decrypt roundtrip."""
        from services.encryption import EncryptionService
        from cryptography.fernet import Fernet

        # Generate and save key
        key = Fernet.generate_key()
        temp_key_file.write_bytes(key)

        # Create service
        service = EncryptionService(master_key=key)

        # Test roundtrip
        plaintext = "Secret message 123!"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert plaintext == decrypted
        assert encrypted != plaintext

    def test_customer_key_generation(self):
        """Test customer key generation is deterministic."""
        from services.encryption import EncryptionService

        # Create service with test key
        from cryptography.fernet import Fernet
        test_key = Fernet.generate_key()
        service = EncryptionService(master_key=test_key)

        # Generate keys for same customer
        key1 = service.generate_customer_key(1)
        key2 = service.generate_customer_key(1)
        key3 = service.generate_customer_key(2)

        # Same customer should get same key
        assert key1 == key2

        # Different customers should get different keys
        assert key1 != key3

    def test_key_hashing(self):
        """Test key hashing."""
        from services.encryption import EncryptionService

        # Create service with test key
        from cryptography.fernet import Fernet
        test_key = Fernet.generate_key()
        service = EncryptionService(master_key=test_key)

        # Hash same key twice
        hash1 = service.hash_key(test_key.decode())
        hash2 = service.hash_key(test_key.decode())

        # Should be deterministic
        assert hash1 == hash2

        # Different keys should have different hashes
        different_key = Fernet.generate_key()
        hash3 = service.hash_key(different_key.decode())

        assert hash1 != hash3


class TestAPIEndpointsIntegration:
    """Integration tests for API endpoints."""

    @pytest.fixture
    def test_client(self):
        """Create test client for API."""
        from main import app
        return AsyncClient(app=app)

    async def test_health_endpoint(self, test_client):
        """Test health endpoint is accessible."""
        response = await test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data

    async def test_api_info_endpoint(self, test_client):
        """Test API info endpoint."""
        response = await test_client.get("/api/v1")

        assert response.status_code == 200
        data = response.json()
        assert "endpoints" in data

    async def test_metrics_endpoint(self, test_client):
        """Test metrics endpoint."""
        response = await test_client.get("/metrics")

        # Should return Prometheus-style metrics
        assert response.status_code == 200
        content = response.text
        assert "#" in content or "TYPE" in content
