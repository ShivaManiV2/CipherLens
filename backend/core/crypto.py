"""
CipherLens — RSA Cryptography Module

Modularized from the original app.py. Provides:
  • RSA key pair generation (per-user)
  • Document signing (SHA-256 + PKCS#1 v1.5)
  • Signature verification
  • File hash computation
"""

import base64
from typing import Tuple

from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256


def generate_rsa_keypair(bits: int = 2048) -> Tuple[str, str]:
    """
    Generate an RSA key pair.

    Args:
        bits: Key size in bits (default 2048).

    Returns:
        Tuple of (private_key_pem, public_key_pem) as UTF-8 strings.
    """
    key = RSA.generate(bits)
    private_key_pem = key.export_key("PEM").decode("utf-8")
    public_key_pem = key.publickey().export_key("PEM").decode("utf-8")
    return private_key_pem, public_key_pem


def sign_document(file_data: bytes, private_key_pem: str) -> str:
    """
    Sign file data with an RSA private key.

    Process: SHA-256 hash → PKCS#1 v1.5 signature → Base64 encode.

    Args:
        file_data: Raw bytes of the document.
        private_key_pem: PEM-encoded RSA private key string.

    Returns:
        Base64-encoded signature string.
    """
    private_key = RSA.import_key(private_key_pem.encode("utf-8"))
    h = SHA256.new(file_data)
    signature = pkcs1_15.new(private_key).sign(h)
    return base64.b64encode(signature).decode("utf-8")


def verify_signature(file_data: bytes, signature_b64: str, public_key_pem: str) -> bool:
    """
    Verify a Base64-encoded RSA signature against file data.

    Args:
        file_data: Raw bytes of the document.
        signature_b64: Base64-encoded signature string.
        public_key_pem: PEM-encoded RSA public key string.

    Returns:
        True if valid, False otherwise.
    """
    try:
        public_key = RSA.import_key(public_key_pem.encode("utf-8"))
        signature = base64.b64decode(signature_b64)
        h = SHA256.new(file_data)
        pkcs1_15.new(public_key).verify(h, signature)
        return True
    except (ValueError, TypeError):
        return False


def get_file_hash(file_data: bytes) -> str:
    """
    Compute the SHA-256 hex digest of file data.

    Args:
        file_data: Raw bytes of the document.

    Returns:
        64-character hex string.
    """
    h = SHA256.new(file_data)
    return h.hexdigest()


def encrypt_private_key(private_key_pem: str, master_key: bytes) -> str:
    """
    Encrypt the user's RSA private key using AES-GCM before saving to the DB.
    """
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes

    cipher = AES.new(master_key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(private_key_pem.encode("utf-8"))
    
    # Store nonce + tag + ciphertext together
    payload = cipher.nonce + tag + ciphertext
    return base64.b64encode(payload).decode("utf-8")


def decrypt_private_key(encrypted_b64: str, master_key: bytes) -> str:
    """
    Decrypt the user's RSA private key from the DB using AES-GCM.
    """
    from Crypto.Cipher import AES

    payload = base64.b64decode(encrypted_b64)
    nonce = payload[:16]
    tag = payload[16:32]
    ciphertext = payload[32:]

    cipher = AES.new(master_key, AES.MODE_GCM, nonce=nonce)
    try:
        decrypted = cipher.decrypt_and_verify(ciphertext, tag)
        return decrypted.decode("utf-8")
    except ValueError as e:
        raise ValueError("Failed to decrypt private key. Master key may be incorrect or data corrupted.") from e
