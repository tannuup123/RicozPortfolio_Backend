# AGENTS.md

# RicozPortfolio Backend — AI Agent Working Rules

This file defines HOW AI coding agents should work on the RicozPortfolio Backend.

It does not replace:
- `Doc/architecture.md`
- `Doc/implementation-plan.md`
- `Doc/mvp-requirements.md`
- Other technical/product documentation

Those documents define WHAT the system should build.

---

# 1. CORE OPERATING MODE

Work semi-autonomously.

Default workflow:

1. Understand the requested task.
2. Identify the current project phase.
3. Check relevant project documentation.
4. Check Graphify context when useful.
5. Inspect only relevant files.
6. Create a short implementation plan.
7. Implement the smallest correct change.
8. Run focused tests.
9. Review changed files and diff.
10. Report completion.

Do not ask for approval for every small implementation detail.

Approval is required for:
- major architecture changes
- security-sensitive changes
- tenant-isolation changes with unclear implications
- destructive database operations
- destructive migrations
- dependency additions when genuinely new
- dependency upgrades
- module-boundary changes
- data-loss operations
- conflicting authoritative requirements

---

# 2. TASK SCOPE

Work only within the requested task/module.

Rules:

- Do not modify unrelated modules.
- Do not perform opportunistic refactoring.
- Do not rewrite working code merely because another approach appears cleaner.
- Do not rename unrelated files/classes.
- Do not reorganize the project unnecessarily.
- Do not implement future-phase functionality.
- Do not expand scope without a valid technical reason.

If an unrelated change is genuinely required:

1. Identify why it is required.
2. Explain the dependency.
3. Ask for approval if the change is substantial or high-risk.

---

# 3. PROJECT CONTEXT FIRST

Before implementation:

- Read relevant project documentation.
- Reuse existing architectural decisions.
- Reuse existing implementation patterns.
- Check existing modules before creating new ones.
- Check existing utilities/services/models before creating duplicates.
- Use Graphify when it provides useful codebase relationships.

Do not repeatedly rediscover information that has already been established.

Prefer:

Documentation → Graphify → targeted source inspection

instead of:

Entire repository scan → repeated source inspection → repeated analysis

---

# 4. GRAPHIFY

Graphify is the project's codebase knowledge/navigation system.

Use the existing Graphify knowledge graph when it is available.

Graphify should primarily be used for:

- codebase navigation
- locating relevant modules
- dependency discovery
- relationship discovery
- architectural context
- understanding cross-file relationships
- finding relevant symbols

## Graphify Rules

- Check existing Graphify context before broad repository exploration.
- Do not rebuild Graphify for every task.
- Do not regenerate Graphify when the existing graph is sufficient.
- Rebuild/update Graphify only when:
    - `graphify-out/graph.json` is missing
    - the graph is stale
    - relevant codebase structure changed substantially
    - the task explicitly requires graph regeneration

Do not manually recreate Graphify extraction logic unless absolutely necessary.

Do not create temporary scripts merely to reproduce functionality already provided by Graphify.

Do not modify application code merely to make Graphify work.

Graphify is a navigation/context tool.

Graphify is NOT an authority over source-code correctness.

Always inspect the actual source files before modifying them.

## Graphify Efficiency

Do not:

- rebuild the entire graph for a small code change
- repeatedly run Graphify without a reason
- scan unrelated files because Graphify exists
- regenerate semantic extraction unnecessarily
- create multiple Graphify extraction scripts

Prefer existing:

- `graphify-out/graph.json`
- `graphify-out/GRAPH_REPORT.md`
- Graphify navigation/context

---

# 5. PHASE-AWARE WORKFLOW

Always determine the current project phase from:

`Doc/implementation-plan.md`

Do not assume the phase.

Only implement work belonging to the requested/current phase unless explicitly instructed otherwise.

---

# 6. SKILL / AGENT SELECTION

Use the minimum number of skills/agents necessary.

General rule:

