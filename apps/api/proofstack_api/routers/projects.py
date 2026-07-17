"""Tenant-isolated project CRUD and analysis history."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from proofstack_shared.enums import AnalysisStatus, Role
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from proofstack_api.audit import record_audit
from proofstack_api.auth import get_current_user, require_role
from proofstack_api.database import get_db
from proofstack_api.models import AnalysisRun, Project, User
from proofstack_api.repositories import get_project_for_user
from proofstack_api.schemas import (
    AnalysisResponse,
    Page,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_response(project: Project, analysis_count: int = 0) -> ProjectResponse:
    return ProjectResponse.model_validate(project).model_copy(
        update={"analysis_count": analysis_count}
    )


@router.get("", response_model=Page[ProjectResponse])
def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    provider: str | None = Query(default=None, max_length=40),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ProjectResponse]:
    predicates = [Project.organization_id == user.organization_id]
    if search:
        needle = f"%{search.strip()}%"
        predicates.append(or_(Project.name.ilike(needle), Project.description.ilike(needle)))
    if provider:
        predicates.append(Project.repository_provider == provider)
    total = db.scalar(select(func.count()).select_from(Project).where(*predicates)) or 0
    rows = db.execute(
        select(Project, func.count(AnalysisRun.id))
        .outerjoin(AnalysisRun)
        .where(*predicates)
        .group_by(Project.id)
        .order_by(Project.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[_project_response(project, count) for project, count in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    request: Request,
    user: User = Depends(require_role(Role.MAINTAINER)),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    duplicate = db.scalar(
        select(Project.id).where(
            Project.organization_id == user.organization_id,
            Project.slug == payload.slug,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="A project with this slug already exists")
    project = Project(
        organization_id=user.organization_id,
        created_by=user.id,
        **payload.model_dump(),
    )
    db.add(project)
    db.flush()
    record_audit(
        db,
        user=user,
        action="project.created",
        resource_type="project",
        resource_id=project.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(project)
    return _project_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    project = get_project_for_user(db, project_id, user)
    count = (
        db.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(AnalysisRun.project_id == project.id)
        )
        or 0
    )
    return _project_response(project, count)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    request: Request,
    user: User = Depends(require_role(Role.MAINTAINER)),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    project = get_project_for_user(db, project_id, user)
    updates = payload.model_dump(exclude_unset=True)
    if "slug" in updates:
        duplicate = db.scalar(
            select(Project.id).where(
                Project.organization_id == user.organization_id,
                Project.slug == updates["slug"],
                Project.id != project.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="A project with this slug already exists")
    for key, value in updates.items():
        setattr(project, key, value)
    record_audit(
        db,
        user=user,
        action="project.updated",
        resource_type="project",
        resource_id=project.id,
        metadata={"fields": sorted(updates)},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(project)
    return _project_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    request: Request,
    user: User = Depends(require_role(Role.MAINTAINER)),
    db: Session = Depends(get_db),
) -> None:
    project = get_project_for_user(db, project_id, user)
    record_audit(
        db,
        user=user,
        action="project.deleted",
        resource_type="project",
        resource_id=project.id,
        metadata={"name": project.name},
        ip_address=request.client.host if request.client else None,
    )
    db.delete(project)
    db.commit()


@router.get("/{project_id}/analyses", response_model=Page[AnalysisResponse])
def project_analyses(
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    analysis_status: AnalysisStatus | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[AnalysisResponse]:
    project = get_project_for_user(db, project_id, user)
    predicates = [AnalysisRun.project_id == project.id]
    if analysis_status:
        predicates.append(AnalysisRun.status == analysis_status)
    total = db.scalar(select(func.count()).select_from(AnalysisRun).where(*predicates)) or 0
    analyses = list(
        db.scalars(
            select(AnalysisRun)
            .where(*predicates)
            .order_by(AnalysisRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return Page(
        items=[AnalysisResponse.model_validate(item) for item in analyses],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )
