# RicozPortfolio — Implementation Plan

**Status:** Ready to execute. Built directly on `architecture.md` (how) and `mvp-requirements.md` (what) — no scope or architecture decisions are re-litigated here.
**Audience:** this document is meant to be fed to an AI coding agent (e.g. Antigravity CLI) **one phase at a time**. Never paste the whole document as a single build instruction — see Section 0.

---

## 0. How to Use This Plan With an AI Coding Agent

The macro pipeline for the whole project, and the micro pipeline repeated inside every feature slice, is the same:

```
Requirements → Architecture → Foundation → Database → APIs → Business Logic → Tests → Frontend → Integration → Deployment → MVP Validation
```

Rules for AI-assisted execution:
1. **One phase at a time.** Give the agent only the current phase's section below, plus `architecture.md` and the relevant feature entries from `mvp-requirements.md`. Do not ask it to "build RicozPortfolio" in one prompt.
2. **Within a phase, one feature slice at a time**, in this fixed order: DB model → migration → schema → repository → service → API endpoint → unit/API tests → frontend API client → frontend UI → integration test → manual test → commit. Do not move to the next feature until this sequence's tests pass and the code is committed.
3. **Always paste the specific `mvp-requirements.md` entry** (purpose, business rules, acceptance criteria) for the feature being built — acceptance criteria become the test cases.
4. **Ask the agent to plan before coding**, review the plan against `architecture.md`'s layering, then generate one layer at a time.
5. **Verification before proceeding**: each phase ends with an explicit Definition of Done — do not start the next phase until it's met.

---

## 1. Phase Overview

| Phase | Name | Repo(s) |
|---|---|---|
| 0 | Requirements & Architecture Confirmation | both (docs only) |
| 1 | Foundation | both |
| 2 | Database | backend |
| 3 | Authentication & Organization | both |
| 4 | RBAC | both |
| 5 | Strategy & Demand (Goals, Ideas) | both |
| 6 | Business Case & Approval (critical seam) | both |
| 7 | Portfolio & Project Core | both |
| 8 | Task & Milestone Execution | both |
| 9 | Financial & Risk | both |
| 10 | Dashboards | both |
| 11 | Testing Hardening | both |
| 12 | Deployment | both |
| 13 | MVP Validation | both |

---

## Phase 0 — Requirements & Architecture Confirmation

- **Objective:** Confirm the AI agent (and any human reviewer) has the same shared context before any code is written.
- **Prerequisites:** none.
- **Tasks:** Place `architecture.md`, `mvp-requirements.md`, `implementation-plan.md` in `RicozPortfolio-Backend/Doc/` and `RicozPortfolio-Frontend/Doc/`. Review both docs once end-to-end.
- **Files/folders:** `Doc/architecture.md`, `Doc/mvp-requirements.md`, `Doc/implementation-plan.md` in both repos.
- **DB changes / API endpoints / backend / frontend work:** none.
- **Testing:** none.
- **Verification:** both repos' `Doc/` folders contain all three files.
- **Definition of Done:** docs committed to both repos on `main`.

---

## Phase 1 — Foundation

