"""Health-check endpoint tests — Phase 1."""


def test_health_returns_200(client):
    """GET /health must return 200 with {"status": "ok"}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