1. Identify the current phase.
2. Identify the requested task.
3. Select one primary implementation skill/agent.
4. Add a specialist only when genuinely required.
5. Do not make multiple agents independently solve the same implementation problem.
6. Do not invoke an agent merely because it is available.
7. Reuse information already discovered by another agent.

Prefer:

ONE primary implementation agent

over:

multiple agents performing the same work.

---

# 7. PHASE 1 — FOUNDATION

Typical responsibilities:

- project scaffolding
- FastAPI application setup
- configuration
- environment handling
- database foundation
- SQLAlchemy Base/session
- Alembic initialization
- Docker
- CI
- basic testing infrastructure

Primary skill:

- backend implementation skill

Use architecture skill/agent only when:

- architecture is unclear
- module boundaries are being established
- major infrastructure decisions are required

Use testing skill/agent when:

- testing infrastructure is being established
- shared infrastructure changes require broader verification

Do not introduce unnecessary technologies.

---

# 8. PHASE 2 — DATABASE

Typical responsibilities:

- SQLAlchemy models
- relationships
- constraints
- indexes
- tenant ownership
- Alembic migrations
- database fixtures
- model tests
- repository/database behavior

Primary skill:

- backend/database implementation skill

Architecture skill/agent may be used for:

- tenant data architecture
- relationship design
- module ownership
- major database architecture decisions

Testing skill/agent may be used for:

- model tests
- constraints
- relationships
- repository behavior
- tenant-isolation tests

## Phase 2 Workflow

For database implementation:

1. Read the approved database requirements.
2. Inspect existing database/session/Base configuration.
3. Check relevant models.
4. Check Graphify context if useful.
5. Determine ownership and tenant scope.
6. Implement models/relationships.
7. Generate migration.
8. Inspect migration manually.
9. Apply migration.
10. Run focused database tests.
11. Review diff.
12. Report results.

Never blindly trust Alembic autogeneration.

---

# 9. PHASE 3 — AUTHENTICATION / AUTHORIZATION

Primary skill:

- backend implementation skill

Use security/auth specialist when available and genuinely required.

Use architecture skill when:

- authentication architecture changes
- authorization boundaries change
- tenant authorization model changes

Testing should include:

- authentication behavior
- authorization behavior
- invalid credentials
- access-control boundaries
- tenant-isolation behavior

Security-sensitive changes require careful review.

---

# 10. PHASE 4 — API / MODULE IMPLEMENTATION

Primary skill:

- backend implementation skill

Use architecture skill when:

- module boundaries change
- API architecture changes
- cross-module dependencies are introduced

Use testing skill for:

- endpoint tests
- service tests
- repository tests
- validation tests

Follow the existing modular-monolith architecture.

---

# 11. PHASE 5 — ASYNC / SCALING / INFRASTRUCTURE

Primary skill:

- backend implementation skill

Use infrastructure/devops skill when genuinely required for:

- Docker
- workers
- Redis
- Celery
- RabbitMQ
- deployment
- background jobs
- infrastructure configuration

Use architecture skill for:

- scaling architecture
- worker architecture
- queue architecture
- distributed processing decisions

Do not introduce:

- Redis
- Celery
- RabbitMQ
- ARQ
- additional workers
- microservices

unless required by the approved project plan or explicitly requested.

---

# 12. PHASE 6 — AI / ADVANCED FEATURES

Use the minimum required combination of:

- backend implementation skill
- AI-specific skill
- architecture skill when architecture decisions are involved
- testing skill when feature verification is required

Do not implement AI/advanced functionality during earlier phases merely because the technology is available.

Follow the approved implementation plan.

---

# 13. MODULAR MONOLITH

The backend follows a modular-monolith architecture.

Rules:

- Keep module boundaries clear.
- Keep domain responsibilities inside the appropriate module.
- Avoid unnecessary coupling.
- Avoid circular dependencies.
- Do not move functionality between modules without justification.
- Do not introduce microservices.
- Do not create unnecessary cross-module dependencies.
- Do not bypass module boundaries merely for convenience.

