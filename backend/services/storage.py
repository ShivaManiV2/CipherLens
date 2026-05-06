"""
CipherLens — File Storage Service

Abstraction layer for document & signature storage.
Currently uses the local filesystem. In Phase 4, swap this implementation
for an S3/MinIO-compatible class without changing the API layer.
"""

import os
import uuid

import aiofiles

from backend.config import DOCUMENTS_DIR, SIGNATURES_DIR


class StorageService:
    """
    Local filesystem storage backend.

    Directory layout:
        storage/
        ├── documents/   ← uploaded files (UUID-renamed)
        └── signatures/  ← .sig files
    """

    def __init__(self):
        os.makedirs(DOCUMENTS_DIR, exist_ok=True)
        os.makedirs(SIGNATURES_DIR, exist_ok=True)

    @staticmethod
    def _generate_filename(original_filename: str) -> str:
        """Generate a unique storage filename preserving the original extension."""
        ext = os.path.splitext(original_filename)[1]
        return f"{uuid.uuid4().hex}{ext}"

    # ─── Documents ────────────────────────────────────────

    async def save_document(self, file_data: bytes, original_filename: str) -> str:
        """
        Save a document to storage.

        Returns:
            The UUID-based stored filename.
        """
        stored_filename = self._generate_filename(original_filename)
        filepath = os.path.join(DOCUMENTS_DIR, stored_filename)
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(file_data)
        return stored_filename

    async def get_document(self, filename: str) -> bytes:
        """Read a document from storage by its stored filename."""
        filepath = os.path.join(DOCUMENTS_DIR, filename)
        async with aiofiles.open(filepath, "rb") as f:
            return await f.read()

    def delete_document(self, filename: str) -> None:
        """Delete a document from storage."""
        filepath = os.path.join(DOCUMENTS_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)

    # ─── Signatures ───────────────────────────────────────

    async def save_signature(self, signature_data: str, doc_filename: str) -> str:
        """
        Save a base64 signature alongside its document.

        Returns:
            The .sig filename.
        """
        sig_filename = f"{doc_filename}.sig"
        filepath = os.path.join(SIGNATURES_DIR, sig_filename)
        async with aiofiles.open(filepath, "w") as f:
            await f.write(signature_data)
        return sig_filename

    async def get_signature(self, doc_filename: str) -> str:
        """Read a signature file by its parent document filename."""
        filepath = os.path.join(SIGNATURES_DIR, f"{doc_filename}.sig")
        async with aiofiles.open(filepath, "r") as f:
            return await f.read()

    def delete_signature(self, doc_filename: str) -> None:
        """Delete a signature file."""
        filepath = os.path.join(SIGNATURES_DIR, f"{doc_filename}.sig")
        if os.path.exists(filepath):
            os.remove(filepath)


# Singleton instance used across the app
storage_service = StorageService()
