"""Bounded public GitHub repository and pull-request source provider."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import quote, urlparse

from .archive import SafeZipExtractor, _single_root
from .source import (
    PreparedSource,
    SourcePreparationError,
    SourceRequest,
    SourceType,
    validate_source_tree,
)


class HttpResponse(Protocol):
    status_code: int
    content: bytes
    headers: Any

    def json(self) -> Any:
        """Decode the response JSON body."""


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> HttpResponse:
        """Issue one bounded HTTP GET request."""


class GitHubSourceProvider:
    def __init__(
        self,
        *,
        client: HttpClient | None = None,
        extractor: SafeZipExtractor | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = client
        self.extractor = extractor or SafeZipExtractor()
        self.timeout_seconds = timeout_seconds

    def prepare(self, request: SourceRequest) -> PreparedSource:
        if not request.github_url:
            raise SourcePreparationError(
                "github_url_missing", "A public GitHub repository or pull request URL is required."
            )
        owner, repository, pull_number = parse_github_url(request.github_url)
        client = self._client or _default_client(self.timeout_seconds)
        token = request.github_token or os.getenv("PROOFSTACK_GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "ProofStack/0.1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        api_base = f"https://api.github.com/repos/{owner}/{repository}"
        base_revision: str | None = None
        head_revision: str | None = None
        diff_text = ""
        if pull_number is not None:
            pull_response = client.get(
                f"{api_base}/pulls/{pull_number}", headers=headers, timeout=self.timeout_seconds
            )
            pull_data = _json_or_error(pull_response, "pull request")
            try:
                base_revision = str(pull_data["base"]["sha"])
                head_revision = str(pull_data["head"]["sha"])
            except (KeyError, TypeError) as exc:
                raise SourcePreparationError(
                    "github_response_invalid", "GitHub returned incomplete pull request metadata."
                ) from exc
            diff_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
            diff_content = _read_bounded(
                client,
                f"{api_base}/pulls/{pull_number}",
                headers=diff_headers,
                timeout=self.timeout_seconds,
                max_bytes=request.limits.max_diff_bytes,
                resource="pull request diff",
            )
            diff_text = diff_content.decode("utf-8", errors="replace")
            reference = head_revision
        else:
            repository_response = client.get(
                api_base, headers=headers, timeout=self.timeout_seconds
            )
            repository_data = _json_or_error(repository_response, "repository")
            reference = request.reference or str(repository_data.get("default_branch", "main"))
            head_revision = reference
        archive_url = (
            f"https://codeload.github.com/{owner}/{repository}/zip/{quote(reference, safe='')}"
        )
        parent = request.destination_parent.resolve() if request.destination_parent else None
        temporary_root = Path(tempfile.mkdtemp(prefix="proofstack-github-", dir=parent))
        archive_path = temporary_root / "source.zip"
        destination = temporary_root / "repository"
        try:
            archive_content = _read_bounded(
                client,
                archive_url,
                headers={
                    "Accept": "application/zip",
                    "User-Agent": "ProofStack/0.1.0",
                },
                timeout=self.timeout_seconds,
                max_bytes=request.limits.max_repository_bytes,
                resource="repository archive",
                follow_redirects=True,
            )
            archive_path.write_bytes(archive_content)
            stats = self.extractor.extract(archive_path, destination, request.limits)
            archive_path.unlink()
            root = _single_root(destination)
            validate_source_tree(root, request.limits)
            return PreparedSource(
                root=root,
                source_type=SourceType.GITHUB,
                source_reference=request.github_url,
                diff_text=diff_text,
                base_revision=base_revision,
                head_revision=head_revision,
                metadata={
                    **stats,
                    "owner": owner,
                    "repository": repository,
                    "pull_number": pull_number,
                },
                cleanup_path=temporary_root,
            )
        except Exception:
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise


def parse_github_url(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise SourcePreparationError(
            "invalid_github_url",
            "Only HTTPS github.com repository and pull request URLs are accepted.",
        )
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or len(parts) not in {2, 4}:
        raise SourcePreparationError(
            "invalid_github_url", "Use https://github.com/owner/repository or a /pull/number URL."
        )
    owner, repository = parts[0], parts[1].removesuffix(".git")
    identifier = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
    if (
        not identifier.fullmatch(owner)
        or not identifier.fullmatch(repository)
        or repository in {".", ".."}
    ):
        raise SourcePreparationError(
            "invalid_github_url", "The GitHub owner or repository name is invalid."
        )
    pull_number = None
    if len(parts) == 4:
        if parts[2] != "pull" or not parts[3].isdigit() or int(parts[3]) <= 0:
            raise SourcePreparationError(
                "invalid_github_url", "The GitHub pull request URL is invalid."
            )
        pull_number = int(parts[3])
    if parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port:
        raise SourcePreparationError(
            "invalid_github_url", "The GitHub URL contains unsupported components."
        )
    return owner, repository, pull_number


def _default_client(timeout_seconds: float) -> HttpClient:
    try:
        import httpx
    except ImportError as exc:
        raise SourcePreparationError(
            "http_client_unavailable", "GitHub analysis requires the httpx package."
        ) from exc
    return cast(HttpClient, httpx.Client(timeout=timeout_seconds, follow_redirects=False))


def _json_or_error(response: HttpResponse, resource: str) -> dict[str, Any]:
    _raise_http_error(response, resource)
    try:
        value = response.json()
    except Exception as exc:
        raise SourcePreparationError(
            "github_response_invalid", f"GitHub returned invalid {resource} metadata."
        ) from exc
    if not isinstance(value, dict):
        raise SourcePreparationError(
            "github_response_invalid", f"GitHub returned invalid {resource} metadata."
        )
    return value


def _raise_http_error(response: HttpResponse, resource: str) -> None:
    if response.status_code in {401, 403, 429}:
        raise SourcePreparationError(
            "github_rate_limited",
            (
                "GitHub rejected the request or its rate limit was reached. Configure a "
                "read-only token or retry later."
            ),
        )
    if response.status_code == 404:
        raise SourcePreparationError(
            "github_not_found", f"The requested GitHub {resource} is not public or does not exist."
        )
    if not 200 <= response.status_code < 300:
        raise SourcePreparationError(
            "github_request_failed", f"GitHub could not provide the requested {resource}."
        )


def _read_bounded(
    client: HttpClient,
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
    max_bytes: int,
    resource: str,
    follow_redirects: bool = False,
) -> bytes:
    stream = getattr(client, "stream", None)
    if callable(stream):
        with stream(
            "GET",
            url,
            headers=headers,
            timeout=timeout,
            follow_redirects=follow_redirects,
        ) as response:
            _raise_http_error(response, resource)
            declared_size = response.headers.get("content-length")
            if declared_size and declared_size.isdigit() and int(declared_size) > max_bytes:
                raise SourcePreparationError(
                    "download_too_large",
                    f"The downloaded {resource} exceeds the configured limit.",
                )
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise SourcePreparationError(
                        "download_too_large",
                        f"The downloaded {resource} exceeds the configured limit.",
                    )
            return bytes(content)
    response = client.get(
        url,
        headers=headers,
        timeout=timeout,
        follow_redirects=follow_redirects,
    )
    _raise_http_error(response, resource)
    if len(response.content) > max_bytes:
        raise SourcePreparationError(
            "download_too_large", f"The downloaded {resource} exceeds the configured limit."
        )
    return response.content
