from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest
from proofstack_providers import (
    GitHubSourceProvider,
    SourceLimits,
    SourcePreparationError,
    SourceRequest,
    SourceType,
)


class FakeResponse:
    def __init__(
        self,
        *,
        content: bytes = b"",
        json_body: dict[str, Any] | None = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.content = content
        self._json_body = json_body or {}
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._json_body

    def iter_bytes(self) -> list[bytes]:
        return [self.content[index : index + 13] for index in range(0, len(self.content), 13)]

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeGitHubClient:
    def __init__(self, archive: bytes, *, declared_size: int | None = None) -> None:
        self.archive = archive
        self.declared_size = declared_size
        self.stream_headers: dict[str, str] = {}

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        assert url == "https://api.github.com/repos/openai/example"
        return FakeResponse(json_body={"default_branch": "main"})

    def stream(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        assert method == "GET"
        assert url == "https://codeload.github.com/openai/example/zip/main"
        self.stream_headers = dict(kwargs["headers"])
        headers = (
            {"content-length": str(self.declared_size)} if self.declared_size is not None else {}
        )
        return FakeResponse(content=self.archive, headers=headers)


def _repository_archive() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("example-main/app.py", "VALUE = 1\n")
    return output.getvalue()


def test_github_provider_streams_a_bounded_public_archive(tmp_path: Path) -> None:
    client = FakeGitHubClient(_repository_archive())
    provider = GitHubSourceProvider(client=client)
    prepared = provider.prepare(
        SourceRequest(
            SourceType.GITHUB,
            github_url="https://github.com/openai/example",
            github_token="api-only-token",
            destination_parent=tmp_path,
        )
    )

    assert (prepared.root / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert prepared.head_revision == "main"
    assert "Authorization" not in client.stream_headers
    assert prepared.cleanup_path is not None
    shutil.rmtree(prepared.cleanup_path)


def test_github_provider_rejects_declared_oversized_archive(tmp_path: Path) -> None:
    client = FakeGitHubClient(_repository_archive(), declared_size=500_000)
    provider = GitHubSourceProvider(client=client)

    with pytest.raises(SourcePreparationError, match="exceeds"):
        provider.prepare(
            SourceRequest(
                SourceType.GITHUB,
                github_url="https://github.com/openai/example",
                destination_parent=tmp_path,
                limits=SourceLimits(max_repository_bytes=1000),
            )
        )
    assert not list(tmp_path.glob("proofstack-github-*"))
