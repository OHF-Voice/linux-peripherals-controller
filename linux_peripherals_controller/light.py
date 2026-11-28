"""The light of Home Assistant: the background of the LEDs.

It is what the LEDs show when no display function is active. Its state is a value that Home Assistant changes and that is stored
across restarts. Like the LED ring of the Home Assistant Voice PE it starts off, in a light blue at 66 % brightness.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .appearance import Color


@dataclass(frozen=True)
class LightState:
    """The light, every value from 0 to 1."""

    on: bool = False
    brightness: float = 0.66
    red: float = 0.094
    green: float = 0.733
    blue: float = 0.949

    @property
    def color(self) -> Color:
        """The color at full brightness."""
        return Color(round(self.red * 255), round(self.green * 255), round(self.blue * 255))

    def to_dict(self) -> dict[str, Any]:
        """The state for the state file."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LightState":
        """
        Read the state from the state file.
        :param data: The stored values. Missing or invalid values keep their default.
        """
        default = cls()
        on = data.get("on")
        return cls(
            on=on if isinstance(on, bool) else default.on,
            brightness=_unit(data.get("brightness"), default.brightness),
            red=_unit(data.get("red"), default.red),
            green=_unit(data.get("green"), default.green),
            blue=_unit(data.get("blue"), default.blue),
        )


def apply_light_command(
    light: LightState,
    on: Optional[bool] = None,
    brightness: Optional[float] = None,
    rgb: Optional[tuple[float, float, float]] = None,
) -> LightState:
    """
    Change the light as Home Assistant asks.
    :param light: The light before.
    :param on: The new on/off state, None to keep it.
    :param brightness: The new brightness, None to keep it. Clamped to 0 to 1.
    :param rgb: The new color (red, green, blue), None to keep it. Clamped to 0 to 1.
    :return: The new light.
    """
    changes: dict[str, Any] = {}
    if on is not None:
        changes["on"] = on
    if brightness is not None:
        changes["brightness"] = _clamp(brightness)
    if rgb is not None:
        changes["red"], changes["green"], changes["blue"] = (_clamp(value) for value in rgb)
    return dataclasses.replace(light, **changes)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _unit(value: Any, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return _clamp(value)
