"""Shared test fixtures.

Provides a FastAPI TestClient for endpoint tests.
A test-database fixture with real Postgres will be added in Phase 2
when models and migrations exist.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    """Yield a synchronous test client for the FastAPI application."""
    with TestClient(app) as c:
        yield c
