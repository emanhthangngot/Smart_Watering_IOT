"""Action verification: create response and GET read-back are separate evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from contracts import Verification


def verify_action(
    *,
    expected_id: str,
    expected_status: str,
    expected_params: Mapping[str, Any],
    post_result: Mapping[str, Any],
    read_back: Mapping[str, Any] | None,
    window: str,
    evidence_refs: list[str] | None = None,
) -> Verification:
    observed = {"post": dict(post_result), "read_back": dict(read_back or {})}
    passed = bool(
        read_back
        and post_result.get("id") == expected_id
        and post_result.get("status") == expected_status
        and post_result.get("params") == dict(expected_params)
        and read_back.get("id") == expected_id
        and read_back.get("status") == expected_status
        and read_back.get("params") == dict(expected_params)
    )
    return Verification(
        layer="ACTION",
        expected={"id": expected_id, "status": expected_status, "params": dict(expected_params)},
        observed=observed,
        result="PASS" if passed else "FAIL",
        window=window,
        evidence_refs=evidence_refs or [],
    )
