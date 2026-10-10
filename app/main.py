"""RicozPortfolio Backend — FastAPI application entry point.

Phase 1: CORS middleware + GET /health only. No business logic.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.approvals import router as approvals_router
from app.api.v1.auth import router as auth_router
from app.api.v1.budget import project_budget_router
from app.api.v1.business_cases import router as business_cases_router
from app.api.v1.expenses import project_expenses_router
from app.api.v1.ideas import router as ideas_router
from app.api.v1.milestones import (
    milestones_router,
    project_milestones_router,
)
from app.api.v1.portfolios import router as portfolios_router
from app.api.v1.projects import router as projects_router
from app.api.v1.risks import (
    project_risks_router,
    risks_router,
)
from app.api.v1.strategic_goals import router as strategic_goals_router
from app.api.v1.tasks import (
    project_tasks_router,
    tasks_router,
)
from app.api.v1.users import router as users_router
from app.core.config import settings

app = FastAPI(
    title="RicozPortfolio API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — architecture.md §6: explicit origins, credentials required for cookie flow.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(ideas_router, prefix="/api/v1/ideas", tags=["ideas"])
app.include_router(
    business_cases_router,
    prefix="/api/v1/ideas/{idea_id}/business-case",
    tags=["business-cases"],
)
app.include_router(
    approvals_router,
    prefix="/api/v1/ideas/{idea_id}/approvals",
    tags=["approvals"],
)
app.include_router(strategic_goals_router, prefix="/api/v1/strategic-goals", tags=["strategic-goals"])
app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
app.include_router(portfolios_router, prefix="/api/v1/portfolios", tags=["portfolios"])
app.include_router(projects_router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(
    project_tasks_router,
    prefix="/api/v1/projects/{project_id}/tasks",
    tags=["tasks"],
)
app.include_router(
    tasks_router,
    prefix="/api/v1/tasks",
    tags=["tasks"],
)
app.include_router(
    project_milestones_router,
    prefix="/api/v1/projects/{project_id}/milestones",
    tags=["milestones"],
)
app.include_router(
    milestones_router,
    prefix="/api/v1/milestones",
    tags=["milestones"],
)
app.include_router(
    project_budget_router,
    prefix="/api/v1/projects/{project_id}/budget",
    tags=["budgets"],
)
app.include_router(
    project_expenses_router,
    prefix="/api/v1/projects/{project_id}/expenses",
    tags=["expenses"],
)
app.include_router(
    project_risks_router,
    prefix="/api/v1/projects/{project_id}/risks",
    tags=["risks"],
)
app.include_router(
    risks_router,
    prefix="/api/v1/risks",
    tags=["risks"],
)



@app.get("/health")
def health_check() -> dict:
    """Liveness probe — returns 200 with status ok."""
    return {"status": "ok"}

