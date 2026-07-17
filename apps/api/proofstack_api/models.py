"""SQLAlchemy persistence models for the complete ProofStack audit domain."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

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
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from proofstack_api.database import Base


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    users: Mapped[list["User"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_org_email", "organization_id", "email", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False), default=Role.OWNER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    organization: Mapped[Organization] = relationship(back_populates="users")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_org_slug", "organization_id", "slug", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    default_branch: Mapped[str] = mapped_column(String(120), default="main")
    repository_provider: Mapped[str] = mapped_column(String(40), default="local")
    repository_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))

    organization: Mapped[Organization] = relationship(back_populates="projects")
    analyses: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index("ix_analysis_project_created", "project_id", "created_at"),
        Index("ix_analysis_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False))
    source_reference: Mapped[str] = mapped_column(String(2000), default="")
    base_revision: Mapped[str | None] = mapped_column(String(160), nullable=True)
    head_revision: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus, native_enum=False), default=AnalysisStatus.QUEUED, index=True
    )
    verdict: Mapped[Verdict] = mapped_column(
        Enum(Verdict, native_enum=False), default=Verdict.UNKNOWN
    )
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_components: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_stage: Mapped[str] = mapped_column(String(100), default="QUEUED")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    requirements_text: Mapped[str] = mapped_column(Text, default="")
    policy_name: Mapped[str] = mapped_column(String(100), default="default")
    runner_name: Mapped[str] = mapped_column(String(40), default="native")
    validation_commands: Mapped[list[list[str]]] = mapped_column(JSON, default=list)
    workspace_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    diff_text: Mapped[str] = mapped_column(Text, default="")

    project: Mapped[Project] = relationship(back_populates="analyses")
    requirements: Mapped[list["Requirement"]] = relationship(
        cascade="all, delete-orphan", back_populates="analysis"
    )
    changed_files: Mapped[list["ChangedFile"]] = relationship(
        cascade="all, delete-orphan", back_populates="analysis"
    )
    symbols: Mapped[list["CodeSymbol"]] = relationship(
        cascade="all, delete-orphan", back_populates="analysis"
    )
    dependency_edges: Mapped[list["DependencyEdge"]] = relationship(
        cascade="all, delete-orphan", back_populates="analysis"
    )
    findings: Mapped[list["Finding"]] = relationship(
        cascade="all, delete-orphan", back_populates="analysis"
    )
    test_executions: Mapped[list["TestExecution"]] = relationship(
        cascade="all, delete-orphan", back_populates="analysis"
    )
    artifacts: Mapped[list["EvidenceArtifact"]] = relationship(
        cascade="all, delete-orphan", back_populates="analysis"
    )
    policy_decisions: Mapped[list["PolicyDecision"]] = relationship(
        cascade="all, delete-orphan", back_populates="analysis"
    )
    events: Mapped[list["AnalysisEvent"]] = relationship(
        cascade="all, delete-orphan", back_populates="analysis"
    )


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(100), default="user")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    coverage_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    analysis: Mapped[AnalysisRun] = relationship(back_populates="requirements")


class ChangedFile(Base):
    __tablename__ = "changed_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(2000), index=True)
    change_type: Mapped[str] = mapped_column(String(40))
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    is_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    old_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    analysis: Mapped[AnalysisRun] = relationship(back_populates="changed_files")
    symbols: Mapped[list["CodeSymbol"]] = relationship(back_populates="file")


class CodeSymbol(Base):
    __tablename__ = "code_symbols"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("changed_files.id", ondelete="SET NULL"), nullable=True
    )
    qualified_name: Mapped[str] = mapped_column(String(1000), index=True)
    symbol_type: Mapped[str] = mapped_column(String(50))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    signature: Mapped[str] = mapped_column(Text, default="")
    complexity: Mapped[int] = mapped_column(Integer, default=1)
    exported: Mapped[bool] = mapped_column(Boolean, default=False)
    changed: Mapped[bool] = mapped_column(Boolean, default=False)

    analysis: Mapped[AnalysisRun] = relationship(back_populates="symbols")
    file: Mapped[ChangedFile | None] = relationship(back_populates="symbols")


class DependencyEdge(Base):
    __tablename__ = "dependency_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    source_symbol: Mapped[str] = mapped_column(String(1000))
    target_symbol: Mapped[str] = mapped_column(String(1000))
    edge_type: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    analysis: Mapped[AnalysisRun] = relationship(back_populates="dependency_edges")


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        Index("ix_findings_analysis_severity", "analysis_run_id", "severity"),
        Index("ix_findings_analysis_category", "analysis_run_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[FindingCategory] = mapped_column(Enum(FindingCategory, native_enum=False))
    severity: Mapped[FindingSeverity] = mapped_column(Enum(FindingSeverity, native_enum=False))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_id: Mapped[str] = mapped_column(String(200), index=True)
    remediation: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[FindingStatus] = mapped_column(
        Enum(FindingStatus, native_enum=False), default=FindingStatus.OPEN
    )

    analysis: Mapped[AnalysisRun] = relationship(back_populates="findings")


class TestExecution(Base):
    __tablename__ = "test_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    command: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[TestStatus] = mapped_column(Enum(TestStatus, native_enum=False))
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    stdout_excerpt: Mapped[str] = mapped_column(Text, default="")
    stderr_excerpt: Mapped[str] = mapped_column(Text, default="")
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    environment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    analysis: Mapped[AnalysisRun] = relationship(back_populates="test_executions")


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(160))
    storage_path: Mapped[str] = mapped_column(String(2000))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    analysis: Mapped[AnalysisRun] = relationship(back_populates="artifacts")


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    policy_name: Mapped[str] = mapped_column(String(160))
    rule_id: Mapped[str] = mapped_column(String(200))
    outcome: Mapped[PolicyOutcome] = mapped_column(Enum(PolicyOutcome, native_enum=False))
    explanation: Mapped[str] = mapped_column(Text)
    observed_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    expected_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    evidence_references: Mapped[list[str]] = mapped_column(JSON, default=list)

    analysis: Mapped[AnalysisRun] = relationship(back_populates="policy_decisions")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_org_created", "organization_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(200), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AnalysisEvent(Base):
    __tablename__ = "analysis_events"
    __table_args__ = (Index("ix_events_analysis_created", "analysis_run_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(30), default="info")
    message: Mapped[str] = mapped_column(Text)
    progress: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="completed")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    analysis: Mapped[AnalysisRun] = relationship(back_populates="events")
