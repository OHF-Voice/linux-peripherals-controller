"""The device configuration: the settings of one device, written by the user in a TOML file.

Everything in it is optional. A missing file (no ``--device-config``) is the same as an empty one. The file is checked completely:
a key that is not known, or a value that is not valid, is an error, so LPC never starts with a part of the configuration.

Example::

    brightness = 0.5

    [buttons.button]
    role = "mute"

    [colors]
    listening = "#0000ff"

    [patterns]
    listening = "pulse"

    [sensors.temperature]
    interval = 60
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, TypeVar

from .appearance import Color, PatternName
from .button_roles import ButtonRole
from .display import DisplayFunction

T = TypeVar("T")


class DeviceConfigError(ValueError):
    """The device configuration cannot be used. The message names the file and the key."""


@dataclass(frozen=True)
class ButtonConfig:
    """Settings of one button. None means: as the device type says."""

    role: Optional[ButtonRole] = None
    pin: Optional[int] = None


@dataclass(frozen=True)
class SensorConfig:
    """Settings of one sensor. None means: as the device type says."""

    interval: Optional[float] = None


@dataclass(frozen=True)
class DeviceConfig:
    """The settings of one device."""

    brightness: Optional[float] = None
    buttons: Mapping[str, ButtonConfig] = field(default_factory=dict)
    colors: Mapping[DisplayFunction, Color] = field(default_factory=dict)
    patterns: Mapping[DisplayFunction, PatternName] = field(default_factory=dict)
    sensors: Mapping[str, SensorConfig] = field(default_factory=dict)


def load_device_config(path: Optional[Path]) -> DeviceConfig:
    """
    Read the device configuration.
    :param path: The TOML file, None for no device configuration.
    :raises DeviceConfigError: If the file cannot be read or is not valid.
    """
    if path is None:
        return DeviceConfig()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DeviceConfigError(f"{path}: cannot be read: {exc}") from exc
    return parse_device_config(text, str(path))


def parse_device_config(text: str, source: str) -> DeviceConfig:
    """
    Check and read the text of a device configuration.
    :param text: The TOML text.
    :param source: Name of the file, for the error messages.
    :raises DeviceConfigError: If the text is not valid TOML, has a key that is not known or a value that is not valid.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise DeviceConfigError(f"{source}: not valid TOML: {exc}") from exc

    _check_keys(data, ("brightness", "buttons", "colors", "patterns", "sensors"), "", source)
    return DeviceConfig(
        brightness=_brightness(data.get("brightness"), source) if "brightness" in data else None,
        buttons=_tables(data.get("buttons", {}), "buttons", source, _button),
        colors=_function_values(data.get("colors", {}), "colors", source, _color),
        patterns=_function_values(data.get("patterns", {}), "patterns", source, _pattern),
        sensors=_tables(data.get("sensors", {}), "sensors", source, _sensor),
    )


def _fail(source: str, key: str, problem: str) -> DeviceConfigError:
    return DeviceConfigError(f"{source}: {key}: {problem}" if key else f"{source}: {problem}")


def _check_keys(table: Mapping[str, Any], allowed: tuple[str, ...], path: str, source: str) -> None:
    for key in table:
        if key not in allowed:
            raise _fail(source, f"{path}.{key}" if path else key, f"unknown key, allowed: {', '.join(allowed)}")


def _brightness(value: Any, source: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
        raise _fail(source, "brightness", f"{value!r} is not a number from 0 to 1")
    return float(value)


def _tables(value: Any, path: str, source: str, read: Callable[[Mapping[str, Any], str, str], T]) -> dict[str, T]:
    if not isinstance(value, dict):
        raise _fail(source, path, "must be a table")
    result = {}
    for name, table in value.items():
        if not isinstance(table, dict):
            raise _fail(source, f"{path}.{name}", "must be a table")
        result[name] = read(table, f"{path}.{name}", source)
    return result


def _button(table: Mapping[str, Any], path: str, source: str) -> ButtonConfig:
    _check_keys(table, ("role", "pin"), path, source)
    role = pin = None
    if "role" in table:
        try:
            role = ButtonRole(table["role"])
        except ValueError:
            raise _fail(source, f"{path}.role", f"{table['role']!r} is not a role, allowed: {', '.join(r.value for r in ButtonRole)}") from None
    if "pin" in table:
        pin = table["pin"]
        if isinstance(pin, bool) or not isinstance(pin, int) or pin < 0:
            raise _fail(source, f"{path}.pin", f"{pin!r} is not a pin number")
    return ButtonConfig(role, pin)


def _sensor(table: Mapping[str, Any], path: str, source: str) -> SensorConfig:
    _check_keys(table, ("interval",), path, source)
    interval = None
    if "interval" in table:
        interval = table["interval"]
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval <= 0:
            raise _fail(source, f"{path}.interval", f"{interval!r} is not a number of seconds above 0")
        interval = float(interval)
    return SensorConfig(interval)


def _function_values(value: Any, path: str, source: str, read: Callable[[Any, str, str], T]) -> dict[DisplayFunction, T]:
    if not isinstance(value, dict):
        raise _fail(source, path, "must be a table")
    _check_keys(value, tuple(f.value for f in DisplayFunction), path, source)
    return {DisplayFunction(name): read(item, f"{path}.{name}", source) for name, item in value.items()}


def _color(value: Any, path: str, source: str) -> Color:
    if not isinstance(value, str):
        raise _fail(source, path, f"{value!r} is not a color, expected a text like #ff8000")
    try:
        return Color.from_hex(value)
    except ValueError as exc:
        raise _fail(source, path, str(exc)) from None


def _pattern(value: Any, path: str, source: str) -> PatternName:
    try:
        return PatternName(value)
    except ValueError:
        raise _fail(source, path, f"{value!r} is not a pattern, allowed: {', '.join(p.value for p in PatternName)}") from None
