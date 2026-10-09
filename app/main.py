"""RicozPortfolio Backend — FastAPI application entry point.

Phase 1: CORS middleware + GET /health only. No business logic.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.approvals import router as approvals_router
from app.api.v1.auth import router as auth_router
from app.api.v1.business_cases import router as business_cases_router
from app.api.v1.ideas import router as ideas_router
from app.api.v1.strategic_goals import router as strategic_goals_router
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



@app.get("/health")
def health_check() -> dict:
    """Liveness probe — returns 200 with status ok."""
    return {"status": "ok"}

