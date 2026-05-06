"""
CipherLens — Document Endpoints

POST /api/documents/sign                  — Upload & sign a document
POST /api/documents/verify                — Verify a document + signature
GET  /api/documents/                      — List user's signed documents
GET  /api/documents/{doc_id}/download-sig — Download a .sig file
GET  /api/documents/{doc_id}/insights     — Get ML analysis results
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File,
    HTTPException, Request, UploadFile, status,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, get_db
from backend.core.crypto import get_file_hash, sign_document, verify_signature, decrypt_private_key
from backend.config import MASTER_KEY
from backend.models.models import AuditLog, Document, User
from backend.services.storage import storage_service
from backend.services.ml_pipeline import process_document_ml

router = APIRouter(prefix="/api/documents", tags=["Documents"])


# ─── Response Schemas ─────────────────────────────────────

class DocumentResponse(BaseModel):
    id: int
    original_filename: str
    file_hash: str
    file_size: Optional[int] = None
    document_type: str
    ml_classification_confidence: Optional[float] = 0.0
    ml_processed: Optional[bool] = False
    created_at: datetime

    class Config:
        from_attributes = True


class SignResponse(BaseModel):
    message: str
    document: DocumentResponse
    signature_b64: Optional[str] = None


class VerifyResponse(BaseModel):
    signature_valid: bool
    message: str
    file_hash: str


class EntityDetail(BaseModel):
    persons: List[str] = Field(default_factory=list)
    organizations: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)
    amounts: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    legal_references: List[str] = Field(default_factory=list)
    groups: List[str] = Field(default_factory=list)
    events: List[str] = Field(default_factory=list)


class InsightsResponse(BaseModel):
    document_id: int
    original_filename: str
    document_type: str
    classification_confidence: float
    ml_processed: bool
    extracted_entities: EntityDetail
    text_preview: str


# ─── Endpoints ────────────────────────────────────────────

@router.post("/sign", response_model=SignResponse, summary="Sign a document")
async def sign_doc(
    request: Request,
    background_tasks: BackgroundTasks,
    document: UploadFile = File(..., description="The document file to sign"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a document and sign it with the authenticated user's RSA private key.

    Process:
    1. Read file bytes
    2. Compute SHA-256 hash
    3. Sign hash with user's private key (PKCS#1 v1.5)
    4. Store document + signature
    5. Save metadata to database
    6. Log action in audit trail
    7. **Queue ML analysis as a background task** (non-blocking)
    """
    file_data = await document.read()
    if not file_data:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Cryptographic operations
    decrypted_key = decrypt_private_key(current_user.private_key_encrypted, MASTER_KEY)
    signature_b64 = sign_document(file_data, decrypted_key)
    file_hash = get_file_hash(file_data)

    # Persist files
    stored_filename = await storage_service.save_document(file_data, document.filename)
    await storage_service.save_signature(signature_b64, stored_filename)

    # Save metadata to DB — document_type starts as "processing..."
    doc_record = Document(
        filename=stored_filename,
        original_filename=document.filename,
        file_hash=file_hash,
        signature=signature_b64,
        file_size=len(file_data),
        document_type="processing...",
        ml_processed=False,
        owner_id=current_user.id,
    )
    db.add(doc_record)

    # Audit trail
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="SIGN",
            ip_address=request.client.host if request.client else "unknown",
            details=f"Signed: {document.filename} (hash: {file_hash[:16]}…)",
        )
    )
    db.commit()
    db.refresh(doc_record)

    # ─── Queue ML analysis (non-blocking) ────────────
    background_tasks.add_task(process_document_ml, doc_record.id)

    return SignResponse(
        message="Document signed successfully. AI analysis is processing in the background.",
        document=DocumentResponse.model_validate(doc_record),
        signature_b64=signature_b64,
    )


@router.post("/verify", response_model=VerifyResponse, summary="Verify a signature")
async def verify_doc(
    request: Request,
    document: UploadFile = File(..., description="The document to verify"),
    signature: UploadFile = File(..., description="The .sig signature file"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verify a document's signature against the current user's RSA public key.

    Upload both the original document and the .sig file to check integrity.
    """
    file_data = await document.read()
    sig_data = await signature.read()

    if not file_data or not sig_data:
        raise HTTPException(
            status_code=400,
            detail="Both document and signature files are required",
        )

    signature_b64 = sig_data.decode("utf-8").strip()
    file_hash = get_file_hash(file_data)

    # Cryptographic verification
    is_valid = verify_signature(file_data, signature_b64, current_user.public_key)

    # Audit trail
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="VERIFY",
            ip_address=request.client.host if request.client else "unknown",
            details=f"Verified: {document.filename} — {'VALID' if is_valid else 'INVALID'}",
        )
    )
    db.commit()

    return VerifyResponse(
        signature_valid=is_valid,
        message="Signature is VALID ✅" if is_valid else "Signature is INVALID ❌",
        file_hash=file_hash,
    )


@router.get("/", response_model=List[DocumentResponse], summary="List signed documents")
async def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all documents signed by the currently authenticated user."""
    docs = (
        db.query(Document)
        .filter(Document.owner_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return docs


@router.get(
    "/{doc_id}/insights",
    response_model=InsightsResponse,
    summary="Get AI insights for a document",
)
async def get_document_insights(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the ML analysis results for a specific signed document.

    Returns:
    - Document classification (type + confidence)
    - Extracted entities (persons, orgs, dates, amounts, etc.)
    - Text preview (first 500 characters)

    If ML processing is still in progress, `ml_processed` will be False.
    """
    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.owner_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Parse entities JSON
    try:
        entities = json.loads(doc.extracted_entities) if doc.extracted_entities else {}
    except json.JSONDecodeError:
        entities = {}

    return InsightsResponse(
        document_id=doc.id,
        original_filename=doc.original_filename,
        document_type=doc.document_type,
        classification_confidence=doc.ml_classification_confidence or 0.0,
        ml_processed=doc.ml_processed,
        extracted_entities=EntityDetail(**entities) if entities else EntityDetail(),
        text_preview=doc.extracted_text_preview or "",
    )


@router.get(
    "/{doc_id}/download-signature",
    summary="Download a signature file",
)
async def download_signature(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download the .sig signature file for a specific document."""
    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.owner_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return Response(
        content=doc.signature.encode("utf-8"),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{doc.original_filename}.sig"'
        },
    )
