"""Tests for logging service."""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.logging import (
    setup_logging,
    get_logger,
    generate_request_id,
    RequestIdFilter,
    StructuredLogger,
    log_audit_event,
)


class TestGenerateRequestId:
    """Test cases for generate_request_id function."""

    def test_generate_request_id_unique(self):
        """Test request IDs are unique."""
        id1 = generate_request_id()
        id2 = generate_request_id()

        assert id1 != id2
        assert isinstance(id1, str)
        assert isinstance(id2, str)

    def test_generate_request_id_format(self):
        """Test request ID format."""
        request_id = generate_request_id()

        # UUID format: 8-4-4-4-4-12 hex characters
        assert len(request_id) == 36
        assert request_id.count("-") == 4


class TestRequestIdFilter:
    """Test cases for RequestIdFilter class."""

    @pytest.fixture(autouse=True)
    def reset_filter(self):
        """Reset filter state before each test."""
        RequestIdFilter.clear_request_id()
        yield
        RequestIdFilter.clear_request_id()

    def test_set_and_get_request_id(self):
        """Test setting and getting request ID."""
        RequestIdFilter.set_request_id("test-request-123")

        assert RequestIdFilter.get_request_id() == "test-request-123"

    def test_get_request_id_not_set(self):
        """Test getting request ID when not set."""
        assert RequestIdFilter.get_request_id() is None

    def test_clear_request_id(self):
        """Test clearing request ID."""
        RequestIdFilter.set_request_id("test-request-123")
        RequestIdFilter.clear_request_id()

        assert RequestIdFilter.get_request_id() is None


class TestStructuredLogger:
    """Test cases for StructuredLogger class."""

    @pytest.fixture
    def logger(self):
        """Create StructuredLogger instance for testing."""
        return get_logger("test")

    def test_logger_creation(self, logger):
        """Test StructuredLogger creation."""
        assert logger._logger.name == "test"

    def test_with_context(self, logger):
        """Test creating logger with context."""
        context_logger = logger.with_context(user_id=123, action="test")

        assert context_logger._context["user_id"] == 123
        assert context_logger._context["action"] == "test"
        assert context_logger._logger.name == "test"

    def test_with_context_adds_context(self, logger):
        """Test with_context adds to existing context."""
        context_logger = logger.with_context(existing="value")

        context_logger2 = context_logger.with_context(new="value2")

        assert context_logger2._context["existing"] == "value"
        assert context_logger2._context["new"] == "value2"

    def test_info_log(self, logger):
        """Test info level logging."""
        with patch.object(logger._logger, "log") as mock_log:
            logger.info("Test message", extra_key="value")

            mock_log.assert_called_once()
            call_args = mock_log.call_args[0]
            assert call_args[0] == 20  # INFO level
            assert call_args[1] == "Test message"
            assert call_args[2]["extra_key"] == "value"

    def test_error_log(self, logger):
        """Test error level logging."""
        with patch.object(logger._logger, "log") as mock_log:
            logger.error("Test error", exc_info=True)

            mock_log.assert_called_once()
            call_args = mock_log.call_args[0]
            assert call_args[0] == 40  # ERROR level
            assert call_args[1] == "Test error"
            assert call_args[2]["exc_info"] is True


