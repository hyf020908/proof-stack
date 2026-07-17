"""Pydantic request and response contracts for the versioned REST API."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from proofstack_shared.enums import (
    AnalysisStatus,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    PolicyOutcome,
    Role,
    SourceType,
    TestStatus,
    Verdict,
)
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Page(ApiModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class RegisterRequest(ApiModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)
    organization_name: str = Field(min_length=2, max_length=160)


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    organization_slug: str | None = Field(default=None, min_length=2, max_length=100)


class RefreshRequest(ApiModel):
    refresh_token: str = Field(min_length=20)


class TokenPair(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - This is an OAuth scheme label.
    expires_in: int


class OrganizationSummary(ApiModel):
    id: str
    name: str
    slug: str


class UserResponse(ApiModel):
    id: str
    organization_id: str
    email: EmailStr
    display_name: str
    role: Role
    is_active: bool
    created_at: datetime
    organization: OrganizationSummary | None = None


class OrganizationResponse(ApiModel):
    id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class OrganizationUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    slug: str | None = Field(default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")


class MemberResponse(ApiModel):
    id: str
    email: EmailStr
    display_name: str
    role: Role
    is_active: bool
    created_at: datetime


class MemberCreate(ApiModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)
    role: Role = Role.VIEWER


class MemberUpdate(ApiModel):
    role: Role | None = None
    is_active: bool | None = None


class ProjectCreate(ApiModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str = Field(default="", max_length=5000)
    default_branch: str = Field(default="main", min_length=1, max_length=120)
    repository_provider: str = Field(default="local", pattern=r"^(local|upload|github|demo)$")
    repository_url: str | None = Field(default=None, max_length=1000)


class ProjectUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    slug: str | None = Field(default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = Field(default=None, max_length=5000)
    default_branch: str | None = Field(default=None, min_length=1, max_length=120)
    repository_provider: str | None = Field(default=None, pattern=r"^(local|upload|github|demo)$")
    repository_url: str | None = Field(default=None, max_length=1000)


class ProjectResponse(ApiModel):
    id: str
    organization_id: str
    name: str
    slug: str
    description: str
    default_branch: str
    repository_provider: str
    repository_url: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    analysis_count: int = 0


class DemoAnalysisRequest(ApiModel):
    requirements: str = Field(default="", max_length=100000)
    policy_name: str = Field(default="default", max_length=100)
    runner: str = Field(default="native", pattern=r"^(native|docker)$")
    validation_commands: list[list[str]] = Field(default_factory=list, max_length=10)


class GitHubAnalysisRequest(ApiModel):
    url: HttpUrl
    requirements: str = Field(default="", max_length=100000)
    policy_name: str = Field(default="default", max_length=100)
    runner: str = Field(default="native", pattern=r"^(native|docker)$")
    validation_commands: list[list[str]] = Field(default_factory=list, max_length=10)

    @field_validator("url")
    @classmethod
    def github_only(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.host not in {"github.com", "www.github.com"}:
            raise ValueError("Only HTTPS github.com repository and pull request URLs are supported")
        from proofstack_providers import SourcePreparationError, parse_github_url

        try:
            parse_github_url(str(value))
        except SourcePreparationError as exc:
            raise ValueError(exc.user_message) from exc
        return value


class AnalysisResponse(ApiModel):
    id: str
    project_id: str
    source_type: SourceType
    source_reference: str
    base_revision: str | None
    head_revision: str | None
    status: AnalysisStatus
    verdict: Verdict
    risk_score: int
    risk_components: dict[str, Any]
    progress: int
    current_stage: str
    started_at: datetime | None
    completed_at: datetime | None
    error_summary: str | None
    created_by: str
    created_at: datetime
    requirements_text: str
    policy_name: str
    runner_name: str
    changed_file_count: int = 0
    finding_count: int = 0
    critical_count: int = 0
    requirement_coverage: float = 0.0
    test_evidence_score: float = 0.0


class ProgressResponse(ApiModel):
    analysis_id: str
    status: AnalysisStatus
    progress: int
    current_stage: str
    verdict: Verdict
    error_summary: str | None
    stages: list[dict[str, Any]]


class AnalysisEventResponse(ApiModel):
    id: str
    stage: str
    level: str
    message: str
    progress: int
    status: str
    duration_ms: int | None
    details: dict[str, Any]
    created_at: datetime


class ChangedFileResponse(ApiModel):
    id: str
    path: str
    change_type: str
    additions: int
    deletions: int
    language: str | None
    risk_score: int
    is_test: bool
    is_generated: bool
    old_hash: str | None
    new_hash: str | None
    metadata_json: dict[str, Any]


class FindingResponse(ApiModel):
    id: str
    analysis_run_id: str
    category: FindingCategory
    severity: FindingSeverity
    title: str
    description: str
    file_path: str | None
    start_line: int | None
    end_line: int | None
    rule_id: str
    remediation: str
    evidence: dict[str, Any]
    fingerprint: str
    status: FindingStatus


class FindingUpdate(ApiModel):
    status: FindingStatus


class GraphNode(ApiModel):
    id: str
    label: str
    type: str
    file_path: str | None = None
    changed: bool = False
    blast_radius: int = 0
    risk_score: int = 0


class GraphEdge(ApiModel):
    id: str
    source: str
    target: str
    type: str
    confidence: float


class GraphResponse(ApiModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = False


class RequirementResponse(ApiModel):
    id: str
    external_id: str | None
    title: str
    description: str
    acceptance_criteria: list[str]
    source: str
    confidence: float
    coverage_score: float
    evidence: dict[str, Any]


class TestExecutionResponse(ApiModel):
    id: str
    command: list[str]
    status: TestStatus
    exit_code: int | None
    duration_ms: int
    stdout_excerpt: str
    stderr_excerpt: str
    timed_out: bool
    environment: dict[str, Any]


class PolicyDecisionResponse(ApiModel):
    id: str
    policy_name: str
    rule_id: str
    outcome: PolicyOutcome
    explanation: str
    observed_value: Any
    expected_value: Any
    evidence_references: list[str]


class PolicyValidateRequest(ApiModel):
    yaml: str = Field(min_length=1, max_length=100000)


class PolicyValidateResponse(ApiModel):
    valid: bool
    name: str | None = None
    version: int | None = None
    rules: int = 0
    errors: list[str] = Field(default_factory=list)


class EvidenceArtifactResponse(ApiModel):
    id: str
    artifact_type: str
    name: str
    content_type: str
    sha256: str
    size: int
    created_at: datetime


class EvidenceResponse(ApiModel):
    analysis_id: str
    ready: bool
    artifacts: list[EvidenceArtifactResponse]
    manifest: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None


class AuditEventResponse(ApiModel):
    id: str
    user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    metadata_json: dict[str, Any]
    ip_address: str | None
    created_at: datetime


class PublicConfigResponse(ApiModel):
    version: str
    environment: str
    demo_mode: bool
    task_backend: str
    runner: str
    github_token_configured: bool
    semgrep_enabled: bool
    llm_enabled: bool


class DashboardResponse(ApiModel):
    project_count: int
    analysis_count: int
    verdict_counts: dict[str, int]
    risk_trend: list[dict[str, Any]]
    severe_finding_count: int
    average_duration_seconds: float
    recent_analyses: list[AnalysisResponse]
    recent_audit_events: list[AuditEventResponse]
