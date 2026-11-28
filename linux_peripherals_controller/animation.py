"""What the LEDs show at a moment: the scene of a display function and the colors of every LED.

A scene is the pattern, color, brightness and amount of what is shown. ``render()`` turns it into one color per LED for a point in
time, so a pattern moves when it is rendered again later. The functions only compute, the LEDs are written by the device.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from .appearance import Color, PatternName
from .display import DisplayFunction
from .light import LightState
from .lva_status import LvaStatus

FRAME_INTERVAL_SECONDS = 1 / 30
PULSE_PERIOD_SECONDS = 2.0
PULSE_MIN_LEVEL = 0.15
SPIN_SECONDS_PER_TURN = 1.0
BLINK_PERIOD_SECONDS = 0.5
_SPIN_TAIL = (1.0, 0.4, 0.1)
_DARK = Color(0, 0, 0)


@dataclass(frozen=True)
class Scene:
    """
    What the LEDs show.
    :param pattern: How the LEDs move.
    :param color: The color at full brightness.
    :param brightness: 0 to 1.
    :param amount: 0 to 1 for the ``progress`` pattern (time left, volume), None for a full ring.
    :param started_at: When the scene started, the time patterns are counted from.
    """

    pattern: PatternName
    color: Color
    brightness: float
    amount: Optional[float] = None
    started_at: float = 0.0


@dataclass(frozen=True)
class DisplayState:
    """
    Everything a device needs to show: the display function, its amount and the light of Home Assistant as the background.
    :param function: The display function, None for the background.
    :param amount: 0 to 1 for the functions that show an amount, else None.
    :param light: The light of Home Assistant.
    :param started_at: When the display function started.
    """

    function: Optional[DisplayFunction]
    amount: Optional[float]
    light: LightState
    started_at: float = 0.0


def display_amount(function: Optional[DisplayFunction], status: LvaStatus) -> Optional[float]:
    """
    The amount a display function shows.
    :param function: The display function.
    :param status: The status of LVA.
    :return: The time left in percent of the timer for ``timer_active``, the volume for ``volume`` (both as 0 to 1), else None.
    """
    if function == DisplayFunction.TIMER_ACTIVE and status.timer_remaining_percentage is not None:
        return _clamp(status.timer_remaining_percentage / 100)
    if function == DisplayFunction.VOLUME and status.volume is not None:
        return _clamp(status.volume / 100)
    return None


def scene_for(
    display: DisplayState,
    colors: Mapping[DisplayFunction, Color],
    patterns: Mapping[DisplayFunction, PatternName],
    brightness: float,
) -> Optional[Scene]:
    """
    Choose the scene for what is to be shown.
    :param display: What is to be shown.
    :param colors: The color of every display function the device offers.
    :param patterns: The pattern of every display function the device offers.
    :param brightness: Brightness of the display functions (from the device configuration).
    :return: The scene of the display function. For the background, or a function the device does not offer, the light of Home
    Assistant (solid), None if it is off.
    """
    function = display.function
    if function is not None and function in colors and function in patterns:
        return Scene(patterns[function], colors[function], brightness, display.amount, display.started_at)
    if display.light.on:
        return Scene(PatternName.SOLID, display.light.color, display.light.brightness)
    return None


def is_animated(scene: Optional[Scene]) -> bool:
    """True if the scene changes over time and has to be rendered again and again."""
    return scene is not None and scene.pattern in (PatternName.PULSE, PatternName.SPIN, PatternName.BLINK)


def render(scene: Optional[Scene], count: int, now: float) -> Tuple[Color, ...]:
    """
    The colors of the LEDs.
    :param scene: What is shown, None for dark LEDs.
    :param count: Number of LEDs.
    :param now: The current time, in the clock of ``Scene.started_at``.
    :return: One color per LED.

    ``solid`` lights every LED, ``pulse`` breathes between 15 % and full brightness every 2 s, ``blink`` is on and off for 0.25 s
    each, ``spin`` runs one LED with a short tail around once a second, ``progress`` lights the share ``amount`` of the LEDs (the
    last one partly).
    """
    if scene is None or count <= 0:
        return (_DARK,) * max(count, 0)
    elapsed = max(0.0, now - scene.started_at)
    levels = _levels(scene, count, elapsed)
    return tuple(_scale(scene.color, scene.brightness * level) for level in levels)


def _levels(scene: Scene, count: int, elapsed: float) -> Tuple[float, ...]:
    if scene.pattern == PatternName.PULSE:
        wave = 0.5 - 0.5 * math.cos(2 * math.pi * elapsed / PULSE_PERIOD_SECONDS)
        return (PULSE_MIN_LEVEL + (1 - PULSE_MIN_LEVEL) * wave,) * count
    if scene.pattern == PatternName.BLINK:
        on = (elapsed % BLINK_PERIOD_SECONDS) < BLINK_PERIOD_SECONDS / 2
        return (1.0 if on else 0.0,) * count
    if scene.pattern == PatternName.SPIN:
        head = int(elapsed * count / SPIN_SECONDS_PER_TURN) % count
        levels = [0.0] * count
        for offset, level in enumerate(_SPIN_TAIL[: max(1, count - 1)]):
            levels[(head - offset) % count] = level
        return tuple(levels)
    if scene.pattern == PatternName.PROGRESS:
        lit = count * (1.0 if scene.amount is None else _clamp(scene.amount))
        return tuple(_clamp(lit - index) for index in range(count))
    return (1.0,) * count


def _scale(color: Color, factor: float) -> Color:
    factor = _clamp(factor)
    return Color(round(color.red * factor), round(color.green * factor), round(color.blue * factor))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
