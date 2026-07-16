# Future Improvements

A running list of gaps and enhancements identified from a full pass over the codebase. Grouped by urgency.

## 🔴 Security — fix before any real deployment

- [x] **Remove hardcoded secrets from `docker-compose.yml`.** Fixed — `SECRET_KEY`, `MASTER_KEY`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, and `POSTGRES_DB` are now read from environment variable substitution (`${VAR:?...}`), sourced from a git-ignored `.env` file. Compose will now fail fast with a clear error if a required secret isn't set, instead of falling back to a checked-in value. **The previously committed values are still exposed in git history — rotate them if this repo/history is or will be public.**
- [x] **Restrict CORS.** Fixed — `backend/main.py` now reads `CORS_ORIGINS` from `backend/config.py` (comma-separated list, defaults to `http://localhost:3000`) instead of `allow_origins=["*"]`. Set `CORS_ORIGINS` per environment to the real frontend domain(s) in production.
- [x] **Add a `.env.example` file.** Added at the repo root, covering `SECRET_KEY`, `MASTER_KEY`, `HF_TOKEN`, `CORS_ORIGINS`, and the `POSTGRES_*` variables used by `docker-compose.yml`, with generation commands for the two secret values.
- [ ] **Reconsider client-side token encryption.** `frontend/app/page.tsx` derives an AES-GCM key from a static, hardcoded passphrase/salt to "encrypt" the JWT before storing it client-side. Since the passphrase ships in the JS bundle, this only obscures the token from casual inspection — it isn't real confidentiality against anyone who reads the source. Worth deciding whether this protection is intentional (defense-in-depth against XSS reading raw localStorage) or should be replaced with an httpOnly cookie.
- [ ] **Resolve the stale "not encrypted" comment.** `backend/models/models.py` still has `# TODO: encrypt at rest (Phase 4)` on the `private_key_encrypted` column, even though `backend/core/crypto.py` already implements AES-GCM encryption for it. Confirm the encryption path is actually wired up end-to-end and remove the stale comment — right now it reads as a contradiction between code and docs.

## 🟠 Correctness / accuracy

- [ ] **Fix the classifier model mismatch.** The README and `TECH_STACK.md` reference `facebook/bart-large-mnli`, but `backend/ml_models/classifier.py` actually calls `typeform/distilbert-base-uncased-mnli`. Pick the intended model and make the code and docs agree — this affects both accuracy expectations and inference cost/latency.
- [ ] **Retire (or finish) the "temporary" static frontend mount.** `backend/main.py` mounts a `frontend_dir` as `StaticFiles` with a comment noting it's temporary until "Phase 3" builds a proper Next.js deployment path. Since the frontend now has its own Dockerfile and dev server, confirm whether this static mount is still needed at all.

## 🟡 Testing

- [ ] **Expand backend test coverage.** Only `test_auth.py` and `test_crypto.py` exist. There are no tests for the `documents`, `ml`, or `security` API routers, nor for `ml_models/*` (classifier, entity extractor, anomaly detector) or `services/ml_pipeline.py`. At minimum, add integration tests for the upload → classify → sign → verify flow, since that's the core product loop.
- [ ] **Add a frontend test suite.** There is currently no Jest/Vitest/Playwright setup at all. Even a handful of component/interaction tests (login, upload, verification tab) would catch regressions in the single large `page.tsx` component.
- [ ] **Add CI.** No `.github/workflows` (or equivalent) exists — tests, linting, and type-checking only run locally today. A basic pipeline (lint + `pytest` + `next build`/`tsc --noEmit` on PRs) would catch regressions before merge.

## 🟢 Architecture / code quality

- [ ] **Break up `frontend/app/page.tsx`.** The entire UI (auth, upload, dashboard, insights, verification) lives in one ~968-line component. Splitting it into `components/` (e.g. `LoginForm`, `UploadPanel`, `InsightsCard`, `VerificationTab`) would make it testable and easier to extend.
- [ ] **Consider a state-management or data-fetching layer.** There's no React Query/SWR/Zustand — as more views are added, prop-drilling and manual `useState`/`useEffect` fetch logic will get harder to maintain.
- [ ] **Add Python linting/formatting.** The frontend has ESLint, but there's no `ruff`/`black`/`flake8` config for the backend despite a nontrivial Python codebase across `api/`, `core/`, `db/`, `models/`, `ml_models/`, and `services/`.
- [ ] **Customize `frontend/README.md`.** It's still the unmodified default `create-next-app` boilerplate — worth replacing with a short pointer back to the root README, or removing.

## 🔵 Features / roadmap ideas

- [ ] **Object storage support.** The README already frames storage as "Local filesystem → S3/MinIO-ready" — implementing that swap would make the app viable beyond a single-host deployment.
- [ ] **Audit log UI.** The backend has an `AuditLog` model; consider surfacing a searchable/filterable audit trail view in the frontend rather than only backing it with data.
- [ ] **Multi-file / batch upload and verification.** Currently framed around one document at a time; batch signing/verification would help with real document sets (e.g. a folder of contracts).
- [ ] **Role-based access control.** Today auth is a single `User` model with JWT — no notion of admin vs. standard user, which would matter for any team/enterprise use case implied by "Legal Document" / "Financial Report" categories.
- [ ] **Rate limiting on auth & upload endpoints.** Not currently present; worth adding given the app handles sensitive documents and exposes login/register endpoints publicly.

---

*This list reflects a point-in-time review of the codebase. Re-audit periodically as the "12-week build series" progresses — some items above may already be addressed in later phases not yet reflected in docs.*
