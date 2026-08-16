"""Allowlist-only projection at the LLM boundary."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any

from .state import FarmStateSnapshot, _freeze


class ForbiddenStateKey(ValueError):
    """Raised when a forbidden field appears anywhere in a provider input."""


class InvalidAllowlistPath(ValueError):
    """Raised for an empty or malformed allowlist path."""


def assert_no_forbidden_keys(value: Any, forbidden: Iterable[str] = ("scenario",)) -> None:
    forbidden_keys = frozenset(forbidden)

    def visit(item: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if key in forbidden_keys:
                    dotted = ".".join((*path, str(key)))
                    raise ForbiddenStateKey(dotted)
                visit(child, (*path, str(key)))
        elif isinstance(item, (list, tuple, set, frozenset)):
            for child in item:
                visit(child, path)

    visit(value)


def _normalise_paths(allowed_paths: Iterable[str | tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    paths: list[tuple[str, ...]] = []
    for raw_path in allowed_paths:
        path = tuple(raw_path.split(".")) if isinstance(raw_path, str) else tuple(raw_path)
        if not path or any(not part for part in path):
            raise InvalidAllowlistPath(raw_path)
        paths.append(path)
    return tuple(sorted(set(paths)))


_NO_MATCH = object()


def _project(value: Any, paths: tuple[tuple[str, ...], ...], prefix: tuple[str, ...] = ()) -> Any:
    if (*prefix, "*") in paths:
        return _freeze(value)
    if prefix in paths and not isinstance(value, (Mapping, list, tuple)):
        return _freeze(value)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key in sorted(value):
            path = (*prefix, str(key))
            if any(candidate[: len(path)] == path for candidate in paths):
                projected = _project(value[key], paths, path)
                if projected is not _NO_MATCH:
                    output[key] = projected
        return MappingProxyType(output) if output else _NO_MATCH
    if isinstance(value, (list, tuple)):
        projected_items = tuple(
            item
            for item in (_project(item, paths, prefix) for item in value)
            if item is not _NO_MATCH
        )
        return projected_items if projected_items else _NO_MATCH
    return _NO_MATCH


def build_llm_slice(
    snapshot: FarmStateSnapshot, allowed_paths: Iterable[str | tuple[str, ...]]
) -> Mapping[str, Any]:
    """Project only explicitly allowed paths and return an immutable result."""

    assert_no_forbidden_keys(snapshot.sections)
    paths = _normalise_paths(allowed_paths)
    projected = _project(snapshot.sections, paths)
    return MappingProxyType({}) if projected is _NO_MATCH else projected


__all__ = [
    "ForbiddenStateKey",
    "InvalidAllowlistPath",
    "assert_no_forbidden_keys",
    "build_llm_slice",
]
