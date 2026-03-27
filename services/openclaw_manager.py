"""OpenClaw orchestration service."""
import json
import os
from pathlib import Path
from typing import Dict, Optional, Any

from config import get_settings
from services.ssh_manager import get_ssh_pool, SSHResult
from services.git_manager import get_git_manager
from services.encryption import get_encryption_service

settings = get_settings()


class OpenClawManager:
    """Service for managing OpenClaw deployments."""

    def __init__(self):
        """Initialize OpenClaw manager."""
        self.ssh_pool = get_ssh_pool()
        self.git_manager = get_git_manager()
        self.encryption = get_encryption_service()

    async def install_openclaw(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        version: str = "latest",
        port: int = 22,
    ) -> SSHResult:
        """
        Install OpenClaw on a remote VPS.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            version: OpenClaw version to install.
            port: SSH port.

        Returns:
            SSHResult with installation output.
        """
        commands = [
            # Check if Node.js is installed
            "if ! command -v node &> /dev/null; then",
            "  echo 'Installing Node.js...'",
            "  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -",
            "  sudo apt-get install -y nodejs",
            "fi",

            # Install OpenClaw via npm
            f"sudo npm install -g openclaw@{version} || sudo npm install -g openclaw@{version} --unsafe-perm",

            # Create OpenClaw directory structure
            "mkdir -p ~/.openclaw/{workspace,skills,credentials}",

            # Verify installation
            "openclaw --version || echo 'openclaw command not found'",

            # Create systemd service directory
            "sudo mkdir -p /etc/systemd/system",

            "echo 'OpenClaw installation completed'"
        ]

        command = " && ".join(commands)
        return await self.ssh_pool.execute(hostname, username, key_path, command, timeout=600, port=port)

    async def setup_openclaw_service(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        config: Dict[str, Any],
        port: int = 22,
    ) -> SSHResult:
        """
        Set up OpenClaw as a systemd service on remote VPS.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            config: OpenClaw configuration.
            port: SSH port.

        Returns:
            SSHResult with setup output.
        """
        config_json = json.dumps(config, indent=2)
        config_json_escaped = config_json.replace('"', '\\"').replace('\n', '\\n')

        commands = [
            # Write configuration
            f"cat > ~/.openclaw/openclaw.json << 'EOF'\n{json.dumps(config, indent=2)}\nEOF",

            # Create systemd service file
            f"""cat > /tmp/openclaw.service << 'EOF'
[Unit]
Description=OpenClaw Gateway
After=network.target

[Service]
Type=simple
User={username}
WorkingDirectory=/home/{username}/.openclaw
Environment="NODE_ENV=production"
ExecStart=/usr/local/bin/openclaw gateway start --config ~/.openclaw/openclaw.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
""",

            # Install systemd service
            "sudo mv /tmp/openclaw.service /etc/systemd/system/openclaw.service",
            "sudo systemctl daemon-reload",
            "sudo systemctl enable openclaw.service",

            # Start the service
            "sudo systemctl start openclaw.service",
            "sleep 3",
            "sudo systemctl status openclaw.service || echo 'Service may be starting...'",
        ]

        command = " && ".join(commands)
        return await self.ssh_pool.execute(hostname, username, key_path, command, timeout=300, port=port)

    async def sync_config(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        customer_id: int,
        port: int = 22,
    ) -> SSHResult:
        """
        Synchronize configuration from Git to remote VPS.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            customer_id: Customer ID.
            port: SSH port.

        Returns:
            SSHResult with sync output.
        """
        config = self.git_manager.get_customer_config(customer_id)

        return await self.setup_openclaw_service(hostname, username, key_path, config, port)

    async def restart_service(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        port: int = 22,
    ) -> SSHResult:
        """
        Restart OpenClaw service on remote VPS.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            port: SSH port.

        Returns:
            SSHResult with restart output.
        """
        commands = [
            "sudo systemctl restart openclaw.service",
            "sleep 3",
            "sudo systemctl status openclaw.service || echo 'Service may be starting...'",
        ]

        command = " && ".join(commands)
        return await self.ssh_pool.execute(hostname, username, key_path, command, timeout=60, port=port)

    async def stop_service(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        port: int = 22,
    ) -> SSHResult:
        """
        Stop OpenClaw service on remote VPS.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            port: SSH port.

        Returns:
            SSHResult with stop output.
        """
        command = "sudo systemctl stop openclaw.service"
        return await self.ssh_pool.execute(hostname, username, key_path, command, timeout=30, port=port)

    async def start_service(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        port: int = 22,
    ) -> SSHResult:
        """
        Start OpenClaw service on remote VPS.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            port: SSH port.

        Returns:
            SSHResult with start output.
        """
        commands = [
            "sudo systemctl start openclaw.service",
            "sleep 3",
            "sudo systemctl status openclaw.service || echo 'Service may be starting...'",
        ]

        command = " && ".join(commands)
        return await self.ssh_pool.execute(hostname, username, key_path, command, timeout=60, port=port)

    async def health_check(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        port: int = 22,
    ) -> Dict[str, Any]:
        """
        Perform health check on remote OpenClaw instance.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            port: SSH port.

        Returns:
            Health check result dictionary.
        """
        # Check service status
        status_result = await self.ssh_pool.execute(
            hostname, username, key_path,
            "sudo systemctl is-active openclaw.service",
            timeout=10,
            port=port,
        )

        # Check if process is running
        process_result = await self.ssh_pool.execute(
            hostname, username, key_path,
            "pgrep -f 'openclaw.*gateway' || echo 'not running'",
            timeout=10,
            port=port,
        )

        # Check version
        version_result = await self.ssh_pool.execute(
            hostname, username, key_path,
            "openclaw --version || echo 'unknown'",
            timeout=10,
            port=port,
        )

        # Check config file exists
        config_result = await self.ssh_pool.execute(
            hostname, username, key_path,
            "test -f ~/.openclaw/openclaw.json && echo 'exists' || echo 'missing'",
            timeout=10,
            port=port,
        )

        return {
            "service_active": status_result.stdout.strip() == "active",
            "process_running": "not running" not in process_result.stdout,
            "version": version_result.stdout.strip(),
            "config_exists": config_result.stdout.strip() == "exists",
            "timestamp": status_result.stdout.strip(),  # Use as timestamp proxy
        }

    async def update_openclaw(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        version: str = "latest",
        port: int = 22,
    ) -> SSHResult:
        """
        Update OpenClaw to a new version.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            version: Target version.
            port: SSH port.

        Returns:
            SSHResult with update output.
        """
        commands = [
            # Stop service
            "sudo systemctl stop openclaw.service",

            # Update OpenClaw
            f"sudo npm install -g openclaw@{version} || sudo npm install -g openclaw@{version} --unsafe-perm",

            # Restart service
            "sudo systemctl start openclaw.service",
            "sleep 3",
            "sudo systemctl status openclaw.service || echo 'Service may be starting...'",
        ]

        command = " && ".join(commands)
        return await self.ssh_pool.execute(hostname, username, key_path, command, timeout=600, port=port)

    async def manage_skill(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        skill_name: str,
        action: str,  # "enable" or "disable"
        port: int = 22,
    ) -> SSHResult:
        """
        Enable or disable a skill on remote VPS.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            skill_name: Name of the skill.
            action: "enable" or "disable".
            port: SSH port.

        Returns:
            SSHResult with operation output.
        """
        if action == "enable":
            command = f"openclaw skill enable {skill_name}"
        elif action == "disable":
            command = f"openclaw skill disable {skill_name}"
        else:
            return SSHResult(
                stdout="",
                stderr=f"Unknown action: {action}",
                exit_code=1,
                duration=0,
            )

        # Restart after change
        restart_result = await self.restart_service(hostname, username, key_path, port)
        command_result = await self.ssh_pool.execute(hostname, username, key_path, command, timeout=60, port=port)

        return command_result

    async def import_config(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        port: int = 22,
    ) -> Dict[str, Any]:
        """
        Import OpenClaw configuration from existing VPS instance.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            port: SSH port.

        Returns:
            Dictionary with imported configuration and status.
        """
        result = {
            "success": False,
            "config": None,
            "error": None,
            "warnings": [],
        }

        try:
            # Check if OpenClaw config exists
            check_result = await self.ssh_pool.execute(
                hostname, username, key_path,
                "test -f ~/.openclaw/openclaw.json && echo 'EXISTS' || echo 'NOT_FOUND'",
                timeout=10,
                port=port,
            )

            if "NOT_FOUND" in check_result.stdout:
                result["error"] = "OpenClaw configuration file not found on VPS"
                result["warnings"].append("OpenClaw may not be installed on this VPS")
                return result

            # Read the configuration file
            read_result = await self.ssh_pool.execute(
                hostname, username, key_path,
                "cat ~/.openclaw/openclaw.json",
                timeout=10,
                port=port,
            )

            if read_result.exit_code != 0:
                result["error"] = f"Failed to read config: {read_result.stderr}"
                return result

            # Parse JSON configuration
            try:
                config = json.loads(read_result.stdout)
                result["success"] = True
                result["config"] = config

                # Add metadata
                result["metadata"] = {
                    "imported_from": hostname,
                    "file_size": len(read_result.stdout),
                    "has_agents_config": "agents" in config,
                    "has_gateway_config": "gateway" in config,
                    "has_channels_config": "channels" in config,
                    "has_commands_config": "commands" in config,
                    "has_skills_config": "skills" in config,
                }

                # Validate configuration structure
                if "agents" not in config:
                    result["warnings"].append("Agents configuration section is missing (expected 'agents', not 'agent')")
                if "gateway" not in config:
                    result["warnings"].append("Gateway configuration section is missing")

                return result

            except json.JSONDecodeError as e:
                result["error"] = f"Invalid JSON in config file: {str(e)}"
                return result

        except Exception as e:
            result["error"] = f"Unexpected error during import: {str(e)}"
            return result


# Global OpenClaw manager instance
_openclaw_manager: Optional[OpenClawManager] = None


def get_openclaw_manager() -> OpenClawManager:
    """Get or create global OpenClaw manager instance."""
    global _openclaw_manager
    if _openclaw_manager is None:
        _openclaw_manager = OpenClawManager()
    return _openclaw_manager
