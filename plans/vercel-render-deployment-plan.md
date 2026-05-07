# Deploy Automated Literature Review: Vercel + Render + Render Postgres

## Summary

Deploy the app as a split production setup:

- **Frontend:** Vercel, using `frontend/` as the project root.
- **Backend:** Render Web Service, running FastAPI from repo root.
- **Database:** Render Postgres in the same region as the backend.
- **Uploads:** Render persistent disk mounted for `REFERENCE_UPLOAD_DIR`.

Use provider URLs first: `*.vercel.app` and `*.onrender.com`. Add custom domains later after the provider-URL deployment is verified.

## Key Changes

- Add one backend deployment config surface before deploying: `CORS_ALLOWED_ORIGINS`, a comma-separated env var used by `backend/main.py` instead of hardcoded localhost-only origins.
- Keep existing API routes unchanged. No request/response schema changes are needed.
- Set `REFERENCE_UPLOAD_DIR=/var/data/reference_uploads` on Render and attach a persistent disk mounted at `/var/data`.
- If repo files are changed for CORS/docs, update `JOURNAL.md` per repo rules.

## Deployment Steps

### 1. Preflight Locally

Run backend checks:

```bash
uv run ruff check .
uv run mypy backend/
uv run pytest tests/ -x
```

Run frontend checks:

```bash
cd frontend
npm install
./node_modules/.bin/tsc --noEmit
npm run build
```

### 2. Create Render Postgres

- Create a Render Postgres database in the same region planned for the backend.
- Copy the **Internal Database URL**.
- Use it for backend `DATABASE_URL`; the app already normalizes `postgresql://` to `postgresql+asyncpg://`.

### 3. Create Render Backend Web Service

- Root directory: repo root.
- Runtime: Python.
- Python version: 3.11.
- Build command:

```bash
pip install -U pip && pip install -e .
```

- Pre-deploy command:

```bash
alembic upgrade head
```

- Start command:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

- Health check path:

```text
/healthz
```

- Attach disk:

```text
name: reference-uploads
mount path: /var/data
size: 5 GB
```

### 4. Set Render Backend Environment Variables

```env
APP_NAME=Literature Review API
DATABASE_URL=<Render internal Postgres URL>
JWT_SECRET_KEY=<generated strong secret>
JWT_ALGORITHM=HS256
OPENROUTER_API_KEY=<your key>
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_DOCUMENT_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_PDF_ENGINE=native
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
TAVILY_API_KEY=<optional, needed for Deep Search web fallback>
TAVILY_BASE_URL=https://api.tavily.com
SEMANTIC_SCHOLAR_API_KEY=<optional>
ADMIN_EMAILS=<comma-separated admin emails>
REFERENCE_UPLOAD_DIR=/var/data/reference_uploads
GOOGLE_CLIENT_ID=<optional>
CORS_ALLOWED_ORIGINS=https://<vercel-production-url>
```

### 5. Create Vercel Frontend Project

- Import the same GitHub repo.
- Root Directory:

```text
frontend
```

- Framework: Next.js.
- Install command:

```bash
npm install
```

- Build command:

```bash
npm run build
```

- Production env vars:

```env
NEXT_PUBLIC_API_BASE_URL=https://<render-backend>.onrender.com
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<optional>
```

### 6. Finalize CORS

- After Vercel gives the production URL, update Render:

```env
CORS_ALLOWED_ORIGINS=https://<vercel-production-url>
```

- Redeploy backend.
- Do not support arbitrary preview URLs in v1; add staging/preview CORS later if needed.

## Test Plan

- Open `https://<render-backend>.onrender.com/healthz`; expect `{"status":"ok"}`.
- Open the Vercel URL and confirm no browser CORS errors.
- Register/login through the frontend.
- Create a project from the first chat message and verify papers load.
- Upload a PDF, confirm it appears as an uploaded paper, then restart/redeploy the Render service and confirm the uploaded file still works.
- Send a standard chat message and verify streaming response.
- Run Deep Search with and without `TAVILY_API_KEY`; without Tavily, academic/project evidence should still work with warnings.
- If `ADMIN_EMAILS` is set, verify `/admin/usage` loads for an allowlisted account.

## Assumptions

- Dashboard-first deployment is the source of truth for the first launch; no `render.yaml` or `vercel.json` is required yet.
- Provider URLs are used first; custom domains are deferred.
- Render service uses a paid plan because persistent disks and pre-deploy migrations are part of this plan.
- Persistent disk is acceptable for v1. If the backend later scales to multiple instances, replace disk uploads with S3/R2 object storage.
- Render Postgres and Render backend stay in the same region and use the internal database URL.

## References

- Render FastAPI docs: <https://render.com/docs/deploy-fastapi>
- Render deploy/pre-deploy docs: <https://render.com/docs/deploys>
- Render Postgres docs: <https://render.com/docs/databases>
- Render health checks: <https://render.com/docs/health-checks>
- Vercel build docs: <https://vercel.com/docs/deployments/configure-a-build>
- Vercel environment variables: <https://vercel.com/docs/projects/environment-variables>