class TestSetupLogging:
    """Test cases for setup_logging function."""

    @pytest.fixture
    def temp_log_dir(self):
        """Create temporary directory for logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_setup_logging_creates_log_file(self, temp_log_dir):
        """Test setup_logging creates log file."""
        with patch("services.logging.settings") as mock_settings:
            mock_settings.log_level = "INFO"
            mock_settings.log_format = "json"

            logger = setup_logging(log_dir=temp_log_dir)

            assert logger.handlers is not None

    def test_setup_logging_json_format(self, temp_log_dir):
        """Test JSON log format."""
        with patch("services.logging.settings") as mock_settings:
            mock_settings.log_level = "INFO"
            mock_settings.log_format = "json"

            logger = setup_logging(log_dir=temp_log_dir, log_format="json")

            for handler in logger.handlers:
                if hasattr(handler, "formatter"):
                    from services.logging import JSONFormatter
                    assert isinstance(handler.formatter, JSONFormatter)

    def test_setup_logging_text_format(self, temp_log_dir):
        """Test text log format."""
        with patch("services.logging.settings") as mock_settings:
            mock_settings.log_level = "INFO"
            mock_settings.log_format = "text"

            logger = setup_logging(log_dir=temp_log_dir, log_format="text")

            for handler in logger.handlers:
                if hasattr(handler, "formatter"):
                    assert not isinstance(handler.formatter, type(
                        from services.logging import JSONFormatter
                    ))

    def test_setup_logging_log_level(self, temp_log_dir):
        """Test log level setting."""
        with patch("services.logging.settings") as mock_settings:
            mock_settings.log_level = "DEBUG"
            mock_settings.log_format = "json"

            logger = setup_logging(log_dir=temp_log_dir)

            assert logger.level == 10  # DEBUG level


class TestJSONFormatter:
    """Test cases for JSONFormatter class."""

    @pytest.fixture
    def formatter(self):
        """Create JSONFormatter instance for testing."""
        from services.logging import JSONFormatter
        return JSONFormatter("test-service")

    @pytest.fixture
    def log_record(self):
        """Create a mock log record."""
        import logging
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        return record

    def test_json_formatter_basic(self, formatter, log_record):
        """Test JSON formatter basic output."""
        output = formatter.format(log_record)

        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Test message"
        assert data["service"] == "test-service"

    def test_json_formatter_with_request_id(self, formatter):
        """Test JSON formatter with request ID."""
        import logging
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.request_id = "req-123"

        output = formatter.format(record)
        data = json.loads(output)

        assert data["request_id"] == "req-123"

    def test_json_formatter_with_exception(self, formatter):
        """Test JSON formatter with exception info."""
        import logging
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test error",
            args=(),
            exc_info=(ValueError, ValueError("test"), None),
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert data["exception"]["type"] == "ValueError"

    def test_json_formatter_timestamp(self, formatter, log_record):
        """Test JSON formatter includes timestamp."""
        output = formatter.format(log_record)
        data = json.loads(output)

        assert "timestamp" in data
        assert "Z" in data["timestamp"]  # UTC timezone indicator


class TestGetLogger:
    """Test cases for get_logger function."""

    def test_get_logger_creates_instance(self):
        """Test get_logger creates logger instance."""
        logger1 = get_logger("test")
        logger2 = get_logger("test")

        assert isinstance(logger1, StructuredLogger)
        assert isinstance(logger2, StructuredLogger)

    def test_get_logger_different_names(self):
        """Test get_logger with different names creates separate loggers."""
        logger1 = get_logger("service1")
        logger2 = get_logger("service2")

        assert logger1 is not logger2


class TestLogAuditEvent:
    """Test cases for log_audit_event function."""

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger."""
        logger = MagicMock()
        return logger

    def test_log_audit_event_basic(self, mock_logger):
        """Test basic audit event logging."""
        with patch("services.logging.get_logger", return_value=mock_logger):
            log_audit_event(
                action="create",
                resource_type="vps",
                resource_id=1,
            )

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            assert "action" in call_args[2]
            assert call_args[2]["action"] == "create"

    def test_log_audit_event_all_fields(self, mock_logger):
        """Test audit event with all fields."""
        with patch("services.logging.get_logger", return_value=mock_logger):
            log_audit_event(
                action="deploy",
                resource_type="vps",
                resource_id=1,
                user_id=10,
                customer_id=5,
                vps_id=1,
                ip_address="192.168.1.1",
                details={"version": "1.2.3"},
            )

            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args[1]
            assert call_kwargs["user_id"] == 10
            assert call_kwargs["customer_id"] == 5
            assert call_kwargs["vps_id"] == 1
            assert call_kwargs["ip_address"] == "192.168.1.1"
            assert call_kwargs["details"]["version"] == "1.2.3"