---

# 14. LAYER RESPONSIBILITIES

## API Layer

Responsible for:

- HTTP
- request handling
- response handling
- dependency injection
- endpoint-level concerns

Do not put substantial business logic into API routes.

## Schema Layer

Responsible for:

- validation
- serialization
- request/response schemas

Do not put database queries inside schemas.

## Service Layer

Responsible for:

- business logic
- workflows
- business rules
- orchestration

## Repository Layer

Responsible for:

- database access
- persistence
- query operations

## Model Layer

Responsible for:

- ORM representation
- database relationships
- constraints
- database-level representation

Do not bypass service/repository boundaries without a valid technical reason.

---

# 15. ARCHITECTURE

Follow the approved project architecture.

Do not:

- redesign architecture automatically
- introduce microservices
- replace approved frameworks
- replace approved technologies
- change module boundaries
- introduce new architectural patterns unnecessarily

If architecture is unclear:

1. Inspect the architecture documentation.
2. Inspect existing implementation.
3. Check Graphify context.
4. If ambiguity remains and the decision is substantial, ask before implementing.

---

# 16. DATABASE

Approved database architecture:

- PostgreSQL
- SQLAlchemy
- Alembic

Rules:

- Reuse existing database configuration.
- Reuse existing session configuration.
- Reuse existing Base.
- Do not create duplicate ORM configurations.
- Do not create duplicate models.
- Do not create duplicate tables.
- Implement only approved entities.
- Implement only approved fields.
- Do not add speculative fields.

---

# 17. DATABASE DESIGN CHECKLIST

Before creating or substantially modifying a model, determine:

- owning module
- tenant scope
- primary key
- required fields
- nullable fields
- foreign keys
- relationships
- ownership
- cascading behavior
- unique constraints
- check constraints
- indexes
- migration impact

Do not create database structures based on guesses.

---

# 18. MULTI-TENANCY

Tenant isolation is a security boundary.

Rules:

- Authenticated tenant/organization context is authoritative.
- Never trust client-supplied `organization_id` / `tenant_id` for authorization.
- Never rely on frontend filtering for tenant security.
- All tenant-owned SELECT operations must respect tenant scope.
- All tenant-owned INSERT operations must respect tenant scope.
- All tenant-owned UPDATE operations must respect tenant scope.
- All tenant-owned DELETE operations must respect tenant scope.
- GET-by-ID queries must be tenant-scoped.
- Relationship queries must be tenant-scoped.
- Repository queries must enforce tenant boundaries where applicable.
- Never allow cross-tenant data access.

Tenant isolation must be tested explicitly.

---

# 19. DATABASE RELATIONSHIPS

Explicitly design:

- 1:1
- 1:N
- N:N

Rules:

- Use approved association/junction tables for N:N relationships.
- Do not add relationships merely for convenience.
- Consider ownership.
- Consider foreign keys.
- Consider cascading behavior.
- Consider tenant boundaries.
- Avoid relationships that create unnecessary coupling.

---

# 20. CONSTRAINTS

Use appropriate database constraints.

Where applicable:

- Primary keys
- Foreign keys
- NOT NULL
- UNIQUE
- CHECK constraints

Do not rely only on application-level validation for database integrity.

---

# 21. INDEXES

Add indexes based on actual query/use-case requirements.

Consider:

- tenant-scoped queries
- foreign-key lookups
- frequently queried fields
- uniqueness requirements

Do not index every column.

Do not create speculative indexes.

---

# 22. ALEMBIC / MIGRATIONS

Alembic is the approved migration system.

Rules:

- Use Alembic for permanent schema changes.
- Generate migrations from the current model state.
- Inspect autogenerated migrations before applying.
- Never blindly trust autogenerated migrations.
- Never hide migration problems by resetting the database.
- Never delete migration history as a troubleshooting shortcut.
- Never modify already-applied migrations unless explicitly instructed.
- Create a new migration for new schema changes.
- Treat destructive migrations as high-risk.
- Require approval before destructive migration operations.

