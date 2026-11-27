"""Which display function the LEDs show.

Several things can be true at once (a timer counts down while the assistant is muted). The display follows a fixed order and shows
only the highest entry. The functions take the state and the time as parameters and decide nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Optional

from .lva_status import LvaStatus


class DisplayFunction(StrEnum):
    """The functions that show the state of the assistant on the LEDs."""

    NO_CONNECTION = "no_connection"
    TIMER_RINGING = "timer_ringing"
    WAKE_WORD = "wake_word"
    LISTENING = "listening"
    THINKING = "thinking"
    TTS = "tts"
    ANNOUNCE = "announce"
    PIPELINE_ERROR = "pipeline_error"
    TIMER_TIMEOUT = "timer_timeout"
    VOLUME = "volume"
    MUTED = "muted"
    TIMER_ACTIVE = "timer_active"


DEFAULT_TRANSIENT_SECONDS: Mapping[DisplayFunction, float] = {
    DisplayFunction.PIPELINE_ERROR: 1.5,
    DisplayFunction.TIMER_TIMEOUT: 3.0,
    DisplayFunction.VOLUME: 1.0,
}
_PIPELINE_FUNCTIONS = {
    "wake_word": DisplayFunction.WAKE_WORD,
    "listening": DisplayFunction.LISTENING,
    "speech_detected": DisplayFunction.LISTENING,
    "thinking": DisplayFunction.THINKING,
    "tts": DisplayFunction.TTS,
    "announce": DisplayFunction.ANNOUNCE,
}


@dataclass(frozen=True)
class TransientDisplay:
    """A function that is shown for a short time and then ends."""

    function: DisplayFunction
    ends_at: float


def start_transient(name: str, now: float, durations: Optional[Mapping[DisplayFunction, float]] = None) -> Optional[TransientDisplay]:
    """
    Start a function that is shown for a short time.
    :param name: Name of the function (``pipeline_error``, ``timer_timeout`` or ``volume``).
    :param now: The current time.
    :param durations: How long each of them is shown, in seconds. ``DEFAULT_TRANSIENT_SECONDS`` when None.
    :return: The running display, None if the name is not such a function.
    """
    durations = DEFAULT_TRANSIENT_SECONDS if durations is None else durations
    try:
        function = DisplayFunction(name)
    except ValueError:
        return None
    if function not in durations:
        return None
    return TransientDisplay(function, now + durations[function])


def select_display_function(status: LvaStatus, link_connected: bool, transient: Optional[TransientDisplay], now: float) -> Optional[DisplayFunction]:
    """
    Choose what the LEDs show.
    :param status: The status of LVA.
    :param link_connected: True while LPC is connected to LVA.
    :param transient: The function shown for a short time, None if there is none.
    :param now: The current time.
    :return: The function with the highest priority, None if the LEDs show the background (the light of Home Assistant).
    Order: no connection to LVA, ringing timer, no connection of LVA to Home Assistant, voice pipeline, short functions (error,
    timeout, volume), muted, counting timer. A timer rings also while LVA is not connected to Home Assistant, so it wins over that.
    A paused timer has no function.
    """
    if not link_connected:
        return DisplayFunction.NO_CONNECTION
    if status.timer_status == "ringing":
        return DisplayFunction.TIMER_RINGING
    if status.lva_status != "connected":
        return DisplayFunction.NO_CONNECTION
    if status.state in _PIPELINE_FUNCTIONS:
        return _PIPELINE_FUNCTIONS[status.state]
    if transient is not None and now < transient.ends_at:
        return transient.function
    if status.muted:
        return DisplayFunction.MUTED
    if status.timer_status == "active":
        return DisplayFunction.TIMER_ACTIVE
    return None
