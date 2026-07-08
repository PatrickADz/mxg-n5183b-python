"""Shared pytest fixtures: a fully mocked PyVISA resource so tests never
need real hardware."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mxg_n5183b import N5183B


class FakeInstrument:
    """A minimal stand-in for a pyvisa resource.

    Tracks every write, and returns canned answers for queries so the
    driver's logic (parsing, validation, error-queue draining) can be
    exercised without a real signal generator.
    """

    def __init__(self):
        self.written_commands: list[str] = []
        self.timeout = None
        self._frequency = 1e9
        self._power = -10.0
        self._output_state = "0"
        self._mod_state = "0"
        # A queue of (code, message) tuples to return from SYST:ERR?,
        # drained one at a time; tests can push errors into this.
        self.error_queue: list[tuple[int, str]] = []

    def write(self, command: str) -> None:
        self.written_commands.append(command)
        if command.startswith(":FREQ ") or command.startswith(":FREQ:CW"):
            self._frequency = float(command.split()[-1])
        elif command.startswith(":POW "):
            self._power = float(command.split()[-1])
        elif command.startswith(":OUTP "):
            self._output_state = "1" if command.endswith("ON") else "0"
        elif command.startswith(":MOD:STAT "):
            self._mod_state = "1" if command.endswith("ON") else "0"

    def query(self, command: str) -> str:
        if command == "*IDN?":
            return "Keysight Technologies,N5183B,FAKE-SN-0001,1.0.0"
        if command == "SYST:ERR?":
            if self.error_queue:
                code, message = self.error_queue.pop(0)
                return f'{code},"{message}"'
            return '+0,"No error"'
        if command == ":FREQ?":
            return str(self._frequency)
        if command == ":POW?":
            return str(self._power)
        if command == ":OUTP?":
            return self._output_state
        if command == ":MOD:STAT?":
            return self._mod_state
        if command == ":SWE:CPOIN?":
            return "1"
        raise ValueError(f"FakeInstrument received unexpected query: {command}")

    def close(self) -> None:
        pass


@pytest.fixture
def fake_instrument():
    return FakeInstrument()


@pytest.fixture
def sg(fake_instrument):
    """A connected N5183B driver instance backed by FakeInstrument."""
    with patch("mxg_n5183b.driver.pyvisa.ResourceManager") as mock_rm_cls:
        mock_rm = MagicMock()
        mock_rm.open_resource.return_value = fake_instrument
        mock_rm_cls.return_value = mock_rm

        driver = N5183B("TCPIP::192.0.2.1::INSTR", check_errors=True)
        yield driver
        driver.disconnect()
