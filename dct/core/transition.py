"""Transition base class / decorator for DCT transitions."""

from __future__ import annotations

import copy
import functools
import logging
from abc import ABC, abstractmethod
from typing import Any

import pydantic
import pydantic.dataclasses
from pydantic.dataclasses import dataclass as _pydantic_dataclass

# Types that are always safe to pass through without copying.
_IMMUTABLE_ATOMIC = (int, float, str, bool, bytes, complex, type(None))


def _is_immutable(obj: Any) -> bool:
    if isinstance(obj, _IMMUTABLE_ATOMIC):
        return True
    if isinstance(obj, frozenset):
        return True
    if isinstance(obj, tuple):
        return all(_is_immutable(item) for item in obj)
    if isinstance(obj, pydantic.BaseModel) and obj.model_config.get("frozen", False):
        return True
    if pydantic.dataclasses.is_pydantic_dataclass(type(obj)):
        cfg = getattr(type(obj), "__pydantic_config__", None)
        if cfg is not None and getattr(cfg, "frozen", False):
            return True
    return False


def _safe_copy(obj: Any) -> Any:
    return obj if _is_immutable(obj) else copy.deepcopy(obj)


logger = logging.getLogger(__name__)


def _wrap_call(cls: type) -> None:
    """Replace cls.__call__ with a logging + deep-copy wrapper (stays in cls.__dict__)."""
    original = cls.__dict__["__call__"]

    @functools.wraps(original)
    def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        name = type(self).__name__
        logger.info("%s started", name)
        safe_args = tuple(_safe_copy(a) for a in args)
        safe_kwargs = {k: _safe_copy(v) for k, v in kwargs.items()}
        try:
            result = original(self, *safe_args, **safe_kwargs)
        except Exception:
            logger.info("%s failed", name)
            raise
        logger.info("%s finished", name)
        return result

    cls.__call__ = _wrapped  # type: ignore[method-assign]


class Transition(ABC):
    """Base class / decorator for DCT transitions.

    Usage as base class (preferred)::

        class Power(Transition):
            exponent: int | float
            def __call__(self, base: int | float) -> float:
                return float(base ** self.exponent)

    Usage as class decorator (equivalent)::

        @Transition
        class Div:
            def __call__(self, nominator: int | float, denominator: int | float) -> float:
                return nominator / denominator
    """

    @abstractmethod
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Override in subclasses to implement the transition."""
        ...

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Called when `class Foo(Transition):` is defined."""
        super().__init_subclass__(**kwargs)
        _pydantic_dataclass(cls)
        if "__call__" in cls.__dict__:
            _wrap_call(cls)

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        """Enables `@Transition` decorator usage: Transition(SomeClass) → SomeClass."""
        if (
            cls is Transition
            and len(args) == 1
            and isinstance(args[0], type)
            and not kwargs
        ):
            target = args[0]
            _pydantic_dataclass(target)
            if "__call__" in target.__dict__:
                _wrap_call(target)
            return target
        return super().__new__(cls)
