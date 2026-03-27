"""Structured logging service with JSON support and request ID tracking."""
import json
import logging
import logging.handlers
import os
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from config import get_settings

settings = get_settings()


class RequestIdFilter(logging.Filter):
    """Logging filter to add request ID to log records."""

    _local = threading.local()

    @classmethod
    def set_request_id(cls, request_id: str) -> None:
        """
        Set the current request ID.

        Args:
            request_id: Request ID to set.
        """
        cls._local.request_id = request_id

    @classmethod
    def get_request_id(cls) -> Optional[str]:
        """Get the current request ID."""
        return getattr(cls._local, "request_id", None)

    @classmethod
    def clear_request_id(cls) -> None:
        """Clear the current request ID."""
        cls._local.request_id = None

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request ID to log record."""
        record.request_id = self.get_request_id()
        return True


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def __init__(self, service_name: str = "openclaw-vps-manager"):
        """
        Initialize JSON formatter.

        Args:
            service_name: Name of the service.
        """
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record to format.

        Returns:
            JSON formatted log entry.
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "service": self.service_name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request ID if available
        if hasattr(record, "request_id") and record.request_id:
            log_data["request_id"] = record.request_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
            }

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "stack_info",
                "request_id",
            }:
                log_data[key] = value

        return json.dumps(log_data, default=str)


class StructuredLogger:
    """Structured logger with context support."""

    def __init__(self, name: str):
        """
        Initialize structured logger.

        Args:
            name: Logger name.
        """
        self._logger = logging.getLogger(name)
        self._context: Dict[str, Any] = {}

    def with_context(self, **kwargs: Any) -> "StructuredLogger":
        """
        Create a new logger with additional context.

        Args:
            **kwargs: Context key-value pairs.

        Returns:
            New logger with context.
        """
        new_logger = StructuredLogger(self._logger.name)
        new_logger._context = {**self._context, **kwargs}
        return new_logger

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        """
        Log a message with context.

        Args:
            level: Log level.
            msg: Log message.
            **kwargs: Additional context.
        """
        extra = {**self._context, **kwargs}
        self._logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log info message."""
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log warning message."""
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log error message."""
        self._log(logging.ERROR, msg, exc_info=exc_info, **kwargs)

    def critical(self, msg: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, msg, exc_info=exc_info, **kwargs)


def setup_logging(
    level: Optional[str] = None,
    log_format: str = "json",
    log_file: Optional[str] = None,
    log_dir: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Set up structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_format: Log format (json or text).
        log_file: Optional log file path.
        log_dir: Directory for log files (if log_file not specified).
        max_bytes: Maximum size of log file before rotation.
        backup_count: Number of backup log files to keep.

    Returns:
        Root logger instance.
    """
    # Use configured settings if not specified
    if level is None:
        level = settings.log_level
    if log_format is None:
        log_format = settings.log_format

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create request ID filter
    request_id_filter = RequestIdFilter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.addFilter(request_id_filter)

    if log_format == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s"
            )
        )

    root_logger.addHandler(console_handler)

    # File handler with rotation if specified
    if log_file or log_dir:
        log_path = Path(log_file) if log_file else Path(log_dir) / "vps-manager.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(level)
        file_handler.addFilter(request_id_filter)

        if log_format == "json":
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s"
                )
            )

        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger.

    Args:
        name: Logger name (typically __name__).

    Returns:
        StructuredLogger instance.
    """
    return StructuredLogger(name)


def generate_request_id() -> str:
    """
    Generate a unique request ID.

    Returns:
        Request ID string.
    """
    return str(uuid.uuid4())


class LoggingMiddleware:
    """Middleware to add request ID to logs and log HTTP requests."""

    def __init__(self, app):
        """
        Initialize logging middleware.

        Args:
            app: FastAPI application.
        """
        self.app = app
        self.logger = get_logger("http")

    async def __call__(self, scope, receive, send):
        """Process request and log."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Generate request ID
        request_id = generate_request_id()
        RequestIdFilter.set_request_id(request_id)

        # Extract request info
        method = scope["method"]
        path = scope["path"]
        query_string = scope.get("query_string", b"").decode()
        full_path = f"{path}?{query_string}" if query_string else path

        # Log request start
        self.logger.info(
            f"{method} {full_path}",
            method=method,
            path=path,
            request_id=request_id,
        )

        # Capture response status
        start_time = datetime.utcnow()
        status_code = 500  # Default to error

        async def send_wrapper(message):
            """Wrapper to capture response status."""
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            self.logger.error(
                f"Request failed: {str(e)}",
                exc_info=True,
                method=method,
                path=path,
                status_code=500,
            )
            raise
        finally:
            # Log request completion
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.logger.info(
                f"{method} {full_path} - {status_code}",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration * 1000,
            )
            RequestIdFilter.clear_request_id()


def log_audit_event(
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    user_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    vps_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Log an audit event.

    Args:
        action: Action performed (create, update, delete, etc.).
        resource_type: Type of resource (customer, vps, etc.).
        resource_id: ID of the resource.
        user_id: ID of the user performing the action.
        customer_id: Customer ID (if applicable).
        vps_id: VPS ID (if applicable).
        details: Additional event details.
        ip_address: IP address of the request.
    """
    logger = get_logger("audit")
    audit_data = {
        "action": action,
        "resource_type": resource_type,
    }

    if resource_id is not None:
        audit_data["resource_id"] = resource_id
    if user_id is not None:
        audit_data["user_id"] = user_id
    if customer_id is not None:
        audit_data["customer_id"] = customer_id
    if vps_id is not None:
        audit_data["vps_id"] = vps_id
    if details is not None:
        audit_data["details"] = details
    if ip_address is not None:
        audit_data["ip_address"] = ip_address

    logger.info(f"Audit event: {action} {resource_type}", **audit_data)
