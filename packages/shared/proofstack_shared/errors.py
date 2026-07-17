"""Public error contracts that keep internal traces out of API responses."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ProofStackError(Exception):
    """Base exception with a stable machine-readable code."""

    def __init__(self, message: str, *, code: str = "proofstack_error") -> None:
        super().__init__(message)
        self.code = code


class NotFoundError(ProofStackError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="not_found")


class AuthorizationError(ProofStackError):
    def __init__(self, message: str = "You do not have permission to perform this action") -> None:
        super().__init__(message, code="forbidden")


class UnsafeInputError(ProofStackError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="unsafe_input")
