"""In-process cache for probe and pytest results from an unchanged tree."""

from __future__ import annotations

import copy
import threading

_MISSING = object()
_lock = threading.Lock()
_values: dict[tuple, object] = {}


def clear() -> None:
    with _lock:
        _values.clear()


def get(key: tuple) -> object | None:
    with _lock:
        value = _values.get(key, _MISSING)
    if value is _MISSING:
        return None
    return copy.deepcopy(value)


def put(key: tuple, value: object) -> None:
    with _lock:
        _values[key] = copy.deepcopy(value)
