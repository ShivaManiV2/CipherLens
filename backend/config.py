"""
CipherLens — Centralized Configuration
Loads settings from environment variables with sensible defaults for local development.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Application ──────────────────────────────────────────
APP_NAME = "CipherLens"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "AI-Enhanced Secure Document Signing & Verification Platform"

# ─── Security / JWT ───────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "cipherlens-dev-secret-CHANGE-IN-PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# ─── CORS ──────────────────────────────────────────────────
# Comma-separated list of allowed frontend origins, e.g. "http://localhost:3000,https://app.example.com"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

# ─── Encryption at Rest ───────────────────────────────────
# AES-256 requires a 32-byte key. In dev, we use a fixed 32-byte string.
# In production, this should be a strong securely generated key provided via env.
MASTER_KEY = os.getenv("MASTER_KEY", "cipherlens-dev-master-key-32byte").encode("utf-8")
if len(MASTER_KEY) != 32:
    MASTER_KEY = MASTER_KEY.ljust(32, b"x")[:32]

# ─── Database ─────────────────────────────────────────────
# SQLite for local dev — swap to PostgreSQL via env var for production
# Example: DATABASE_URL=postgresql://user:pass@localhost:5432/cipherlens
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cipherlens.db")

# ─── File Storage ─────────────────────────────────────────
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
DOCUMENTS_DIR = os.path.join(STORAGE_DIR, "documents")
SIGNATURES_DIR = os.path.join(STORAGE_DIR, "signatures")

# ─── Machine Learning ─────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN", "")
