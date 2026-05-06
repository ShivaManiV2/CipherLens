"""
CipherLens — ML Intelligence Endpoints

POST /api/ml/analyze          — Standalone ML analysis (no signing)
GET  /api/ml/models-status    — Check if ML models are loaded
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from backend.api.deps import get_current_user
from backend.models.models import User
from backend.services.ml_pipeline import analyze_file_standalone

router = APIRouter(prefix="/api/ml", tags=["ML Intelligence"])


# ─── Response Schemas ─────────────────────────────────────

class EntityResponse(BaseModel):
    persons: List[str] = Field(default_factory=list)
    organizations: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)
    amounts: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    legal_references: List[str] = Field(default_factory=list)
    groups: List[str] = Field(default_factory=list)
    events: List[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    filename: str
    document_type: str
    confidence: float
    entities: EntityResponse
    text_preview: str
    text_length: int


class ModelStatusResponse(BaseModel):
    classifier_loaded: bool
    ner_loaded: bool
    tesseract_available: bool


# ─── Endpoints ────────────────────────────────────────────

@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze a document with AI",
)
async def analyze_document(
    document: UploadFile = File(..., description="The document to analyze"),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a document for standalone ML analysis **without signing**.

    The AI pipeline will:
    1. Extract text from the document (PDF, DOCX, Image, TXT)
    2. Classify the document type (NDA, Invoice, Contract, etc.)
    3. Extract key entities (Persons, Organizations, Dates, Amounts)

    This is useful for previewing AI insights before committing to a signature.
    """
    file_data = await document.read()
    if not file_data:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    result = analyze_file_standalone(file_data, document.filename)

    return AnalyzeResponse(
        filename=result["filename"],
        document_type=result["document_type"],
        confidence=result["confidence"],
        entities=EntityResponse(**result["entities"]) if result["entities"] else EntityResponse(),
        text_preview=result["text_preview"],
        text_length=result["text_length"],
    )


@router.get(
    "/models-status",
    response_model=ModelStatusResponse,
    summary="Check ML model status",
)
async def get_models_status(
    current_user: User = Depends(get_current_user),
):
    """
    Check whether the ML models are loaded and ready.
    Useful for dashboard indicators.
    """
    from backend.ml_models.classifier import _classifier_pipeline
    from backend.ml_models.entity_extractor import _nlp_model

    # Check Tesseract
    tesseract_ok = False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        tesseract_ok = True
    except Exception:
        pass

    return ModelStatusResponse(
        classifier_loaded=_classifier_pipeline is not None,
        ner_loaded=_nlp_model is not None,
        tesseract_available=tesseract_ok,
    )
