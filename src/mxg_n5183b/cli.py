"""Command-line interface for quick bench use of the N5183B driver.

Examples:
    python -m mxg_n5183b --resource TCPIP::192.168.0.11::INSTR idn
    python -m mxg_n5183b set-freq --freq-hz 1e9
    python -m mxg_n5183b sweep --start-hz 1e9 --stop-hz 2e9 --step-hz 1e8 --dwell-s 0.5
"""

from __future__ import annotations

import argparse
import logging
import shlex
import sys

from .config import load_config
from .driver import N5183B
from .exceptions import MXGError

logger = logging.getLogger(__name__)

SHELL_HELP = """\
Available commands:
  idn                          Query *IDN?
  freq <hz>                    Set CW frequency, e.g. 'freq 1e9'
  freq?                        Read current frequency
  power <dbm>                  Set output power, e.g. 'power -10'
  power?                       Read current power
  output on|off                Enable/disable RF output
  output?                      Read RF output state
  mod on|off                   Enable/disable modulation
  sweep <start> <stop> <step> [dwell]
                                Start a software sweep (dwell defaults to 0.5 s)
  stop                          Stop a running software sweep
  error?                        Read the next SCPI error queue entry
  help                          Show this message
  exit / quit                   Close the connection and leave
"""


def _run_shell_command(sg: N5183B, line: str) -> None:
    """Parse and execute a single interactive-shell command line."""
    parts = shlex.split(line)
    cmd, args = parts[0].lower(), parts[1:]

    if cmd == "idn":
        print(sg.get_idn())
    elif cmd == "freq":
        sg.set_frequency(float(args[0]))
    elif cmd == "freq?":
        print(f"{sg.get_frequency():.6g} Hz")
    elif cmd == "power":
        sg.set_power(float(args[0]))
    elif cmd == "power?":
        print(f"{sg.get_power():.2f} dBm")
    elif cmd == "output":
        sg.set_rf_output(args[0].lower() == "on")
    elif cmd == "output?":
        print("ON" if sg.get_rf_output_state() else "OFF")
    elif cmd == "mod":
        sg.enable_modulation(args[0].lower() == "on")
    elif cmd == "sweep":
        start_hz, stop_hz, step_hz = (float(a) for a in args[:3])
        dwell_s = float(args[3]) if len(args) > 3 else 0.5
        sg.start_software_sweep(start_hz, stop_hz, step_hz, dwell_s=dwell_s)
        print("Sweep started in the background; use 'stop' to end it.")
    elif cmd == "stop":
        sg.stop_software_sweep()
        print("Sweep stopped.")
    elif cmd == "error?":
        print(sg.read_error())
    elif cmd in ("help", "?"):
        print(SHELL_HELP)
    else:
        print(f"Unknown command: '{cmd}'. Type 'help' for the command list.")


def run_interactive_shell(sg: N5183B) -> None:
    """Keep one VISA connection open and dispatch short typed commands.

    Meant for bench work: tweaking frequency/power/RF output repeatedly
    without paying the connect/disconnect cost of the CLI on every call.
    """
    print(f"Connected to: {sg.get_idn()}")
    print("MXG N5183B interactive shell. Type 'help' for commands, 'exit' to quit.")
    while True:
        try:
            line = input("mxg> ").strip()
        except EOFError:
            print()
            break

        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break

        try:
            _run_shell_command(sg, line)
        except MXGError as exc:
            print(f"Error: {exc}")
        except (IndexError, ValueError):
            print("Bad arguments for that command. Type 'help' to check the syntax.")
        except KeyboardInterrupt:
            print()
            continue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mxg_n5183b",
        description="CLI for the Keysight MXG N5183B signal generator",
    )
    parser.add_argument("--config", help="Path to config.ini (default: ./config.ini)")
    parser.add_argument("--resource", help="VISA resource string, overrides config.ini")
    parser.add_argument(
        "--timeout-ms", type=int, help="VISA timeout in ms, overrides config.ini"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("idn", help="Query and print *IDN?")

    freq_parser = subparsers.add_parser("set-freq", help="Set CW frequency")
    freq_parser.add_argument("--freq-hz", type=float, required=True)

    power_parser = subparsers.add_parser("set-power", help="Set output power")
    power_parser.add_argument("--power-dbm", type=float, required=True)

    output_parser = subparsers.add_parser("rf-output", help="Enable/disable RF output")
    output_parser.add_argument("--state", choices=["on", "off"], required=True)

    sweep_parser = subparsers.add_parser("sweep", help="Run a software frequency sweep")
    sweep_parser.add_argument("--start-hz", type=float, required=True)
    sweep_parser.add_argument("--stop-hz", type=float, required=True)
    sweep_parser.add_argument("--step-hz", type=float, required=True)
    sweep_parser.add_argument("--dwell-s", type=float, default=0.5)
    sweep_parser.add_argument("--power-dbm", type=float, default=None)

    subparsers.add_parser(
        "shell",
        help="Open an interactive session (connect once, type short commands)",
    )

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    config = load_config(
        config_path=args.config,
        cli_resource_name=args.resource,
        cli_timeout_ms=args.timeout_ms,
    )

    try:
        with N5183B(
            config.resource_name,
            timeout_ms=config.timeout_ms,
            check_errors=config.check_errors,
        ) as sg:
            if args.command == "idn":
                print(sg.get_idn())
            elif args.command == "set-freq":
                sg.set_frequency(args.freq_hz)
            elif args.command == "set-power":
                sg.set_power(args.power_dbm)
            elif args.command == "rf-output":
                sg.set_rf_output(args.state == "on")
            elif args.command == "sweep":
                if args.power_dbm is not None:
                    sg.set_power_then_sweep(
                        power_dbm=args.power_dbm,
                        start_hz=args.start_hz,
                        stop_hz=args.stop_hz,
                        step_hz=args.step_hz,
                        dwell_s=args.dwell_s,
                    )
                else:
                    sg.start_software_sweep(
                        start_hz=args.start_hz,
                        stop_hz=args.stop_hz,
                        step_hz=args.step_hz,
                        dwell_s=args.dwell_s,
                    )
                print("Sweep started. Press Ctrl+C to stop.")
                try:
                    while sg.is_software_sweeping:
                        pass
                except KeyboardInterrupt:
                    sg.stop_software_sweep()
            elif args.command == "shell":
                run_interactive_shell(sg)
    except MXGError as exc:
        logger.error("%s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
