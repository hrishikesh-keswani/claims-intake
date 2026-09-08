"""Unit tests for rule evaluation and submission.

Written from `docs/api-contract.md` section 4 and `docs/requirements-brief.md`.
Each rule has a parametrized test covering both sides of its comparison and the
boundary. Inputs are typed `date` and `Decimal` values, never strings or floats.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claims.models import NotificationRequest, Policy, RuleFailure
from claims.policy_client import LookupFailureReason, PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import (
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
    evaluate_loss_after_inception,
    evaluate_loss_before_expiry,
    evaluate_not_duplicate,
    evaluate_notification,
    evaluate_policy_exists,
    evaluate_policy_not_cancelled,
    submit_notification,
)


def _notification(**overrides: object) -> NotificationRequest:
    payload: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 4, 2),
        "claim_type": "collision",
        "estimated_amount": Decimal("4200.00"),
    }
    payload.update(overrides)
    return NotificationRequest.model_validate(payload)


def _policy(**overrides: object) -> Policy:
    payload: dict[str, object] = {
        "policy_number": "MOT-4471",
        "product": "personal_auto_standard",
        "effective_date": date(2026, 3, 1),
        "expiry_date": date(2027, 2, 28),
        "cancellation_date": None,
        "limit": Decimal("50000.00"),
        "permitted_claim_types": [
            "collision",
            "theft",
            "glass",
            "liability",
            "weather",
        ],
    }
    payload.update(overrides)
    return Policy.model_validate(payload)


class TestEvaluatePolicyExists:
    @pytest.fixture
    def policy_client(self) -> StubPolicyClient:
        return StubPolicyClient()

    @pytest.mark.parametrize(
        "policy_number, expect_passed, expect_code",
        [
            pytest.param("MOT-4471", True, None, id="policy-exists"),
            pytest.param(
                "MOT-9999", False, "POLICY_NOT_FOUND", id="policy-not-found"
            ),
        ],
    )
    def test_v1_policy_exists_in_the_master(
        self,
        policy_client: StubPolicyClient,
        policy_number: str,
        expect_passed: bool,
        expect_code: str | None,
    ) -> None:
        notification = _notification(policy_number=policy_number)
        outcome = evaluate_policy_exists(notification, policy_client)
        assert outcome.passed is expect_passed
        if expect_passed:
            assert outcome.code is None
            assert outcome.rule is None
        else:
            assert outcome.rule == "V-1"
            assert outcome.code == expect_code


class TestEvaluateLossAfterInception:
    @pytest.mark.parametrize(
        "loss_date, expect_passed",
        [
            pytest.param(date(2026, 3, 14), False, id="before-inception"),
            pytest.param(date(2026, 3, 15), True, id="on-inception-wi-0142-ac-3"),
            pytest.param(date(2026, 3, 16), True, id="after-inception"),
        ],
    )
    def test_v2_loss_date_against_effective_date(
        self, loss_date: date, expect_passed: bool
    ) -> None:
        policy = _policy(effective_date=date(2026, 3, 15))
        notification = _notification(loss_date=loss_date)
        outcome = evaluate_loss_after_inception(notification, policy)
        assert outcome.passed is expect_passed
        if expect_passed:
            assert outcome.code is None
        else:
            assert outcome.rule == "V-2"
            assert outcome.code == "LOSS_BEFORE_INCEPTION"


class TestEvaluatePolicyNotCancelled:
    @pytest.mark.parametrize(
        "cancellation_date, loss_date, expect_passed",
        [
            pytest.param(
                date(2026, 1, 15),
                date(2026, 1, 14),
                True,
                id="before-cancellation",
            ),
            pytest.param(
                date(2026, 1, 15),
                date(2026, 1, 15),
                False,
                id="on-cancellation-wi-0158-ac-2",
            ),
            pytest.param(
                date(2026, 1, 15),
                date(2026, 1, 16),
                False,
                id="after-cancellation",
            ),
            pytest.param(
                None,
                date(2026, 4, 2),
                True,
                id="cancellation-date-absent-wi-0158-ac-3",
            ),
        ],
    )
    def test_v7_loss_date_against_cancellation_date(
        self,
        cancellation_date: date | None,
        loss_date: date,
        expect_passed: bool,
    ) -> None:
        policy = _policy(
            effective_date=date(2025, 6, 1),
            expiry_date=date(2026, 5, 31),
            cancellation_date=cancellation_date,
        )
        notification = _notification(loss_date=loss_date)
        outcome = evaluate_policy_not_cancelled(notification, policy)
        assert outcome.passed is expect_passed
        if expect_passed:
            assert outcome.code is None
        else:
            assert outcome.rule == "V-7"
            assert outcome.code == "POLICY_CANCELLED"


class TestEvaluateLossBeforeExpiry:
    @pytest.mark.parametrize(
        "loss_date, expect_passed",
        [
            pytest.param(date(2026, 2, 27), True, id="before-expiry"),
            pytest.param(date(2026, 2, 28), True, id="on-expiry"),
            pytest.param(date(2026, 3, 1), False, id="after-expiry"),
        ],
    )
    def test_v3_loss_date_against_expiry_date(
        self, loss_date: date, expect_passed: bool
    ) -> None:
        policy = _policy(
            effective_date=date(2025, 3, 1),
            expiry_date=date(2026, 2, 28),
        )
        notification = _notification(loss_date=loss_date)
        outcome = evaluate_loss_before_expiry(notification, policy)
        assert outcome.passed is expect_passed
        if expect_passed:
            assert outcome.code is None
        else:
            assert outcome.rule == "V-3"
            assert outcome.code == "LOSS_AFTER_EXPIRY"


class TestEvaluateAmountWithinLimit:
    @pytest.mark.parametrize(
        "estimated_amount, expect_passed",
        [
            pytest.param(Decimal("49999.99"), True, id="below-limit"),
            pytest.param(Decimal("50000.00"), True, id="equal-to-limit"),
            pytest.param(Decimal("50000.01"), False, id="above-limit"),
        ],
    )
    def test_v4_estimated_amount_against_limit(
        self, estimated_amount: Decimal, expect_passed: bool
    ) -> None:
        policy = _policy(limit=Decimal("50000.00"))
        notification = _notification(estimated_amount=estimated_amount)
        outcome = evaluate_amount_within_limit(notification, policy)
        assert outcome.passed is expect_passed
        if expect_passed:
            assert outcome.code is None
        else:
            assert outcome.rule == "V-4"
            assert outcome.code == "AMOUNT_EXCEEDS_LIMIT"


class TestEvaluateClaimTypeCovered:
    @pytest.mark.parametrize(
        "claim_type, permitted, expect_passed",
        [
            pytest.param(
                "collision",
                ["collision", "theft", "glass", "liability", "weather"],
                True,
                id="type-permitted",
            ),
            pytest.param(
                "collision",
                ["liability"],
                False,
                id="type-not-permitted",
            ),
        ],
    )
    def test_v5_claim_type_against_product_cover(
        self,
        claim_type: str,
        permitted: list[str],
        expect_passed: bool,
    ) -> None:
        policy = _policy(permitted_claim_types=permitted)
        notification = _notification(claim_type=claim_type)
        outcome = evaluate_claim_type_covered(notification, policy)
        assert outcome.passed is expect_passed
        if expect_passed:
            assert outcome.code is None
        else:
            assert outcome.rule == "V-5"
            assert outcome.code == "TYPE_NOT_COVERED"


class TestEvaluateNotDuplicate:
    @pytest.fixture
    def repo(self) -> NotificationRepository:
        return NotificationRepository()

    @pytest.mark.parametrize(
        "pre_record, mutate, expect_duplicate",
        [
            pytest.param(True, "none", True, id="same-triple"),
            pytest.param(True, "claim_type", False, id="two-of-three-claim-type"),
            pytest.param(True, "loss_date", False, id="two-of-three-loss-date"),
            pytest.param(
                True, "policy_number", False, id="two-of-three-policy-number"
            ),
            pytest.param(
                False, "none", False, id="rejected-not-recorded-wi-0151-ac-3"
            ),
        ],
    )
    def test_v6_duplicate_matches_recorded_triple(
        self,
        repo: NotificationRepository,
        pre_record: bool,
        mutate: str,
        expect_duplicate: bool,
    ) -> None:
        recorded = _notification()
        if pre_record:
            repo.record(recorded)
        query = recorded
        if mutate == "claim_type":
            query = _notification(claim_type="theft")
        elif mutate == "loss_date":
            query = _notification(loss_date=date(2026, 4, 3))
        elif mutate == "policy_number":
            query = _notification(policy_number="MOT-4472")
        outcome = evaluate_not_duplicate(query, repo)
        assert outcome.passed is (not expect_duplicate)
        if expect_duplicate:
            assert outcome.rule == "V-6"
            assert outcome.code == "DUPLICATE_NOTIFICATION"
            assert "existing_claim_reference" in outcome.detail
        else:
            assert outcome.code is None


class TestEvaluateNotification:
    @pytest.mark.parametrize(
        "policy, notification, expected_rule, expected_code",
        [
            pytest.param(
                _policy(effective_date=date(2026, 3, 15), limit=Decimal("50000.00")),
                _notification(
                    loss_date=date(2026, 3, 2),
                    estimated_amount=Decimal("72000.00"),
                ),
                "V-2",
                "LOSS_BEFORE_INCEPTION",
                id="v2-before-v4",
            ),
            pytest.param(
                _policy(
                    effective_date=date(2025, 1, 1),
                    expiry_date=date(2025, 12, 31),
                    cancellation_date=date(2025, 10, 1),
                ),
                _notification(loss_date=date(2026, 1, 8)),
                "V-7",
                "POLICY_CANCELLED",
                id="v7-before-v3-wi-0158-ac-4",
            ),
        ],
    )
    def test_reports_first_failure_in_contract_order(
        self,
        policy: Policy,
        notification: NotificationRequest,
        expected_rule: str,
        expected_code: str,
    ) -> None:
        failure = evaluate_notification(notification, policy)
        assert isinstance(failure, RuleFailure)
        assert failure.rule_id == expected_rule
        assert failure.error_code == expected_code

    def test_returns_none_when_policy_rules_pass(self) -> None:
        failure = evaluate_notification(_notification(), _policy())
        assert failure is None


class TestSubmitNotification:
    @pytest.fixture
    def policy_client(self) -> StubPolicyClient:
        return StubPolicyClient()

    @pytest.fixture
    def repo(self) -> NotificationRepository:
        return NotificationRepository()

    def test_records_when_every_rule_passes(
        self, policy_client: StubPolicyClient, repo: NotificationRepository
    ) -> None:
        notification = _notification()
        outcome = submit_notification(notification, policy_client, repo)
        assert outcome.passed is True
        assert outcome.claim_reference is not None
        assert outcome.claim_reference.startswith("CLM-")
        found = repo.find_matching(
            notification.policy_number,
            notification.loss_date,
            notification.claim_type,
        )
        assert found is not None
        assert found.claim_reference == outcome.claim_reference

    def test_policy_not_found_is_v1_not_v2(
        self, policy_client: StubPolicyClient, repo: NotificationRepository
    ) -> None:
        """WI-0142 AC-4: a missing policy is POLICY_NOT_FOUND, never V-2."""
        notification = _notification(
            policy_number="MOT-9999",
            loss_date=date(2020, 1, 1),
        )
        outcome = submit_notification(notification, policy_client, repo)
        assert outcome.passed is False
        assert outcome.rule == "V-1"
        assert outcome.code == "POLICY_NOT_FOUND"
        assert (
            repo.find_matching(
                notification.policy_number,
                notification.loss_date,
                notification.claim_type,
            )
            is None
        )

    @pytest.mark.parametrize(
        "reason",
        [
            pytest.param("timeout", id="timeout"),
            pytest.param("unreachable", id="unreachable"),
            pytest.param("unparsable", id="unparsable"),
        ],
    )
    def test_policy_lookup_failed_propagates_with_reason(
        self, repo: NotificationRepository, reason: LookupFailureReason
    ) -> None:
        client = StubPolicyClient(fail_with=reason)
        notification = _notification()
        with pytest.raises(PolicyLookupFailed) as exc_info:
            submit_notification(notification, client, repo)
        assert exc_info.value.reason == reason
        assert exc_info.value.policy_number == notification.policy_number

    def test_duplicate_includes_existing_claim_reference(
        self, policy_client: StubPolicyClient, repo: NotificationRepository
    ) -> None:
        first = submit_notification(_notification(), policy_client, repo)
        second = submit_notification(_notification(), policy_client, repo)
        assert first.passed is True
        assert second.passed is False
        assert second.rule == "V-6"
        assert second.code == "DUPLICATE_NOTIFICATION"
        assert second.detail["existing_claim_reference"] == first.claim_reference

    def test_failed_submission_is_not_recorded(
        self, policy_client: StubPolicyClient, repo: NotificationRepository
    ) -> None:
        notification = _notification(
            policy_number="MOT-4486",
            loss_date=date(2026, 3, 14),
            claim_type="collision",
            estimated_amount=Decimal("6200.00"),
        )
        outcome = submit_notification(notification, policy_client, repo)
        assert outcome.passed is False
        assert outcome.code == "TYPE_NOT_COVERED"
        assert (
            repo.find_matching(
                notification.policy_number,
                notification.loss_date,
                notification.claim_type,
            )
            is None
        )
