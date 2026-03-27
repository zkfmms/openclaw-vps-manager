"""Configuration management for VPS Manager."""
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = Field(
        default="postgresql://openclaw:password@localhost:5432/openclaw_vps_manager",
        description="PostgreSQL connection URL"
    )

    # Git Repository
    git_repo_path: str = Field(
        default="/var/git/openclaw-configs",
        description="Local path to Git repository"
    )
    git_repo_url: Optional[str] = Field(
        default=None,
        description="Remote Git repository URL"
    )

    # SSH Keys
    ssh_keys_path: str = Field(
        default="/var/ssh/keys",
        description="Directory to store SSH keys"
    )
    ssh_key_type: str = Field(
        default="ed25519",
        description="SSH key type (ed25519 or rsa)"
    )
    ssh_key_passphrase: str = Field(
        default="",
        description="Optional passphrase for SSH keys"
    )

    # Encryption
    encryption_key_path: str = Field(
        default="/var/keys/encryption",
        description="Path to encryption key file"
    )
    encryption_algorithm: str = Field(
        default="AES-256-GCM",
        description="Encryption algorithm to use"
    )

    # JWT
    jwt_secret: str = Field(
        default="change-this-in-production",
        description="Secret for JWT token signing"
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT algorithm"
    )
    jwt_expiration_hours: int = Field(
        default=24,
        description="JWT token expiration in hours"
    )

    # mTLS
    tls_cert_path: str = Field(
        default="/var/tls/cert.pem",
        description="Path to TLS certificate"
    )
    tls_key_path: str = Field(
        default="/var/tls/key.pem",
        description="Path to TLS private key"
    )
    tls_ca_cert_path: str = Field(
        default="/var/tls/ca.pem",
        description="Path to CA certificate"
    )
    tls_verify_client: bool = Field(
        default=True,
        description="Whether to verify client certificates"
    )

    # OpenClaw
    openclaw_default_version: str = Field(
        default="latest",
        description="Default OpenClaw version to install"
    )
    openclaw_install_path: str = Field(
        default="/usr/local/bin/openclaw",
        description="Path where OpenClaw is installed"
    )
    openclaw_config_path: str = Field(
        default="~/.openclaw/openclaw.json",
        description="Path to OpenClaw config file"
    )
    openclaw_port: int = Field(
        default=18789,
        description="OpenClaw Gateway port"
    )

    # API
    api_host: str = Field(
        default="0.0.0.0",
        description="API server host"
    )
    api_port: int = Field(
        default=8000,
        description="API server port"
    )
    api_prefix: str = Field(
        default="/api/v1",
        description="API URL prefix"
    )

    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    log_format: str = Field(
        default="json",
        description="Log format (json or text)"
    )

    # Rate Limiting
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting"
    )
    rate_limit_requests: int = Field(
        default=100,
        description="Number of requests per period"
    )
    rate_limit_period: int = Field(
        default=60,
        description="Rate limit period in seconds"
    )

    @field_validator("ssh_key_type")
    @classmethod
    def validate_ssh_key_type(cls, v: str) -> str:
        """Validate SSH key type."""
        if v not in ("ed25519", "rsa"):
            raise ValueError("SSH key type must be 'ed25519' or 'rsa'")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()

    def get_ssh_key_path(self, vps_id: int) -> Path:
        """Get the path to SSH key for a specific VPS."""
        return Path(self.ssh_keys_path) / f"vps_{vps_id}_key"

    def get_customer_branch(self, customer_id: int) -> str:
        """Get the Git branch name for a customer."""
        return f"customer-{customer_id}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
