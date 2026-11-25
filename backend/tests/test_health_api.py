import pytest


@pytest.mark.api
def test_health_check_returns_ok_status(client):
    """GET /api/health should return 200 OK with service status metadata."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "service": "MahjarParents Backend API",
    }
