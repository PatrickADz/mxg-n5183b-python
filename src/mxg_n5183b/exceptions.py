"""Custom exception hierarchy for the MXG N5183B driver.

Using a dedicated hierarchy (instead of bare Exception / built-in
ValueError) lets callers distinguish between a connection problem, an
instrument-reported SCPI error, and an invalid parameter passed in from
Python, and catch each case independently.
"""

from __future__ import annotations


class MXGError(Exception):
    """Base class for all errors raised by this driver."""


class MXGConnectionError(MXGError):
    """Raised when the VISA session cannot be opened or is lost."""


class MXGCommandError(MXGError):
    """Raised when the instrument's SCPI error queue reports a problem.

    Attributes:
        code: The SCPI error code returned by ``SYST:ERR?``.
        message: The human-readable message that came with the code.
    """

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"SCPI error {code}: {message}")


class MXGParameterError(MXGError):
    """Raised when a parameter supplied by the caller is out of range
    or otherwise invalid, before anything is sent to the instrument.
    """
