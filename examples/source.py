"""DCT Sources — iterable data providers that feed values into transition DAGs."""
from __future__ import annotations

import logging
from typing import Iterator

from pydantic.dataclasses import dataclass
from rich.logging import RichHandler

FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

logger = logging.getLogger("source")

class Source:
    """Abstract base class for DCT sources.

    Subclasses must define `__iter__` (returning an `Iterator[T]`) and
    `__getitem__` so values can be pulled by index or iteration.
    The type parameter `T` of `__iter__` determines the output port type seen
    by the node library.
    """


@dataclass
class ConstSource(Source):
    """Yields the same constant `value` exactly `count` times per run."""

    value: float
    count: int = 10

    def __iter__(self) -> Iterator[float]:
        for _ in range(self.count):
            yield self.value

    def __getitem__(self, index: int) -> float:
        return self.value


@dataclass
class ConstIntSource(Source):
    """Yields the same constant `value` exactly `count` times per run."""

    value: int
    count: int = 10

    def __iter__(self) -> Iterator[int]:
        for _ in range(self.count):
            yield self.value

    def __getitem__(self, index: int) -> int:
        return self.value

@dataclass
class RangeSource(Source):
    """
    Yields the output of range(start, stop, step)
    """
    stop: int
    start: int = 0
    step: int = 1

    def __iter__(self) -> Iterator[int]:
        for value in range(self.start, self.stop, self.step):
            logger.info(f"yielding {value}")
            yield value

    def __getitem__(self, index: int) -> int:
        value = self.step * index + self.start

        if not self.start <= value < self.stop:
            raise IndexError(index)

        return value
