"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Day 4 lab. Implement against `docs/api-contract.md` sections 5 and 6.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from claims.models import NotificationRequest
from claims.policy_client import (
    LookupFailureReason,
    PolicyClient,
    PolicyLookupFailed,
    StubPolicyClient,
)
from claims.repository import NotificationRepository
from claims.service import ValidationOutcome, submit_notification

app = FastAPI(title="Claims Intake Service")

_policy_client = StubPolicyClient()
_repository = NotificationRepository()


def get_policy_client() -> PolicyClient:
    return _policy_client


def get_repository() -> NotificationRepository:
    return _repository


# Contract section 6: every error code maps to exactly one HTTP status.
STATUS_BY_CODE: dict[str, int] = {
    "MALFORMED_REQUEST": 400,
    "DUPLICATE_NOTIFICATION": 409,
    "POLICY_NOT_FOUND": 422,
    "LOSS_BEFORE_INCEPTION": 422,
    "POLICY_CANCELLED": 422,
    "LOSS_AFTER_EXPIRY": 422,
    "AMOUNT_EXCEEDS_LIMIT": 422,
    "TYPE_NOT_COVERED": 422,
    "INTERNAL_ERROR": 500,
    "POLICY_MASTER_INVALID_RESPONSE": 502,
    "POLICY_MASTER_UNAVAILABLE": 503,
    "POLICY_MASTER_TIMEOUT": 504,
}

LOOKUP_CODE_BY_REASON: dict[LookupFailureReason, str] = {
    "unreachable": "POLICY_MASTER_UNAVAILABLE",
    "timeout": "POLICY_MASTER_TIMEOUT",
    "unparsable": "POLICY_MASTER_INVALID_RESPONSE",
}

MESSAGES: dict[str, str] = {
    "MALFORMED_REQUEST": "The request body could not be interpreted.",
    "DUPLICATE_NOTIFICATION": (
        "A notification for this policy, loss date, and claim type has already "
        "been recorded."
    ),
    "POLICY_NOT_FOUND": "The policy number does not exist in the policy master.",
    "LOSS_BEFORE_INCEPTION": "The loss date is before the policy effective date.",
    "POLICY_CANCELLED": (
        "The policy has a cancellation date and the loss date falls on or after it."
    ),
    "LOSS_AFTER_EXPIRY": "The loss date is after the policy expiry date.",
    "AMOUNT_EXCEEDS_LIMIT": "The estimated amount exceeds the policy limit.",
    "TYPE_NOT_COVERED": "The claim type is not permitted on the policy's product.",
    "INTERNAL_ERROR": "The service encountered an unexpected internal failure.",
    "POLICY_MASTER_UNAVAILABLE": (
        "The policy master could not be reached or did not respond."
    ),
    "POLICY_MASTER_TIMEOUT": (
        "The policy master did not respond within the allowed time."
    ),
    "POLICY_MASTER_INVALID_RESPONSE": (
        "The policy master returned a response the service cannot parse."
    ),
}

_REASON_BY_ERROR_TYPE: dict[str, str] = {
    "missing": "required_field_missing",
    "extra_forbidden": "unexpected_field",
    "literal_error": "value_not_in_vocabulary",
    "enum": "value_not_in_vocabulary",
}

_JSON_ERROR_TYPES = frozenset({"json_invalid", "json_decode"})


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def error_envelope(
    code: str,
    *,
    message: str | None = None,
    detail: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build the section 5 envelope with the section 6 status for `code`."""
    status = STATUS_BY_CODE.get(code, STATUS_BY_CODE["INTERNAL_ERROR"])
    body: dict[str, Any] = {
        "code": code,
        "message": message if message is not None else MESSAGES.get(code, code),
        "detail": _jsonable(detail if detail is not None else {}),
    }
    return JSONResponse(status_code=status, content=body)


def _field_from_loc(loc: tuple[Any, ...]) -> str | None:
    parts = [part for part in loc if part != "body" and not isinstance(part, int)]
    if not parts:
        return None
    return str(parts[0])


def _malformed_detail(exc: RequestValidationError) -> dict[str, Any]:
    errors = exc.errors()
    if not errors:
        return {}
    first = errors[0]
    error_type = str(first.get("type", ""))
    if error_type in _JSON_ERROR_TYPES:
        return {}
    loc = first.get("loc", ())
    if not isinstance(loc, tuple):
        loc = tuple(loc)
    field = _field_from_loc(loc)
    if field is None:
        return {}
    reason = _REASON_BY_ERROR_TYPE.get(error_type, "wrong_type_or_format")
    return {"field": field, "reason": reason}


@app.exception_handler(RequestValidationError)
async def malformed_request_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    # FastAPI's default is 422. Contract 2.4 and 6.1 assign parse failures to 400.
    return error_envelope(
        "MALFORMED_REQUEST",
        message=MESSAGES["MALFORMED_REQUEST"],
        detail=_malformed_detail(exc),
    )


@app.exception_handler(Exception)
async def internal_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    return error_envelope(
        "INTERNAL_ERROR",
        message=MESSAGES["INTERNAL_ERROR"],
        detail={},
    )


def _response_for_outcome(outcome: ValidationOutcome) -> JSONResponse:
    if outcome.passed:
        if outcome.claim_reference is None:
            return error_envelope("INTERNAL_ERROR")
        return JSONResponse(
            status_code=201,
            content={
                "claim_reference": outcome.claim_reference,
                "status": "recorded",
            },
        )
    if outcome.code is None or outcome.code not in STATUS_BY_CODE:
        return error_envelope("INTERNAL_ERROR")
    return error_envelope(
        outcome.code,
        message=MESSAGES.get(outcome.code),
        detail=outcome.detail,
    )


PolicyClientDep = Annotated[PolicyClient, Depends(get_policy_client)]
RepositoryDep = Annotated[NotificationRepository, Depends(get_repository)]


@app.post("/notifications")
def create_notification(
    notification: NotificationRequest,
    policy_client: PolicyClientDep,
    repository: RepositoryDep,
) -> JSONResponse:
    try:
        outcome = submit_notification(notification, policy_client, repository)
    except PolicyLookupFailed as exc:
        code = LOOKUP_CODE_BY_REASON[exc.reason]
        return error_envelope(code, message=MESSAGES[code], detail={})
    return _response_for_outcome(outcome)