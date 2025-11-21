"""
Encryption Service for securing sensitive credentials.
Uses Fernet symmetric encryption for password protection.
"""
from cryptography.fernet import Fernet
import os
import base64


class EncryptionService:
    """
    Service for encrypting and decrypting sensitive data like passwords.
    Uses Fernet symmetric encryption (AES 128 in CBC mode).
    """

    def __init__(self):
        """
        Initialize encryption service with a key.
        Key is loaded from environment or generated on first run.
        """
        self.cipher = self._initialize_cipher()
        print("[OK] Encryption Service initialized")

    def _initialize_cipher(self) -> Fernet:
        """
        Initialize Fernet cipher with encryption key.

        Returns:
            Fernet cipher instance
        """
        from config import settings

        # Try to load key from settings
        key = settings.encryption_key

        if key:
            # Use existing key from settings
            try:
                return Fernet(key.encode())
            except Exception as e:
                print(f"WARNING: Invalid ENCRYPTION_KEY in environment: {e}")
                print("Generating new encryption key...")

        # Generate new key
        key = Fernet.generate_key()
        print(f"\n{'='*60}")
        print("WARNING: New encryption key generated!")
        print(f"{'='*60}")
        print("Add this to your .env file:")
        print(f"ENCRYPTION_KEY={key.decode()}")
        print(f"{'='*60}\n")

        return Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt sensitive data (like passwords).

        Args:
            plaintext: The string to encrypt

        Returns:
            Encrypted string (base64 encoded)
        """
        if not plaintext:
            return ""

        try:
            encrypted_bytes = self.cipher.encrypt(plaintext.encode())
            return encrypted_bytes.decode()
        except Exception as e:
            print(f"Encryption failed: {e}")
            raise

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt sensitive data.

        Args:
            ciphertext: The encrypted string to decrypt

        Returns:
            Decrypted plaintext string
        """
        if not ciphertext:
            return ""

        try:
            decrypted_bytes = self.cipher.decrypt(ciphertext.encode())
            return decrypted_bytes.decode()
        except Exception as e:
            print(f"Decryption failed: {e}")
            raise

    def encrypt_dict(self, data: dict, keys_to_encrypt: list) -> dict:
        """
        Encrypt specific keys in a dictionary.

        Args:
            data: Dictionary containing sensitive data
            keys_to_encrypt: List of keys to encrypt (e.g., ['password'])

        Returns:
            Dictionary with specified keys encrypted
        """
        encrypted_data = data.copy()

        for key in keys_to_encrypt:
            if key in encrypted_data and encrypted_data[key]:
                encrypted_data[key] = self.encrypt(encrypted_data[key])

        return encrypted_data

    def decrypt_dict(self, data: dict, keys_to_decrypt: list) -> dict:
        """
        Decrypt specific keys in a dictionary.

        Args:
            data: Dictionary containing encrypted data
            keys_to_decrypt: List of keys to decrypt (e.g., ['password'])

        Returns:
            Dictionary with specified keys decrypted
        """
        decrypted_data = data.copy()

        for key in keys_to_decrypt:
            if key in decrypted_data and decrypted_data[key]:
                decrypted_data[key] = self.decrypt(decrypted_data[key])

        return decrypted_data


# Singleton instance
_encryption_service = None


def get_encryption_service() -> EncryptionService:
    """
    Get singleton instance of EncryptionService.

    Returns:
        EncryptionService instance
    """
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
