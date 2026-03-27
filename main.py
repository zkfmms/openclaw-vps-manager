"""OpenClaw VPS Manager - Main Application Entry Point."""
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime, timedelta
import secrets

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import uvicorn

from config import get_settings
from database import init_db
from api import vps, customers, config, audit, deployments
from api import vps_sync
from auth.middleware import verify_mtls
from models import User
from services.exceptions import (
    VPSManagerError,
    AuthenticationError,
    AuthorizationError,
    ValidationError,
    RateLimitError,
    handle_exception,
)
from services.monitoring import (
    get_metrics,
    get_health_status,
    RequestContext,
)
from services.logging import (
    setup_logging,
    get_logger,
    generate_request_id,
    RequestIdFilter,
)

settings = get_settings()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(
        "Starting OpenClaw VPS Manager...",
        database_url=settings.database_url.replace(
            settings.database_url.split("@")[0].split("://")[1],
            "***",
        ) if "@" in settings.database_url else settings.database_url,
        git_repo_path=settings.git_repo_path,
        api_port=settings.api_port,
    )

    # Initialize logging
    setup_logging()

    # Initialize health checks
    health = get_health_status()
    health.set_status("startup", "healthy", "Application starting")

    # Initialize database
    try:
        await init_db()
        health.set_status("database", "healthy", "Database connection established")
        logger.info("Database initialized successfully")
    except Exception as e:
        health.set_status("database", "unhealthy", f"Database connection failed: {str(e)}")
        logger.error("Database initialization failed", exc_info=True)
        raise

    # Initialize SSH pool
    from services.ssh_manager import get_ssh_pool
    try:
        pool = get_ssh_pool()
        health.set_status("ssh_pool", "healthy", "SSH connection pool initialized")
        logger.info("SSH pool initialized")
    except Exception as e:
        health.set_status("ssh_pool", "degraded", f"SSH pool initialization warning: {str(e)}")
        logger.warning("SSH pool initialization warning", exc_info=True)

    # Initialize metrics
    metrics = get_metrics()
    metrics.increment("application_start")

    health.set_status("startup", "healthy", "Application started")
    logger.info("OpenClaw VPS Manager started successfully")

    yield

    # Shutdown
    logger.info("Shutting down OpenClaw VPS Manager...")

    # Close SSH pool
    try:
        await pool.close_all()
        logger.info("SSH pool closed")
    except Exception as e:
        logger.error("Error closing SSH pool", exc_info=True)

    metrics.increment("application_stop")
    logger.info("OpenClaw VPS Manager stopped")


# Rate limiting in-memory store
_rate_limit_store: dict[str, list[float]] = {}


def check_rate_limit(identifier: str) -> bool:
    """
    Check if request is within rate limits.

    Args:
        identifier: Unique identifier for the client (IP or user ID).

    Returns:
        True if request is allowed, False otherwise.
    """
    if not settings.rate_limit_enabled:
        return True

    now = datetime.utcnow().timestamp()
    period = settings.rate_limit_period
    limit = settings.rate_limit_requests

    # Clean old entries
    if identifier in _rate_limit_store:
        _rate_limit_store[identifier] = [
            t for t in _rate_limit_store[identifier]
            if now - t < period
        ]
    else:
        _rate_limit_store[identifier] = []

    # Check if limit exceeded
    if len(_rate_limit_store[identifier]) >= limit:
        return False

    # Add current request
    _rate_limit_store[identifier].append(now)
    return True


def get_client_identifier(request: Request) -> str:
    """
    Get client identifier for rate limiting.

    Args:
        request: FastAPI request object.

    Returns:
        Client identifier string.
    """
    # Try to get user ID from request state (set by auth middleware)
    if hasattr(request.state, "user") and request.state.user:
        return f"user:{request.state.user.id}"

    # Fall back to IP address
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


# Validate password strength
def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password strength.

    Args:
        password: Password to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if len(password) < 12:
        return False, "Password must be at least 12 characters long"

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

    if not (has_upper and has_lower):
        return False, "Password must contain both uppercase and lowercase letters"

    if not has_digit:
        return False, "Password must contain at least one digit"

    if not has_special:
        return False, "Password must contain at least one special character"

    return True, None


# Create FastAPI application
app = FastAPI(
    title="OpenClaw VPS Manager",
    description="Central management server for OpenClaw instances across multiple VPSes",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "X-Request-ID",
        "X-Client-ID",
    ],
)

# Add gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add trusted host middleware for production
if settings.api_host != "0.0.0.0":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[settings.api_host, "*localhost*", "*.local"],
    )


