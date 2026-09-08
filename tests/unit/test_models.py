"""Unit tests for request and policy models.

Inputs come from `data/fnol_valid.json`, `data/fnol_invalid.json`, `data/fnol_edge.json`,
and `data/policies.json`.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from claims.models import NotificationRequest, RuleFailure

from .data import (
    MODEL_LAYER_REJECTS,
    fnol_cases,
    fnol_ids,
    policy_from_master,
)

_ALL_FNOL = (
    fnol_cases("fnol_valid.json")
    + fnol_cases("fnol_invalid.json")
    + fnol_cases("fnol_edge.json")
)
_ALL_FNOL_IDS = (
    fnol_ids("fnol_valid.json")
    + fnol_ids("fnol_invalid.json")
    + fnol_ids("fnol_edge.json")
)


class TestNotificationRequest:
    @pytest.mark.parametrize("case_id, payload", _ALL_FNOL, ids=_ALL_FNOL_IDS)
    def test_fnol_files_at_the_model_boundary(
        self, case_id: str, payload: dict[str, Any]
    ) -> None:
        if case_id in MODEL_LAYER_REJECTS:
            with pytest.raises(ValidationError):
                NotificationRequest.model_validate(payload)
            return
        req = NotificationRequest.model_validate(payload)
        assert req.policy_number == payload["policy_number"]
        assert req.claim_type == payload["claim_type"]


class TestPolicy:
    @pytest.mark.parametrize(
        "policy_number, cancelled",
        [("MOT-4471", False), ("MOT-4497", True)],
        ids=["MOT-4471-active", "MOT-4497-cancelled"],
    )
    def test_policies_json_cancellation_date(
        self, policy_number: str, cancelled: bool
    ) -> None:
        policy = policy_from_master(policy_number)
        assert policy.policy_number == policy_number
        if cancelled:
            assert policy.cancellation_date is not None
        else:
            assert policy.cancellation_date is None


class TestRuleFailure:
    @pytest.mark.parametrize(
        "rule_id, error_code",
        [
            ("V-1", "POLICY_NOT_FOUND"),
            ("V-2", "LOSS_BEFORE_INCEPTION"),
            ("V-7", "POLICY_CANCELLED"),
            ("V-3", "LOSS_AFTER_EXPIRY"),
            ("V-4", "AMOUNT_EXCEEDS_LIMIT"),
            ("V-5", "TYPE_NOT_COVERED"),
            ("V-6", "DUPLICATE_NOTIFICATION"),
        ],
        ids=[
            "POLICY_NOT_FOUND",
            "LOSS_BEFORE_INCEPTION",
            "POLICY_CANCELLED",
            "LOSS_AFTER_EXPIRY",
            "AMOUNT_EXCEEDS_LIMIT",
            "TYPE_NOT_COVERED",
            "DUPLICATE_NOTIFICATION",
        ],
    )
    def test_carries_rule_id_and_error_code_separately(
        self, rule_id: str, error_code: str
    ) -> None:
        failure = RuleFailure(rule_id=rule_id, error_code=error_code)
        assert failure.rule_id == rule_id
        assert failure.error_code == error_code
        with pytest.raises(ValidationError):
            failure.rule_id = "V-9"
