"""
CipherLens — ML Models Package

Provides AI-powered document intelligence:
  • text_extractor  — Multi-format text extraction (PDF, Image, DOCX, TXT)
  • classifier      — Zero-shot document classification (NLP)
  • entity_extractor — Named entity recognition (NER)
"""

from backend.ml_models.text_extractor import extract_text
from backend.ml_models.classifier import classify_document, classify_document_top_n
from backend.ml_models.entity_extractor import extract_entities, get_entity_summary

__all__ = [
    "extract_text",
    "classify_document",
    "classify_document_top_n",
    "extract_entities",
    "get_entity_summary",
]
