"""Encryption service for configuration data."""
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from config import get_settings

settings = get_settings()


class EncryptionService:
    """Service for encrypting and decrypting configuration data."""

    def __init__(self, master_key: Optional[bytes] = None):
        """
        Initialize encryption service.

        Args:
            master_key: Optional master key for encryption. If not provided,
                       will load from configured path or generate a new one.
        """
        self._master_key = master_key or self._load_or_generate_master_key()
        self.fernet = Fernet(self._master_key)

    def _load_or_generate_master_key(self) -> bytes:
        """
        Load master key from file or generate a new one.

        Returns:
            Master key as bytes.
        """
        key_path = Path(settings.encryption_key_path)

        if key_path.exists():
            return key_path.read_bytes()

        # Generate new key
        key = Fernet.generate_key()

        # Ensure directory exists
        key_path.parent.mkdir(parents=True, exist_ok=True)

        # Save key with restricted permissions
        key_path.write_bytes(key)
        key_path.chmod(0o600)

        return key

    def encrypt(self, data: str) -> str:
        """
        Encrypt string data.

        Args:
            data: String data to encrypt.

        Returns:
            Encrypted data as base64 string.
        """
        encrypted = self.fernet.encrypt(data.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")

    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt encrypted string data.

        Args:
            encrypted_data: Base64-encoded encrypted data.

        Returns:
            Decrypted string.
        """
        encrypted_bytes = base64.b64decode(encrypted_data.encode("utf-8"))
        decrypted = self.fernet.decrypt(encrypted_bytes)
        return decrypted.decode("utf-8")

    def encrypt_dict(self, data: dict) -> str:
        """
        Encrypt dictionary data.

        Args:
            data: Dictionary to encrypt.

        Returns:
            Encrypted data as base64 string.
        """
        import json
        return self.encrypt(json.dumps(data))

    def decrypt_dict(self, encrypted_data: str) -> dict:
        """
        Decrypt to dictionary.

        Args:
            encrypted_data: Base64-encoded encrypted data.

        Returns:
            Decrypted dictionary.
        """
        import json
        decrypted = self.decrypt(encrypted_data)
        return json.loads(decrypted)

    def generate_customer_key(self, customer_id: int) -> str:
        """
        Generate a unique encryption key for a customer.

        Args:
            customer_id: Customer ID.

        Returns:
            Base64-encoded encryption key.
        """
        salt = f"customer-{customer_id}".encode("utf-8")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._master_key))
        return key.decode("utf-8")

    def hash_key(self, key: str) -> str:
        """
        Create a hash of an encryption key for storage.

        Args:
            key: Encryption key.

        Returns:
            Hash of the key.
        """
        import hashlib
        return hashlib.sha256(key.encode("utf-8")).hexdigest()


# Global encryption service instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """Get or create global encryption service instance."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