- **Objective:** Both repos scaffolded, dockerized, CI green, booting end-to-end. No business logic.
- **Prerequisites:** Phase 0 complete.
- **Backend tasks:**
  1. Init repo, protect `main`.
  2. `pyproject.toml`/requirements: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2.0`, `alembic`, `pydantic>=2`, `pydantic-settings`, `psycopg[binary]`, `pyjwt`, `passlib[bcrypt]`, `python-multipart`; dev: `pytest`, `pytest-asyncio`, `httpx`, `ruff`.
  3. `app/main.py`: FastAPI instance, CORS middleware (per `architecture.md` §6/§10), `GET /health`.
  4. `app/core/config.py`: `pydantic-settings` reading all env vars listed in `architecture.md` §10. `.env.example` committed.
  5. `app/db/session.py` (engine/session factory), `app/db/base.py` (declarative base) — no models yet.
  6. `alembic init alembic`; `env.py` wired to `Base.metadata` and `DATABASE_URL`.
  7. `Dockerfile` (multi-stage, entrypoint runs `alembic upgrade head` then `uvicorn`).
  8. `docker-compose.yml`: `postgres`, `redis`, `backend`.
  9. `tests/conftest.py` with test-DB fixture; `tests/test_health.py` asserting `GET /health` → 200.
  10. `.github/workflows/ci.yml`: Postgres service container → install deps → `alembic upgrade head` → `pytest` → `ruff check`.
  11. `README.md`: setup, env vars, test/run instructions, pointer to `Doc/architecture.md`.
- **Frontend tasks:**
  1. Init repo, protect `main`.
  2. `npm create vite@latest . -- --template react-ts`.
  3. Install/configure Tailwind.
  4. Install `react-router-dom`, `@tanstack/react-query`, `react-hook-form`, `zod`.
  5. `src/api/client.ts`: fetch wrapper, `credentials:'include'`, base URL from `VITE_API_URL`, 401-refresh interceptor (stubbed).
  6. `src/auth/AuthContext.tsx`: in-memory access-token state, `useAuth()` hook (stubbed).
  7. `src/routes.tsx`: placeholder route tree matching the page hierarchy in `architecture.md` §4, `ProtectedRoute` shell.
  8. `src/components/layout/AppShell.tsx`: basic sidebar/topbar.
  9. `.env.example`: `VITE_API_URL=http://localhost:8000/api/v1`.
  10. `Dockerfile` (multi-stage build → static serve).
  11. `.github/workflows/ci.yml`: install → `npm run lint` → `npm run build`.
  12. `README.md`.
- **Files/folders:** as listed above (matches `architecture.md` §2 exactly).
- **DB changes:** none yet.
- **API endpoints:** `GET /health` only.
- **Testing:** health-check test (backend); CI lint+build (frontend).
- **Verification:** `docker compose up` boots Postgres+Redis+backend; `/health` → 200. `npm run dev` boots the shell with no crash.
- **Definition of Done:** both repos' CI green on `main`; both READMEs accurate for a fresh clone; zero feature logic exists.

---

## Phase 2 — Database

