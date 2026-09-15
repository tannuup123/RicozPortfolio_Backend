"""RicozPortfolio Backend — FastAPI application entry point.

Phase 1: CORS middleware + GET /health only. No business logic.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/health")
def health_check() -> dict:
    """Liveness probe — returns 200 with status ok."""
    return {"status": "ok"}
