"""Turns the buttons going down and up into presses (single, double, triple, long, repeat).

The timing is decided by ``press_detection.py``. This module only keeps the state of every button and calls ``tick()`` on the
event loop at the time ``next_deadline()`` names.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Mapping, Optional

from .press_detection import ButtonState, DetectionConfig, Presses, next_deadline, press, release, tick

_LOGGER = logging.getLogger(__name__)


class ButtonInput:
    """
    The presses of the buttons of a device.
    :param buttons: How the presses are told apart, per button name.
    :param on_press: Called with the button name and the press type for every complete press.
    :param clock: Returns the current time in seconds, the clock of the event loop by default.
    """

    def __init__(self, buttons: Mapping[str, DetectionConfig], on_press: Callable[[str, str], None], clock: Optional[Callable[[], float]] = None) -> None:
        self._configs = dict(buttons)
        self._on_press = on_press
        self._clock = clock or time.monotonic
        self._states = {name: ButtonState() for name in self._configs}
        self._ticks: dict[str, asyncio.TimerHandle] = {}

    def change(self, name: str, down: bool) -> None:
        """
        A button went down or up. Call it on the event loop.
        :param name: Name of the button. Unknown names are ignored.
        :param down: True when it went down, False when it went up.
        """
        config = self._configs.get(name)
        if config is None:
            _LOGGER.debug("Ignoring button '%s': the device type has no such button", name)
            return
        now = self._clock()
        presses: Presses = ()
        if down:
            self._states[name], presses = press(self._states[name], now, config)
        else:
            self._states[name] = release(self._states[name], now)
        self._report(name, presses)
        self._schedule(name)

    def close(self) -> None:
        """Stop the pending ticks."""
        for handle in self._ticks.values():
            handle.cancel()
        self._ticks.clear()

    def _tick(self, name: str) -> None:
        self._ticks.pop(name, None)
        self._states[name], presses = tick(self._states[name], self._clock(), self._configs[name])
        self._report(name, presses)
        self._schedule(name)

    def _report(self, name: str, presses: Presses) -> None:
        for press_type in presses:
            _LOGGER.debug("Button '%s': %s press", name, press_type)
            self._on_press(name, press_type)

    def _schedule(self, name: str) -> None:
        if (handle := self._ticks.pop(name, None)) is not None:
            handle.cancel()
        deadline = next_deadline(self._states[name], self._configs[name])
        if deadline is not None:
            delay = max(0.0, deadline - self._clock())
            self._ticks[name] = asyncio.get_running_loop().call_later(delay, self._tick, name)
