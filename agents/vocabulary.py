"""Small, closed interaction vocabulary for the M3 coordinator."""

from enum import StrEnum


class InteractionVerb(StrEnum):
    PROPOSE = "PROPOSE"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REQUEST_MORE_EVIDENCE = "REQUEST_MORE_EVIDENCE"
    REVISE = "REVISE"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"


__all__ = ["InteractionVerb"]