## Migration Safety

Never use:

- database reset
- migration history deletion
- migration file deletion

as a generic solution to a migration problem.

If a migration is invalid:

1. Determine whether it has been applied.
2. Inspect Alembic revision state.
3. Inspect the migration.
4. Determine the correct recovery strategy.
5. Ask approval if recovery can cause data loss/history changes.

---

# 23. DOCKER VS WINDOWS DATABASE CONNECTION

The project may execute in two contexts:

## Docker

Inside Docker Compose networking:

`postgres:5432`

The shared Docker database configuration should continue using the Docker hostname.

## Windows Host

Host-side execution such as:

- local Alembic commands
- local pytest
- local scripts

may require:

`localhost:5432`

Do not globally replace the Docker database hostname merely to make host-side commands work.

Prefer a local environment override or host-specific database URL.

Do not use SQLite as a workaround.

Do not create duplicate database configurations unnecessarily.

---

# 24. TESTING

Prefer focused tests first.

Do not run the entire test suite after every tiny change.

Examples:

Small model change:

- run relevant model tests

Repository change:

- run repository tests

API change:

- run relevant endpoint tests

Shared infrastructure change:

- expand testing appropriately

Database changes should test, where applicable:

- model creation
- constraints
- relationships
- foreign keys
- repository behavior
- migration behavior
- tenant isolation

At meaningful milestones, run broader tests.

---

# 25. SECURITY

Never:

- expose passwords
- expose API keys
- expose tokens
- expose credentials
- commit secrets
- weaken authorization
- bypass tenant isolation
- disable security checks just to make tests pass

If security implications are unclear:

Stop and inspect/review before implementing.

Security-sensitive changes require careful review.

---

# 26. DEPENDENCIES

Before adding a dependency:

1. Check whether existing dependencies already provide the functionality.
2. Check the current project stack.
3. Check whether the dependency is actually required.

Do not add dependencies automatically.

Ask for approval before introducing a genuinely new dependency.

Do not upgrade unrelated packages.

Do not perform dependency upgrades as part of unrelated implementation work.

---

# 27. REFACTORING

Do not refactor unrelated code.

Do not:

- rewrite working code unnecessarily
- rename unrelated files
- reorganize unrelated modules
- change coding patterns without reason
- replace working implementations simply because another approach appears cleaner

Refactor only when:

- explicitly requested
- required for the current task
- required to fix a real defect
- required for security/correctness

---

# 28. IMPLEMENTATION STYLE

Always prefer:

- smallest correct change
- existing project patterns
- existing utilities
- existing abstractions
- explicit behavior
- maintainable code
- backward compatibility where required

Avoid:

- speculative functionality
- speculative abstractions
- duplicate utilities
- duplicate services
- duplicate models
- future-phase implementation
- unnecessary complexity

---

# 29. AGENT COLLABORATION

Use the minimum number of agents necessary.

Preferred:

Primary implementation agent
↓
Focused testing/review when required

Architecture agent should be used for:

- architecture decisions
- major design reviews
- module-boundary decisions
- major database architecture
- major scaling decisions

Backend agent should be used for:

- backend implementation
- database implementation
- API/service/repository implementation

Testing agent should be used for:

- focused testing
- test strategy
- test review
- regression verification

Do not:

- have multiple agents independently implement the same feature
- repeatedly hand work between agents
- invoke specialists without a real need
- duplicate repository inspection across agents

---

# 30. PLANNING

## Small Task

Use:

Understand
→ Implement
→ Focused Test

## Medium Task

Use:

Inspect
→ Short Plan
→ Implement
→ Test
→ Review

## High-Risk Task

Use:

Inspect
→ Detailed Plan
→ Approval
→ Implement
→ Test
→ Review

Do not create unnecessarily long plans for simple tasks.

---

# 31. TOKEN OPTIMIZATION

Optimize context usage without sacrificing correctness.

Rules:

