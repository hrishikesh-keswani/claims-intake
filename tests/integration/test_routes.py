"""HTTP integration tests for POST /notifications.

These tests go through the ASGI surface, not `submit_notification`. Status, code,
and actionable detail keys are asserted against `docs/api-contract.md` sections 3,
5, and 6.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import app, get_policy_client, get_repository
from claims.policy_client import LookupFailureReason, StubPolicyClient
from claims.repository import NotificationRepository
from tests.unit.data import fnol_payload

CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")


@pytest.fixture
def policy_client() -> StubPolicyClient:
    return StubPolicyClient()


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


@pytest.fixture
def client(
    policy_client: StubPolicyClient, repository: NotificationRepository
) -> Iterator[TestClient]:
    app.dependency_overrides[get_policy_client] = lambda: policy_client
    app.dependency_overrides[get_repository] = lambda: repository
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _post(client: TestClient, payload: dict[str, Any]) -> Any:
    return client.post("/notifications", json=payload)


class TestAcceptedNotification:
    def test_valid_notification_returns_201_with_claim_reference(
        self, client: TestClient
    ) -> None:
        response = _post(client, fnol_payload("VALID-01"))
        assert response.status_code == 201
        body = response.json()
        assert CLAIM_REFERENCE.match(body["claim_reference"])
        assert body["status"] == "recorded"


class TestRuleRejections:
    @pytest.mark.parametrize(
        "case_id, code, status",
        [
            pytest.param("INVALID-01", "POLICY_NOT_FOUND", 422, id="V-1"),
            pytest.param("INVALID-02", "LOSS_BEFORE_INCEPTION", 422, id="V-2"),
            pytest.param("INVALID-07", "POLICY_CANCELLED", 422, id="V-7"),
            pytest.param("INVALID-03", "LOSS_AFTER_EXPIRY", 422, id="V-3"),
            pytest.param("INVALID-04", "AMOUNT_EXCEEDS_LIMIT", 422, id="V-4"),
            pytest.param("INVALID-05", "TYPE_NOT_COVERED", 422, id="V-5"),
        ],
    )
    def test_each_rule_returns_its_contract_code_and_status(
        self, client: TestClient, case_id: str, code: str, status: int
    ) -> None:
        response = _post(client, fnol_payload(case_id))
        assert response.status_code == status
        body = response.json()
        assert body["code"] == code
        assert isinstance(body["detail"], dict)
        assert "claim_reference" not in body

    def test_policy_not_found_is_distinguishable_from_dependency_failures(
        self, client: TestClient
    ) -> None:
        response = _post(client, fnol_payload("INVALID-01"))
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "POLICY_NOT_FOUND"
        assert body["code"] not in {
            "POLICY_MASTER_UNAVAILABLE",
            "POLICY_MASTER_TIMEOUT",
            "POLICY_MASTER_INVALID_RESPONSE",
        }

    def test_duplicate_includes_existing_claim_reference(
        self, client: TestClient
    ) -> None:
        first = _post(client, fnol_payload("VALID-01"))
        assert first.status_code == 201
        existing = first.json()["claim_reference"]
        second = _post(client, fnol_payload("INVALID-06"))
        assert second.status_code == 409
        body = second.json()
        assert body["code"] == "DUPLICATE_NOTIFICATION"
        assert body["detail"]["existing_claim_reference"] == existing


class TestParseFailures:
    def test_missing_required_field_returns_400_not_a_rule_code(
        self, client: TestClient
    ) -> None:
        response = _post(client, fnol_payload("EDGE-08"))
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "MALFORMED_REQUEST"
        assert body["detail"]["field"] == "estimated_amount"
        assert body["detail"]["reason"] == "required_field_missing"

    def test_extra_field_is_rejected_rather_than_ignored(
        self, client: TestClient
    ) -> None:
        payload = dict(fnol_payload("VALID-01"))
        payload["unexpected"] = "should-not-be-accepted"
        response = _post(client, payload)
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "MALFORMED_REQUEST"
        assert body["detail"]["field"] == "unexpected"
        assert body["detail"]["reason"] == "unexpected_field"

    def test_invalid_json_returns_400_with_empty_detail(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/notifications",
            content=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "MALFORMED_REQUEST"
        assert body["detail"] == {}


class TestDependencyFailures:
    @pytest.mark.parametrize(
        "reason, code, status",
        [
            pytest.param("timeout", "POLICY_MASTER_TIMEOUT", 504, id="timeout"),
            pytest.param(
                "unreachable", "POLICY_MASTER_UNAVAILABLE", 503, id="unreachable"
            ),
            pytest.param(
                "unparsable", "POLICY_MASTER_INVALID_RESPONSE", 502, id="unparsable"
            ),
        ],
    )
    def test_lookup_failure_reason_maps_to_its_5xx(
        self,
        repository: NotificationRepository,
        reason: LookupFailureReason,
        code: str,
        status: int,
    ) -> None:
        failing_client = StubPolicyClient(fail_with=reason)
        app.dependency_overrides[get_policy_client] = lambda: failing_client
        app.dependency_overrides[get_repository] = lambda: repository
        try:
            with TestClient(app, raise_server_exceptions=False) as test_client:
                response = _post(test_client, fnol_payload("VALID-01"))
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == status
        assert 500 <= response.status_code < 600
        body = response.json()
        assert body["code"] == code
        assert body["detail"] == {}
        assert response.status_code >= 500
