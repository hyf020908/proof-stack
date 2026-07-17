"""End-to-end API tests over SQLite and the real inline analysis pipeline."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from proofstack_api.database import SessionLocal
from proofstack_api.models import AnalysisRun, User
from proofstack_shared.enums import AnalysisStatus, Role, SourceType
from proofstack_worker.tasks import run_analysis

PASSWORD = "correct-horse-battery-staple"


def register(
    client: TestClient,
    *,
    email: str = "owner@example.com",
    organization: str = "Acme Engineering",
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "Repository Owner",
            "password": PASSWORD,
            "organization_name": organization,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def authorization(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def create_project(client: TestClient, headers: dict[str, str], slug: str = "service") -> str:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "Payment Service",
            "slug": slug,
            "description": "A service under evidence-driven review.",
            "repository_provider": "demo",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_register_login_refresh_and_identity(client: TestClient) -> None:
    tokens = register(client)
    me = client.get("/api/v1/auth/me", headers=authorization(tokens))
    assert me.status_code == 200
    assert me.json()["role"] == "owner"
    assert me.json()["organization"]["slug"] == "acme-engineering"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": PASSWORD},
    )
    assert login.status_code == 200
    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != login.json()["access_token"]

    events = client.get("/api/v1/audit-events", headers=authorization(tokens))
    assert events.status_code == 200
    assert {item["action"] for item in events.json()["items"]} >= {
        "user.registered",
        "user.logged_in",
    }


def test_project_crud_and_cross_organization_isolation(client: TestClient) -> None:
    first = register(client)
    first_headers = authorization(first)
    project_id = create_project(client, first_headers)
    listed = client.get("/api/v1/projects?search=Payment", headers=first_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    patched = client.patch(
        f"/api/v1/projects/{project_id}",
        headers=first_headers,
        json={"description": "Updated description"},
    )
    assert patched.status_code == 200

    second = register(
        client,
        email="other@example.com",
        organization="Other Organization",
    )
    assert (
        client.get(f"/api/v1/projects/{project_id}", headers=authorization(second)).status_code
        == 404
    )
    assert client.delete(f"/api/v1/projects/{project_id}", headers=first_headers).status_code == 204


def test_viewer_cannot_mutate_projects(client: TestClient) -> None:
    tokens = register(client)
    me = client.get("/api/v1/auth/me", headers=authorization(tokens)).json()
    with SessionLocal() as db:
        user = db.get(User, me["id"])
        assert user is not None
        user.role = Role.VIEWER
        db.commit()
    denied = client.post(
        "/api/v1/projects",
        headers=authorization(tokens),
        json={"name": "Denied Project", "slug": "denied-project"},
    )
    assert denied.status_code == 403


def test_owner_manages_organization_members_and_policy_validation(client: TestClient) -> None:
    tokens = register(client)
    headers = authorization(tokens)
    organization = client.get("/api/v1/organizations/current", headers=headers)
    assert organization.status_code == 200
    updated_organization = client.patch(
        "/api/v1/organizations/current",
        headers=headers,
        json={"name": "Acme Evidence Engineering"},
    )
    assert updated_organization.status_code == 200
    assert updated_organization.json()["name"] == "Acme Evidence Engineering"
    created = client.post(
        "/api/v1/organizations/current/members",
        headers=headers,
        json={
            "email": "reviewer@example.com",
            "display_name": "Evidence Reviewer",
            "password": PASSWORD,
            "role": "reviewer",
        },
    )
    assert created.status_code == 201, created.text
    member_id = created.json()["id"]
    changed = client.patch(
        f"/api/v1/organizations/current/members/{member_id}",
        headers=headers,
        json={"role": "viewer", "is_active": False},
    )
    assert changed.status_code == 200
    assert changed.json()["role"] == "viewer"
    assert changed.json()["is_active"] is False
    members = client.get("/api/v1/organizations/current/members", headers=headers)
    assert members.status_code == 200
    assert members.json()["total"] == 2

    policies = client.get("/api/v1/policies", headers=headers)
    assert policies.status_code == 200
    assert policies.json()[0]["name"] == "default"
    invalid = client.post(
        "/api/v1/policies/validate",
        headers=headers,
        json={"yaml": "name: broken\nversion: 1\nrules: []"},
    )
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False


def test_demo_analysis_generates_real_findings_graph_and_evidence(client: TestClient) -> None:
    demo = client.post("/api/v1/auth/demo")
    assert demo.status_code == 200
    headers = authorization(demo.json())
    project_id = create_project(client, headers, "demo-service")
    started = client.post(
        f"/api/v1/projects/{project_id}/analyses/demo",
        headers=headers,
        json={"policy_name": "default", "runner": "native"},
    )
    assert started.status_code == 202, started.text
    analysis_id = started.json()["id"]

    analysis = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers)
    assert analysis.status_code == 200
    assert analysis.json()["status"] == "completed", analysis.text
    assert analysis.json()["verdict"] in {"warn", "fail"}
    assert analysis.json()["risk_score"] > 0

    findings = client.get(
        f"/api/v1/analyses/{analysis_id}/findings?page_size=200",
        headers=headers,
    )
    assert findings.status_code == 200
    rules = {item["rule_id"] for item in findings.json()["items"]}
    assert "python.subprocess-shell" in rules
    assert any(rule.startswith("secret.") for rule in rules)
    assert "test.changed-source-without-evidence" in rules

    graph = client.get(f"/api/v1/analyses/{analysis_id}/graph", headers=headers)
    assert graph.status_code == 200
    assert graph.json()["nodes"]
    evidence = client.get(f"/api/v1/analyses/{analysis_id}/evidence", headers=headers)
    assert evidence.status_code == 200
    assert evidence.json()["ready"] is True
    download = client.get(f"/api/v1/analyses/{analysis_id}/evidence/download", headers=headers)
    assert download.status_code == 200
    assert download.content.startswith(b"PK")

    finding_id = findings.json()["items"][0]["id"]
    updated = client.patch(
        f"/api/v1/findings/{finding_id}",
        headers=headers,
        json={"status": "acknowledged"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "acknowledged"


def test_upload_analysis_runs_pipeline(client: TestClient) -> None:
    tokens = register(client)
    headers = authorization(tokens)
    project_id = create_project(client, headers, "upload-service")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "service.py",
            "def normalize(value: str) -> str:\n    return value.strip().lower()\n",
        )
        bundle.writestr(
            "tests/test_service.py",
            (
                "from service import normalize\n\n"
                "def test_normalize():\n    assert normalize(' A ') == 'a'\n"
            ),
        )
    response = client.post(
        f"/api/v1/projects/{project_id}/analyses/upload",
        headers=headers,
        files={"source": ("source.zip", archive.getvalue(), "application/zip")},
        data={"requirements": "# Normalize values\nInput values must be normalized."},
    )
    assert response.status_code == 202, response.text
    analysis = client.get(f"/api/v1/analyses/{response.json()['id']}", headers=headers)
    assert analysis.status_code == 200
    assert analysis.json()["status"] == "completed", analysis.text


def test_cancel_and_failed_task_states_are_explicit(client: TestClient) -> None:
    tokens = register(client)
    headers = authorization(tokens)
    project_id = create_project(client, headers, "state-service")
    me = client.get("/api/v1/auth/me", headers=headers).json()
    with SessionLocal() as db:
        run = AnalysisRun(
            project_id=project_id,
            source_type=SourceType.PATH,
            source_reference="missing-source",
            created_by=me["id"],
            status=AnalysisStatus.QUEUED,
        )
        db.add(run)
        db.commit()
        analysis_id = run.id
    cancelled = client.post(f"/api/v1/analyses/{analysis_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/v1/analyses/{analysis_id}/cancel", headers=headers).status_code == 409


def test_missing_source_task_fails_with_user_facing_summary(
    client: TestClient, tmp_path: Path
) -> None:
    tokens = register(client)
    headers = authorization(tokens)
    project_id = create_project(client, headers, "failed-task-service")
    me = client.get("/api/v1/auth/me", headers=headers).json()
    with SessionLocal() as db:
        run = AnalysisRun(
            project_id=project_id,
            source_type=SourceType.PATH,
            source_reference=str(tmp_path / "missing"),
            created_by=me["id"],
            status=AnalysisStatus.QUEUED,
        )
        db.add(run)
        db.commit()
        analysis_id = run.id
    run_analysis(analysis_id)
    with SessionLocal() as db:
        failed = db.get(AnalysisRun, analysis_id)
        assert failed is not None
        assert failed.status == AnalysisStatus.FAILED
        assert failed.error_summary
        assert "source" in failed.error_summary.lower()


def test_health_ready_version_and_dashboard(client: TestClient) -> None:
    assert client.get("/api/v1/health").json()["status"] == "healthy"
    assert client.get("/api/v1/ready").json()["status"] == "ready"
    assert client.get("/api/v1/version").json()["version"] == "0.1.0"
    tokens = register(client)
    dashboard = client.get("/api/v1/dashboard", headers=authorization(tokens))
    assert dashboard.status_code == 200
    assert dashboard.json()["project_count"] == 0
    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert "proofstack_analyses_total" in metrics.text
