# RicozPortfolio — Architecture

**Status:** Approved for MVP implementation.
**Companion docs:** `mvp-requirements.md` (what to build), `implementation-plan.md` (how/when to build it, phase-by-phase).
**Style used below:** `[DECIDED]` = confirmed in prior discussion. `[PROPOSED]` = a reasonable default not explicitly discussed; open to change without affecting scope.

---

## 1. System Overview

RicozPortfolio is a multi-tenant Project Portfolio Management (PPM) SaaS covering the lifecycle: **Strategy → Demand/Ideas → Business Case → Approval → Portfolio Planning → Project Execution → Monitoring (Budget/Risk) → Dashboards**. `[DECIDED]`

**Deployment topology `[DECIDED]`:**

```
Browser
   │  HTTPS
   ▼
Vercel (Frontend)                RicozPortfolio-Frontend repo
   │  fetch(credentials:'include')
   ▼
Railway / Render (Backend)       RicozPortfolio-Backend repo
   │  FastAPI + Uvicorn, modular monolith
   ├──▶ Managed PostgreSQL (PaaS-provided)
   └──▶ Redis (provisioned, idle for MVP)
```

**Two independent repositories `[DECIDED]`:**
- `RicozPortfolio-Backend` — FastAPI, SQLAlchemy 2.0, PostgreSQL, Alembic, Pydantic v2, JWT, Redis, Celery (scaffolded, unused), Pytest.
- `RicozPortfolio-Frontend` — React, TypeScript, Vite, Tailwind CSS.

Each is independently version-controlled, tested, built, and deployed. Docker Compose is kept in both for local development and as a portability path to any host beyond the chosen PaaS. `[DECIDED]`

**Architectural style `[DECIDED]`:** modular monolith on the backend — one deployable FastAPI service, internally organized into clearly bounded modules (auth, organizations, strategy, demand, business-cases, approvals, portfolios, projects, tasks, milestones, risks, budgets, dashboards). Not microservices: the MVP's traffic and team size don't justify that cost, and a modular monolith keeps a clean extraction path if a module ever needs to split out later.

---

## 2. Repository Structures

### `RicozPortfolio-Backend`
```
RicozPortfolio-Backend/
├── app/
│   ├── api/v1/               # one router module per bounded module
│   │   ├── auth.py
│   │   ├── organizations.py
│   │   ├── users.py
│   │   ├── strategic_goals.py
│   │   ├── ideas.py
│   │   ├── business_cases.py
│   │   ├── approvals.py
│   │   ├── portfolios.py
│   │   ├── projects.py
│   │   ├── tasks.py
│   │   ├── milestones.py
│   │   ├── risks.py
│   │   ├── budgets.py
│   │   └── dashboards.py
│   ├── core/
│   │   ├── config.py          # pydantic-settings
│   │   ├── security.py        # hashing, JWT, cookie helpers
│   │   ├── deps.py            # get_db, get_current_user, require_role
│   │   └── exceptions.py      # domain exceptions + global handler
│   ├── models/                # SQLAlchemy 2.0 declarative models, one file per aggregate
│   ├── schemas/                # Pydantic v2 request/response models
│   ├── services/                # business logic, one file per module
│   ├── repositories/            # SQLAlchemy queries, always org-scoped
│   ├── db/
│   │   ├── base.py
│   │   └── session.py
│   ├── tasks/                   # Celery task scaffold — empty for MVP
│   └── main.py
├── alembic/
│   ├── versions/
│   └── env.py
├── tests/
│   ├── unit/
│   ├── api/
│   └── conftest.py
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── alembic.ini
├── pyproject.toml
├── .github/workflows/ci.yml
├── Doc/
│   ├── architecture.md
│   ├── mvp-requirements.md
│   └── implementation-plan.md
└── README.md
```

### `RicozPortfolio-Frontend`
```
RicozPortfolio-Frontend/
├── src/
│   ├── api/                  # typed client, one module per resource
│   ├── auth/                 # AuthContext, useAuth, ProtectedRoute, bootstrapAuth
│   ├── components/
│   │   ├── ui/
│   │   └── layout/
│   ├── features/
│   │   ├── auth/
│   │   ├── strategy/
│   │   ├── demand/
│   │   ├── portfolios/
│   │   └── projects/
│   ├── routes.tsx
│   └── main.tsx
├── Dockerfile
├── .env.example
├── vite.config.ts
├── tailwind.config.ts
├── .github/workflows/ci.yml
├── Doc/                       # same three docs, kept in sync for frontend context
│   ├── architecture.md
│   ├── mvp-requirements.md
│   └── implementation-plan.md
└── README.md
```

