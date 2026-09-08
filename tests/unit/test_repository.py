"""Unit tests for the notification repository.

Notifications under test are built from `data/fnol_valid.json`,
`data/fnol_invalid.json`, and `data/fnol_edge.json`.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

import pytest

from claims.repository import NotificationRepository

from .data import notification_from_fnol


def _recording_year() -> int:
    return datetime.now(tz=UTC).date().year


class TestNotificationRepository:
    @pytest.fixture
    def repo(self) -> NotificationRepository:
        return NotificationRepository()

    @pytest.mark.parametrize(
        "case_id",
        [
            "VALID-01",
            "VALID-02",
            "VALID-03",
            "VALID-04",
            "VALID-05",
            "VALID-06",
            "VALID-07",
            "VALID-08",
        ],
        ids=[
            "VALID-01",
            "VALID-02",
            "VALID-03",
            "VALID-04",
            "VALID-05",
            "VALID-06",
            "VALID-07",
            "VALID-08",
        ],
    )
    def test_record_issues_contract_reference(
        self, repo: NotificationRepository, case_id: str
    ) -> None:
        req = notification_from_fnol(case_id)
        recorded = repo.record(req)
        year = _recording_year()
        assert re.match(r"^CLM-\d{4}-\d{6}$", recorded.claim_reference)
        assert recorded.claim_reference.startswith(f"CLM-{year}-")
        assert recorded.loss_date == req.loss_date
        assert recorded.estimated_amount == req.estimated_amount
        assert recorded.status == "recorded"

    def test_reference_uses_recording_year_not_loss_year(
        self, repo: NotificationRepository
    ) -> None:
        notification = notification_from_fnol("VALID-01").model_copy(
            update={"loss_date": date(2025, 12, 15)}
        )
        recorded = repo.record(notification)
        assert recorded.loss_date == date(2025, 12, 15)
        assert recorded.claim_reference == f"CLM-{_recording_year()}-000001"

    def test_references_are_unique_for_recorded_fnol(
        self, repo: NotificationRepository
    ) -> None:
        year = _recording_year()
        first = repo.record(notification_from_fnol("EDGE-01"))
        second = repo.record(notification_from_fnol("EDGE-02"))
        assert first.claim_reference == f"CLM-{year}-000001"
        assert second.claim_reference == f"CLM-{year}-000002"
        assert first.claim_reference != second.claim_reference

    def test_instances_do_not_share_state(self) -> None:
        first = notification_from_fnol("EDGE-01")
        repo1 = NotificationRepository()
        repo2 = NotificationRepository()
        recorded = repo1.record(first)
        assert (
            repo2.find_matching(first.policy_number, first.loss_date, first.claim_type)
            is None
        )
        assert repo2.record(notification_from_fnol("EDGE-01")).claim_reference == (
            f"CLM-{_recording_year()}-000001"
        )
        assert recorded.claim_reference == f"CLM-{_recording_year()}-000001"

    def test_allocate_claim_reference_does_not_record(
        self, repo: NotificationRepository
    ) -> None:
        req = notification_from_fnol("EDGE-01")
        reference = repo.allocate_claim_reference()
        assert reference == f"CLM-{_recording_year()}-000001"
        assert (
            repo.find_matching(req.policy_number, req.loss_date, req.claim_type) is None
        )

    @pytest.mark.parametrize(
        "query_id, expect_match",
        [
            ("EDGE-01", True),
            ("EDGE-02", False),
            ("INVALID-01", False),
        ],
        ids=["EDGE-01-same-triple", "EDGE-02-different-triple", "INVALID-01-different-triple"],
    )
    def test_duplicate_matches_only_the_recorded_fnol_triple(
        self, repo: NotificationRepository, query_id: str, expect_match: bool
    ) -> None:
        recorded = repo.record(notification_from_fnol("EDGE-01"))
        query = notification_from_fnol(query_id)
        found = repo.find_matching(query.policy_number, query.loss_date, query.claim_type)
        if expect_match:
            assert found is not None
            assert found.claim_reference == recorded.claim_reference
        else:
            assert found is None

    @pytest.mark.parametrize(
        "use_other_policy, use_other_date, use_other_type",
        [
            pytest.param(False, False, True, id="same-policy-and-date"),
            pytest.param(False, True, False, id="same-policy-and-type"),
            pytest.param(True, False, False, id="same-date-and-type"),
        ],
    )
    def test_two_of_three_fields_from_fnol_is_not_a_duplicate(
        self,
        repo: NotificationRepository,
        use_other_policy: bool,
        use_other_date: bool,
        use_other_type: bool,
    ) -> None:
        recorded = repo.record(notification_from_fnol("EDGE-01"))
        other = notification_from_fnol("EDGE-03")
        found = repo.find_matching(
            other.policy_number if use_other_policy else recorded.policy_number,
            other.loss_date if use_other_date else recorded.loss_date,
            other.claim_type if use_other_type else recorded.claim_type,
        )
        assert found is None

    def test_find_matching_among_recorded_fnol(
        self, repo: NotificationRepository
    ) -> None:
        repo.record(notification_from_fnol("EDGE-01"))
        repo.record(notification_from_fnol("EDGE-02"))
        repo.record(notification_from_fnol("INVALID-01"))
        query = notification_from_fnol("EDGE-02")
        found = repo.find_matching(query.policy_number, query.loss_date, query.claim_type)
        assert found is not None
        assert found.estimated_amount == query.estimated_amount

    def test_rejected_notification_is_not_a_duplicate(
        self, repo: NotificationRepository
    ) -> None:
        """INVALID-06 is refused, so a later submission of the same triple is not a duplicate."""
        rejected = notification_from_fnol("INVALID-06")
        repo.allocate_claim_reference()
        assert (
            repo.find_matching(
                rejected.policy_number, rejected.loss_date, rejected.claim_type
            )
            is None
        )
        recorded = repo.record(rejected)
        found = repo.find_matching(
            rejected.policy_number, rejected.loss_date, rejected.claim_type
        )
        assert found is not None
        assert found.claim_reference == recorded.claim_reference
        assert found.claim_reference == f"CLM-{_recording_year()}-000002"