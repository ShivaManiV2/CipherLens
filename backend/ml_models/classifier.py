"""
CipherLens — Intelligent Document Classifier (Zero-Shot NLP)

Uses Hugging Face's `facebook/bart-large-mnli` zero-shot classification
pipeline to categorize documents without any fine-tuning.

The model is loaded lazily on first use and cached in memory for
subsequent requests.
"""

import logging
from typing import List, Optional, Tuple

import httpx
from backend.config import HF_TOKEN

logger = logging.getLogger(__name__)

# ─── Candidate Labels ─────────────────────────────────────
# These are the document categories the model will classify into.
DEFAULT_LABELS: List[str] = [
    "Non-Disclosure Agreement",
    "Invoice",
    "Contract",
    "Medical Record",
    "Legal Document",
    "Financial Report",
    "Job Resume",
    "Letter",
    "Government Document",
    "Other",
]

# ─── Module-level cache ──────────────────────────────────
_classifier_pipeline = None
_MODEL_NAME = "typeform/distilbert-base-uncased-mnli"
_MAX_INPUT_LENGTH = 1024  # Characters to feed the model (truncated for speed)

# ─── Keyword Signals ─────────────────────────────────────
# Used to boost NLI scores when strong textual evidence is present.
KEYWORD_SIGNALS = {
    "Job Resume": [
        "experience", "education", "skills", "objective", "gpa", "internship",
        "bachelor", "master", "university", "college", "linkedin", "github",
        "projects", "certifications", "references", "proficient", "worked at",
        "curriculum vitae", "employment history"
    ],
    "Medical Record": [
        "diagnosis", "patient", "symptoms", "treatment", "disease", "clinical",
        "prescription", "hospital", "doctor", "physician", "pathology", "radiology",
        "therapy", "medication", "icd", "vital signs", "prognosis", "biopsy",
        "dermatology", "skin", "lesion", "tumor", "cancer", "scan", "mri",
        "classification accuracy", "dataset", "model accuracy", "deep learning",
        "convolutional", "neural network", "segmentation", "dermoscopy"
    ],
    "Invoice": [
        "invoice", "bill to", "amount due", "total", "payment", "subtotal",
        "tax", "due date", "purchase order", "quantity", "unit price"
    ],
    "Non-Disclosure Agreement": [
        "non-disclosure", "confidential", "nda", "proprietary", "trade secret",
        "shall not disclose", "confidentiality agreement", "binding agreement"
    ],
    "Contract": [
        "agreement", "hereby agrees", "terms and conditions", "obligations",
        "parties agree", "signed by", "effective date", "breach", "termination",
        "indemnification", "liability"
    ],
    "Financial Report": [
        "revenue", "profit", "loss", "balance sheet", "cash flow", "earnings",
        "fiscal year", "quarterly", "annual report", "assets", "liabilities",
        "shareholder", "dividend", "ebitda"
    ],
    "Legal Document": [
        "whereas", "hereinafter", "pursuant", "jurisdiction", "plaintiff",
        "defendant", "court", "affidavit", "notary", "statute", "legislation"
    ],
    "Government Document": [
        "government", "ministry", "department", "federal", "state", "regulation",
        "official", "gazette", "act of", "public sector", "municipality"
    ],
    "Letter": [
        "dear", "sincerely", "regards", "to whom it may concern",
        "i am writing", "please find", "yours truly", "kind regards"
    ],
}

KEYWORD_CONFIDENCE_THRESHOLD = 0.25  # Min keyword hit rate to trust keyword classification


def _keyword_scores(text: str) -> dict:
    """Return raw keyword hit rates (0–1) per label."""
    text_lower = text.lower()
    scores = {}
    for label, keywords in KEYWORD_SIGNALS.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        scores[label] = hits / len(keywords)
    return scores


def _apply_keyword_boost(text: str, nli_scores: dict) -> Tuple[str, float]:
    """
    Hybrid classification:
    - If keyword evidence is strong (>= threshold), use keyword winner with
      a confidence derived from keyword hit rate (scales 50%–95%).
    - If keyword evidence is weak, fall back to NLI model winner.
    """
    kw = _keyword_scores(text)
    best_kw_label = max(kw, key=kw.get)
    best_kw_rate = kw[best_kw_label]

    if best_kw_rate >= KEYWORD_CONFIDENCE_THRESHOLD:
        # Map keyword hit rate (0.25–1.0) → confidence (50%–95%)
        confidence = round(0.50 + (best_kw_rate - 0.25) * (0.45 / 0.75), 4)
        confidence = min(confidence, 0.95)
        logger.info(f"Keyword classification winner: '{best_kw_label}' (hit rate: {best_kw_rate:.2f})")
        return (best_kw_label, confidence)

    # Fall back to NLI model
    best_nli_label = max(nli_scores, key=nli_scores.get)
    return (best_nli_label, round(nli_scores[best_nli_label], 4))



def _get_classifier():
    """
    Lazy-load the zero-shot classification pipeline.
    Downloads the model on first run (~1.6GB), then uses the HF cache.
    """
    global _classifier_pipeline

    if _classifier_pipeline is None:
        logger.info(f"Loading zero-shot classifier: {_MODEL_NAME} ...")
        try:
            from transformers import pipeline

            _classifier_pipeline = pipeline(
                "zero-shot-classification",
                model=_MODEL_NAME,
                device=-1,  # CPU — set to 0 for GPU
            )
            logger.info("Classifier loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load classifier: {e}")
            raise

    return _classifier_pipeline


