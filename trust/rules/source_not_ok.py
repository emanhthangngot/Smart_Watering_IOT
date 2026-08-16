from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from trust._access import field

KIND = "hard"
NAME = "source_not_ok"


def rule(bundle: Any, windows: Any) -> bool:
    del windows
    if not isinstance(bundle, Mapping):
        return False
    return any(
        field(item, "source_status", field(item, "status", "ok")) != "ok"
        for item in bundle.values()
    )
