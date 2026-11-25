"""Press types of a button: single, double, triple and long, and the repeat while it is held.

A driver only knows when a button goes down and up. The press type follows from the timing, like on the Home Assistant Voice PE
center button: a press counts as single, double or triple when no further press follows within a short gap, and as long when the
button is held for a while. The functions take the state and the time as parameters and return the new state and the presses that
are complete now. They start no timers: ``next_deadline()`` tells when ``tick()`` has to be called.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

LONG_PRESS_SECONDS = 1.0
MULTI_PRESS_GAP_SECONDS = 0.25
REPEAT_AFTER_SECONDS = 0.5
REPEAT_INTERVAL_SECONDS = 0.25
_MAX_COUNTED_PRESSES = 3
_PRESS_BY_COUNT = {1: "single", 2: "double", 3: "triple"}


@dataclass(frozen=True)
class DetectionConfig:
    """
    How the presses of one button are told apart.
    :param long_after: Seconds the button has to be held for a long press.
    :param gap: Seconds without another press after which single, double and triple presses are complete.
    :param repeat_after: Seconds of holding after which ``repeat`` presses start, None if holding does not repeat. A button that
    repeats has no long press.
    :param repeat_interval: Seconds between two ``repeat`` presses.
    """

    long_after: float = LONG_PRESS_SECONDS
    gap: float = MULTI_PRESS_GAP_SECONDS
    repeat_after: Optional[float] = None
    repeat_interval: float = REPEAT_INTERVAL_SECONDS


@dataclass(frozen=True)
class ButtonState:
    """What is known about one button between two calls."""

    down_since: Optional[float] = None
    presses: int = 0
    last_release: Optional[float] = None
    hold_reported: bool = False
    next_repeat: Optional[float] = None


Presses = Tuple[str, ...]


def press(state: ButtonState, now: float, config: DetectionConfig) -> Tuple[ButtonState, Presses]:
    """
    The button went down.
    :param state: The state before.
    :param now: The current time in seconds.
    :param config: How the presses are told apart.
    :return: The new state and the presses that are complete now: an earlier press whose gap has passed without a tick.
    """
    if state.down_since is not None:
        return state, ()
    state, completed = tick(state, now, config)
    return ButtonState(down_since=now, presses=state.presses, last_release=state.last_release), completed


def release(state: ButtonState, now: float) -> ButtonState:
    """
    The button went up.
    :param state: The state before.
    :param now: The current time in seconds.
    :return: The new state. Releasing a button that was held for a long press or repeat starts nothing new.
    """
    if state.down_since is None:
        return state
    if state.hold_reported:
        return ButtonState()
    return ButtonState(presses=min(state.presses + 1, _MAX_COUNTED_PRESSES), last_release=now)


def tick(state: ButtonState, now: float, config: DetectionConfig) -> Tuple[ButtonState, Presses]:
    """
    Time has passed. Call it at the time ``next_deadline()`` gave, and before the next ``press()`` or ``release()``.
    :param state: The state before.
    :param now: The current time in seconds.
    :param config: How the presses are told apart.
    :return: The new state and the presses that are complete now: ``single``, ``double`` or ``triple``, ``long``, or ``repeat``.
    """
    if state.down_since is not None:
        return _tick_held(state, now, config)
    if state.presses > 0 and state.last_release is not None and now - state.last_release >= config.gap:
        return ButtonState(), (_PRESS_BY_COUNT[state.presses],)
    return state, ()


def next_deadline(state: ButtonState, config: DetectionConfig) -> Optional[float]:
    """
    When ``tick()`` has to be called next.
    :param state: The current state.
    :param config: How the presses are told apart.
    :return: The time in seconds, None if nothing is waiting.
    """
    if state.down_since is not None:
        if not state.hold_reported:
            return state.down_since + (config.long_after if config.repeat_after is None else config.repeat_after)
        return state.next_repeat
    if state.presses > 0 and state.last_release is not None:
        return state.last_release + config.gap
    return None


def _tick_held(state: ButtonState, now: float, config: DetectionConfig) -> Tuple[ButtonState, Presses]:
    assert state.down_since is not None
    held = now - state.down_since
    if not state.hold_reported:
        if config.repeat_after is not None and held >= config.repeat_after:
            return ButtonState(down_since=state.down_since, hold_reported=True, next_repeat=now + config.repeat_interval), ("repeat",)
        if config.repeat_after is None and held >= config.long_after:
            return ButtonState(down_since=state.down_since, hold_reported=True), ("long",)
        return state, ()
    if state.next_repeat is not None and now >= state.next_repeat:
        return ButtonState(down_since=state.down_since, hold_reported=True, next_repeat=now + config.repeat_interval), ("repeat",)
    return state, ()
