"""Load the instrument address from config.ini instead of hardcoding it.

Handy once you have several example/test scripts and don't want to edit
the resource string in each one separately — set it once in config.ini.

Prerequisite:
    cp config.example.ini config.ini
    # then edit config.ini with your instrument's real address

Usage:
    python examples/using_config_file.py
"""

from mxg_n5183b import N5183B
from mxg_n5183b.config import load_config


def main() -> None:
    config = load_config()  # reads ./config.ini, falls back to defaults

    with N5183B(
        config.resource_name,
        timeout_ms=config.timeout_ms,
        check_errors=config.check_errors,
    ) as sg:
        print("Connected to:", sg.get_idn())
        print(f"Using resource: {config.resource_name}")

        sg.set_power_then_sweep(
            power_dbm=0.0,
            start_hz=1e9,
            stop_hz=1.5e9,
            step_hz=50e6,
            dwell_s=0.3,
        )

        while sg.is_software_sweeping:
            pass

        print("Sweep finished.")


if __name__ == "__main__":
    main()
