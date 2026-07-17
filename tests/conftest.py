"""Shared isolated test configuration for API, worker, and CLI tests."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

TEST_RUNTIME = Path(tempfile.mkdtemp(prefix="proofstack-tests-"))
os.environ["PROOFSTACK_ENV"] = "test"
os.environ["PROOFSTACK_DEMO_MODE"] = "true"
os.environ["PROOFSTACK_DATABASE_URL"] = f"sqlite:///{TEST_RUNTIME / 'test.sqlite3'}"
os.environ["PROOFSTACK_SECRET_KEY"] = "proofstack-test-secret-with-at-least-thirty-two-characters"
os.environ["PROOFSTACK_TASK_BACKEND"] = "inline"
os.environ["PROOFSTACK_RUNNER"] = "native"
os.environ["PROOFSTACK_ARTIFACT_ROOT"] = str(TEST_RUNTIME / "artifacts")
os.environ["PROOFSTACK_WORKSPACE_ROOT"] = str(TEST_RUNTIME / "workspaces")

from fastapi.testclient import TestClient
from proofstack_api.database import Base, engine
from proofstack_api.main import app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del session, exitstatus
    engine.dispose()
    shutil.rmtree(TEST_RUNTIME, ignore_errors=True)
