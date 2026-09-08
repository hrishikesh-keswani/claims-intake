"""Persistence for recorded notifications.

An in-memory store is sufficient for Week 1 and is deliberate rather than a
shortcut. The rules do not know where a notification is stored, so replacing this
with a database in a later week is a change to one module.

Duplicate detection (WI-0151) is a query against recorded rows, which is why it
lives here rather than in the rule table.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from claims.models import ClaimRecord, NotificationRequest


class NotificationRepository:
    """Stores accepted notifications, issues claim references, and answers duplicates."""

    def __init__(self) -> None:
        self._records: list[ClaimRecord] = []
        self._reference_sequences: dict[int, int] = {}

    def allocate_claim_reference(self, year: int | None = None) -> str:
        """Issue the next unused `CLM-YYYY-NNNNNN` for `year`.

        Contract section 3: `YYYY` is the calendar year in which the notification
        is recorded, unique, never reissued, zero-padded sequence. Default `year`
        is today so a caller cannot pass `loss_date.year` by accident.

        Sequence state is independent of `_records`, so allocating a reference
        without `record` cannot create a duplicate row (WI-0151 AC-3).
        """
        if year is None:
            year = datetime.now(tz=UTC).date().year
        self._reference_sequences[year] = self._reference_sequences.get(year, 0) + 1
        sequence = self._reference_sequences[year]
        return f"CLM-{year}-{sequence:06d}"

    def record(self, notification: NotificationRequest) -> ClaimRecord:
        """Persist an accepted notification. This is the only way a ClaimRecord is created."""
        recorded = ClaimRecord(
            policy_number=notification.policy_number,
            loss_date=notification.loss_date,
            claim_type=notification.claim_type,
            estimated_amount=notification.estimated_amount,
            claim_reference=self.allocate_claim_reference(),
            status="recorded",
        )
        self._records.append(recorded)
        return recorded

    def find_matching(
        self,
        policy_number: str,
        loss_date: date,
        claim_type: str,
    ) -> ClaimRecord | None:
        """Return the recorded row matching all three WI-0151 AC-1 fields, if any.

        Only `_records` is searched. A refused notification is never appended, so
        it cannot be the thing a later submission duplicates (WI-0151 AC-3).
        """
        for record in self._records:
            if (
                record.policy_number == policy_number
                and record.loss_date == loss_date
                and record.claim_type == claim_type
            ):
                return record
        return None