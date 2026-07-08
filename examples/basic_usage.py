"""Basic usage: connect, read identification, set frequency/power, toggle RF output.

This is the "arrive at the bench and use the equipment" script — copy it,
change RESOURCE_NAME, and run.

Usage:
    python examples/basic_usage.py
"""

from mxg_n5183b import N5183B

# Replace with your instrument's actual VISA resource string.
# For TCP/IP instruments this is typically "TCPIP::<ip-address>::INSTR".
RESOURCE_NAME = "TCPIP::192.168.0.11::INSTR"


def main() -> None:
    # Using N5183B as a context manager guarantees the RF output is turned
    # off and the VISA session is closed when the block exits, even if
    # something raises partway through.
    with N5183B(RESOURCE_NAME) as sg:
        print("Connected to:", sg.get_idn())

        sg.set_frequency(1e9)  # 1 GHz
        sg.set_power(-10.0)  # -10 dBm
        sg.set_rf_output(True)

        print(f"Frequency: {sg.get_frequency():.6g} Hz")
        print(f"Power:     {sg.get_power():.2f} dBm")
        print(f"RF output: {'ON' if sg.get_rf_output_state() else 'OFF'}")

        input("Press Enter to turn off the RF output and disconnect...")


if __name__ == "__main__":
    main()
