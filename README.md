# mxg-n5183b-python

Python driver and CLI for the Keysight MXG N5183B RF signal generator, used for RF characterization in radio astronomy receiver systems.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)

## Features

- SCPI communication over VISA (TCP/IP, GPIB, USB) via PyVISA
- Automatic SCPI error-queue checking after every write
- Context manager support with automatic RF-output shutdown on exit
- Software (host-timed) frequency sweep on a background thread, with an optional per-point callback
- Hardware (instrument-timed) LIST/STEP sweep using the signal generator's own sweep engine
- `set_power_then_sweep()` convenience method for the common bench workflow: fix power, then sweep frequency
- Layered configuration: CLI arguments -> `config.ini` -> built-in defaults
- Full test suite using a mocked VISA resource — no hardware required to run tests

## Installation

```bash
git clone https://github.com/PatrickADz/mxg-n5183b-python.git
cd mxg-n5183b-python
pip install -r requirements.txt
pip install -e .
```

For development (tests, formatting):

```bash
pip install -r requirements-dev.txt
```

## Quick Start

```python
from mxg_n5183b import N5183B

with N5183B("TCPIP::192.168.0.11::INSTR") as sg:
    print(sg.get_idn())
    sg.set_power_then_sweep(
        power_dbm=0,
        start_hz=1e9,
        stop_hz=2e9,
        step_hz=100e6,
        dwell_s=0.5,
    )
```

The RF output is automatically turned off when the `with` block exits, even if an exception occurs.

### Command line

```bash
# Copy and edit the example config first
cp config.example.ini config.ini

python -m mxg_n5183b idn
python -m mxg_n5183b set-freq --freq-hz 1e9
python -m mxg_n5183b sweep --start-hz 1e9 --stop-hz 2e9 --step-hz 1e8 --dwell-s 0.5
```

### Interactive shell

For bench work where you're repeatedly tweaking frequency, power, or RF
output, `shell` opens one connection and keeps it open instead of
reconnecting on every command:

```bash
python -m mxg_n5183b shell
```

```
mxg> freq 1e9
mxg> power -10
mxg> output on
mxg> output?
ON
mxg> exit
```

Type `help` inside the shell for the full command list.

## Examples

See [`examples/`](examples/) for ready-to-run scripts: basic connect/configure,
a software sweep with a per-point callback, a hardware STEP sweep, and
loading the instrument address from `config.ini`.

## Repository Structure

```
mxg-n5183b-python/
├── src/mxg_n5183b/
│   ├── __init__.py       # Public API
│   ├── driver.py         # N5183B driver class
│   ├── exceptions.py     # Custom exception hierarchy
│   ├── config.py         # Layered config (CLI > config.ini > defaults)
│   ├── cli.py            # Command-line interface + interactive shell
│   └── __main__.py       # `python -m mxg_n5183b` entry point
├── examples/
│   ├── basic_usage.py
│   ├── software_sweep_with_callback.py
│   ├── hardware_step_sweep.py
│   └── using_config_file.py
├── tests/
│   ├── conftest.py       # Mocked VISA fixtures
│   └── test_driver.py
├── config.example.ini
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── LICENSE
```

## Tests

```bash
pytest tests/ -v
```

All tests run against a mocked VISA resource (`FakeInstrument` in `tests/conftest.py`), so no physical signal generator is needed.

## Context / Notes

Developed for RF characterization and LO-chain validation of heterodyne receivers at CePIA.
It provides both software-controlled sweeps for synchronized measurements and hardware-timed sweeps for rapid instrument verification.
## License

MIT — see [LICENSE](LICENSE).
