"""Hardware (instrument-timed) frequency sweep using the signal
generator's own STEP sweep engine.

Faster and more precisely timed than the software sweep, at the cost of
losing per-point Python callbacks — the instrument runs the sweep on its
own. Good for a quick RF sanity check, or when you're triggering
externally and just need the source to retrace a band continuously.

Usage:
    python examples/hardware_step_sweep.py
"""

import time

from mxg_n5183b import N5183B

RESOURCE_NAME = "TCPIP::192.168.0.11::INSTR"


def main() -> None:
    with N5183B(RESOURCE_NAME) as sg:
        print("Connected to:", sg.get_idn())

        sg.set_power(0.0)
        sg.set_rf_output(True)

        sg.configure_step_sweep(
            start_hz=1e9,
            stop_hz=2e9,
            points=101,
            dwell_s=0.002,
            spacing="LIN",
        )
        sg.start_hardware_sweep(trigger_source="IMM", continuous=True)
        print("Hardware sweep running (free-running, continuous retrace).")

        try:
            print("Sweeping... press Ctrl+C to stop.")
            while True:
                print(f"  current point: {sg.get_sweep_point()}")
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            sg.stop_hardware_sweep()
            print("Hardware sweep stopped, instrument back in CW mode.")


if __name__ == "__main__":
    main()
