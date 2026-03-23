"""Sink base class / decorator for DCT sinks."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic.dataclasses import dataclass as _pydantic_dataclass

from dct.core.transition import _wrap_call

logger = logging.getLogger(__name__)


class Sink(ABC):
    """Base class / decorator for DCT sinks.

    A sink is a terminal node that receives one value per source row via
    ``__call__`` and accumulates state.  After the source is fully drained,
    the executor calls ``close()`` exactly once, sequentially in the main
    thread — making it safe to flush buffers, write files, etc. without any
    additional locking.

    If the DAG runs in parallel mode, ``__call__`` may be invoked from
    multiple threads concurrently; implementations that mutate shared state
    must protect it with a lock.

    Usage as base class (preferred)::

        class Collect(Sink):
            results: list = dataclasses.field(default_factory=list)
            def __call__(self, value: float) -> None:
                self.results.append(value)
            def close(self) -> None:
                print("collected", self.results)

    Usage as class decorator (equivalent)::

        @Sink
        class Collect:
            def __call__(self, value: float) -> None: ...
            def close(self) -> None: ...
    """

    @abstractmethod
    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """Called once per source row with the upstream value(s)."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Called once after all rows have been processed."""
        ...

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _pydantic_dataclass(cls)
        if "__call__" in cls.__dict__:
            _wrap_call(cls)

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        """Enables ``@Sink`` decorator usage: Sink(SomeClass) → SomeClass."""
        if cls is Sink and len(args) == 1 and isinstance(args[0], type) and not kwargs:
            target = args[0]
            _pydantic_dataclass(target)
            if "__call__" in target.__dict__:
                _wrap_call(target)
            return target
        return super().__new__(cls)
