"""Tests for SSH manager service."""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from paramiko import SSHException

from services.ssh_manager import (
    SSHResult,
    SSHConnection,
    SSHConnectionPool,
    SSHMultiplexer,
    SSHKeyManager,
)


class TestSSHResult:
    """Test cases for SSHResult dataclass."""

    def test_ssh_result_creation(self):
        """Test SSHResult creation with valid data."""
        result = SSHResult(
            stdout="command output",
            stderr="error output",
            exit_code=0,
            duration=1.5,
        )
        assert result.stdout == "command output"
        assert result.stderr == "error output"
        assert result.exit_code == 0
        assert result.duration == 1.5


class TestSSHConnection:
    """Test cases for SSHConnection class."""

    @pytest.fixture
    def mock_key_file(self):
        """Create a mock SSH key file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "test_key"
            key_path.write_text("mock key content")
            yield key_path

    @pytest.fixture
    def ssh_connection(self, mock_key_file):
        """Create SSHConnection instance for testing."""
        return SSHConnection(
            hostname="test.example.com",
            username="testuser",
            key_path=mock_key_file,
            port=22,
        )

    def test_ssh_connection_init(self, ssh_connection):
        """Test SSHConnection initialization."""
        assert ssh_connection.hostname == "test.example.com"
        assert ssh_connection.username == "testuser"
        assert ssh_connection.port == 22
        assert ssh_connection.is_connected is False
        assert ssh_connection.client is None

    @patch("paramiko.Ed25519Key.from_private_key_file")
    @patch("paramiko.SSHClient")
    def test_ssh_connection_connect(self, mock_ssh_client, mock_key, ssh_connection):
        """Test SSH connection establishment."""
        mock_client = MagicMock()
        mock_ssh_client.return_value = mock_client

        ssh_connection.connect()

        assert ssh_connection.is_connected is True
        assert ssh_connection.client == mock_client
        mock_client.connect.assert_called_once()
        mock_client.set_missing_host_key_policy.assert_called_once()

    def test_ssh_connection_execute_success(self, ssh_connection):
        """Test successful command execution."""
        mock_client = MagicMock()
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.side_effect = [b"output", b"error"]
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""

        mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
        ssh_connection.client = mock_client
        ssh_connection.is_connected = True

        result = ssh_connection.execute("echo test")

        assert result.exit_code == 0
        assert "output" in result.stdout
        assert result.stderr == ""

    def test_ssh_connection_execute_failure(self, ssh_connection):
        """Test command execution with failure."""
        mock_client = MagicMock()
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 1
        mock_stdout.read.side_effect = [b"", b"error message"]
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b"error message"

        mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
        ssh_connection.client = mock_client
        ssh_connection.is_connected = True

        result = ssh_connection.execute("invalid command")

        assert result.exit_code == 1
        assert "error message" in result.stderr

    def test_ssh_connection_execute_reconnect(self, ssh_connection):
        """Test command execution triggers reconnect if disconnected."""
        with patch.object(ssh_connection, "connect") as mock_connect:
            ssh_connection.is_connected = False
            ssh_connection.execute("test")
            mock_connect.assert_called_once()

    def test_ssh_connection_execute_exception(self, ssh_connection):
        """Test command execution handles exceptions."""
        ssh_connection.client = MagicMock()
        ssh_connection.client.exec_command.side_effect = SSHException("Connection lost")
        ssh_connection.is_connected = True

        result = ssh_connection.execute("test")

        assert result.exit_code == -1
        assert "Connection lost" in result.stderr

    def test_ssh_connection_close(self, ssh_connection):
        """Test SSH connection close."""
        mock_client = MagicMock()
        ssh_connection.client = mock_client
        ssh_connection.is_connected = True

        ssh_connection.close()

        mock_client.close.assert_called_once()
        assert ssh_connection.client is None
        assert ssh_connection.is_connected is False

    async def test_ssh_connection_context_manager(self, ssh_connection):
        """Test SSHConnection as context manager."""
        with patch.object(ssh_connection, "connect") as mock_connect:
            with patch.object(ssh_connection, "close") as mock_close:
                async def test():
                    async with ssh_connection:
                        pass
                await test()
                mock_connect.assert_called_once()
                mock_close.assert_called_once()


class TestSSHConnectionPool:
    """Test cases for SSHConnectionPool class."""

    @pytest.fixture
    async def connection_pool(self):
        """Create SSHConnectionPool instance for testing."""
        pool = SSHConnectionPool(max_idle_time=10, max_pool_size=5)
        yield pool
        await pool.close_all()

    def test_connection_key_generation(self, connection_pool):
        """Test connection key generation."""
        key = connection_pool._get_connection_key(
            hostname="test.example.com",
            username="testuser",
            key_path=Path("/tmp/key"),
            port=22,
        )
        expected = "testuser@test.example.com:22:/tmp/key"
        assert key == expected

    @pytest.mark.asyncio
    async def test_get_connection_new(self, connection_pool):
        """Test getting a new connection from pool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "test_key"
            key_path.write_text("mock key")

            with patch("services.ssh_manager.SSHConnection") as mock_conn_class:
                mock_conn = MagicMock()
                mock_conn.is_connected = True
                mock_conn_class.return_value = mock_conn

                conn = await connection_pool.get_connection(
                    hostname="test.example.com",
                    username="testuser",
                    key_path=key_path,
                    port=22,
                )

                assert conn == mock_conn
                mock_conn_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_connection_cached(self, connection_pool):
        """Test getting cached connection from pool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "test_key"
            key_path.write_text("mock key")

            with patch("services.ssh_manager.SSHConnection") as mock_conn_class:
                mock_conn = MagicMock()
                mock_conn.is_connected = True
                mock_conn_class.return_value = mock_conn

                # First call
                conn1 = await connection_pool.get_connection(
                    hostname="test.example.com",
                    username="testuser",
                    key_path=key_path,
                    port=22,
                )
                # Second call should return cached connection
                conn2 = await connection_pool.get_connection(
                    hostname="test.example.com",
                    username="testuser",
                    key_path=key_path,
                    port=22,
                )

                assert conn1 == conn2
                assert mock_conn_class.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_command(self, connection_pool):
        """Test executing command through pool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "test_key"
            key_path.write_text("mock key")

            with patch.object(connection_pool, "get_connection") as mock_get_conn:
                mock_conn = MagicMock()
                mock_result = SSHResult(
                    stdout="output", stderr="", exit_code=0, duration=1.0
                )
                mock_conn.execute.return_value = mock_result
                mock_get_conn.return_value = mock_conn

                result = await connection_pool.execute(
                    hostname="test.example.com",
                    username="testuser",
                    key_path=key_path,
                    command="test command",
                )

                assert result == mock_result
                mock_conn.execute.assert_called_once_with("test command", 300)

    @pytest.mark.asyncio
    async def test_cleanup_old_connections(self, connection_pool):
        """Test cleanup of idle connections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "test_key"
            key_path.write_text("mock key")

            mock_conn = MagicMock()
            mock_conn.last_used = 0  # Very old connection
            connection_pool.connections["test_key"] = mock_conn

            await connection_pool._cleanup_old_connections()

            assert len(connection_pool.connections) == 0

    @pytest.mark.asyncio
    async def test_close_all(self, connection_pool):
        """Test closing all connections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "test_key"
            key_path.write_text("mock key")

            mock_conn1 = MagicMock()
            mock_conn2 = MagicMock()
            connection_pool.connections["key1"] = mock_conn1
            connection_pool.connections["key2"] = mock_conn2

            await connection_pool.close_all()

            assert len(connection_pool.connections) == 0


