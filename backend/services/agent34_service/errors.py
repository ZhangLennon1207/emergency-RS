from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from pydantic import ValidationError


@dataclass(frozen=True)
class ErrorSpec:
    status: int
    message: str
    retryable: bool


ERRORS = {
    "EMPTY_CLAIM_LIST": ErrorSpec(422, "claim_list must contain at least one claim", False),
    "UNKNOWN_EVIDENCE_ID": ErrorSpec(422, "a claim references an unknown evidence identifier", False),
    "MODEL_NOT_READY": ErrorSpec(503, "the requested model runtime is not ready", True),
    "MODEL_TIMEOUT": ErrorSpec(504, "model inference exceeded the service time limit", True),
    "INTERNAL_ERROR": ErrorSpec(500, "an unexpected internal error occurred", False),
    "INVALID_REQUEST": ErrorSpec(422, "request validation failed", False),
    "IMAGE_DECODE_FAILED": ErrorSpec(422, "an uploaded image cannot be decoded", False),
    "SERVICE_BUSY": ErrorSpec(503, "Agent34 runtime is busy", True),
    "MODEL_OUTPUT_INVALID": ErrorSpec(502, "model output failed contract validation", False),
    "UNAUTHORIZED": ErrorSpec(401, "authentication failed", False),
}


def service_error(code: str) -> HTTPException:
    spec = ERRORS[code]
    return HTTPException(spec.status, detail={
        "code": code, "message": spec.message, "retryable": spec.retryable,
    })


def validation_code(exc: ValidationError) -> str:
    for error in exc.errors():
        loc = tuple(str(item) for item in error.get("loc", ()))
        message = str(error.get("msg", "")).lower()
        if "claim_list" in loc and error.get("type") == "too_short":
            return "EMPTY_CLAIM_LIST"
        if "unknown identifiers" in message:
            return "UNKNOWN_EVIDENCE_ID"
    return "INVALID_REQUEST"


def runtime_code(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError,)):
        return "MODEL_TIMEOUT"
    if isinstance(exc, (FileNotFoundError, ImportError, ModuleNotFoundError)):
        return "MODEL_NOT_READY"
    if isinstance(exc, RuntimeError):
        message = str(exc).lower()
        if any(token in message for token in (
            "not configured", "not found", "missing", "cuda out of memory",
            "no gpu", "no kernel image", "failed to load",
        )):
            return "MODEL_NOT_READY"
        if "timeout" in message or "timed out" in message:
            return "MODEL_TIMEOUT"
    return "INTERNAL_ERROR"
