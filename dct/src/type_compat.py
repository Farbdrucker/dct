"""Type compatibility utilities for DCT."""

from __future__ import annotations

import types
import typing


def normalize_type(annotation: object) -> frozenset[str]:
    """Convert a type annotation to a frozenset of type name strings.

    Returns empty frozenset for unannotated / inspect.Parameter.empty → treated as "any".
    """
    import inspect

    if annotation is inspect.Parameter.empty or annotation is None:
        return frozenset()

    # Plain type, e.g. int, float, str
    if isinstance(annotation, type):
        return frozenset([annotation.__name__])

    # Python 3.10+ union: int | float  → types.UnionType
    if isinstance(annotation, types.UnionType):
        result: set[str] = set()
        for arg in typing.get_args(annotation):
            result |= normalize_type(arg)
        return frozenset(result)

    # typing.Union / typing.Optional
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        result = set()
        for arg in typing.get_args(annotation):
            if arg is type(None):
                result.add("None")
            else:
                result |= normalize_type(arg)
        return frozenset(result)

    # Generic aliases like list[int], dict[str, int] — use the origin name
    if origin is not None and isinstance(origin, type):
        return frozenset([origin.__name__])

    # Fallback: stringify
    return frozenset([str(annotation)])


def is_compatible(source: frozenset[str], target: frozenset[str]) -> bool:
    """Return True if source is compatible with target.

    An empty set means "any type" and is always compatible.
    Otherwise source must be a subset of target (every type source can produce
    is accepted by target).
    """
    if not source or not target:
        return True
    return source.issubset(target)
