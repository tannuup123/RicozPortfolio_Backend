# RicozPortfolio Backend

Multi-tenant Project Portfolio Management (PPM) SaaS backend.

**Stack:** FastAPI · SQLAlchemy 2.0 · PostgreSQL · Alembic · Pydantic v2 · JWT · Redis (provisioned, idle for MVP) · Celery (scaffolded, unused)

See [`Doc/architecture.md`](Doc/architecture.md) for full architecture documentation.

---

## Prerequisites

- Python 3.11+
- PostgreSQL 16+
- Redis 7+ (provisioned; not actively used in MVP)
- Docker & Docker Compose (optional, for containerised development)

## Quick Start (Local)

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd RicozPortfolio_Backend

# 2. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Set up environment variables
copy .env.example .env   # then edit .env with your values

# 5. Run database migrations
alembic upgrade head

# 6. Start the dev server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs at `http://localhost:8000/docs`.

## Quick Start (Docker)

```bash
# Copy and edit environment config
copy .env.example .env

# Boot all services (Postgres + Redis + Backend)
docker compose up --build
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+psycopg://...`) | see `.env.example` |
| `JWT_SECRET_KEY` | Secret for signing JWTs | `change-me-to-a-random-secret` |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `FRONTEND_ORIGIN` | Allowed CORS origin (exact Vercel URL in prod) | `http://localhost:5173` |
| `COOKIE_SECURE` | Set `true` in production (HTTPS) | `false` |
| `COOKIE_SAMESITE` | `lax` for local, `none` for cross-domain prod | `lax` |
| `ENVIRONMENT` | `local` / `staging` / `production` | `local` |

## Running Tests

```bash
pytest -v
```

## Linting

```bash
ruff check .
```

## Project Structure

```
RicozPortfolio_Backend/
├── app/
│   ├── api/v1/          # Route modules (one per bounded module)
│   ├── core/            # Config, security, dependencies, exceptions
│   ├── db/              # Engine, session factory, declarative base
│   ├── models/          # SQLAlchemy 2.0 models (Phase 2+)
│   ├── schemas/         # Pydantic v2 request/response schemas
│   ├── services/        # Business logic layer
│   ├── repositories/    # Data access layer (org-scoped queries)
│   ├── tasks/           # Celery tasks (scaffolded, unused for MVP)
│   └── main.py          # FastAPI application entry point
├── alembic/             # Database migrations
├── tests/               # Pytest test suite
├── Doc/                 # Architecture & requirements docs
├── docker-compose.yml   # Local dev: Postgres + Redis + Backend
├── Dockerfile           # Multi-stage production build
├── pyproject.toml       # Dependencies & tooling config
└── .env.example         # Environment variable template
```
