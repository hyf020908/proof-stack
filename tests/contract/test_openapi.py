"""Contract checks for stable endpoints and uniform public errors."""

from fastapi.testclient import TestClient


def test_openapi_contains_frontend_contract(client: TestClient) -> None:
    schema = client.get("/api/v1/openapi.json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    required = {
        "/api/v1/auth/login",
        "/api/v1/projects",
        "/api/v1/projects/{project_id}/analyses/demo",
        "/api/v1/analyses/{analysis_id}/progress",
        "/api/v1/analyses/{analysis_id}/findings",
        "/api/v1/analyses/{analysis_id}/graph",
        "/api/v1/analyses/{analysis_id}/evidence/download",
        "/api/v1/dashboard",
    }
    assert required <= set(paths)


def test_validation_errors_use_uniform_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json={"email": "invalid"})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["request_id"]
    assert payload["error"]["details"]
