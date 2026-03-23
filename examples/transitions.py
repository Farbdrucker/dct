import threading

from dct.src.sink import Sink
from dct.src.transition import Transition


# Style 1: inheritance (preferred)
class AddTwoInt(Transition):
    """
    Adding two integers
    """
    def __call__(self, a: int, b: int) -> int:
        return a + b


class AddTwoFloats(Transition):
    """
    Adding two floats
    """
    def __call__(self, a: float, b: float) -> float:
        return a + b


class Power(Transition):
    """
    base^exponent

    Args:
        exponent (int|float): the power
    """
    exponent: int | float

    def __call__(self, base: int | float) -> float:
        return float(base ** self.exponent)


class Root(Transition):
    radix: int | float

    def __call__(self, value: int | float) -> float:
        return float(value ** (1 / self.radix))


# Style 2: class decorator (equivalent)
@Transition
class Div:
    """
    Divide the nominator by the denominator
    """
    def __call__(self, nominator: int | float, denominator: int | float) -> float:
        return float(nominator / denominator)


class Collect(Sink):
    """Accumulate every result into a list and print a summary on close.

    Thread-safe: a lock protects the shared list when running in parallel mode.
    """

    def __call__(self, value: int | float) -> None:
        with self._lock:
            self._results.append(value)

    def close(self) -> None:
        print(f"Collect: {len(self._results)} values, sum={sum(self._results)}")

    def __post_init__(self) -> None:
        self._results: list[int | float] = []
        self._lock = threading.Lock()
