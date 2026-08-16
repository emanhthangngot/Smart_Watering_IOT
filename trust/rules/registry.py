"""Discover rule modules so contributors never edit a shared list literal."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from typing import Any

Rule = Callable[[Any, Any], bool]


def _discover(kind: str) -> dict[str, Rule]:
    package = importlib.import_module("trust.rules")
    found: dict[str, Rule] = {}
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name.startswith("_") or module_info.name == "registry":
            continue
        module = importlib.import_module(f"{package.__name__}.{module_info.name}")
        if getattr(module, "KIND", None) == kind and callable(
            candidate := getattr(module, "rule", None)
        ):
            found[getattr(module, "NAME", module_info.name)] = candidate
    return dict(sorted(found.items()))


def hard_fails() -> dict[str, Rule]:
    return _discover("hard")


def soft_rules() -> dict[str, Rule]:
    return _discover("soft")


# Immutable-at-import discovery, not a hand-maintained module list.
HARD_FAILS = hard_fails()
SOFT_RULES = soft_rules()