`[DECIDED]` No shared monorepo tooling. The only contract between repos is the API surface (Section 6). Place this same set of three docs in both repos' `Doc/` folder so an AI coding agent working in either repo has full context without needing the other repo open.

---

## 3. Backend Architecture

**Layering and request flow (modular monolith, each module follows this identically):**

```
HTTP request
  → Router (api/v1/<module>.py)       — path/query params, delegates to service
  → Pydantic schema                    — validates input
  → Dependency injection                — get_db, get_current_user, require_role(...)
  → Service (services/<module>_service.py)  — business rules, orchestration
  → Repository (repositories/<module>_repository.py) — SQLAlchemy queries, org-scoped
  → PostgreSQL
  → Service maps result → response schema
  → Router returns response
```

| Concern | Lives in | Notes |
|---|---|---|
| Authentication | `core/security.py`, `core/deps.py` | JWT verify + cookie handling |
| Authorization (RBAC) | `core/deps.py::require_role(...)` + service-layer ownership checks | Role check at router level; "is this PM a member of this project" at service level |
| Validation | `schemas/` | Pydantic v2, `model_config = ConfigDict(from_attributes=True)` |
| Business logic | `services/` | ROI calc, approval rules, health-flag rule, idea→project conversion |
| Data access | `repositories/` | Every query filtered by `organization_id`; never trust a client-supplied org id |
| Background jobs | `tasks/` | Scaffolded only; no MVP feature requires it (Section 7) |
| Caching | none for MVP | Would live in `services/` if added, never in `repositories/` |
| Error handling | `core/exceptions.py` | Domain exceptions raised in `services/`, mapped to HTTP by a global FastAPI exception handler — routers never catch business errors directly |
| Logging | stdlib `logging`, structured/JSON in prod | Configured in `core/config.py`; `[PROPOSED]` request-id middleware for traceability |

**Module boundaries (modular monolith discipline):** each module (`ideas`, `projects`, etc.) only calls another module's *service* layer, never reaches into another module's repository or models directly. This is what keeps the monolith "modular" and preserves a clean extraction path later without requiring it now.

---

## 4. Frontend Architecture

- **State management `[PROPOSED]`:** React Query for server state/caching; local component state/Context for UI state. No Redux.
- **API client (`src/api/client.ts`):** `fetch` wrapper, always `credentials: 'include'` (required for the cookie-based refresh flow, Section 5), attaches `Authorization: Bearer <access_token>` from in-memory state, single-retry-after-refresh on 401.
- **Auth (`src/auth/`):** access token held in memory only (React state/ref) — never `localStorage`/`sessionStorage`. `bootstrapAuth.ts` silently calls refresh on app load to re-establish session from the httpOnly cookie.
- **Forms:** `react-hook-form` + `zod`, schemas mirroring backend Pydantic validation.
- **Routing/protection:** `react-router-dom`; `<ProtectedRoute roles={[...]}>` reads `AuthContext`.
- **Error/loading states:** React Query's `isLoading`/`isError`, surfaced via shared `<LoadingState/>` / `<ErrorState/>`.

**Page hierarchy:**
```
Login / Register
Dashboard (org home)
Strategy → Goals
Demand → Ideas List → Idea Detail (Business Case, Approval, Convert-to-Project)
Portfolios → Portfolio List → Portfolio Detail (dashboard)
Projects → Project Detail (Overview, Tasks, Milestones, Risks, Budget, Team)
Admin (org_admin only) → Users & Roles
```

---

## 5. Authentication & Authorization

**Token flow `[DECIDED]`:**

| Token | Storage | Lifetime `[PROPOSED]` | Transport |
|---|---|---|---|
| Access token (JWT) | In-memory, frontend | 15–30 min | `Authorization: Bearer` header |
| Refresh token | httpOnly, Secure cookie, set by backend | 7 days, rotated on each use `[PROPOSED]` | Automatic cookie, scoped `Path=/api/v1/auth` |

**Cookie settings (cross-domain — Vercel ≠ Railway/Render domain):**
```
Set-Cookie: refresh_token=<value>; HttpOnly; Secure; SameSite=None; Path=/api/v1/auth; Max-Age=604800
```
`SameSite=Lax` will **not** work cross-domain — it must be `None; Secure`, which requires HTTPS (true in prod on both PaaS providers). `[PROPOSED]` Local dev exception: `SameSite=Lax` only when `ENVIRONMENT=local`, config-driven, documented, never shipped to prod.

