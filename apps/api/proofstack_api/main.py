"""FastAPI application factory and middleware composition."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from proofstack_shared.config import Settings, get_settings
from proofstack_shared.errors import ProofStackError
from proofstack_shared.logging import configure_logging
from proofstack_shared.version import VERSION

from proofstack_api.database import Base, engine
from proofstack_api.routers import (
    analyses,
    audit,
    auth,
    findings,
    organizations,
    policies,
    projects,
    system,
)

LOGGER = logging.getLogger("proofstack.api")


def _error(
    request: Request, status_code: int, code: str, message: str, details: object = None
) -> JSONResponse:
    payload = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
            "details": details or {},
        }
    }
    return JSONResponse(status_code=status_code, content=payload)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or get_settings()
    configure_logging(runtime.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if runtime.env in {"development", "test"}:
            Base.metadata.create_all(engine)
        yield

    application = FastAPI(
        title="ProofStack API",
        summary="Evidence-driven acceptance for AI-generated code changes",
        description=(
            "ProofStack prepares a repository safely, analyzes a change, executes bounded "
            "validation, evaluates policy, and exports a verifiable evidence bundle."
        ),
        version=VERSION,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next: object) -> object:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))[:128]
        request.state.request_id = request_id
        started = monotonic()
        response = await call_next(request)  # type: ignore[operator]
        duration_ms = round((monotonic() - started) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(duration_ms)
        LOGGER.info(
            "api_request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return _error(request, 422, "validation_error", "Request validation failed", details)

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        message = str(exc.detail) if not isinstance(exc.detail, dict) else "Request failed"
        return _error(
            request,
            exc.status_code,
            "http_error",
            message,
            exc.detail if isinstance(exc.detail, dict) else None,
        )

    @application.exception_handler(ProofStackError)
    async def domain_error(request: Request, exc: ProofStackError) -> JSONResponse:
        status_code = 403 if exc.code == "forbidden" else 400
        if exc.code == "not_found":
            status_code = 404
        return _error(request, status_code, exc.code, str(exc))

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, _: Exception) -> JSONResponse:
        message = "An unexpected error occurred"
        if runtime.env == "development":
            message += "; inspect the structured API log for details"
        return _error(request, 500, "internal_error", message)

    prefix = "/api/v1"
    application.include_router(auth.router, prefix=prefix)
    application.include_router(organizations.router, prefix=prefix)
    application.include_router(projects.router, prefix=prefix)
    application.include_router(analyses.router, prefix=prefix)
    application.include_router(findings.router, prefix=prefix)
    application.include_router(policies.router, prefix=prefix)
    application.include_router(audit.router, prefix=prefix)
    application.include_router(system.router, prefix=prefix)
    return application


app = create_app()
