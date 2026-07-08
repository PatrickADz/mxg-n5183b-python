# Examples

Copy any of these, edit `RESOURCE_NAME` (or set up `config.ini`), and run
directly:

```bash
python examples/basic_usage.py
```

| Script | What it shows |
|---|---|
| `basic_usage.py` | Connect, read `*IDN?`, set frequency/power, toggle RF output |
| `software_sweep_with_callback.py` | Host-timed sweep with a callback at each point (e.g. reading a power meter) |
| `hardware_step_sweep.py` | Instrument-timed STEP sweep — faster, no per-point callback |
| `using_config_file.py` | Load the resource address from `config.ini` instead of hardcoding it |

All examples use `N5183B` as a context manager, so the RF output is turned
off automatically when the script ends or is interrupted.

For quick manual bench testing (adjusting frequency/power/output
repeatedly without writing a script), use the interactive shell instead:

```bash
python -m mxg_n5183b shell
```
