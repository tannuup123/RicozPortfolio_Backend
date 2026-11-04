"""Tests for CORS configuration and preflight validation."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def test_client():
    """Synchronous test client without DB overrides."""
    with TestClient(app) as client:
        yield client


def test_cors_production_origin_allowed(test_client):
    """Verify that the production Vercel frontend origin receives CORS headers with credentials."""
    resp = test_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://ricoz-portfolio-frontend.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://ricoz-portfolio-frontend.vercel.app"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_current_preview_origin_allowed(test_client):
    """Verify that the current active preview Vercel frontend receives CORS headers with credentials."""
    origin = "https://ricoz-portfolio-frontend-git-f-bc85ac-tanmay-upadhyays-projects.vercel.app"
    resp = test_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_future_project_preview_origin_allowed_via_regex(test_client):
    """Verify that future preview deployments of this exact project are matched by allow_origin_regex."""
    origin = "https://ricoz-portfolio-frontend-git-feature-dashboard-tanmay-upadhyays-projects.vercel.app"
    resp = test_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin
    assert resp.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://localhost:3000"])
def test_cors_localhost_origins_allowed(test_client, origin):
    """Verify that local development origins remain allowed."""
    resp = test_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin
    assert resp.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.parametrize(
    "origin",
    [
        "https://malicious.vercel.app",
        "https://otherproject-tanmay-upadhyays-projects.vercel.app",
        "https://ricoz-portfolio-frontend-attacker-projects.vercel.app",
        "https://ricoz-portfolio-frontend.vercel.app.attacker.com",
        "http://ricoz-portfolio-frontend-git-f-bc85ac-tanmay-upadhyays-projects.vercel.app",
    ],
)
def test_cors_unrelated_origins_rejected(test_client, origin):
    """Verify that unrelated Vercel domains or spoofed URLs are strictly rejected."""
    resp = test_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers
