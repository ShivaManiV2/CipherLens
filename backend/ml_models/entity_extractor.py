"""
CipherLens — Named Entity Extraction (NER)

Uses spaCy's pre-trained English model to extract structured entities
from document text: persons, organizations, dates, monetary amounts,
locations, and legal references.

The spaCy model is loaded lazily on first use and cached in memory.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Module-level cache ──────────────────────────────────
_nlp_model = None
_MODEL_NAME = "en_core_web_sm"
_MAX_TEXT_LENGTH = 100_000  # spaCy limit for large docs


# ─── Entity type mapping ─────────────────────────────────
# Maps spaCy's entity labels to our structured categories
ENTITY_MAP = {
    "PERSON": "persons",
    "ORG": "organizations",
    "DATE": "dates",
    "MONEY": "amounts",
    "GPE": "locations",       # Geopolitical entities (countries, cities)
    "LOC": "locations",       # Non-GPE locations
    "LAW": "legal_references",
    "NORP": "groups",         # Nationalities, religious groups, political groups
    "EVENT": "events",
}


def _get_nlp():
    """
    Lazy-load the spaCy NLP model.
    Downloads `en_core_web_sm` if not already installed.
    """
    global _nlp_model

    if _nlp_model is None:
        logger.info(f"Loading spaCy model: {_MODEL_NAME} ...")
        try:
            import spacy
            try:
                _nlp_model = spacy.load(_MODEL_NAME)
            except OSError:
                # Model not installed — download it
                logger.info(f"Model {_MODEL_NAME} not found, downloading...")
                from spacy.cli import download
                download(_MODEL_NAME)
                _nlp_model = spacy.load(_MODEL_NAME)

            logger.info("spaCy model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load spaCy model: {e}")
            raise

    return _nlp_model


def extract_entities(text: str) -> Dict[str, List[str]]:
    """
    Extract named entities from document text.

    Args:
        text: Extracted text from the document.

    Returns:
        Dictionary with entity categories as keys and lists of
        deduplicated entity strings as values. Example:
        {
            "persons": ["John Doe", "Jane Smith"],
            "organizations": ["Acme Corp"],
            "dates": ["January 1, 2025"],
            "amounts": ["$50,000"],
            "locations": ["New York"],
            "legal_references": [],
            "groups": [],
            "events": []
        }
    """
    # Initialize empty result structure
    result: Dict[str, List[str]] = {
        "persons": [],
        "organizations": [],
        "dates": [],
        "amounts": [],
        "locations": [],
        "legal_references": [],
        "groups": [],
        "events": [],
    }

    if not text or not text.strip():
        logger.warning("Empty text provided for entity extraction.")
        return result

    # Truncate very long documents to avoid memory issues
    truncated_text = text[:_MAX_TEXT_LENGTH]

    try:
        nlp = _get_nlp()
        doc = nlp(truncated_text)

        # Collect entities with deduplication
        seen: Dict[str, set] = {key: set() for key in result}

        for ent in doc.ents:
            category = ENTITY_MAP.get(ent.label_)
            if category and ent.text.strip():
                cleaned = ent.text.strip()
                if cleaned not in seen[category]:
                    seen[category].add(cleaned)
                    result[category].append(cleaned)

        # Limit to top 20 per category to keep response size manageable
        for key in result:
            result[key] = result[key][:20]

        total = sum(len(v) for v in result.values())
        logger.info(f"Extracted {total} entities across {len(result)} categories.")

    except Exception as e:
        logger.error(f"Entity extraction failed: {e}")

    return result


def get_entity_summary(entities: Dict[str, List[str]]) -> str:
    """
    Generate a human-readable summary of extracted entities.

    Useful for audit logs and quick previews.
    """
    parts = []
    for category, items in entities.items():
        if items:
            label = category.replace("_", " ").title()
            parts.append(f"{label}: {', '.join(items[:5])}")

    return " | ".join(parts) if parts else "No entities found"
