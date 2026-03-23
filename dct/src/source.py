"""Source base class / decorator for DCT sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator

from pydantic.dataclasses import dataclass as _pydantic_dataclass


class Source(ABC):
    """Base class / decorator for DCT sources.

    Subclasses become Pydantic dataclasses automatically.  The type parameter
    of ``__iter__`` determines the output port type shown in the node library.

    Usage as base class (preferred)::

        class ConstSource(Source):
            value: float
            count: int = 10
            def __iter__(self) -> Iterator[float]:
                for _ in range(self.count):
                    yield self.value

    Usage as class decorator (equivalent)::

        @Source
        class ConstSource:
            value: float
            count: int = 10
            def __iter__(self) -> Iterator[float]:
                for _ in range(self.count):
                    yield self.value
    """

    @abstractmethod
    def __iter__(self) -> Iterator[Any]:
        """Yield one value per row to feed into the DAG."""
        ...

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _pydantic_dataclass(cls)

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        """Enables ``@Source`` decorator usage: Source(SomeClass) → SomeClass."""
        if (
            cls is Source
            and len(args) == 1
            and isinstance(args[0], type)
            and not kwargs
        ):
            target = args[0]
            _pydantic_dataclass(target)
            return target
        return super().__new__(cls)
