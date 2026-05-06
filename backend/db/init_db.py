"""
CipherLens — Database Initialization
Creates all tables on startup if they don't already exist.
Data is preserved across restarts.
"""

from backend.db.database import engine, Base
from backend.models.models import User, Document, AuditLog  # noqa: F401 — import to register models


def init_db():
    """Initialize DB schema. Only creates tables that don't exist yet — data is preserved."""
    Base.metadata.create_all(bind=engine)
