"""Draws what is to be shown on the device, once when it changes and every frame while it moves.

What is drawn and how is the business of the device (``BaseDevice.draw()``). This module only keeps the current display state and
calls the device again on the event loop while ``is_animated()`` says so.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

from .animation import FRAME_INTERVAL_SECONDS, DisplayState
from .devices.base import BaseDevice


class LedOutput:
    """
    Keeps the LEDs of a device up to date.
    :param device: The device that draws.
    :param clock: Returns the current time in seconds.
    :param frame_interval: Seconds between two frames of a moving pattern.
    """

    def __init__(self, device: BaseDevice, clock: Callable[[], float] = time.monotonic, frame_interval: float = FRAME_INTERVAL_SECONDS) -> None:
        self._device = device
        self._clock = clock
        self._frame_interval = frame_interval
        self._display: Optional[DisplayState] = None
        self._next_frame: Optional[asyncio.TimerHandle] = None

    @property
    def display(self) -> Optional[DisplayState]:
        """What is shown now, None before the first ``show()``."""
        return self._display

    def show(self, display: DisplayState) -> None:
        """
        Show something else. Call it on the event loop.
        :param display: What is to be shown.
        """
        self._display = display
        self._draw()

    def close(self) -> None:
        """Stop drawing frames."""
        if self._next_frame is not None:
            self._next_frame.cancel()
            self._next_frame = None

    def _draw(self) -> None:
        self.close()
        if self._display is None:
            return
        self._device.draw(self._display, self._clock())
        if self._device.is_animated(self._display):
            self._next_frame = asyncio.get_running_loop().call_later(self._frame_interval, self._draw)