def classify_document(
    text: str,
    candidate_labels: Optional[List[str]] = None,
) -> Tuple[str, float]:
    """
    Classify a document's text into one of the candidate categories.

    Args:
        text: Extracted text from the document.
        candidate_labels: Optional custom labels. Defaults to DEFAULT_LABELS.

    Returns:
        Tuple of (predicted_label, confidence_score).
        Returns ("Unknown", 0.0) if classification fails.
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for classification.")
        return ("Unknown", 0.0)

    labels = candidate_labels or DEFAULT_LABELS

    # Truncate to avoid excessive inference time / OOM
    truncated_text = text[:_MAX_INPUT_LENGTH]

    try:
        if HF_TOKEN:
            logger.info("Using Hugging Face Inference API (MoritzLaurer/ModernBERT-large-zeroshot-v2.0)...")
            API_URL = "https://router.huggingface.co/hf-inference/models/facebook/bart-large-mnli"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            payload = {
                "inputs": truncated_text,
                "parameters": {
                    "candidate_labels": labels,
                }
            }
            import time
            with httpx.Client() as client:
                for attempt in range(3):
                    try:
                        resp = client.post(API_URL, headers=headers, json=payload, timeout=60.0)
                        if resp.status_code == 503:
                            wait = int(resp.json().get("estimated_time", 20))
                            logger.info(f"HF model loading, waiting {wait}s (attempt {attempt+1}/3)...")
                            time.sleep(min(wait, 30))
                            continue
                        if resp.status_code >= 400:
                            logger.error(f"HF API error {resp.status_code}: {resp.text}")
                            resp.raise_for_status()
                        break
                    except httpx.ReadTimeout:
                        logger.warning(f"HF API timeout on attempt {attempt+1}/3, retrying...")
                        if attempt == 2:
                            raise
            result = resp.json()
            logger.info(f"HF API raw response: {result}")
            # HF router returns a flat list of {label, score} dicts
            # Normalize into the same format as the local pipeline:
            # {"labels": [...], "scores": [...]}
            if isinstance(result, list) and result and "label" in result[0]:
                sorted_result = sorted(result, key=lambda x: x["score"], reverse=True)
                result = {
                    "labels": [r["label"] for r in sorted_result],
                    "scores": [r["score"] for r in sorted_result],
                }
            elif isinstance(result, list):
                result = result[0]
        else:
            clf = _get_classifier()
            result = clf(
                truncated_text,
                candidate_labels=labels,
                multi_label=False,
                hypothesis_template="This document is a {}."
            )

        # Apply keyword boost and re-rank
        raw_scores = dict(zip(result["labels"], result["scores"]))
        predicted_label, confidence = _apply_keyword_boost(text, raw_scores)
        confidence = round(confidence, 4)

        logger.info(f"Classification: '{predicted_label}' (confidence: {confidence})")
        return (predicted_label, confidence)

    except Exception as e:
        logger.error(f"Classification failed: {e}")
        return ("Unknown", 0.0)


def classify_document_top_n(
    text: str,
    n: int = 3,
    candidate_labels: Optional[List[str]] = None,
) -> List[Tuple[str, float]]:
    """
    Return the top N classifications with their confidence scores.

    Useful for displaying alternative categories on the dashboard.

    Args:
        text: Extracted text from the document.
        n: Number of top results to return.
        candidate_labels: Optional custom labels.

    Returns:
        List of (label, score) tuples sorted by confidence descending.
    """
    if not text or not text.strip():
        return [("Unknown", 0.0)]

    labels = candidate_labels or DEFAULT_LABELS
    truncated_text = text[:_MAX_INPUT_LENGTH]

    try:
        if HF_TOKEN:
            API_URL = "https://router.huggingface.co/hf-inference/models/facebook/bart-large-mnli"
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            payload = {
                "inputs": truncated_text,
                "parameters": {
                    "candidate_labels": labels,
                    "multi_label": False,
                    "hypothesis_template": "This text was written as a {}."
                }
            }
            import time
            with httpx.Client() as client:
                for attempt in range(3):
                    try:
                        resp = client.post(API_URL, headers=headers, json=payload, timeout=60.0)
                        if resp.status_code == 503:
                            wait = int(resp.json().get("estimated_time", 20))
                            logger.info(f"HF model loading, waiting {wait}s (attempt {attempt+1}/3)...")
                            time.sleep(min(wait, 30))
                            continue
                        resp.raise_for_status()
                        break
                    except httpx.ReadTimeout:
                        logger.warning(f"HF API timeout on attempt {attempt+1}/3, retrying...")
                        if attempt == 2:
                            raise
                result = resp.json()
                if isinstance(result, list) and result and "label" in result[0]:
                    sorted_result = sorted(result, key=lambda x: x["score"], reverse=True)
                    result = {
                        "labels": [r["label"] for r in sorted_result],
                        "scores": [r["score"] for r in sorted_result],
                    }
                elif isinstance(result, list):
                    result = result[0]
        else:
            clf = _get_classifier()
            result = clf(
                truncated_text,
                candidate_labels=labels,
                multi_label=False,
                hypothesis_template="This document is a {}."
            )

        top_results = [
            (label, round(score, 4))
            for label, score in zip(result["labels"][:n], result["scores"][:n])
        ]
        return top_results

    except Exception as e:
        logger.error(f"Classification failed: {e}")
        return [("Unknown", 0.0)]
