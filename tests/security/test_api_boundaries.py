"""API security boundary tests for uploads, tenancy, and production configuration."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from proofstack_shared.config import DEVELOPMENT_SECRET, Settings
from pydantic import ValidationError
from tests.integration.test_api import authorization, create_project, register


def _archive(name: str, content: str = "safe") -> bytes:
    value = io.BytesIO()
    with zipfile.ZipFile(value, "w") as bundle:
        bundle.writestr(name, content)
    return value.getvalue()


def test_zip_slip_and_symlink_uploads_are_rejected(client: TestClient) -> None:
    tokens = register(client)
    headers = authorization(tokens)
    project_id = create_project(client, headers, "secure-upload")
    traversal = client.post(
        f"/api/v1/projects/{project_id}/analyses/upload",
        headers=headers,
        files={"source": ("source.zip", _archive("../../escape.py"), "application/zip")},
    )
    assert traversal.status_code == 422
    assert "unsafe" in traversal.json()["error"]["message"].lower()

    value = io.BytesIO()
    with zipfile.ZipFile(value, "w") as bundle:
        info = zipfile.ZipInfo("linked.py")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        bundle.writestr(info, "target.py")
    symlink = client.post(
        f"/api/v1/projects/{project_id}/analyses/upload",
        headers=headers,
        files={"source": ("source.zip", value.getvalue(), "application/zip")},
    )
    assert symlink.status_code == 422


def test_upload_type_and_github_host_validation(client: TestClient) -> None:
    tokens = register(client)
    headers = authorization(tokens)
    project_id = create_project(client, headers, "input-validation")
    wrong_type = client.post(
        f"/api/v1/projects/{project_id}/analyses/upload",
        headers=headers,
        files={"source": ("source.txt", b"not an archive", "text/plain")},
    )
    assert wrong_type.status_code == 422
    github = client.post(
        f"/api/v1/projects/{project_id}/analyses/github",
        headers=headers,
        json={"url": "https://example.com/owner/repository"},
    )
    assert github.status_code == 422


def test_production_rejects_default_secret_and_demo_mode() -> None:
    with pytest.raises(ValidationError):
        Settings(env="production", demo_mode=False, secret_key=DEVELOPMENT_SECRET)
    with pytest.raises(ValidationError):
        Settings(
            env="production",
            demo_mode=True,
            secret_key="a-production-secret-that-is-long-and-randomized",
        )
