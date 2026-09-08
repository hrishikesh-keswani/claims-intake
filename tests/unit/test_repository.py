"""Unit tests for the notification repository.

Notifications under test are built from `data/fnol_valid.json`,
`data/fnol_invalid.json`, and `data/fnol_edge.json`.
"""

from __future__ import annotations

import re

import pytest

from claims.repository import NotificationRepository

from .data import claim_from_fnol, notification_from_fnol


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
        recorded = repo.record(claim_from_fnol(case_id))
        year = req.loss_date.year
        assert re.match(r"^CLM-\d{4}-\d{6}$", recorded.claim_reference)
        assert recorded.claim_reference.startswith(f"CLM-{year}-")
        assert recorded.loss_date == req.loss_date
        assert recorded.estimated_amount == req.estimated_amount
        assert recorded.status == "recorded"

    def test_references_are_unique_for_recorded_fnol(
        self, repo: NotificationRepository
    ) -> None:
        first = repo.record(claim_from_fnol("EDGE-01"))
        second = repo.record(claim_from_fnol("EDGE-02"))
        assert first.claim_reference == "CLM-2026-000001"
        assert second.claim_reference == "CLM-2026-000002"
        assert first.claim_reference != second.claim_reference

    def test_instances_do_not_share_state(self) -> None:
        first = claim_from_fnol("EDGE-01")
        repo1 = NotificationRepository()
        repo2 = NotificationRepository()
        recorded = repo1.record(first)
        assert (
            repo2.find_matching(first.policy_number, first.loss_date, first.claim_type)
            is None
        )
        assert repo2.record(claim_from_fnol("EDGE-01")).claim_reference == "CLM-2026-000001"
        assert recorded.claim_reference == "CLM-2026-000001"

    def test_allocate_claim_reference_does_not_record(
        self, repo: NotificationRepository
    ) -> None:
        req = notification_from_fnol("EDGE-01")
        reference = repo.allocate_claim_reference(req.loss_date.year)
        assert reference == "CLM-2026-000001"
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
        recorded = repo.record(claim_from_fnol("EDGE-01"))
        query = notification_from_fnol(query_id)
        found = repo.find_matching(query.policy_number, query.loss_date, query.claim_type)
        if expect_match:
            assert found is not None
            assert found.claim_reference == recorded.claim_reference
        else:
            assert found is None

    def test_two_of_three_fields_from_fnol_is_not_a_duplicate(
        self, repo: NotificationRepository
    ) -> None:
        recorded = claim_from_fnol("EDGE-01")
        other = notification_from_fnol("EDGE-03")
        repo.record(recorded)
        assert (
            repo.find_matching(
                recorded.policy_number, recorded.loss_date, other.claim_type
            )
            is None
        )
        assert (
            repo.find_matching(
                recorded.policy_number, other.loss_date, recorded.claim_type
            )
            is None
        )
        assert (
            repo.find_matching(
                other.policy_number, recorded.loss_date, recorded.claim_type
            )
            is None
        )

    def test_find_matching_among_recorded_fnol(
        self, repo: NotificationRepository
    ) -> None:
        repo.record(claim_from_fnol("EDGE-01"))
        repo.record(claim_from_fnol("EDGE-02"))
        repo.record(claim_from_fnol("INVALID-01"))
        query = notification_from_fnol("EDGE-02")
        found = repo.find_matching(query.policy_number, query.loss_date, query.claim_type)
        assert found is not None
        assert found.estimated_amount == query.estimated_amount

    def test_rejected_notification_is_not_a_duplicate(
        self, repo: NotificationRepository
    ) -> None:
        """INVALID-06 is well formed but never recorded, so resubmitting is not a duplicate."""
        rejected = notification_from_fnol("INVALID-06")
        assert (
            repo.find_matching(
                rejected.policy_number, rejected.loss_date, rejected.claim_type
            )
            is None
        )
        accepted = repo.record(claim_from_fnol("EDGE-02"))
        assert accepted.claim_reference == "CLM-2026-000001"
        assert (
            repo.find_matching(
                rejected.policy_number, rejected.loss_date, rejected.claim_type
            )
            is None
        )
