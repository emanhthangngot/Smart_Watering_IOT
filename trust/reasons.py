"""Stable human-readable explanations for trust decisions."""

from __future__ import annotations

from trust.score import ScoreSnapshot
from trust.tier import Tier


def explain(snapshot: ScoreSnapshot, tier: Tier | str) -> str:
    cap = f", capped at {snapshot.cap_applied:.2f}" if snapshot.cap_applied is not None else ""
    rules = ", ".join(snapshot.rules_fired) if snapshot.rules_fired else "none"
    components = (
        f"F={snapshot.freshness:.2f}, C={snapshot.completeness:.2f}, "
        f"K={snapshot.consistency:.2f}{cap}"
    )
    return (
        f"{snapshot.scope}: {tier}; DCS={snapshot.dcs:.2f} "
        f"({components}); "
        f"rules={rules}; policy={snapshot.dcsPolicyVersion}."
    )
