"""
(C) 2025 by PatrickADz.

Python driver for the Keysight MXG N5183B RF signal generator.

Communicates over SCPI via PyVISA (TCP/IP, GPIB, or USB — anything a VISA
resource string can address). Designed for laboratory RF characterization
and receiver testing where the instrument is fixed at a frequency/power or
stepped/swept across a band.

Typical usage:

    from mxg_n5183b import N5183B

    with N5183B("TCPIP::192.168.0.11::INSTR") as sg:
        sg.set_power_then_sweep(
            power_dbm=0,
            start_hz=1e9,
            stop_hz=2e9,
            step_hz=100e6,
            dwell_s=0.5,
        )

        version 1.0 July 2025
"""

from __future__ import annotations

import logging
import threading
import time
from types import TracebackType
from typing import Callable, Optional, Type

import pyvisa

from .exceptions import MXGCommandError, MXGConnectionError, MXGError, MXGParameterError

logger = logging.getLogger(__name__)

# Instrument frequency range (9 kHz - 20 GHz for the N5183B base unit).
# Some frequency-extension options narrow or widen this; check the data
# sheet for your specific unit if you hit unexpected range errors.
MIN_FREQUENCY_HZ = 9e3
MAX_FREQUENCY_HZ = 20e9

# Sweep spacing modes accepted by :SWEep:SPACing
_SWEEP_SPACING = {"LIN", "LINEAR", "LOG", "LOGARITHMIC"}

# Point-trigger sources accepted by :LIST:TRIGger:SOURce
_TRIGGER_SOURCES = {
    "BUS",
    "IMM",
    "IMMEDIATE",
    "EXT",
    "EXTERNAL",
    "INT",
    "INTERNAL",
    "KEY",
    "TIM",
    "TIMER",
}