**CSRF mitigation `[PROPOSED]`:** access token (used for all real API calls) is never in a cookie, so a CSRF-triggered refresh call yields nothing to the attacker; additionally require a custom header (e.g. `X-Requested-With`) on `/auth/refresh` to block naive cross-site form-based triggers.

**Endpoints:** `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`.

**Roles `[DECIDED — from product requirements]`:**

| Role | Scope |
|---|---|
| `org_admin` | Full org control: users, roles, org settings, plus everything below |
| `portfolio_manager` | Strategic goals, idea review, business cases, approvals, idea→project conversion, portfolios, view all org projects |
| `project_manager` | Manage assigned projects: members, tasks, milestones, budget, risks |
| `team_member` | View assigned projects/tasks, update own task status, submit ideas |

Enforcement: role-level via `require_role(...)` FastAPI dependency at the router; project-membership-level (e.g., "is this PM actually on this project") in the service layer.

**Multi-tenancy `[DECIDED]`:** shared database, shared schema, `organization_id` on every tenant-scoped table; every repository method filters/sets it explicitly. `[PROPOSED, deferred]` Postgres Row-Level Security is a future hardening step, not required for MVP since isolation is enforced in the service/repository layers.

**Identity model `[DECIDED]`:** `users.email` is globally `UNIQUE`. One email = one user = one organization for MVP. Multi-org membership, if ever needed, is a future extension (`organization_memberships` join table) — not built now.

---

## 6. API Architecture

- Base path: `/api/v1`.
- Auth: `Authorization: Bearer <access_token>` on all protected routes except refresh/logout (cookie-based).
- Error shape (global handler, consistent everywhere):
  ```json
  { "error": { "code": "IDEA_NOT_APPROVED", "message": "Idea must be approved before conversion." } }
  ```
- Pagination `[PROPOSED]`: `?limit=20&offset=0` → `{ "items": [...], "total": N }`.
- Filtering: query params match field names (`?status=submitted`).
- Timestamps: ISO 8601 UTC. IDs: UUID strings.
- CORS: `allow_origins=[<exact Vercel URL>, http://localhost:5173]`, `allow_credentials=True` (required for the cookie flow).

**Endpoint groups (full detail — request/response bodies, roles — lives in `mvp-requirements.md` per feature; this section fixes the routing surface):**
`/auth`, `/users`, `/strategic-goals`, `/ideas`, `/ideas/{id}/business-case`, `/ideas/{id}/approvals`, `/ideas/{id}/convert`, `/portfolios`, `/projects`, `/projects/{id}/members`, `/projects/{id}/tasks`, `/projects/{id}/milestones`, `/projects/{id}/risks`, `/projects/{id}/budget`, `/projects/{id}/expenses`, `/portfolios/{id}/dashboard`, `/projects/{id}/dashboard`.

---

## 7. Redis & Celery — MVP Usage Decision

`[DECIDED]` **Neither is used by any MVP feature.** No caching need (small dataset, low MVP traffic) and no background-job need (no email, no scheduled jobs, no report generation, no heavy computation in MVP scope).

- **Redis**: provisioned in `docker-compose.yml` and on the PaaS from day one (zero extra cost to have it ready), but zero application code is written against it until a real need exists — e.g., dashboard query caching at scale, or rate-limiting on `/auth/login`.
- **Celery**: scaffolded folder (`app/tasks/`) only; no worker process is deployed for MVP. Activate when notifications (post-MVP) are built.

This is a hard rule for the implementation plan: do not add caching or background jobs "for later convenience" during MVP phases — it adds operational surface area with no MVP-facing benefit.

---

## 8. Security

- Passwords hashed with `passlib[bcrypt]`, never logged or returned in any response.
- JWT signed with `JWT_SECRET_KEY` (env var, never committed); `[PROPOSED]` HS256 for MVP simplicity — RS256 is a later hardening step if multiple services ever need to verify tokens independently.
- All secrets via environment variables (`core/config.py`, `pydantic-settings`); `.env` gitignored, `.env.example` committed with placeholder values only.
- Tenant isolation enforced at the repository layer (Section 5) — every query is `organization_id`-scoped; verified by an explicit cross-org test sweep (see `implementation-plan.md` Phase: Testing Hardening).
- CORS locked to explicit origins, never `*`, because credentials are involved (Section 6).
- Refresh token rotation on each use `[PROPOSED]` limits replay-token lifetime.
- `[PROPOSED]` Rate limiting on `/auth/login` and `/auth/register` is a post-MVP hardening item (would be the first real use of Redis, per Section 7).
- No PII beyond name/email/org in MVP scope; no payment data touches this system.

