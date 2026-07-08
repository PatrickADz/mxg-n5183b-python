"""Layered configuration for the MXG N5183B CLI.

Resolution order (highest priority first):
    1. Command-line arguments
    2. ``config.ini`` (path given by --config, default ``./config.ini``)
    3. Built-in defaults defined below
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULTS = {
    "resource_name": "TCPIP::192.168.0.11::INSTR",
    "timeout_ms": 5000,
    "check_errors": True,
}


@dataclass
class MXGConfig:
    resource_name: str
    timeout_ms: int
    check_errors: bool


def _read_config_file(config_path: Path) -> dict:
    if not config_path.exists():
        return {}

    parser = configparser.ConfigParser()
    parser.read(config_path)
    if "mxg" not in parser:
        return {}

    section = parser["mxg"]
    values = {}
    if "resource_name" in section:
        values["resource_name"] = section.get("resource_name")
    if "timeout_ms" in section:
        values["timeout_ms"] = section.getint("timeout_ms")
    if "check_errors" in section:
        values["check_errors"] = section.getboolean("check_errors")
    return values


def load_config(
    config_path: Optional[str] = None,
    cli_resource_name: Optional[str] = None,
    cli_timeout_ms: Optional[int] = None,
    cli_check_errors: Optional[bool] = None,
) -> MXGConfig:
    """Merge defaults, config.ini, and CLI overrides into one config.

    Any argument left as None falls through to the next layer down.
    """
    merged = dict(DEFAULTS)
    merged.update(_read_config_file(Path(config_path or "config.ini")))

    if cli_resource_name is not None:
        merged["resource_name"] = cli_resource_name
    if cli_timeout_ms is not None:
        merged["timeout_ms"] = cli_timeout_ms
    if cli_check_errors is not None:
        merged["check_errors"] = cli_check_errors

    return MXGConfig(**merged)
