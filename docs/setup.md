# Setup, Development & Deployment

## Local development (no Docker)

Requirements: Python 3.12+, Node 22, PostgreSQL 16, Redis 7 (optional locally; required in production).

```bash
# 1. Database roles (once, as a PostgreSQL superuser). Local-only passwords.
psql -U postgres -f infra/postgres/init-roles.sql

# 2. API
cd apps/api
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # then set ENCRYPTION_KEYS (command in the file)
alembic upgrade head        # runs as aisv_owner
DEMO_PASSWORD='choose-a-local-password' python -m scripts.seed_demo   # optional, labelled demo data
uvicorn app.main:app --reload --port 8000
# Crawls: with REDIS_URL set, run a worker in another terminal:
#   celery -A app.worker worker -Q crawl --loglevel INFO
# or set CRAWL_EXECUTION=thread in .env to run crawls in the API process (development only).

# 3. Web (new terminal)
cd apps/web
npm ci
npm run dev                 # http://localhost:3000 ; /api/* is proxied to :8000
```

With `EMAIL_BACKEND=console`, invitation and password-reset emails are printed by the API process.

## Tests and checks

```bash
cd apps/api && . .venv/bin/activate
ruff check app tests scripts && mypy app && pytest -q && pip-audit --skip-editable

cd apps/web
npm run lint -- --max-warnings=0 && npm run typecheck && npm run build && npm audit --omit=dev
# End-to-end (needs the aisv_e2e database migrated; see .github/workflows/ci.yml)
MIGRATION_DATABASE_URL=postgresql+psycopg://aisv_owner:change-me-owner@localhost:5432/aisv_e2e ../api/.venv/bin/alembic -c ../api/alembic.ini upgrade head
npx playwright test
```

After changing API schemas: `python -m scripts.export_openapi` (in `apps/api`) then `npm run gen:api` (in `apps/web`). CI fails if either is stale.

## Docker Compose (reference deployment)

```bash
cp .env.example .env    # replace every placeholder with strong random values
docker compose up -d --build
# open http://localhost:8080
```

Topology: `caddy` (edge, TLS) → `web` (Next.js) → `api` (FastAPI) → `postgres`, `redis`; `worker` (Celery) runs crawls.
`postgres` and `redis` are on an **internal** network. `api` and `worker` additionally join an `egress` network
for outbound verification/crawl requests (SafeFetcher refuses private addresses). Nothing but Caddy publishes ports.

Production checklist:
- `APP_ENV=production` (enforces SMTP email, Redis, encryption keys; enables `__Host-` Secure cookies and HSTS).
- `SITE_ADDRESS=app.yourdomain.com` and `PUBLIC_WEB_URL=https://app.yourdomain.com` (Caddy obtains certificates).
- SMTP settings for invitations/password reset.
- `ALLOW_SIGNUP=false` if you do not want public self-service workspace creation.
- `next build` bakes the API origin into the web image (`API_ORIGIN` build arg, default `http://api:8000`).

### Client IP and rate limiting
Next.js rewrites forward a client-supplied `X-Forwarded-For` unchanged and do not add one. The API therefore
must only trust that header when an edge proxy that **overwrites** it (Caddy does) sits in front, and the API
is reachable only from the web container. Without such a proxy, per-IP limits see one shared IP; per-account
login limits still apply.

### cPanel / shared hosting
Not supported for the application: it needs long-running Python and Node processes, PostgreSQL with
row-level security and roles, and Redis. Use a VPS (2 vCPU / 4 GB minimum) or managed containers.

## Backup and restore

```bash
# Backup (custom format, includes RLS policies and grants)
docker compose exec -T postgres pg_dump -U postgres -d aisv -Fc > aisv-$(date +%F).dump
# Restore into an empty database whose roles already exist (init.sh creates them)
docker compose exec -T postgres pg_restore -U postgres -d aisv --clean --if-exists < aisv-YYYY-MM-DD.dump
```
Keep `ENCRYPTION_KEYS` backed up separately: MFA secrets (and later integration tokens) cannot be decrypted
without them. Test restores regularly; a backup that has not been restored is not a backup.

### Rotating the encryption key
Prepend a new key: `ENCRYPTION_KEYS=new,old`. New secrets use the new key; old ones still decrypt. A
re-encryption job to retire the old key is planned before integration tokens are stored (Phase 3).

## Not yet verified in this environment
`docker compose build` could not be completed inside the cloud development sandbox (containers there have no
route to the package registries, and Docker Hub rate-limited image pulls). `docker compose config` validates.
The same images build in CI-style environments with normal network access; verify on your target host.
