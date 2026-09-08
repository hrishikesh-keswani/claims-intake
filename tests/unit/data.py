"""Load course fixtures from `data/` for unit tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from claims.models import NotificationRequest, Policy

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

MODEL_LAYER_REJECTS = frozenset({"EDGE-08", "EDGE-11", "EDGE-12"})

_FNOL_FILES = ("fnol_valid.json", "fnol_invalid.json", "fnol_edge.json")


def fnol_rows(filename: str) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads((DATA_DIR / filename).read_text()))


def fnol_payload(case_id: str) -> dict[str, Any]:
    for filename in _FNOL_FILES:
        for row in fnol_rows(filename):
            if row["id"] == case_id:
                return cast(dict[str, Any], row["payload"])
    raise KeyError(case_id)


def fnol_cases(filename: str) -> list[tuple[str, dict[str, Any]]]:
    return [(row["id"], row["payload"]) for row in fnol_rows(filename)]


def fnol_ids(filename: str) -> list[str]:
    return [
        f"{row['id']}-malformed"
        if row["id"] in MODEL_LAYER_REJECTS
        else f"{row['id']}-survives-to-rules"
        for row in fnol_rows(filename)
    ]


def notification_from_fnol(case_id: str) -> NotificationRequest:
    return NotificationRequest.model_validate(fnol_payload(case_id))


def policy_from_master(policy_number: str) -> Policy:
    for row in json.loads((DATA_DIR / "policies.json").read_text()):
        if row["policy_number"] == policy_number:
            return Policy.model_validate(row)
    raise KeyError(policy_number)
