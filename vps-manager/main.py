"""OpenClaw VPS Manager - Main Application Entry Point."""
from contextlib import asynccontextmanager
from typing import List
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from config import get_settings
from database import init_db
from api import vps, customers, config, audit, deployments
from auth.middleware import verify_mtls
from models import User

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("Starting OpenClaw VPS Manager...")
    print(f"Database URL: {settings.database_url}")
    print(f"Git Repository: {settings.git_repo_path}")
    print(f"API listening on {settings.api_host}:{settings.api_port}")

    # Initialize database
    await init_db()

    yield

    # Shutdown
    print("Shutting down OpenClaw VPS Manager...")
    # Close SSH pool
    from services.ssh_manager import get_ssh_pool
    pool = get_ssh_pool()
    await pool.close_all()


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
    allow_methods=["*"],
    allow_headers=["*"],
)


# mTLS verification middleware
@app.middleware("http")
async def mtls_middleware(request: Request, call_next):
    """mTLS verification middleware."""
    # Skip mTLS verification for health endpoint and docs
    if request.url.path in ["/health", "/docs", "/openapi.json", "/redoc"]:
        return await call_next(request)

    try:
        await verify_mtls(request)
    except HTTPException:
        if settings.tls_verify_client:
            raise
        # Continue if mTLS is disabled

    response = await call_next(request)

    # Add security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    return response


# Logging middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Request logging middleware."""
    start_time = datetime.utcnow()

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration = (datetime.utcnow() - start_time).total_seconds()

    # Log request
    print(f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s")

    return response


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": request.url.path,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler."""
    print(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "path": request.url.path,
        },
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "OpenClaw VPS Manager",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


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
