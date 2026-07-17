"""Tenant-scoped data access helpers used across API routers and tasks."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from proofstack_api.models import AnalysisRun, Finding, Project, User


def get_project_for_user(db: Session, project_id: str, user: User) -> Project:
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == user.organization_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def get_analysis_for_user(db: Session, analysis_id: str, user: User) -> AnalysisRun:
    analysis = db.scalar(
        select(AnalysisRun)
        .join(Project, AnalysisRun.project_id == Project.id)
        .where(
            AnalysisRun.id == analysis_id,
            Project.organization_id == user.organization_id,
        )
    )
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return analysis


def get_finding_for_user(db: Session, finding_id: str, user: User) -> Finding:
    finding = db.scalar(
        select(Finding)
        .join(AnalysisRun, Finding.analysis_run_id == AnalysisRun.id)
        .join(Project, AnalysisRun.project_id == Project.id)
        .where(Finding.id == finding_id, Project.organization_id == user.organization_id)
    )
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return finding
