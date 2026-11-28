"""Drivers that open no hardware and only log what they would do, for ``--simulate-hardware``.

They let LPC run on a machine without the device, for development and the end-to-end tests. A simulated button is never pressed.
"""

from __future__ import annotations

import logging
from typing import Sequence

from ..appearance import Color

_LOGGER = logging.getLogger(__name__)


class SimulatedLedStrip:
    """
    LEDs that log every change of their colors at debug level.
    :param count: Number of LEDs.
    :param name: Name of the LEDs for the log.
    """

    def __init__(self, count: int, name: str) -> None:
        self._count = count
        self._name = name
        self._last: tuple[Color, ...] = ()
        _LOGGER.info("Simulated LEDs: %s LEDs (%s)", count, name)

    @property
    def count(self) -> int:
        """Number of LEDs."""
        return self._count

    def write(self, pixels: Sequence[Color]) -> None:
        """
        Log the colors when they differ from the last ones.
        :param pixels: One color per LED.
        """
        pixels = tuple(pixels)
        if pixels != self._last:
            self._last = pixels
            _LOGGER.debug("Simulated LEDs: %s", " ".join(f"#{p.red:02x}{p.green:02x}{p.blue:02x}" for p in pixels) or "off")

    def close(self) -> None:
        """Nothing to release."""


class SimulatedHardware:
    """
    Any other simulated hardware (a button, an output pin, a HID device).
    :param name: What it stands for, for the log.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        _LOGGER.info("Simulated %s", name)

    def write(self, report: Sequence[int]) -> None:
        """
        Log an output report.
        :param report: The report.
        """
        _LOGGER.debug("Simulated %s: write %s", self._name, bytes(report).hex(" "))

    def close(self) -> None:
        """Nothing to release."""
