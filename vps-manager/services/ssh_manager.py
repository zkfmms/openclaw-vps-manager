"""SSH connection management service."""
import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import paramiko
from paramiko import SSHClient, AutoAddPolicy

from config import get_settings

settings = get_settings()


@dataclass
class SSHResult:
    """Result of SSH command execution."""
    stdout: str
    stderr: str
    exit_code: int
    duration: float


class SSHConnection:
    """Wrapper for a single SSH connection with keepalive."""

    def __init__(self, hostname: str, username: str, key_path: Path, port: int = 22):
        """
        Initialize SSH connection.

        Args:
            hostname: Target hostname or IP.
            username: SSH username.
            key_path: Path to SSH private key.
            port: SSH port.
        """
        self.hostname = hostname
        self.username = username
        self.key_path = key_path
        self.port = port
        self.client: Optional[SSHClient] = None
        self.last_used: float = 0
        self.is_connected = False

    def connect(self) -> None:
        """Establish SSH connection."""
        self.client = SSHClient()
        self.client.set_missing_host_key_policy(AutoAddPolicy())

        key = paramiko.Ed25519Key.from_private_key_file(str(self.key_path))
        self.client.connect(
            hostname=self.hostname,
            port=self.port,
            username=self.username,
            pkey=key,
            timeout=30,
        )
        self.is_connected = True
        self.last_used = time.time()

    def execute(self, command: str, timeout: int = 300) -> SSHResult:
        """
        Execute command over SSH.

        Args:
            command: Command to execute.
            timeout: Command timeout in seconds.

        Returns:
            SSHResult with output and exit code.
        """
        if not self.is_connected or not self.client:
            self.connect()

        self.last_used = time.time()
        start_time = time.time()

        try:
            stdin, stdout, stderr = self.client.exec_command(
                command,
                timeout=timeout,
                get_pty=True,
            )

            exit_code = stdout.channel.recv_exit_status()
            stdout_str = stdout.read().decode("utf-8", errors="replace")
            stderr_str = stderr.read().decode("utf-8", errors="replace")

            duration = time.time() - start_time

            return SSHResult(
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                duration=duration,
            )
        except Exception as e:
            duration = time.time() - start_time
            return SSHResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration=duration,
            )

    def close(self) -> None:
        """Close SSH connection."""
        if self.client:
            self.client.close()
            self.client = None
            self.is_connected = False

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class SSHConnectionPool:
    """Pool of reusable SSH connections with keepalive."""

    def __init__(self, max_idle_time: float = 300, max_pool_size: int = 10):
        """
        Initialize connection pool.

        Args:
            max_idle_time: Maximum idle time before closing connection (seconds).
            max_pool_size: Maximum number of connections in pool.
        """
        self.connections: Dict[str, SSHConnection] = {}
        self.lock = asyncio.Lock()
        self.max_idle_time = max_idle_time
        self.max_pool_size = max_pool_size

    def _get_connection_key(self, hostname: str, username: str, key_path: Path, port: int = 22) -> str:
        """Generate unique key for connection."""
        return f"{username}@{hostname}:{port}:{key_path}"

    async def get_connection(self, hostname: str, username: str, key_path: Path, port: int = 22) -> SSHConnection:
        """
        Get or create SSH connection.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            port: SSH port.

        Returns:
            SSHConnection instance.
        """
        key = self._get_connection_key(hostname, username, key_path, port)

        async with self.lock:
            # Check for existing connection
            if key in self.connections:
                conn = self.connections[key]
                if conn.is_connected:
                    conn.last_used = time.time()
                    return conn
                else:
                    # Connection closed, remove it
                    del self.connections[key]

            # Check pool size
            if len(self.connections) >= self.max_pool_size:
                await self._cleanup_old_connections()

            # Create new connection
            conn = SSHConnection(hostname, username, key_path, port)
            self.connections[key] = conn

        return conn

    async def execute(
        self,
        hostname: str,
        username: str,
        key_path: Path,
        command: str,
        timeout: int = 300,
        port: int = 22,
    ) -> SSHResult:
        """
        Execute command on remote host.

        Args:
            hostname: Target hostname.
            username: SSH username.
            key_path: Path to SSH key.
            command: Command to execute.
            timeout: Command timeout.
            port: SSH port.

        Returns:
            SSHResult with output.
        """
        conn = await self.get_connection(hostname, username, key_path, port)
        # Run in thread to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, conn.execute, command, timeout)
        return result

    async def _cleanup_old_connections(self) -> None:
        """Close idle connections."""
        current_time = time.time()
        to_remove = []

        for key, conn in self.connections.items():
            idle_time = current_time - conn.last_used
            if idle_time > self.max_idle_time:
                to_remove.append(key)

        for key in to_remove:
            conn = self.connections.pop(key)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

    async def close_all(self) -> None:
        """Close all connections."""
        async with self.lock:
            for conn in self.connections.values():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, conn.close)
            self.connections.clear()


class SSHMultiplexer:
    """Execute multiple SSH commands in parallel."""

    def __init__(self, pool: SSHConnectionPool):
        """
        Initialize multiplexer.

        Args:
            pool: SSH connection pool to use.
        """
        self.pool = pool

    async def execute_parallel(
        self,
        commands: List[Tuple[str, str, Path, str, int, int]]
    ) -> List[SSHResult]:
        """
        Execute multiple commands in parallel.

        Args:
            commands: List of tuples (hostname, username, key_path, command, timeout, port).

        Returns:
            List of SSHResults in same order as commands.
        """
        tasks = []
        for hostname, username, key_path, command, timeout, port in commands:
            task = self.pool.execute(hostname, username, key_path, command, timeout, port)
            tasks.append(task)

        return await asyncio.gather(*tasks)


class SSHKeyManager:
    """Manage SSH key generation and rotation."""

    @staticmethod
    def generate_keypair(key_type: str = "ed25519", passphrase: Optional[str] = None) -> Tuple[Path, Path]:
        """
        Generate SSH key pair.

        Args:
            key_type: Key type (ed25519 or rsa).
            passphrase: Optional passphrase for private key.

        Returns:
            Tuple of (private_key_path, public_key_path).
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            private_key_path = Path(tmpdir) / f"key_{key_type}"
            public_key_path = Path(tmpdir) / f"key_{key_type}.pub"

            if key_type == "ed25519":
                key = paramiko.Ed25519Key.generate()
            else:  # rsa
                key = paramiko.RSAKey.generate(bits=4096)

            private_key_path.write_bytes(
                key.as_bytes(passphrase=passphrase)
            )

            public_key_path.write_text(
                f"{key.get_name()} {key.get_base64()}"
            )

            # Move to permanent location
            final_private = Path(settings.ssh_keys_path) / private_key_path.name
            final_public = Path(settings.ssh_keys_path) / public_key_path.name

            settings.ssh_keys_path.mkdir(parents=True, exist_ok=True)

            final_private.write_bytes(private_key_path.read_bytes())
            final_public.write_text(public_key_path.read_text())

            # Set restrictive permissions
            final_private.chmod(0o600)
            final_public.chmod(0o644)

            return final_private, final_public


# Global connection pool
_ssh_pool: Optional[SSHConnectionPool] = None


def get_ssh_pool() -> SSHConnectionPool:
    """Get or create global SSH connection pool."""
    global _ssh_pool
    if _ssh_pool is None:
        _ssh_pool = SSHConnectionPool()
    return _ssh_pool
