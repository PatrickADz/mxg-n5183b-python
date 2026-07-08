"""Python driver and CLI for the Keysight MXG N5183B RF signal generator."""

from .driver import MAX_FREQUENCY_HZ, MIN_FREQUENCY_HZ, N5183B
from .exceptions import (
    MXGCommandError,
    MXGConnectionError,
    MXGError,
    MXGParameterError,
)

__all__ = [
    "N5183B",
    "MIN_FREQUENCY_HZ",
    "MAX_FREQUENCY_HZ",
    "MXGError",
    "MXGConnectionError",
    "MXGCommandError",
    "MXGParameterError",
]

__version__ = "1.0.0"
