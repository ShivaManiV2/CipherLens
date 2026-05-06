"""
CipherLens — ML Pipeline Orchestration Service

Coordinates the full ML workflow for a document:
  1. Extract text (PDF / Image / DOCX / TXT)
  2. Classify document type (zero-shot NLP)
  3. Extract named entities (NER)
  4. Persist results to the database

This runs as a FastAPI BackgroundTask so it does NOT block
the signing response. If ML fails, the document is still signed
and stored — ML fields simply remain at their defaults.
"""

import json
import logging

from sqlalchemy.orm import Session

from backend.db.database import SessionLocal
from backend.ml_models.text_extractor import extract_text
from backend.ml_models.classifier import classify_document
from backend.ml_models.entity_extractor import extract_entities, get_entity_summary
from backend.models.models import Document, AuditLog
from backend.services.storage import storage_service

logger = logging.getLogger(__name__)

# Maximum characters to store as a preview
_PREVIEW_LENGTH = 500


def process_document_ml(doc_id: int) -> None:
    """
    Run the full ML pipeline on a stored document.

    This is designed to be called from a BackgroundTask. It opens
    its own DB session so it's independent of the request lifecycle.

    Steps:
        1. Load document record & read file from storage
        2. Extract text based on file type
        3. Classify document using zero-shot NLP
        4. Extract named entities using spaCy NER
        5. Update the Document record with all ML results
        6. Log the ML processing action to the audit trail

    Args:
        doc_id: Primary key of the Document to process.
    """
    db: Session = SessionLocal()

    try:
        # ─── 1. Load document ────────────────────────────
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            logger.error(f"ML Pipeline: Document {doc_id} not found")
            return

        logger.info(f"ML Pipeline: Processing document {doc_id} ({doc.original_filename})")

        # Read file bytes from storage
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context — use run_coroutine_threadsafe
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    storage_service.get_document(doc.filename), loop
                )
                file_data = future.result(timeout=30)
            else:
                file_data = loop.run_until_complete(
                    storage_service.get_document(doc.filename)
                )
        except RuntimeError:
            # No event loop — create one
            file_data = asyncio.run(storage_service.get_document(doc.filename))

        # ─── 2. Extract text ─────────────────────────────
        logger.info(f"ML Pipeline: Extracting text from {doc.original_filename}")
        text = extract_text(file_data, doc.original_filename)

        text_preview = text[:_PREVIEW_LENGTH] if text else ""

        if not text:
            logger.warning(f"ML Pipeline: No text extracted from {doc.original_filename}")
            doc.document_type = "Unreadable"
            doc.ml_classification_confidence = 0.0
            doc.extracted_entities = "{}"
            doc.extracted_text_preview = ""
            doc.ml_processed = True
            db.commit()
            return

        # ─── 3. Classify document ────────────────────────
        logger.info(f"ML Pipeline: Classifying document {doc_id}")
        doc_type, confidence = classify_document(text)

        # ─── 4. Extract entities ─────────────────────────
        logger.info(f"ML Pipeline: Extracting entities from document {doc_id}")
        entities = extract_entities(text)
        entities_json = json.dumps(entities, ensure_ascii=False)

        # ─── 5. Update document record ───────────────────
        doc.document_type = doc_type
        doc.ml_classification_confidence = confidence
        doc.extracted_entities = entities_json
        doc.extracted_text_preview = text_preview
        doc.ml_processed = True

        # ─── 6. Audit log ────────────────────────────────
        entity_summary = get_entity_summary(entities)
        db.add(
            AuditLog(
                user_id=doc.owner_id,
                action="ML_PROCESS",
                ip_address="background-task",
                details=(
                    f"ML analysis complete for '{doc.original_filename}': "
                    f"Type={doc_type} ({confidence:.1%}), "
                    f"Entities: {entity_summary[:200]}"
                ),
            )
        )

        db.commit()
        logger.info(
            f"ML Pipeline: Document {doc_id} processed — "
            f"Type='{doc_type}' (confidence={confidence:.1%}), "
            f"Entities extracted: {sum(len(v) for v in entities.values())}"
        )

    except Exception as e:
        logger.error(f"ML Pipeline: Failed for document {doc_id}: {e}", exc_info=True)
        # Mark as processed even on failure so we don't retry indefinitely
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc and not doc.ml_processed:
                doc.document_type = "Processing Failed"
                doc.ml_processed = True
                db.commit()
        except Exception:
            pass

    finally:
        db.close()


def analyze_file_standalone(file_data: bytes, filename: str) -> dict:
    """
    Run ML analysis on raw file data without saving to DB.

    Useful for the standalone /api/ml/analyze endpoint.

    Args:
        file_data: Raw bytes of the file.
        filename: Original filename.

    Returns:
        Dictionary with ML results:
        {
            "filename": str,
            "document_type": str,
            "confidence": float,
            "entities": dict,
            "text_preview": str,
            "text_length": int,
        }
    """
    # Extract text
    text = extract_text(file_data, filename)

    if not text:
        return {
            "filename": filename,
            "document_type": "Unreadable",
            "confidence": 0.0,
            "entities": {},
            "text_preview": "",
            "text_length": 0,
        }

    # Classify
    doc_type, confidence = classify_document(text)

    # Extract entities
    entities = extract_entities(text)

    return {
        "filename": filename,
        "document_type": doc_type,
        "confidence": round(confidence, 4),
        "entities": entities,
        "text_preview": text[:_PREVIEW_LENGTH],
        "text_length": len(text),
    }