class TestSSHMultiplexer:
    """Test cases for SSHMultiplexer class."""

    @pytest.fixture
    def multiplexer(self):
        """Create SSHMultiplexer instance for testing."""
        pool = MagicMock()
        return SSHMultiplexer(pool)

    @pytest.mark.asyncio
    async def test_execute_parallel(self, multiplexer):
        """Test executing multiple commands in parallel."""
        commands = [
            ("host1", "user1", Path("/key1"), "cmd1", 30, 22),
            ("host2", "user2", Path("/key2"), "cmd2", 30, 22),
        ]

        mock_results = [
            SSHResult(stdout="out1", stderr="", exit_code=0, duration=1.0),
            SSHResult(stdout="out2", stderr="", exit_code=0, duration=1.0),
        ]

        multiplexer.pool.execute = AsyncMock(side_effect=mock_results)

        results = await multiplexer.execute_parallel(commands)

        assert len(results) == 2
        assert multiplexer.pool.execute.call_count == 2


class TestSSHKeyManager:
    """Test cases for SSHKeyManager class."""

    @pytest.fixture
    def key_manager(self):
        """Create SSHKeyManager instance for testing."""
        return SSHKeyManager()

    @patch("services.ssh_manager.settings")
    @patch("paramiko.Ed25519Key.generate")
    @patch("services.ssh_manager.Path.write_bytes")
    @patch("services.ssh_manager.Path.write_text")
    def test_generate_keypair_ed25519(
        self,
        mock_write_text,
        mock_write_bytes,
        mock_key_generate,
        mock_settings,
    ):
        """Test generating Ed25519 key pair."""
        mock_settings.ssh_keys_path = Path("/tmp/test_keys")
        mock_key = MagicMock()
        mock_key.as_bytes.return_value = b"key_bytes"
        mock_key.get_name.return_value = "ssh-ed25519"
        mock_key.get_base64.return_value = "base64_key"
        mock_key_generate.return_value = mock_key

        with patch("pathlib.Path.mkdir"):
            private_key, public_key = SSHKeyManager.generate_keypair("ed25519")

            mock_key_generate.assert_called_once()
            assert isinstance(private_key, Path)
            assert isinstance(public_key, Path)

    @patch("services.ssh_manager.settings")
    @patch("paramiko.RSAKey.generate")
    def test_generate_keypair_rsa(self, mock_key_generate, mock_settings):
        """Test generating RSA key pair."""
        mock_settings.ssh_keys_path = Path("/tmp/test_keys")
        mock_key = MagicMock()
        mock_key.as_bytes.return_value = b"key_bytes"
        mock_key.get_name.return_value = "ssh-rsa"
        mock_key.get_base64.return_value = "base64_key"
        mock_key_generate.return_value = mock_key

        with patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_bytes"), \
             patch("pathlib.Path.write_text"):
            private_key, public_key = SSHKeyManager.generate_keypair("rsa", "passphrase")

            mock_key_generate.assert_called_once_with(bits=4096)

    @patch("services.ssh_manager.settings")
    @patch("paramiko.Ed25519Key.generate")
    def test_generate_keypair_with_passphrase(
        self, mock_key_generate, mock_settings
    ):
        """Test generating key pair with passphrase."""
        mock_settings.ssh_keys_path = Path("/tmp/test_keys")
        mock_key = MagicMock()
        mock_key.as_bytes.return_value = b"key_bytes"
        mock_key_generate.return_value = mock_key

        with patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_bytes"), \
             patch("pathlib.Path.write_text"):
            SSHKeyManager.generate_keypair("ed25519", "test_pass")

            mock_key.as_bytes.assert_called_once_with(passphrase="test_pass")