---

## 9. Testing Strategy

| Type | MVP-required | Deferred |
|---|---|---|
| Unit (services) | ROI calc, health-flag rule, role-check logic | Exhaustive edge cases on post-MVP fields |
| API (per endpoint) | Happy path + unauthenticated + wrong-role, for every MUST-HAVE endpoint | — |
| Auth | Register, login, expired/invalid token, refresh flow (incl. cookie flags), logout | Brute-force/rate-limit tests |
| RBAC | Table-driven test: each role blocked from each restricted action | — |
| Tenant isolation | Cross-org access attempt on every resource type returns 403/404 | — |
| DB/model | Constraint behavior (unique, FK) | — |
| Integration | Full Idea→BusinessCase→Approval→Convert→Project journey via API | — |
| Frontend | `[PROPOSED]` component tests (Vitest + RTL) for forms, protected routes, silent-refresh-on-401 | Full e2e (Playwright) |

`[PROPOSED]` Test DB: real Postgres (via Docker service container in CI), not SQLite — the schema uses Postgres-specific `ENUM`/`UUID` types. Coverage target: 80% on `services/` and `repositories/`; not enforced on router boilerplate.

---

## 10. Docker & CI/CD

**Backend:**
- Multi-stage `Dockerfile`: builder installs deps → runtime copies app, entrypoint runs `alembic upgrade head` then starts `uvicorn`.
- `docker-compose.yml`: `postgres`, `redis` (idle), `backend`.
- CI (`.github/workflows/ci.yml`): Postgres service container → install deps → `alembic upgrade head` against test DB → `pytest` → `ruff check`. Merge blocked on failure.
- Deploy: Railway or Render, migrations run automatically via the entrypoint on each deploy.

**Frontend:**
- Multi-stage `Dockerfile` (build → static serve) for local parity/portability; Vercel builds directly from the repo in production.
- CI: install deps → `npm run lint` → `npm run build`.
- Deploy: Vercel, auto-deploy on `main`.

**Environment variables `[PROPOSED names]`:** Backend — `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `REDIS_URL`, `FRONTEND_ORIGIN`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, `ENVIRONMENT`. Frontend — `VITE_API_URL`.

---

## 11. Scalability Considerations (kept practical, not over-built for MVP)

- **Modular monolith** gives a clear future extraction seam per module if one (e.g., dashboards/analytics) ever needs independent scaling — not needed at MVP traffic.
- **Stateless backend**: JWT access tokens mean any number of backend instances can be run behind a load balancer without session affinity — horizontal scaling on the PaaS is a config change, not an architecture change.
- **Database**: managed Postgres from a PaaS provider handles MVP load comfortably; connection pooling (`[PROPOSED]` via SQLAlchemy's pool or PgBouncer) becomes relevant only past MVP traffic.
- **Redis/Celery** are pre-provisioned specifically so scaling into caching/background jobs later is a code change, not an infrastructure change (Section 7).
- Things deliberately **not** built now because they're premature at MVP scale: read replicas, CDN-fronted API, multi-region deployment, schema-per-tenant isolation, Kubernetes.

---

## 12. Key Architectural Decisions Log

| # | Decision | Rationale |
|---|---|---|
| 1 | Modular monolith, not microservices | Team size/traffic don't justify microservice overhead; module boundaries preserve a future split path |
| 2 | Two independent repos (Backend/Frontend) | Independent deploy cadence, independent CI, matches confirmed decision |
| 3 | Access token in memory, refresh token in httpOnly cookie | Reduces XSS exposure vs. localStorage; standard practice for SPA + API split across domains |
| 4 | `SameSite=None; Secure` on refresh cookie | Required because frontend/backend are on different domains (Vercel vs. Railway/Render) |
| 5 | `UNIQUE(email)` globally | Matches confirmed one-email-one-user-one-org MVP assumption; extension path documented for later multi-org support |
| 6 | Redis & Celery provisioned but unused | No MVP feature needs them; avoids both under- and over-building infrastructure |
| 7 | Shared-schema multi-tenancy via `organization_id` | Simplest approach satisfying the hard isolation requirement; RLS deferred as hardening |
| 8 | PaaS deployment (Railway/Render + Vercel), Docker kept | Fast path to a live MVP; Docker preserves portability to any future host |