- Do not scan the entire repository unnecessarily.
- Do not repeatedly read the same files.
- Do not repeatedly rediscover architecture.
- Use project documentation.
- Use Graphify context when useful.
- Inspect only relevant modules.
- Inspect direct dependencies when required.
- Do not investigate future requirements during the current task.
- Do not repeatedly explain the same context.
- Keep implementation reports concise.
- Use focused tests first.
- Avoid unnecessary agent invocations.
- Avoid unnecessary Graphify rebuilds.
- Avoid temporary scripts when existing tooling can perform the task.

Token optimization must NEVER override:

- correctness
- security
- database integrity
- tenant isolation
- required testing

---

# 32. CHANGE CONTROL

Do not silently make major decisions.

If requirements conflict:

1. Identify the conflict.
2. Identify the authoritative sources.
3. Do not silently choose one if the decision is substantial.
4. Ask for clarification.

If a task requires substantial unrelated changes:

- stop
- explain why
- request approval if necessary

If data loss or destructive behavior is possible:

- stop
- explain the risk
- request approval

---

# 33. GIT

Do not automatically commit.

Do not automatically:

- reset
- revert
- amend
- rewrite history
- force push

unless explicitly instructed.

Before reporting completion:

- review changed files
- review the diff
- verify that unrelated files were not modified

After successful completion provide:

Suggested Git commit message

Do not execute the commit unless requested.

---

# 34. DOCUMENTATION

Keep responsibilities separated.

## AGENTS.md

Defines:

HOW the AI agent should work.

## Architecture Documentation

Defines:

WHAT architecture the system uses.

## Implementation Plan

Defines:

WHAT phases/tasks need to be implemented.

## MVP Requirements

Defines:

WHAT the product requires.

Do not copy the entire implementation plan into AGENTS.md.

Do not duplicate large technical specifications unnecessarily.

Important architectural decisions should be documented in the appropriate project documentation.

---

# 35. TEMPORARY FILES

Avoid creating temporary files in the project.

If a temporary file is genuinely required:

- keep it minimal
- use it only for the current task
- remove it after successful execution when safe
- do not leave debugging scripts behind

Examples of files that should not normally remain:

- scratch scripts
- temporary graph scripts
- debugging output
- generated test artifacts
- temporary migration experiments

Never modify production/application files merely as a temporary debugging mechanism.

---

# 36. COMPLETION VERIFICATION

Before reporting completion verify:

1. Requested task is implemented.
2. Only relevant files changed.
3. Tests were executed.
4. Tests passed or failures are clearly reported.
5. Database changes were verified when applicable.
6. Migration state is understood when applicable.
7. Tenant security was checked when applicable.
8. No accidental unrelated changes exist.
9. Diff was reviewed.

Do not claim completion based only on code generation.

---

# 37. COMPLETION REPORT

After each task, report only:

## Files Created / Modified
- file list

## Implemented
- concise summary

## Tests
- tests executed
- results

## Database / Migrations
- migration changes, if applicable

## Tenant Security
- validation performed, if applicable

## Remaining Blockers / Issues
- blockers only

## Suggested Git Commit
- concise commit message

Do not provide long internal reasoning.

---

# 38. DECISION PRIORITY

When rules conflict, prioritize:

1. Security
2. Data integrity
3. Approved architecture
4. Explicit user requirements
5. Existing project documentation
6. Current implementation patterns
7. Minimal scope
8. Token efficiency

Never sacrifice correctness or security merely to reduce token usage.

---

# 39. FINAL PRINCIPLE

Correctness first.

Security first for tenant and data boundaries.

Follow the approved architecture.

Work within the requested scope.

Use the minimum necessary context.

Use the minimum necessary agents.

Use Graphify when it provides useful context.

Do not rebuild existing context unnecessarily.

Do not redesign completed decisions.

Do not add speculative functionality.

Do not guess when a major decision is unclear.

Make the smallest correct change.

Test the change.

Review the diff.

Report only what matters.