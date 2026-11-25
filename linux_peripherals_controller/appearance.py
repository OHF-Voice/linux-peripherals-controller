"""Colors and patterns of the display functions.

Both are predefined for every display function. A device type or the device configuration can replace them, see ``device_setup``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from .display import DisplayFunction

_HEX_COLOR = re.compile(r"^#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$")


@dataclass(frozen=True)
class Color:
    """A color with each channel from 0 to 255."""

    red: int
    green: int
    blue: int

    @classmethod
    def from_hex(cls, text: str) -> "Color":
        """
        Read a color like ``#ff8000``.
        :param text: The color, a ``#`` and six hexadecimal digits.
        :raises ValueError: If the text is not such a color.
        """
        match = _HEX_COLOR.match(text)
        if match is None:
            raise ValueError(f"'{text}' is not a color, expected # and six hexadecimal digits like #ff8000")
        return cls(*(int(group, 16) for group in match.groups()))


class PatternName(StrEnum):
    """How the LEDs move."""

    SOLID = "solid"
    PULSE = "pulse"
    SPIN = "spin"
    PROGRESS = "progress"
    BLINK = "blink"


DEFAULT_COLORS: Mapping[DisplayFunction, Color] = {
    DisplayFunction.NO_CONNECTION: Color(255, 0, 0),
    DisplayFunction.TIMER_RINGING: Color(0, 0, 255),
    DisplayFunction.WAKE_WORD: Color(255, 255, 255),
    DisplayFunction.LISTENING: Color(0, 128, 255),
    DisplayFunction.THINKING: Color(255, 200, 0),
    DisplayFunction.TTS: Color(0, 255, 0),
    DisplayFunction.ANNOUNCE: Color(0, 255, 128),
    DisplayFunction.PIPELINE_ERROR: Color(255, 0, 0),
    DisplayFunction.TIMER_TIMEOUT: Color(255, 128, 0),
    DisplayFunction.VOLUME: Color(255, 255, 255),
    DisplayFunction.MUTED: Color(255, 0, 0),
    DisplayFunction.TIMER_ACTIVE: Color(0, 255, 255),
}
DEFAULT_PATTERNS: Mapping[DisplayFunction, PatternName] = {
    DisplayFunction.NO_CONNECTION: PatternName.PULSE,
    DisplayFunction.TIMER_RINGING: PatternName.BLINK,
    DisplayFunction.WAKE_WORD: PatternName.BLINK,
    DisplayFunction.LISTENING: PatternName.SPIN,
    DisplayFunction.THINKING: PatternName.PULSE,
    DisplayFunction.TTS: PatternName.PULSE,
    DisplayFunction.ANNOUNCE: PatternName.PULSE,
    DisplayFunction.PIPELINE_ERROR: PatternName.BLINK,
    DisplayFunction.TIMER_TIMEOUT: PatternName.BLINK,
    DisplayFunction.VOLUME: PatternName.PROGRESS,
    DisplayFunction.MUTED: PatternName.SOLID,
    DisplayFunction.TIMER_ACTIVE: PatternName.PROGRESS,
}
