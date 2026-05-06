"""
CipherLens — SQLAlchemy ORM Models

Three core tables:
  • User       — Stores credentials, RSA key pair, and profile info
  • Document   — Metadata for every signed document (hash, signature, ML type)
  • AuditLog   — Immutable record of every security-relevant action
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, Boolean, Float
)
from sqlalchemy.orm import relationship
from backend.db.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    public_key = Column(Text, nullable=False)
    private_key_encrypted = Column(Text, nullable=False)  # TODO: encrypt at rest (Phase 4)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)

    # Relationships
    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)           # UUID-based stored filename
    original_filename = Column(String(255), nullable=False)  # User-facing original name
    file_hash = Column(String(64), nullable=False)           # SHA-256 hex digest
    signature = Column(Text, nullable=False)                 # Base64-encoded RSA signature
    file_size = Column(Integer)                              # Bytes
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    # ─── Phase 2: ML Metadata ────────────────────────────
    document_type = Column(String(100), default="processing...")   # ML classification label
    ml_classification_confidence = Column(Float, default=0.0)     # Confidence score (0.0–1.0)
    extracted_entities = Column(Text, default="{}")                # JSON string of extracted entities
    extracted_text_preview = Column(Text, default="")              # First 500 chars of extracted text
    ml_processed = Column(Boolean, default=False)                  # True once ML pipeline completes

    # Relationships
    owner = relationship("User", back_populates="documents")

    def __repr__(self):
        return f"<Document(id={self.id}, name='{self.original_filename}')>"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)    # REGISTER, LOGIN, SIGN, VERIFY, ML_PROCESS
    ip_address = Column(String(45))                # IPv4 or IPv6
    details = Column(Text)
    timestamp = Column(DateTime, default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', user={self.user_id})>"
