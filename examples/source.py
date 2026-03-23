"""DCT Sources — iterable data providers that feed values into transition DAGs."""
from __future__ import annotations

from typing import Iterator

from dct.src.source import Source


class ConstSource(Source):
    """Yields the same constant `value` exactly `count` times per run."""

    value: float
    count: int = 10

    def __iter__(self) -> Iterator[float]:
        for _ in range(self.count):
            yield self.value

    def __getitem__(self, index: int) -> float:
        return self.value


class ConstIntSource(Source):
    """Yields the same constant `value` exactly `count` times per run."""

    value: int
    count: int = 10

    def __iter__(self) -> Iterator[int]:
        for _ in range(self.count):
            yield self.value

    def __getitem__(self, index: int) -> int:
        return self.value


class RangeSource(Source):
    """Yields the output of range(start, stop, step)."""

    stop: int
    start: int = 0
    step: int = 1

    def __iter__(self) -> Iterator[int]:
        for value in range(self.start, self.stop, self.step):
            yield value

    def __getitem__(self, index: int) -> int:
        value = self.step * index + self.start
        if not self.start <= value < self.stop:
            raise IndexError(index)
        return value
