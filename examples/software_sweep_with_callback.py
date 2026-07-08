"""Software frequency sweep with a per-point callback.

Useful when you need to do something at every frequency point — e.g. read
a power meter or a receiver's output — and don't need instrument-timed
precision. Since this sweep is driven from the host at ~dwell_s per point,
it's a natural fit for slower manual/semi-automated measurements.

Usage:
    python examples/software_sweep_with_callback.py
"""

from mxg_n5183b import N5183B

RESOURCE_NAME = "TCPIP::192.168.0.11::INSTR"


def read_power_meter(freq_hz: float) -> None:
    """Placeholder for whatever you actually want to do at each point.

    Swap this out for a real measurement, e.g. querying a Keysight N1914A
    power meter, reading a receiver's IF power, or logging to a file.
    """
    print(f"  -> at {freq_hz / 1e9:.4f} GHz: (read your instrument here)")


def main() -> None:
    with N5183B(RESOURCE_NAME) as sg:
        print("Connected to:", sg.get_idn())

        sg.set_power(0.0)  # dBm, fixed for the whole sweep
        sg.set_rf_output(True)

        print("Starting software sweep 1-2 GHz in 100 MHz steps...")
        sg.start_software_sweep(
            start_hz=1e9,
            stop_hz=2e9,
            step_hz=100e6,
            dwell_s=0.5,
            callback=read_power_meter,
        )

        # The sweep runs on a background thread; block here until it's done.
        while sg.is_software_sweeping:
            pass

        print("Sweep finished.")


if __name__ == "__main__":
    main()