class N5183B:
    """Driver for the Keysight MXG N5183B RF signal generator.

    Args:
        resource_name: A VISA resource string, e.g. ``"TCPIP::192.168.0.11::INSTR"``.
        timeout_ms: VISA I/O timeout in milliseconds.
        check_errors: If True (default), every write is followed by a
            ``SYST:ERR?`` check and a :class:`MXGCommandError` is raised
            if the instrument reports a problem. Disable only for
            performance-critical loops where you will check errors
            yourself afterwards.
        safe_shutdown: If True (default), the RF output is turned off
            automatically when used as a context manager and the
            ``with`` block exits (normally or via exception).
    """

    def __init__(
        self,
        resource_name: str,
        *,
        timeout_ms: int = 5000,
        check_errors: bool = True,
        safe_shutdown: bool = True,
    ):
        if not resource_name:
            raise MXGParameterError("resource_name must not be empty")

        self.resource_name = resource_name
        self.timeout_ms = timeout_ms
        self.check_errors = check_errors
        self.safe_shutdown = safe_shutdown

        self._rm: Optional[pyvisa.ResourceManager] = None
        self._instrument = None

        self._sweep_thread: Optional[threading.Thread] = None
        self._stop_sweep_event = threading.Event()

        self.connect()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Open the VISA session to the instrument."""
        try:
            self._rm = pyvisa.ResourceManager()
            self._instrument = self._rm.open_resource(self.resource_name)
            self._instrument.timeout = self.timeout_ms
            logger.info("Connecting to N5183B at %s", self.resource_name)
        except Exception as exc:
            raise MXGConnectionError(
                f"Failed to open VISA session to '{self.resource_name}': {exc}"
            ) from exc

        idn = self.get_idn()
        logger.info("Connection established: %s", idn)

    def disconnect(self) -> None:
        """Close the VISA session."""
        if self._instrument is None:
            return
        try:
            logger.info("Closing connection to N5183B at %s", self.resource_name)
            self._instrument.close()
        except Exception as exc:
            raise MXGConnectionError(f"Failed while disconnecting: {exc}") from exc
        finally:
            self._instrument = None

    @property
    def is_connected(self) -> bool:
        return self._instrument is not None

    def __enter__(self) -> "N5183B":
        if not self.is_connected:
            self.connect()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.stop_software_sweep()
        try:
            if self.safe_shutdown:
                self.set_rf_output(False)
        finally:
            self.disconnect()

    # ------------------------------------------------------------------
    # Low-level SCPI helpers
    # ------------------------------------------------------------------
    def _require_connection(self) -> None:
        if self._instrument is None:
            raise MXGConnectionError("Not connected to the instrument")

    def _write(self, command: str) -> None:
        """Send a SCPI command and, if enabled, check the error queue."""
        self._require_connection()
        try:
            self._instrument.write(command)
        except Exception as exc:
            raise MXGConnectionError(f"Failed to write '{command}': {exc}") from exc

        if self.check_errors:
            self._check_error(context=command)

    def _query(self, command: str) -> str:
        """Send a SCPI query and return the (stripped) response."""
        self._require_connection()
        try:
            return self._instrument.query(command).strip()
        except Exception as exc:
            raise MXGConnectionError(f"Failed to query '{command}': {exc}") from exc

    def _check_error(self, context: str = "") -> None:
        """Query the SCPI error queue and raise on the first error found.

        The instrument queues errors, so a single ``SYST:ERR?`` after a
        write only reports one entry; this drains the whole queue so a
        stale error from an earlier command can't silently surface later
        and get blamed on the wrong line.
        """
        while True:
            raw = self._instrument.query("SYST:ERR?").strip()
            code_str, _, message = raw.partition(",")
            try:
                code = int(code_str)
            except ValueError:
                # Unexpected response format; don't mask it, but don't loop forever either.
                logger.warning("Unexpected error-queue response: %s", raw)
                return
            if code == 0:
                return
            suffix = f" (after '{context}')" if context else ""
            raise MXGCommandError(code, message.strip().strip('"') + suffix)

    # ------------------------------------------------------------------
    # Identification / status
    # ------------------------------------------------------------------
    def get_idn(self) -> str:
        """Return the instrument's identification string (``*IDN?``)."""
        return self._query("*IDN?")

    def reset(self) -> None:
        """Reset the instrument to its ``*RST`` default state."""
        self._write("*RST")

    def clear_status(self) -> None:
        """Clear the status byte and all event registers (``*CLS``)."""
        self._write("*CLS")

    def read_error(self) -> str:
        """Return the next entry in the SCPI error queue, unparsed."""
        return self._query("SYST:ERR?")

    # ------------------------------------------------------------------
    # Frequency (CW)
    # ------------------------------------------------------------------
    def set_frequency(self, freq_hz: float) -> None:
        """Set the CW output frequency in Hz.

        Also switches the frequency mode back to CW/FIXed, so this is
        safe to call even right after a hardware sweep has left the
        instrument in LIST mode.
        """
        if not (MIN_FREQUENCY_HZ <= freq_hz <= MAX_FREQUENCY_HZ):
            raise MXGParameterError(
                f"Frequency must be between {MIN_FREQUENCY_HZ:g} Hz and "
                f"{MAX_FREQUENCY_HZ:g} Hz (got {freq_hz:g} Hz)"
            )
        self._write(":FREQ:MODE CW")
        self._write(f":FREQ {freq_hz}")
        logger.info("MXG frequency set to %.6g Hz", freq_hz)

    def get_frequency(self) -> float:
        """Query and return the current output frequency in Hz."""
        return float(self._query(":FREQ?"))

    def step_frequency(self, step_hz: float, direction: str = "up") -> float:
        """Nudge the current CW frequency up or down by ``step_hz``.

        Returns the new frequency in Hz.
        """
        if direction not in ("up", "down"):
            raise MXGParameterError("direction must be 'up' or 'down'")

        current_freq = self.get_frequency()
        new_freq = (
            current_freq + step_hz if direction == "up" else current_freq - step_hz
        )
        self.set_frequency(new_freq)
        return new_freq

    # ------------------------------------------------------------------
    # Power
    # ------------------------------------------------------------------
    def set_power(self, power_dbm: float) -> None:
        """Set the RF output power in dBm."""
        self._write(f":POW {power_dbm}")
        logger.info("MXG power set to %.2f dBm", power_dbm)

    def get_power(self) -> float:
        """Query and return the current RF output power in dBm."""
        return float(self._query(":POW?"))

    # ------------------------------------------------------------------
    # RF output / modulation
    # ------------------------------------------------------------------
    def set_rf_output(self, state: bool) -> None:
        """Turn the RF output on or off."""
        self._write(f":OUTP {'ON' if state else 'OFF'}")
        logger.info("MXG RF output %s", "enabled" if state else "disabled")

    def get_rf_output_state(self) -> bool:
        """Return True if the RF output is currently on."""
        return self._query(":OUTP?") in ("1", "ON")

    def enable_modulation(self, state: bool) -> None:
        """Turn the global modulation state on or off."""
        self._write(f":MOD:STAT {'ON' if state else 'OFF'}")

    def get_modulation_state(self) -> bool:
        """Return True if modulation is currently enabled."""
        return self._query(":MOD:STAT?") in ("1", "ON")

    # ------------------------------------------------------------------
    # Software sweep (host-timed, works on any instrument state)
    # ------------------------------------------------------------------
    @property
    def is_software_sweeping(self) -> bool:
        return self._sweep_thread is not None and self._sweep_thread.is_alive()

    def start_software_sweep(
        self,
        start_hz: float,
        stop_hz: float,
        step_hz: float,
        dwell_s: float = 0.5,
        callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """Sweep the CW frequency from ``start_hz`` to ``stop_hz`` on a
        background thread, setting each point and pausing ``dwell_s``
        seconds between points.

        This is the "software" sweep: it drives the instrument one
        ``:FREQ`` write at a time from the host, so it is slower than a
        hardware LIST/STEP sweep but requires no extra configuration and
        works well for measurements that need a callback (e.g. reading a
        power meter) at every point.

        Args:
            callback: Optional function called with the actual, verified
                frequency (Hz) after each point is set and settled.
        """
        if not (MIN_FREQUENCY_HZ <= start_hz <= MAX_FREQUENCY_HZ):
            raise MXGParameterError("start_hz is outside the instrument's range")
        if not (MIN_FREQUENCY_HZ <= stop_hz <= MAX_FREQUENCY_HZ):
            raise MXGParameterError("stop_hz is outside the instrument's range")
        if step_hz <= 0:
            raise MXGParameterError("step_hz must be positive")
        if abs(stop_hz - start_hz) < step_hz:
            raise MXGParameterError("step_hz is larger than the sweep range")
        if self.is_software_sweeping:
            raise MXGError(
                "A software sweep is already running; call stop_software_sweep() first."
            )

        self._stop_sweep_event.clear()

        def _run_sweep() -> None:
            freq = start_hz
            direction = 1 if stop_hz >= start_hz else -1
            try:
                while not self._stop_sweep_event.is_set():
                    if (direction > 0 and freq > stop_hz) or (
                        direction < 0 and freq < stop_hz
                    ):
                        break
                    self.set_frequency(freq)
                    actual_freq = self.get_frequency()
                    if abs(actual_freq - freq) > 1:
                        logger.warning(
                            "Frequency not applied as requested: got %.6g Hz, expected %.6g Hz",
                            actual_freq,
                            freq,
                        )
                    else:
                        if callback is not None:
                            callback(actual_freq)
                        self._stop_sweep_event.wait(dwell_s)
                    freq += direction * step_hz
            except MXGError as exc:
                logger.error("Software sweep aborted due to instrument error: %s", exc)
            logger.info("Software sweep finished or stopped.")

        self._sweep_thread = threading.Thread(target=_run_sweep, daemon=True)
        self._sweep_thread.start()

    def stop_software_sweep(self, wait: bool = True) -> None:
        """Signal the background software sweep to stop.

        Safe to call even if no sweep is running.
        """
        self._stop_sweep_event.set()
        if wait and self._sweep_thread is not None:
            self._sweep_thread.join()
        self._sweep_thread = None

    # ------------------------------------------------------------------
    # Hardware sweep (instrument-timed LIST/STEP mode)
    # ------------------------------------------------------------------
    def configure_step_sweep(
        self,
        start_hz: float,
        stop_hz: float,
        points: int = 101,
        dwell_s: float = 0.002,
        spacing: str = "LIN",
    ) -> None:
        """Configure (but do not start) a hardware step sweep.

        This uses the instrument's own STEP sweep engine
        (:SWEep subsystem), which is far faster and more precisely timed
        than :meth:`start_software_sweep`, at the cost of needing
        :meth:`start_hardware_sweep` / :meth:`stop_hardware_sweep` to
        control it and leaving the instrument in LIST/STEP frequency mode
        until it's put back into CW (which :meth:`set_frequency` and
        :meth:`stop_hardware_sweep` both do).

        Args:
            points: Number of step points, 2-65535.
            dwell_s: Time to pause at each point once settled, in seconds.
            spacing: ``"LIN"`` or ``"LOG"``.
        """
        if not (MIN_FREQUENCY_HZ <= start_hz <= MAX_FREQUENCY_HZ):
            raise MXGParameterError("start_hz is outside the instrument's range")
        if not (MIN_FREQUENCY_HZ <= stop_hz <= MAX_FREQUENCY_HZ):
            raise MXGParameterError("stop_hz is outside the instrument's range")
        if not (2 <= points <= 65535):
            raise MXGParameterError("points must be between 2 and 65535")
        if dwell_s <= 0:
            raise MXGParameterError("dwell_s must be positive")
        spacing_upper = spacing.upper()
        if spacing_upper not in _SWEEP_SPACING:
            raise MXGParameterError(f"spacing must be one of {_SWEEP_SPACING}")

        self._write(":LIST:TYPE STEP")
        self._write(f":FREQ:STAR {start_hz}")
        self._write(f":FREQ:STOP {stop_hz}")
        self._write(f":SWE:POIN {points}")
        self._write(f":SWE:SPAC {'LIN' if spacing_upper.startswith('LIN') else 'LOG'}")
        self._write(f":SWE:DWEL {dwell_s}")
        logger.info(
            "Configured hardware step sweep: %.6g Hz -> %.6g Hz, %d points, %s spacing",
            start_hz,
            stop_hz,
            points,
            spacing_upper,
        )

    def start_hardware_sweep(
        self, trigger_source: str = "IMM", continuous: bool = True
    ) -> None:
        """Start a previously configured hardware sweep.

        Args:
            trigger_source: Point-trigger source for :LIST:TRIGger:SOURce
                (e.g. ``"IMM"``, ``"BUS"``, ``"EXT"``, ``"KEY"``, ``"TIM"``).
            continuous: If True, the sweep free-runs and retraces
                continuously. If False, a single sweep is triggered and
                the instrument returns to the last point when done.
        """
        trigger_upper = trigger_source.upper()
        if trigger_upper not in _TRIGGER_SOURCES:
            raise MXGParameterError(f"trigger_source must be one of {_TRIGGER_SOURCES}")

        self._write(f":LIST:TRIG:SOUR {trigger_upper}")
        self._write(f":INIT:CONT {'ON' if continuous else 'OFF'}")
        self._write(":FREQ:MODE LIST")
        if not continuous:
            self._write(":INIT:IMM")
        logger.info(
            "Hardware sweep started (trigger=%s, continuous=%s)",
            trigger_upper,
            continuous,
        )

    def stop_hardware_sweep(self) -> None:
        """Abort any running hardware sweep and return to CW mode."""
        self._write(":ABOR")
        self._write(":FREQ:MODE CW")
        logger.info("Hardware sweep stopped; instrument returned to CW mode.")

    def get_sweep_point(self) -> int:
        """Return the current sweep point index (works for LIST or STEP)."""
        return int(self._query(":SWE:CPOIN?"))

    # ------------------------------------------------------------------
    # Convenience: daily lab workflow
    # ------------------------------------------------------------------
    def set_power_then_sweep(
        self,
        power_dbm: float,
        start_hz: float,
        stop_hz: float,
        step_hz: float,
        dwell_s: float = 0.5,
        callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """Fix the output power once, then run a software frequency sweep.

        This mirrors the most common bench workflow: set a power level,
        enable the RF output, and step frequency across a band while
        something else (a power meter, a receiver) is read at each point.
        For instrument-timed sweeps instead, use
        :meth:`configure_step_sweep` + :meth:`start_hardware_sweep`.
        """
        self.set_power(power_dbm)
        self.set_rf_output(True)
        self.start_software_sweep(
            start_hz, stop_hz, step_hz, dwell_s=dwell_s, callback=callback
        )
