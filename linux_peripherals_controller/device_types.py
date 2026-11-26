"""The device types LPC knows: how a device is driven and what it offers.

A device type describes the hardware of one kind of device (LED chip, number of LEDs, buttons and their pins, sensors) and which
display functions it can show. It may also replace the predefined colors and patterns. It is data only, it opens no hardware.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Mapping, Optional, Tuple

from .appearance import Color, PatternName
from .button_roles import ButtonRole
from .display import DisplayFunction


@dataclass(frozen=True)
class LedSpec:
    """The LEDs of a device."""

    driver: str
    count: int
    options: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ButtonSpec:
    """A button of a device, with the role it has by default."""

    name: str
    role: ButtonRole
    pin: Optional[int] = None


@dataclass(frozen=True)
class SensorSpec:
    """A sensor of a device, read every ``interval`` seconds."""

    name: str
    interval: float = 30.0


@dataclass(frozen=True)
class DeviceType:
    """One kind of device."""

    name: str
    description: str
    leds: Optional[LedSpec] = None
    buttons: Tuple[ButtonSpec, ...] = ()
    sensors: Tuple[SensorSpec, ...] = ()
    functions: FrozenSet[DisplayFunction] = frozenset(DisplayFunction)
    colors: Mapping[DisplayFunction, Color] = field(default_factory=dict)
    patterns: Mapping[DisplayFunction, PatternName] = field(default_factory=dict)


class UnknownDeviceType(ValueError):
    """The name is not a device type."""

    def __init__(self, name: str, known: Tuple[str, ...]) -> None:
        super().__init__(f"Unknown device type '{name}'. Known device types: {', '.join(known)}")
        self.name = name
        self.known = known


DEVICE_TYPES: Mapping[str, DeviceType] = {
    "respeaker_2mic_v1": DeviceType(
        name="respeaker_2mic_v1",
        description="ReSpeaker 2-Mic Pi HAT with WM8960 codec: 3 APA102 LEDs on SPI0 and one button on GPIO 17",
        leds=LedSpec("apa102", 3, {"spi_bus": 0, "spi_device": 0, "spi_speed_hz": 8_000_000}),
        buttons=(ButtonSpec("button", ButtonRole.ACTION, pin=17),),
    ),
}


def get_device_type(name: str) -> DeviceType:
    """
    Look up a device type.
    :param name: The name of the device type.
    :raises UnknownDeviceType: If there is no such device type. The error names the known ones.
    """
    try:
        return DEVICE_TYPES[name]
    except KeyError:
        raise UnknownDeviceType(name, known_device_types()) from None


def known_device_types() -> Tuple[str, ...]:
    """The names of all device types, sorted."""
    return tuple(sorted(DEVICE_TYPES))
