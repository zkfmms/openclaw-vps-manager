"""Tests for encryption service."""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.encryption import EncryptionService, get_encryption_service


class TestEncryptionService:
    """Test cases for EncryptionService class."""

    @pytest.fixture
    def temp_key_path(self):
        """Create temporary directory for encryption keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test_encryption_key"

    @pytest.fixture
    def encryption_service(self, temp_key_path):
        """Create EncryptionService instance for testing."""
        with patch("services.encryption.settings") as mock_settings:
            mock_settings.encryption_key_path = str(temp_key_path)
            return EncryptionService()

    def test_encryption_service_init_new_key(self, temp_key_path):
        """Test initialization with new key generation."""
        with patch("services.encryption.settings") as mock_settings:
            mock_settings.encryption_key_path = str(temp_key_path)

            service = EncryptionService()

            # Check key file was created
            assert temp_key_path.exists()

            # Check permissions
            stat = temp_key_path.stat()
            assert oct(stat.st_mode)[-3:] == "600"

            # Check key is valid Fernet key
            from cryptography.fernet import Fernet
            key = temp_key_path.read_bytes()
            assert len(key) == 44  # Fernet key length

    def test_encryption_service_init_existing_key(self, temp_key_path):
        """Test initialization with existing key."""
        from cryptography.fernet import Fernet
        existing_key = Fernet.generate_key()
        temp_key_path.write_bytes(existing_key)
        original_key = temp_key_path.read_bytes()

        with patch("services.encryption.settings") as mock_settings:
            mock_settings.encryption_key_path = str(temp_key_path)

            service = EncryptionService()

            # Key should not have been regenerated
            assert temp_key_path.read_bytes() == original_key

    def test_encrypt_decrypt_string(self, encryption_service):
        """Test encrypting and decrypting a string."""
        plaintext = "This is a secret message"
        encrypted = encryption_service.encrypt(plaintext)
        decrypted = encryption_service.decrypt(encrypted)

        assert plaintext == decrypted
        assert encrypted != plaintext

    def test_encrypt_decrypt_unicode(self, encryption_service):
        """Test encrypting and decrypting unicode strings."""
        plaintext = "Hello 世界! 🌍 Test with emoji"
        encrypted = encryption_service.encrypt(plaintext)
        decrypted = encryption_service.decrypt(encrypted)

        assert plaintext == decrypted

    def test_encrypt_decrypt_dict(self, encryption_service):
        """Test encrypting and decrypting a dictionary."""
        data = {
            "string": "test",
            "number": 42,
            "nested": {"key": "value"},
            "list": [1, 2, 3],
        }

        encrypted = encryption_service.encrypt_dict(data)
        decrypted = encryption_service.decrypt_dict(encrypted)

        assert data == decrypted

    def test_encrypt_empty_string(self, encryption_service):
        """Test encrypting an empty string."""
        plaintext = ""
        encrypted = encryption_service.encrypt(plaintext)
        decrypted = encryption_service.decrypt(encrypted)

        assert plaintext == decrypted

    def test_generate_customer_key(self, encryption_service):
        """Test generating customer-specific keys."""
        key1 = encryption_service.generate_customer_key(1)
        key2 = encryption_service.generate_customer_key(2)
        key3 = encryption_service.generate_customer_key(1)

        # Different customers should have different keys
        assert key1 != key2

        # Same customer should get same key
        assert key1 == key3

    def test_generate_customer_key_is_consistent(self, encryption_service):
        """Test customer key generation is consistent."""
        key1 = encryption_service.generate_customer_key(999)
        key2 = encryption_service.generate_customer_key(999)

        assert key1 == key2

    def test_hash_key(self, encryption_service):
        """Test key hashing."""
        key = "test_key_value"
        hash1 = encryption_service.hash_key(key)
        hash2 = encryption_service.hash_key(key)

        # Hash should be deterministic
        assert hash1 == hash2

        # Hash should be a SHA256 hex string
        assert len(hash1) == 64
        assert all(c in "0123456789abcdef" for c in hash1)

    def test_hash_key_different_inputs(self, encryption_service):
        """Test different keys produce different hashes."""
        key1 = "test_key_1"
        key2 = "test_key_2"

        hash1 = encryption_service.hash_key(key1)
        hash2 = encryption_service.hash_key(key2)

        assert hash1 != hash2

    def test_encrypt_with_custom_master_key(self, temp_key_path):
        """Test initialization with custom master key."""
        from cryptography.fernet import Fernet
        custom_key = Fernet.generate_key()

        service = EncryptionService(master_key=custom_key)

        plaintext = "test message"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert plaintext == decrypted


class TestGetEncryptionService:
    """Test cases for get_encryption_service function."""

    @patch("services.encryption._encryption_service", None)
    def test_get_encryption_service_creates_new(self):
        """Test that get_encryption_service creates a new instance."""
        service = get_encryption_service()
        assert service is not None
        assert isinstance(service, EncryptionService)

    @patch("services.encryption._encryption_service", None)
    def test_get_encryption_service_returns_cached(self):
        """Test that get_encryption_service returns cached instance."""
        service1 = get_encryption_service()
        service2 = get_encryption_service()

        assert service1 is service2


class TestEncryptionErrorHandling:
    """Test cases for encryption error handling."""

    def test_decrypt_invalid_data(self):
        """Test decrypting invalid encrypted data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_key_path = Path(tmpdir) / "test_key"
            with patch("services.encryption.settings") as mock_settings:
                mock_settings.encryption_key_path = str(temp_key_path)
                service = EncryptionService()

                # Test with invalid base64
                with pytest.raises(Exception):
                    service.decrypt("not valid base64!!!")

                # Test with valid base64 but invalid encrypted data
                with pytest.raises(Exception):
                    service.decrypt("dGVzdA==")  # "test" in base64, not encrypted


class TestEncryptionServiceIntegration:
    """Integration tests for encryption service."""

    def test_full_workflow(self):
        """Test full encryption/decryption workflow with multiple keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_key_path = Path(tmpdir) / "test_key"
            with patch("services.encryption.settings") as mock_settings:
                mock_settings.encryption_key_path = str(temp_key_path)
                service = EncryptionService()

                # Generate customer keys
                customer1_key = service.generate_customer_key(1)
                customer2_key = service.generate_customer_key(2)

                # Hash keys
                customer1_hash = service.hash_key(customer1_key)
                customer2_hash = service.hash_key(customer2_key)

                assert customer1_hash != customer2_hash

                # Encrypt data for each customer
                data1 = {"customer": 1, "data": "sensitive"}
                data2 = {"customer": 2, "data": "confidential"}

                encrypted1 = service.encrypt_dict(data1)
                encrypted2 = service.encrypt_dict(data2)

                # Verify different data produces different ciphertext
                assert encrypted1 != encrypted2

                # Decrypt and verify
                decrypted1 = service.decrypt_dict(encrypted1)
                decrypted2 = service.decrypt_dict(encrypted2)

                assert decrypted1 == data1
                assert decrypted2 == data2