# Request ID and rate limiting middleware
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Request context middleware with rate limiting and request ID tracking."""
    # Generate or extract request ID
    request_id = request.headers.get("X-Request-ID") or generate_request_id()
    RequestIdFilter.set_request_id(request_id)

    # Add request ID to state for use in endpoints
    request.state.request_id = request_id

    # Rate limiting
    identifier = get_client_identifier(request)
    if not check_rate_limit(identifier):
        logger.warning(
            f"Rate limit exceeded for {identifier}",
            identifier=identifier,
            path=request.url.path,
        )
        metrics = get_metrics()
        metrics.increment("rate_limit_exceeded", 1.0, {"identifier": identifier})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "RATE_LIMIT_EXCEEDED",
                "message": f"Rate limit exceeded: {settings.rate_limit_requests} requests per {settings.rate_limit_period} seconds",
                "retry_after": settings.rate_limit_period,
            },
        )

    # Process request
    start_time = datetime.utcnow()

    try:
        response = await call_next(request)
    except Exception as e:
        # Log exception and re-raise
        logger.error(
            f"Request failed: {request.method} {request.url.path}",
            exc_info=True,
            request_id=request_id,
        )
        raise

    # Calculate duration
    duration = (datetime.utcnow() - start_time).total_seconds()

    # Record metrics
    metrics = get_metrics()
    request_context = RequestContext(request_id, request.method, request.url.path)
    request_context.record_completion(response.status_code)

    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id

    RequestIdFilter.clear_request_id()

    return response


# Security headers middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to responses."""
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # Remove server info
    response.headers["Server"] = "OpenClaw-VPS-Manager"

    return response


# mTLS verification middleware
@app.middleware("http")
async def mtls_middleware(request: Request, call_next):
    """mTLS verification middleware."""
    # Skip mTLS verification for health endpoints and docs
    if request.url.path in [
        "/health",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
    ]:
        return await call_next(request)

    try:
        await verify_mtls(request)
    except HTTPException:
        if settings.tls_verify_client:
            raise
        # Continue if mTLS is disabled

    response = await call_next(request)

    return response


# Exception handlers
@app.exception_handler(VPSManagerError)
async def vps_manager_error_handler(request: Request, exc: VPSManagerError):
    """Handle custom VPS Manager exceptions."""
    error_data = exc.to_dict()
    error_data["path"] = request.url.path
    error_data["request_id"] = getattr(request.state, "request_id", None)

    logger.error(
        f"VPS Manager error: {exc.code} - {exc.message}",
        code=exc.code,
        status_code=exc.status_code,
        path=request.url.path,
        details=exc.details,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_data,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    request_id = getattr(request.state, "request_id", None)

    logger.warning(
        f"HTTP exception: {exc.status_code} - {exc.detail}",
        status_code=exc.status_code,
        path=request.url.path,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_ERROR",
            "message": str(exc.detail),
            "status_code": exc.status_code,
            "path": request.url.path,
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        f"Unhandled exception: {type(exc).__name__}",
        exc_info=True,
        path=request.url.path,
        request_id=request_id,
    )

    # Get metrics
    metrics = get_metrics()
    metrics.increment("unhandled_exceptions", 1.0)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "status_code": 500,
            "path": request.url.path,
            "request_id": request_id,
        },
    )


# Health check endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint (liveness probe)."""
    health = get_health_status()
    return {
        "status": health.get_status()["status"],
        "service": "OpenClaw VPS Manager",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health/live")
async def liveness_check():
    """Liveness probe - checks if the application is running."""
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health/ready")
async def readiness_check():
    """Readiness probe - checks if the application is ready to accept traffic."""
    health = get_health_status()
    is_ready = health.is_ready()

    response_data = {
        "status": "ready" if is_ready else "not_ready",
        "checks": health.get_status()["checks"],
        "timestamp": datetime.utcnow().isoformat(),
    }

    if not is_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_data,
        )

    return response_data


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus-compatible metrics endpoint."""
    metrics = get_metrics()
    summaries = metrics.get_all_summaries(since=datetime.utcnow() - timedelta(minutes=5))

    lines = []

    # Format metrics in Prometheus format
    for name, summary in summaries.items():
        lines.append(f"# TYPE {name} summary")
        lines.append(f"{name}_count {summary.count}")
        lines.append(f"{name}_sum {summary.avg * summary.count}")
        lines.append(f"{name}_min {summary.min}")
        lines.append(f"{name}_max {summary.max}")

    return "\n".join(lines)


# API version endpoint
@app.get("/api/v1")
async def api_info():
    """API information endpoint."""
    return {
        "name": "OpenClaw VPS Manager API",
        "version": "1.0.0",
        "description": "Central management API for OpenClaw VPS deployments",
        "endpoints": {
            "vps": "/api/v1/vps",
            "customers": "/api/v1/customers",
            "config": "/api/v1/config",
            "audit": "/api/v1/audit",
            "deployments": "/api/v1/deployments",
        },
        "health": {
            "liveness": "/health/live",
            "readiness": "/health/ready",
            "detailed": "/health",
        },
        "metrics": "/metrics",
    }


# Include API routers
app.include_router(
    vps.router,
    prefix="/api/v1",
)

app.include_router(
    customers.router,
    prefix="/api/v1",
)

app.include_router(
    config.router,
    prefix="/api/v1",
)

app.include_router(
    audit.router,
    prefix="/api/v1",
)

app.include_router(
    deployments.router,
    prefix="/api/v1",
)

app.include_router(
    vps_sync.router,
    prefix="/api/v1",
)


# CLI entry point
def main():
    """Main entry point for running the server."""
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
