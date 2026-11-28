"""Puts a device together from its layers.

Every setting comes from the most specific layer that has it: the built-in defaults, then the device type, then the device
configuration. The result is what the rest of LPC uses. The function opens no hardware and reads no file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from .appearance import DEFAULT_COLORS, DEFAULT_PATTERNS, Color, PatternName
from .button_roles import ButtonRole
from .device_config import DeviceConfig, DeviceConfigError
from .device_types import ButtonSpec, DeviceType, SensorKind
from .display import DisplayFunction

DEFAULT_BRIGHTNESS = 1.0


@dataclass(frozen=True)
class ResolvedButton:
    """A button as it is used."""

    name: str
    role: ButtonRole
    pin: Optional[int]


@dataclass(frozen=True)
class ResolvedSensor:
    """A sensor as it is used. ``interval`` None reads it once, then only what the device reports."""

    name: str
    interval: Optional[float]
    unit: str = ""
    device_class: str = ""
    kind: SensorKind = SensorKind.NUMBER
    diagnostic: bool = False


@dataclass(frozen=True)
class ResolvedDevice:
    """A device as it is used: the device type with the device configuration applied."""

    device_type: DeviceType
    brightness: float
    buttons: Tuple[ResolvedButton, ...]
    sensors: Tuple[ResolvedSensor, ...]
    colors: Mapping[DisplayFunction, Color]
    patterns: Mapping[DisplayFunction, PatternName]


def resolve_device(device_type: DeviceType, config: DeviceConfig, source: str = "device configuration") -> ResolvedDevice:
    """
    Apply the device configuration to a device type.
    :param device_type: The device type.
    :param config: The device configuration.
    :param source: Name of the device configuration file, for the error messages.
    :raises DeviceConfigError: If the configuration names a button, sensor or display function that the device type does not have.
    :return: The device. ``colors`` and ``patterns`` only hold the display functions that the device type offers.
    """
    _check_names(config.buttons, {b.name for b in device_type.buttons}, "buttons", "button", device_type, source)
    _check_names(config.sensors, {s.name for s in device_type.sensors}, "sensors", "sensor", device_type, source)
    _check_functions(config.colors, "colors", device_type, source)
    _check_functions(config.patterns, "patterns", device_type, source)

    colors = {f: {**DEFAULT_COLORS, **device_type.colors, **config.colors}[f] for f in device_type.functions}
    patterns = {f: {**DEFAULT_PATTERNS, **device_type.patterns, **config.patterns}[f] for f in device_type.functions}
    return ResolvedDevice(
        device_type=device_type,
        brightness=DEFAULT_BRIGHTNESS if config.brightness is None else config.brightness,
        buttons=tuple(_resolve_button(spec, config) for spec in device_type.buttons),
        sensors=tuple(ResolvedSensor(s.name, _sensor_interval(s.name, s.interval, config), s.unit, s.device_class, s.kind, s.diagnostic) for s in device_type.sensors),
        colors=colors,
        patterns=patterns,
    )


def _resolve_button(spec: ButtonSpec, config: DeviceConfig) -> ResolvedButton:
    own = config.buttons.get(spec.name)
    if own is None:
        return ResolvedButton(spec.name, spec.role, spec.pin)
    return ResolvedButton(spec.name, spec.role if own.role is None else own.role, spec.pin if own.pin is None else own.pin)


def _sensor_interval(name: str, default: Optional[float], config: DeviceConfig) -> Optional[float]:
    own = config.sensors.get(name)
    return default if own is None or own.interval is None else own.interval


def _check_names(configured: Mapping[str, object], available: set[str], table: str, kind: str, device_type: DeviceType, source: str) -> None:
    for name in configured:
        if name not in available:
            have = ", ".join(sorted(available)) or f"no {kind}s"
            raise DeviceConfigError(f"{source}: {table}.{name}: the device type {device_type.name} has no {kind} with this name ({have})")


def _check_functions(configured: Mapping[DisplayFunction, object], table: str, device_type: DeviceType, source: str) -> None:
    for function in configured:
        if function not in device_type.functions:
            raise DeviceConfigError(f"{source}: {table}.{function.value}: the device type {device_type.name} does not offer this display function")
