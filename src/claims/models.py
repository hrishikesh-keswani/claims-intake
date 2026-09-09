"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Day 2 assignment. Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# Contract 2.3. A Literal makes an out-of-vocabulary value unrepresentable
# before any rule (including V-5) runs.
ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]

# Contract 2.2: USD, greater than zero, at most two decimal places.
# Carried on the type so a comparison against policy.limit is the same kind of value.
UsdAmount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class NotificationRequest(BaseModel):
    """A first notice of loss as submitted by the claims portal.

    Shape only (contract 2.2 and 2.4). Policy existence, term, limit, and
    product cover are rules in `service.py`.
    """

    model_config = {"extra": "forbid"}

    policy_number: str = Field(..., min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: UsdAmount
    description: str | None = None


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists.

    cancellation_date is `date | None` so WI-0158 AC-3 is a type check: comparing
    the date without narrowing None does not type-check.
    """

    policy_number: str
    product: str
    effective_date: date
    expiry_date: date
    cancellation_date: date | None
    limit: UsdAmount
    permitted_claim_types: list[ClaimType]


class RuleFailure(BaseModel):
    """A rule violation: identifier and contract error code as distinct fields.

    Frozen so a `rule_id` cannot be written where an `error_code` is expected.
    """

    model_config = {"frozen": True}

    rule_id: str
    error_code: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ClaimRecord(BaseModel):
    """A recorded notification with its issued claim reference (contract section 3)."""

    policy_number: str
    loss_date: date
    claim_type: ClaimType
    estimated_amount: UsdAmount
    claim_reference: str
    status: str = "recorded"
