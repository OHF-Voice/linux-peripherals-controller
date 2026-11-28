"""How a device type is described: how a device is driven and what it offers.

A device type describes the hardware of one kind of device (LED chip, number of LEDs, buttons and their pins, sensors) and which
display functions it can show. It may also replace the predefined colors and patterns. It is data only, it opens no hardware. Every
device type lives in its own file in ``devices/``, together with the code that runs its hardware.
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
