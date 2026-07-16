# CipherLens — Tech Stack

This document explains every major technology used in CipherLens, why it was chosen, and what it's responsible for. It complements the high-level table in [README.md](README.md).

---

## Backend

| Technology | Version | Purpose |
|---|---|---|
| **Python** | 3.10+ (3.11 in Docker) | Primary backend language — chosen for its mature ML/NLP ecosystem (transformers, spaCy, scikit-learn), which a Node or Go backend would lack. |
| **FastAPI** | 0.115.12 | Web framework serving the REST API. Chosen over Flask/Django for native async support (needed for background ML inference), automatic OpenAPI/Swagger docs, and Pydantic-based request validation. |
| **Uvicorn** (`[standard]`) | 0.34.2 | ASGI server that actually runs the FastAPI app; `[standard]` pulls in `uvloop`/`httptools` for performance. |
| **python-multipart** | 0.0.20 | Required by FastAPI to parse `multipart/form-data` — needed for file uploads. |
| **SQLAlchemy** | 2.0.40 | ORM used to define and query the `User`, `Document`, and `AuditLog` tables without hand-writing SQL. Backs both SQLite (default/dev) and PostgreSQL (production, via `DATABASE_URL`). |
| **psycopg2-binary** | ≥2.9.9 | PostgreSQL driver, used when `DATABASE_URL` points at Postgres (as in `docker-compose.yml`). |
| **python-jose** (`[cryptography]`) | 3.4.0 | Issues and verifies JWT access tokens for stateless authentication. |
| **passlib** (`[bcrypt]`) / **bcrypt** | 1.7.4 / 4.3.0 | Hashes and verifies user account passwords before they touch the database. |
| **pycryptodome** | 3.22.0 | Core cryptography engine — generates RSA-2048 keypairs, signs document hashes (PKCS#1 v1.5), and AES-GCM-encrypts private keys at rest. This is the library that gives CipherLens its "signing" feature, distinct from the JWT/bcrypt libraries above which only protect auth. |
| **aiofiles** | 24.1.0 | Non-blocking file reads/writes so large document uploads don't stall the event loop. |
| **python-dotenv** | 1.1.0 | Loads `SECRET_KEY`, `MASTER_KEY`, `HF_TOKEN`, `DATABASE_URL`, etc. from a local `.env` file in development. |

## AI / NLP / Document Processing

| Technology | Version | Purpose |
|---|---|---|
| **Hugging Face `transformers`** | ≥4.40.0 | Runs the zero-shot text classification model that auto-tags each upload (NDA, Invoice, Contract, Medical Record, Legal Document, Financial Report, Job Resume, etc.) without needing a labeled training set for every category. |
| **PyTorch (`torch`)** | ≥2.2.0 | The tensor/inference runtime `transformers` sits on top of. |
| **spaCy** (`en_core_web_sm`) | ≥3.7.0 | Named-entity recognition — pulls structured entities (names, dates, orgs, monetary amounts) out of extracted document text for the "AI Telemetry" dashboard. |
| **scikit-learn** | ≥1.4.0 | Powers the anomaly-detection layer (flagging unusual documents/behavior) added in "Phase 4." |
| **PyMuPDF (`fitz`)** | ≥1.24.0 | Extracts text directly from PDFs (fast path, no OCR needed for text-based PDFs). |
| **pytesseract** + **Pillow** | ≥0.3.10 / ≥10.0.0 | OCR fallback for scanned/image-based documents — Pillow loads/preprocesses the image, pytesseract (wrapping the Tesseract OCR engine) extracts text from it. |
| **python-docx** | ≥1.1.0 | Extracts text from `.docx` Word documents. |

> **Note on model choice:** the README's tech-stack table lists `facebook/bart-large-mnli`, but `backend/ml_models/classifier.py` currently calls `typeform/distilbert-base-uncased-mnli` via the Hugging Face Inference API. DistilBERT is the smaller/faster of the two — worth confirming which one is actually intended before publishing further docs, since this is a real discrepancy between README and code.

## Testing (Backend)

| Technology | Purpose |
|---|---|
| **pytest** / **pytest-asyncio** | Test runner for the backend; `pytest-asyncio` is needed because FastAPI route handlers and DB calls are async. |
| **httpx** | Used both as the test client for hitting FastAPI routes in tests, and as the HTTP client the app itself uses to call the Hugging Face Inference API. |

Coverage today is narrow: `backend/tests/test_auth.py` (register/login) and `backend/tests/test_crypto.py` (RSA sign/verify, AES encrypt/decrypt). There are no tests yet for the `documents`, `ml`, or `security` routers, nor for the ML pipeline itself — see [FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md).

## Frontend

| Technology | Version | Purpose |
|---|---|---|
| **Next.js** | 15.1.0 | React framework (App Router) — provides routing, bundling, dev server, and production build/optimizations in one tool. |
| **React** / **react-dom** | 19.0.0 | UI rendering library Next.js is built on. |
| **TypeScript** | ^5.0.0 | Adds static typing across the frontend to catch mistakes (e.g. malformed API response shapes) before runtime. |
| **Tailwind CSS** | ^4.0.0 (via `@tailwindcss/postcss`) | Utility-first CSS framework used for the glassmorphism styling, layout, and responsive design without hand-written CSS files. |
| **ESLint** (`eslint-config-next`) | ^9.0.0 / 15.1.0 | Lints the TypeScript/React code against Next.js's recommended rules. |

There is currently **no state-management library** (Redux, Zustand, etc.) and **no frontend test framework** (Jest/Vitest/Playwright) — the entire UI lives in a single ~968-line `frontend/app/page.tsx` component using React's built-in `useState`/`useEffect`.

## Database

| Technology | Purpose |
|---|---|
| **SQLite** (default) | Zero-setup embedded database for local development — `sqlite:///./cipherlens.db`. |
| **PostgreSQL 15** (production path) | Swapped in via `DATABASE_URL`; used in `docker-compose.yml` for a production-like local stack. SQLAlchemy's ORM abstraction means the same model/query code works against either. |

## Infrastructure / Deployment

| Technology | Purpose |
|---|---|
| **Docker** (`backend/Dockerfile`, `frontend/Dockerfile`) | Containerizes the backend (Python 3.11-slim + `tesseract-ocr`, `libpq-dev`, `gcc` for native deps) and frontend (Next.js) independently. |
| **Docker Compose** (`docker-compose.yml`) | Orchestrates a local 3-container stack: `db` (Postgres), `backend` (FastAPI, port 8080), `frontend` (Next.js, port 3000). |
| **PowerShell (`start_local.ps1`)** | Windows-native alternative to Docker Compose for day-to-day development — launches backend and frontend as separate local processes. |

There is currently **no CI/CD pipeline** (no `.github/workflows` or equivalent) — tests and linting run only locally today.

## Why this stack, in one paragraph

FastAPI + SQLAlchemy gives a fast, typed, async-friendly REST layer without locking into a database engine, while pycryptodome supplies the actual cryptographic primitives (RSA signing, AES-GCM) that are the product's core value — separate from JWT/bcrypt, which only protect *access* to the app rather than the documents themselves. Python was the natural backend choice specifically because the AI features (Hugging Face `transformers`, spaCy, scikit-learn, PyMuPDF/pytesseract for extraction) all live in Python's ecosystem, avoiding a second service/language just to run inference. On the frontend, Next.js + React + Tailwind is a conventional, fast-to-ship combination for a single-page dashboard-style app, and Docker Compose lets the whole thing (Postgres included) run identically on any machine.
