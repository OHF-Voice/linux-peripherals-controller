"""Drivers that open no hardware and only log what they would do, for ``--simulate-hardware``.

They let LPC run on a machine without the device, for development and the end-to-end tests. A simulated button is never pressed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Mapping, Optional, Sequence

from ..appearance import Color

if TYPE_CHECKING:
    from .satellite1 import PowerContract

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


class SimulatedSatellite1(SimulatedLedStrip):
    """The Satellite1 HAT without ``satellite1d``: a simulated LED ring, nothing can be read and no setting changes."""

    def __init__(self) -> None:
        super().__init__(24, "Satellite1 LED ring")

    def read_environment(self) -> Mapping[str, Optional[float]]:
        """Nothing can be read."""
        return {}

    def mic_muted(self) -> Optional[bool]:
        """Nothing can be read."""
        return None

    def line_out_plugged_in(self) -> Optional[bool]:
        """Nothing can be read."""
        return None

    def amp_level(self) -> Optional[int]:
        """Nothing can be read."""
        return None

    def set_amp_level(self, level: int) -> Optional[int]:
        """
        Log the level, nothing changes.
        :param level: The level.
        :return: None, the level cannot be read.
        """
        _LOGGER.debug("Simulated Satellite1: amplifier level %s", level)
        return self.amp_level()

    def power_contract(self) -> Optional["PowerContract"]:
        """Nothing can be read."""
        return None

    def firmware(self) -> Optional[str]:
        """Nothing can be read."""
        return None
