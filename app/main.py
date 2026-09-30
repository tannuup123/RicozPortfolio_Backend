"""RicozPortfolio Backend — FastAPI application entry point.

Phase 1: CORS middleware + GET /health only. No business logic.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import router as auth_router
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
app.include_router(users_router, prefix="/api/v1/users", tags=["users"])



@app.get("/health")
def health_check() -> dict:
    """Liveness probe — returns 200 with status ok."""
    return {"status": "ok"}

