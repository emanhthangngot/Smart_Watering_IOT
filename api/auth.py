"""Single-operator token authentication with redacted audit identity."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass


class AuthenticationError(ValueError):
    pass


@dataclass(frozen=True)
class OperatorIdentity:
    actor: str
    token_id: str


def authenticate_operator(token: str | None) -> OperatorIdentity:
    configured = os.environ.get("OPERATOR_TOKEN", "")
    if not configured or not token or not hmac.compare_digest(token, configured):
        raise AuthenticationError("invalid operator token")
    actor = os.environ.get("OPERATOR_ACTOR", "farm-operator").strip()
    if not actor:
        raise AuthenticationError("operator actor is not configured")
    token_id = hashlib.sha256(configured.encode("utf-8")).hexdigest()[:12]
    return OperatorIdentity(actor=actor, token_id=token_id)
