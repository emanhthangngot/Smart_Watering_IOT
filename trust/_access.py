"""Small, defensive access helpers shared by pure trust predicates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from struct import pack
from typing import Any


def field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def metric_key(device: str, metric: str) -> str:
    return f"{device}.{metric}"


def reading(bundle: Any, device: str, metric: str) -> Any | None:
    if not isinstance(bundle, Mapping):
        return None
    key = metric_key(device, metric)
    if key in bundle:
        return bundle[key]
    device_value = bundle.get(device)
    if isinstance(device_value, Mapping):
        metrics = device_value.get("metrics", device_value)
        return metrics.get(metric) if isinstance(metrics, Mapping) else None
    return None


def val(bundle: Any, device: str, metric: str) -> float | None:
    candidate = reading(bundle, device, metric)
    value = field(candidate, "value", candidate)
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric and abs(numeric) != float("inf") else None


def values(windows: Any, device: str, metric: str) -> list[float]:
    candidate = reading(windows, device, metric)
    if candidate is None:
        return []
    raw = field(candidate, "values", candidate)
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes, Mapping)):
        return []
    result: list[float] = []
    for item in raw:
        number = field(item, "value", item)
        if isinstance(number, bool):
            continue
        try:
            number = float(number)
        except (TypeError, ValueError):
            continue
        if number == number and abs(number) != float("inf"):
            result.append(number)
    return result


def value_bits(windows: Any, device: str, metric: str) -> list[bytes]:
    """Return IEEE-754 representations so stuck detection is exact, not tolerance based."""
    return [pack(">d", number) for number in values(windows, device, metric)]


def delta(windows: Any, device: str, metric: str) -> float | None:
    series = values(windows, device, metric)
    return series[-1] - series[0] if len(series) >= 2 else None