- **Objective:** All MVP tables exist via Alembic migrations, matching `architecture.md` §5 (product doc) entity design.
- **Prerequisites:** Phase 1 done.
- **Tasks:** Write SQLAlchemy 2.0 models (`app/models/`) and one Alembic migration per logical group, in this order (matches dependency order — nothing references a table that doesn't exist yet):
  1. `organizations`, `users`, `roles`, `user_roles` (+ seed migration for the 4 fixed roles).
  2. `strategic_goals`, `ideas`.
  3. `business_cases`, `approvals`.
  4. `portfolios`, `projects`, `project_members`.
  5. `tasks`, `milestones`, `risks`, `project_budgets`, `expenses`.
- **Files/folders:** `app/models/*.py` (one file per aggregate), `alembic/versions/*.py`.
- **DB changes:** full schema per `mvp-requirements.md` entities — `organization_id` FK on every tenant-scoped table, `UNIQUE(email)` globally on `users`, `UUID` PKs, `created_at`/`updated_at` on all tables, soft-delete (`deleted_at`) on `ideas`/`portfolios`/`projects` only, enums as Postgres `ENUM` types.
- **API endpoints:** none yet.
- **Backend:** models + migrations only, no services/routers yet.
- **Frontend:** no work this phase.
- **Testing:** model/constraint tests (unique, FK) in `tests/unit/`; test asserting the seed migration creates exactly the 4 expected roles.
- **Verification:** `alembic upgrade head` runs clean from an empty DB; rollback (`alembic downgrade -1`) also verified to work at least once per migration group.
- **Definition of Done:** full schema present in the DB, all constraint tests pass, migrations are reproducible on a fresh database.

---

## Phase 3 — Authentication & Organization

- **Objective:** Register/login/refresh/logout work end-to-end, per `mvp-requirements.md` §2.1–2.3 and `architecture.md` §5.
- **Prerequisites:** Phase 2 done.
- **Backend tasks:** `core/security.py` (hashing, JWT encode/decode, cookie helpers) → `services/auth_service.py` (register creates org+user in one transaction; login verifies credentials; refresh validates+rotates cookie) → `repositories/user_repository.py`, `repositories/organization_repository.py` → `api/v1/auth.py` (`POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`).
- **Frontend tasks:** wire `AuthContext` to real endpoints; `features/auth/LoginPage.tsx`, `RegisterPage.tsx`; `bootstrapAuth.ts` silent-refresh-on-load.
- **Files/folders:** `app/core/security.py`, `app/services/auth_service.py`, `app/repositories/{user,organization}_repository.py`, `app/api/v1/auth.py`; `src/features/auth/*`, `src/auth/bootstrapAuth.ts`.
- **DB changes:** none new (uses Phase 2 tables).
- **API endpoints:** the 5 `/auth/*` endpoints listed above.
- **Testing:** register (happy path + duplicate email), login (happy + wrong password), refresh (valid/expired/missing cookie), logout, `/auth/me`. Verify response `Set-Cookie` has `HttpOnly; Secure; SameSite=None` in non-local config.
- **Verification:** manual walkthrough via Swagger `/docs`; frontend login/register forms work against the running backend.
- **Definition of Done:** acceptance criteria in `mvp-requirements.md` §2.1–2.3 all pass as automated tests; a user can register, land on an authenticated shell, refresh on reload, and log out.

---

## Phase 4 — RBAC

- **Objective:** The 4 roles enforce distinct permissions everywhere, per `mvp-requirements.md` §2.4.
- **Prerequisites:** Phase 3 done.
- **Backend tasks:** `core/deps.py::require_role(*roles)` dependency; `PATCH /users/{id}/roles` endpoint (org_admin only); apply `require_role` to every route stubbed so far.
- **Frontend tasks:** `ProtectedRoute` reads roles from `AuthContext`; role-aware navigation (hide links the user can't use).
- **Files/folders:** `app/core/deps.py`, `app/api/v1/users.py`; `src/auth/ProtectedRoute.tsx`.
- **DB changes:** none new.
- **API endpoints:** `GET /users`, `POST /users`, `PATCH /users/{id}/roles`, `PATCH /users/{id}`.
- **Testing:** table-driven RBAC test — every (role × restricted action) combination from `mvp-requirements.md` §2.4's permission table.
- **Verification:** manual check that a `team_member` session cannot reach admin-only UI or API actions.
- **Definition of Done:** full RBAC test matrix green; role assignment endpoint works.

---

## Phase 5 — Strategy & Demand

- **Objective:** Strategic Goals and Idea submission work, per `mvp-requirements.md` §4.1, §5.1.
- **Prerequisites:** Phase 4 done.
- **Backend tasks:** `services/strategic_goal_service.py`, `services/idea_service.py`; `repositories/{strategic_goal,idea}_repository.py`; `api/v1/strategic_goals.py`, `api/v1/ideas.py`.
- **Frontend tasks:** `features/strategy/GoalsPage.tsx`; `features/demand/IdeasListPage.tsx`, `IdeaDetailPage.tsx` (submission form + status display).
- **Files/folders:** as above.
- **DB changes:** none new (Phase 2 tables).
- **API endpoints:** `GET/POST /strategic-goals`, `GET/PATCH/DELETE /strategic-goals/{id}`; `GET/POST /ideas`, `GET/PATCH /ideas/{id}`.
- **Testing:** goal CRUD tests; idea CRUD + status-transition tests; tenant-isolation check for both resources.
- **Verification:** create a goal, submit an idea linked to it, confirm it appears correctly scoped to the org.
- **Definition of Done:** acceptance criteria in `mvp-requirements.md` §4.1/§5.1 pass; frontend pages functional against the live API.

---

## Phase 6 — Business Case & Approval (Critical Seam)

- **Objective:** The Idea → Business Case → Approval → Project conversion journey, per `mvp-requirements.md` §5.2–5.4 — the single most important phase in the MVP.
- **Prerequisites:** Phase 5 done; Phase 7's `projects`/`portfolios` tables already exist from Phase 2 (models only — services come in Phase 7, but the conversion endpoint here creates a `Project` row directly via the project repository).
- **Backend tasks:** `services/business_case_service.py` (ROI calc), `services/approval_service.py` (audit trail), `services/idea_service.py::convert_to_project` (validates `approved` status, creates Project with `source_idea_id`); `api/v1/business_cases.py`, `api/v1/approvals.py`, extend `api/v1/ideas.py` with `POST /ideas/{id}/convert`.
- **Frontend tasks:** Business Case form + Approval action + Convert-to-Project action, all on `IdeaDetailPage.tsx`.
- **Files/folders:** `app/services/{business_case,approval}_service.py`, `app/api/v1/{business_cases,approvals}.py`.
- **DB changes:** none new (Phase 2 tables: `business_cases`, `approvals`, `projects.source_idea_id`).
- **API endpoints:** `POST/PATCH /ideas/{idea_id}/business-case`, `POST /ideas/{idea_id}/approvals`, `GET /ideas/{idea_id}/approvals`, `POST /ideas/{id}/convert`.
- **Testing:** ROI calculation unit test; approval role-check tests; conversion tests (happy path, not-yet-approved rejection, double-conversion rejection); **integration test covering the full journey end-to-end via API calls**.
- **Verification:** manually run the full journey through Swagger, then through the frontend UI.
- **Definition of Done:** all acceptance criteria in `mvp-requirements.md` §5.2–5.4 pass; the end-to-end integration test is green; this is a required demoable checkpoint before continuing.

---

## Phase 7 — Portfolio & Project Core

- **Objective:** Portfolios and Projects (direct creation + membership), per `mvp-requirements.md` §6.1, §7.1.
- **Prerequisites:** Phase 6 done.
- **Backend tasks:** `services/{portfolio,project}_service.py`, `repositories/{portfolio,project}_repository.py`; `api/v1/portfolios.py`, `api/v1/projects.py` (incl. `/projects/{id}/members`).
- **Frontend tasks:** `features/portfolios/PortfolioListPage.tsx`, `PortfolioDetailPage.tsx`; `features/projects/ProjectDetailPage.tsx` shell + Team tab.
- **DB changes:** none new.
- **API endpoints:** `GET/POST /portfolios`, `GET/PATCH/DELETE /portfolios/{id}`; `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}`, `POST/DELETE /projects/{id}/members[/{user_id}]`.
- **Testing:** CRUD + membership tests; tenant isolation; project-manager-must-be-a-member checks (service-layer authorization from `architecture.md` §3).
- **Verification:** create a portfolio, create a project directly inside it, add a member, confirm the Phase 6 conversion path still lands projects correctly in a chosen portfolio.
- **Definition of Done:** §6.1/§7.1 acceptance criteria pass; both creation paths (direct + via conversion) work.

---

## Phase 8 — Task & Milestone Execution

- **Objective:** Tasks and Milestones, per `mvp-requirements.md` §7.2–7.3.
- **Prerequisites:** Phase 7 done.
- **Backend tasks:** `services/{task,milestone}_service.py`, `repositories/{task,milestone}_repository.py`; `api/v1/tasks.py`, `api/v1/milestones.py`.
- **Frontend tasks:** Tasks tab (list + status update) and Milestones tab on `ProjectDetailPage.tsx`.
- **DB changes:** none new.
- **API endpoints:** `GET/POST /projects/{id}/tasks`, `PATCH/DELETE /tasks/{id}`; `GET/POST /projects/{id}/milestones`, `PATCH/DELETE /milestones/{id}`.
- **Testing:** CRUD tests; the "team_member can only update status of their own assigned task" rule tested explicitly.
- **Verification:** assign a task to a team_member, log in as that user, confirm status update works but full edit is blocked.
- **Definition of Done:** §7.2/§7.3 acceptance criteria pass.

---

## Phase 9 — Financial & Risk

- **Objective:** Budget, Expenses, Risks, per `mvp-requirements.md` §8, §9.
- **Prerequisites:** Phase 8 done.
- **Backend tasks:** `services/{budget,risk}_service.py`, `repositories/{budget,expense,risk}_repository.py`; `api/v1/budgets.py` (covers budget+expenses), `api/v1/risks.py`.
- **Frontend tasks:** Budget tab (planned vs. actual) and Risks tab on `ProjectDetailPage.tsx`.
- **DB changes:** none new.
- **API endpoints:** `GET/PUT /projects/{id}/budget`, `GET/POST /projects/{id}/expenses`; `GET/POST /projects/{id}/risks`, `PATCH/DELETE /risks/{id}`.
- **Testing:** budget/expense CRUD + actual-spend calculation tests; risk CRUD tests.
- **Verification:** set a planned budget, log expenses, confirm planned-vs-actual is correct; log risks and confirm status transitions.
- **Definition of Done:** §8/§9 acceptance criteria pass.

---

## Phase 10 — Dashboards

- **Objective:** Project and Portfolio dashboards, per `mvp-requirements.md` §10.1–10.2 — the payoff screens.
- **Prerequisites:** Phase 9 done (dashboards aggregate data from every prior phase).
- **Backend tasks:** `services/dashboard_service.py` (task completion %, budget used %, open risk count, health-flag rule); `api/v1/dashboards.py`.
- **Frontend tasks:** Project dashboard UI, Portfolio dashboard UI (sortable/filterable project list per `mvp-requirements.md` §6.2).
- **DB changes:** none new — dashboards are computed, not stored.
- **API endpoints:** `GET /projects/{id}/dashboard`, `GET /portfolios/{id}/dashboard`.
- **Testing:** health-flag rule unit tests (all branches); dashboard aggregation tests against seeded data with known expected values.
- **Verification:** populate a project with tasks/budget/risks, confirm dashboard numbers match manual calculation.
- **Definition of Done:** §10.1/§10.2 acceptance criteria pass; both dashboards show real, non-fake, non-stale data.

---

## Phase 11 — Testing Hardening

- **Objective:** Close every gap before deployment — this phase exists specifically to catch what feature-by-feature development can miss.
- **Prerequisites:** Phase 10 done.
- **Tasks:**
  1. Tenant-isolation sweep: write an explicit cross-org access test for **every** resource type across the whole API.
  2. Fix any isolation gaps found.
  3. Fill `services/`/`repositories/` coverage to the 80% target from `architecture.md` §9.
  4. Full manual walkthrough of every journey in `mvp-requirements.md`; log and fix bugs found.
  5. Verify cookie flags (`HttpOnly; Secure; SameSite=None`) are correct in a non-local environment config.
- **Files/folders:** primarily additions to `tests/api/test_tenant_isolation.py` (new, comprehensive) and gap-fill across existing test files.
- **DB changes:** none.
- **API endpoints:** none new.
- **Testing:** as above — this phase *is* testing.
- **Verification:** full test suite green; coverage report meets target.
- **Definition of Done:** tenant-isolation sweep complete and green; coverage targets met; no known open bugs from the manual walkthrough.

---

## Phase 12 — Deployment

- **Objective:** Live, publicly reachable MVP with automated deploys.
- **Prerequisites:** Phase 11 done.
- **Tasks:** Finalize backend `Dockerfile`/entrypoint; provision managed Postgres + Redis on Railway/Render; set all env vars (`architecture.md` §10) in the PaaS dashboard; connect `RicozPortfolio-Backend` repo for auto-deploy on `main`; connect `RicozPortfolio-Frontend` repo to Vercel with `VITE_API_URL` pointed at the deployed backend URL; set `FRONTEND_ORIGIN` on the backend to the exact Vercel URL (required for CORS+cookies per `architecture.md` §5–§6).
- **Files/folders:** no new app code; PaaS dashboard configuration + final `.env` values (not committed).
- **DB changes:** run `alembic upgrade head` against the managed production database (via the deploy entrypoint).
- **API endpoints:** none new — this is infra only.
- **Testing:** smoke test every `/auth/*` endpoint and one full journey against the live deployed URLs.
- **Verification:** deployed frontend can register/login/complete the core journey against the deployed backend, with the refresh cookie working cross-domain (the specific risk called out in `architecture.md` §5).
- **Definition of Done:** app reachable at public URLs; migrations ran automatically on deploy; cross-domain cookie flow verified live, not just locally.

---

## Phase 13 — MVP Validation

- **Objective:** Prove the MVP is genuinely demoable, not just "code complete."
- **Prerequisites:** Phase 12 done.
- **Tasks:** Have someone who is **not** the developer run the full journey (register → goal → idea → business case → approve → convert → project → tasks/milestones → budget/risk → dashboards) against the live deployment, with zero developer intervention. Log any friction or bugs; fix demo-blocking issues.
- **DB changes / API endpoints:** none new — fixes only, no new features.
- **Testing:** the live run itself is the test.
- **Verification:** against the `mvp-requirements.md` §13 Definition of Done checklist, item by item.
- **Definition of Done:** the full journey completes successfully end-to-end by a non-developer; every item in `mvp-requirements.md` §13 is checked off.

---

## 2. Day-by-Day Execution Plan (2–4 hrs/day)

`[PROPOSED pacing]` — roughly **10–11 weeks** (50–55 working days). Adjust down if daily time trends toward 4 hrs, up if closer to 2. Never compress by cutting the testing step of a phase.

| Week | Days | Phase | Daily checkpoints |
|---|---|---|---|
| 1 | 1–5 | 1 Foundation | D1: backend skeleton + `/health` + Docker Compose boots · D2: backend CI green · D3: frontend skeleton + routing shell · D4: frontend CI green, both READMEs written · D5: buffer/review |
| 2 | 6–10 | 2 Database | D6: org/user/role models+migration · D7: goals/ideas models+migration · D8: business case/approval models+migration · D9: portfolio/project/members models+migration · D10: tasks/milestones/risks/budget/expenses models+migration, seed script |
| 3 | 11–15 | 3 Auth | D11: `core/security.py` + unit tests · D12: register endpoint+tests · D13: login+`/me`+tests · D14: refresh+logout+cookie-flag tests · D15: frontend AuthContext + Login/Register pages wired |
| 4 | 16–19 | 4 RBAC | D16: `require_role` dependency+tests · D17: role assignment endpoint · D18: full RBAC test matrix · D19: frontend ProtectedRoute + role-aware nav |
| 5 | 20–24 | 5 Strategy/Demand | D20: Goals vertical slice · D21: Ideas create/list/detail+tests · D22: idea status transitions+tests · D23: frontend Goals + Ideas list pages · D24: frontend Idea detail page + submission form |
| 6 | 25–29 | 6 Business Case & Approval | D25: BusinessCase+ROI+tests · D26: Approval+audit trail+tests · D27: convert-to-project endpoint+integration test · D28: frontend Business Case/Approval/Convert UI · D29: full manual run of the critical seam; buffer |
| 7 | 30–34 | 7 Portfolio/Project | D30: Portfolio CRUD+tests · D31: Project CRUD (direct+converted)+tests · D32: members endpoints+tests · D33: frontend Portfolio pages · D34: frontend Project detail shell + Team tab |
| 8 | 35–38 | 8 Execution | D35: Tasks CRUD+tests · D36: Milestones CRUD+tests · D37: frontend Tasks tab · D38: frontend Milestones tab |
| 9 | 39–43 | 9 Financial/Risk | D39: Budget+tests · D40: Expenses+actual-spend calc+tests · D41: Risks CRUD+tests · D42: frontend Budget tab · D43: frontend Risks tab |
| 10 | 44–47 | 10 Dashboards | D44: Project dashboard endpoint+tests · D45: Portfolio dashboard endpoint+health-flag tests · D46: frontend Project dashboard UI · D47: frontend Portfolio dashboard UI |
| 11 | 48–52 | 11 Testing Hardening | D48: tenant-isolation sweep written · D49: fix isolation gaps · D50: coverage gap-fill to target · D51: full manual walkthrough + bug fixes · D52: buffer |
| 12 | 53–55 | 12–13 Deploy & Validate | D53: PaaS provisioning + env config + deploy both repos · D54: live smoke test + cross-domain cookie verification · D55: non-developer demo run, final MVP sign-off |

---

## 3. Final MVP Build Order

```
0 Requirements/Architecture confirmed
   ↓
1 Foundation (both repos bootable)
   ↓
2 Database (full schema)
   ↓
3 Auth & Organization
   ↓
4 RBAC
   ↓
5 Strategy & Demand
   ↓
6 Business Case & Approval  ← the critical seam; do not skip ahead of this
   ↓
7 Portfolio & Project Core
   ↓
8 Task & Milestone Execution
   ↓
9 Financial & Risk
   ↓
10 Dashboards  ← requires 7,8,9 complete (aggregates their data)
   ↓
11 Testing Hardening
   ↓
12 Deployment
   ↓
13 MVP Validation
   ↓
MVP COMPLETE
```

---

## 4. Phase Dependencies

| Phase | Hard-depends on |
|---|---|
| 1 | 0 |
| 2 | 1 |
| 3 | 2 |
| 4 | 3 |
| 5 | 4 |
| 6 | 5 (needs Ideas); models for Portfolios/Projects from Phase 2 |
| 7 | 6 (conversion path must exist to test the full creation story) |
| 8 | 7 |
| 9 | 7 (needs Projects) — does not depend on 8 |
| 10 | 7, 8, 9 (aggregates all three) |
| 11 | 10 (needs the full feature surface to test against) |
| 12 | 11 |
| 13 | 12 |


## 5. What Can Be Developed in Parallel

- **Phase 8 (Tasks/Milestones) and Phase 9 (Financial/Risk)** have no dependency on each other — both only need Phase 7 (Projects) complete. They can be built in either order or, with two people, simultaneously.
- **Within any phase**, backend (model → migration → schema → service → endpoint → tests) and the *previous* phase's frontend polish can overlap — e.g., while Phase 6 backend is underway, minor Phase 5 frontend UX fixes can proceed in parallel without blocking.
- **Frontend page shells** (empty routes/components) for a phase can be scaffolded slightly ahead of that phase's backend endpoints being finished, since Phase 1 already established the routing skeleton — but wiring real data must wait for the corresponding API to be tested and committed.
- Everything from Phase 2 through Phase 6 is **strictly sequential** — each depends on data/behavior the previous phase created (the critical seam in particular should not be parallelized away from its prerequisites).

## 6. MVP Release Checklist

- [ ] All Phase 0–13 Definitions of Done met.
- [ ] Full `mvp-requirements.md` §13 Definition of Done checklist satisfied.
- [ ] No Post-MVP feature (Section 12 of `mvp-requirements.md`) present in either codebase.
- [ ] Backend and frontend CI both green on `main`.
- [ ] Deployed URLs live; cross-domain cookie flow verified in production, not just locally.
- [ ] `alembic upgrade head` verified to run clean against the production database.
- [ ] Environment variables verified set correctly on both PaaS platforms (no dev secrets in prod, no prod secrets in the repo).
- [ ] `README.md` in both repos accurate for a fresh clone + deploy.
- [ ] Non-developer demo run (Phase 13) completed successfully.
- [ ] Git history on both repos is composed of scoped, conventional commits; no secrets in history.

## 7. Open Questions / Assumptions Genuinely Requiring Product-Owner Confirmation

These were marked `[PROPOSED]` across the docs and are low-risk defaults, but should be explicitly confirmed (or overridden) before Phase 3 (Auth) and Phase 10 (Dashboards) respectively, since they're harder to change after data/users exist:

1. **Access token lifetime** (proposed 15–30 min) and **refresh token lifetime** (proposed 7 days) — acceptable, or does your org have a preferred session-length policy?
2. **Health-flag rule** for the portfolio/project dashboard (proposed: budget-used % vs. time-elapsed %, or any open high-impact risk) — is this the right first heuristic, or is there a specific rule you'd prefer for the MVP demo?
3. **Default currency** (`USD`) on project budgets — correct default, or should this be organization-configurable even in MVP?
4. **Multiple roles per user** (proposed: allowed) — confirm this matches how you expect small teams to actually use the product, versus forcing one role per user.
5. **Soft-delete scope** (proposed: only `ideas`, `portfolios`, `projects`; hard delete elsewhere) — confirm this split is acceptable, since it affects what's recoverable if a user deletes something by mistake.

No other open items remain — every other decision point from the prior discussion has been confirmed and is reflected consistently across all three documents.
