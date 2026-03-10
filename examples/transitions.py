import logging

from pydantic.dataclasses import dataclass
from rich import get_console
from rich.logging import RichHandler

FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

logger = logging.getLogger("source")


console = get_console()

@dataclass
class AddTwoInt:
    """
    Adding two integers
    """
    def __call__(self, a: int, b: int) -> int:
        console.print(f"Adding {a} and {b}: {a} + {b} = {a + b}")
        return a + b

@dataclass
class AddTwoFloats:
    """
    Adding two floats
    """
    def __call__(self, a: float, b: float) -> float:
        return a + b


@dataclass
class Div:
    """
    Divide the nominator by the denominator
    """
    def __call__(self, nominator: int | float, denominator: int | float) -> float:
        logger.info(f"Running Div on {nominator}, {denominator}")
        return float(nominator / denominator)

@dataclass
class Power:
    """
    base^exponent

    Args:
        exponent (int|float): the power
    """
    exponent: int | float

    def __call__(self, base: int | float) -> float:
        logger.info(f"Running Power on {base}^{self.exponent}")
        return float(base ** self.exponent)


@dataclass
class Root:
    radix: int | float

    def __call__(self, value: int | float) -> float:
        return float(value ** (1 / self.radix))
