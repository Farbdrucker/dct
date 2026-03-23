"""Internal Result type for DAG execution — Ok[T] or Err."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Successful node result wrapping the produced value."""

    value: T


@dataclass(frozen=True, slots=True)
class Err:
    """Failed or skipped node result.

    ``is_skip=True`` means this node was not actually executed — it was bypassed
    because an upstream node already produced an ``Err``.  Only nodes with
    ``is_skip=False`` are considered the *originating* failure.
    """

    node_id: str
    node_type: str
    exception_type: str
    message: str
    traceback_str: str
    is_skip: bool = False
