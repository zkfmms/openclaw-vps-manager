"""CLI configuration management."""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console

console = Console()


class CLIConfig:
    """Configuration management for CLI."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize CLI configuration.

        Args:
            config_path: Optional path to config file.
        """
        if config_path:
            self.config_path = config_path
        else:
            self.config_dir = Path.home() / ".vps-manager"
            self.config_path = self.config_dir / "config.yml"

        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    self._config = yaml.safe_load(f) or {}
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to load config: {e}[/yellow]")
                self._config = {}
        else:
            self._config = {}

    def _save_config(self) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.

        Args:
            key: Configuration key (supports dot notation).
            default: Default value if key not found.

        Returns:
            Configuration value.
        """
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

        return value if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value.

        Args:
            key: Configuration key (supports dot notation).
            value: Value to set.
        """
        keys = key.split(".")
        config = self._config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value
        self._save_config()

    def get_api_url(self) -> str:
        """
        Get API URL from config or environment.

        Returns:
            API URL string.
        """
        return os.getenv("VPS_MANAGER_API_URL") or self.get("api_url", "http://localhost:8000")

    def set_api_url(self, url: str) -> None:
        """
        Set API URL.

        Args:
            url: API URL to set.
        """
        self.set("api_url", url)

    def get_token(self) -> Optional[str]:
        """
        Get authentication token from config or environment.

        Returns:
            Token string or None.
        """
        return os.getenv("VPS_MANAGER_TOKEN") or self.get("token")

    def set_token(self, token: str) -> None:
        """
        Set authentication token.

        Args:
            token: Token to set.
        """
        self.set("token", token)

    def get_output_format(self) -> str:
        """
        Get output format.

        Returns:
            Output format (table, json, yaml).
        """
        return self.get("output_format", "table")

    def set_output_format(self, format: str) -> None:
        """
        Set output format.

        Args:
            format: Output format to set.
        """
        if format not in ("table", "json", "yaml"):
            raise ValueError("Format must be one of: table, json, yaml")
        self.set("output_format", format)

    def get_timeout(self) -> int:
        """
        Get request timeout.

        Returns:
            Timeout in seconds.
        """
        return self.get("timeout", 30)

    def set_timeout(self, timeout: int) -> None:
        """
        Set request timeout.

        Args:
            timeout: Timeout in seconds.
        """
        self.set("timeout", timeout)

    def get_verify_ssl(self) -> bool:
        """
        Get SSL verification setting.

        Returns:
            Whether to verify SSL.
        """
        return self.get("verify_ssl", True)

    def set_verify_ssl(self, verify: bool) -> None:
        """
        Set SSL verification.

        Args:
            verify: Whether to verify SSL.
        """
        self.set("verify_ssl", verify)

    def get_default_customer_id(self) -> Optional[int]:
        """
        Get default customer ID.

        Returns:
            Default customer ID or None.
        """
        return self.get("default_customer_id")

    def set_default_customer_id(self, customer_id: int) -> None:
        """
        Set default customer ID.

        Args:
            customer_id: Default customer ID to set.
        """
        self.set("default_customer_id", customer_id)

    def get_all(self) -> Dict[str, Any]:
        """
        Get all configuration.

        Returns:
            All configuration as dictionary.
        """
        return self._config.copy()

    def reset(self) -> None:
        """Reset configuration to defaults."""
        self._config = {}
        if self.config_path.exists():
            self.config_path.unlink()
        console.print("[yellow]Configuration reset[/yellow]")

    def init(self, api_url: str, token: str) -> None:
        """
        Initialize configuration with basic settings.

        Args:
            api_url: API URL.
            token: Authentication token.
        """
        self._config = {
            "api_url": api_url,
            "token": token,
            "output_format": "table",
            "timeout": 30,
            "verify_ssl": True,
        }
        self._save_config()
        console.print("[green]Configuration initialized[/green]")

    def show(self) -> None:
        """Display current configuration."""
        config = self.get_all()

        # Hide sensitive data
        display_config = config.copy()
        if "token" in display_config:
            token = display_config["token"]
            if token:
                display_config["token"] = f"{token[:8]}...{token[-4:]}" if len(token) > 12 else "***"

        import json
        console.print_json(json.dumps(display_config, indent=2))


# Global config instance
_config: Optional[CLIConfig] = None


def get_config() -> CLIConfig:
    """Get or create global CLI configuration."""
    global _config
    if _config is None:
        _config = CLIConfig()
    return _config
