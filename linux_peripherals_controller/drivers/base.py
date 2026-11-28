"""What every driver has in common: the error it raises and the shape of an LED strip.

A driver opens one kind of hardware and does nothing else: it writes what it is given and reports what it reads. What is shown or
what a press means is decided elsewhere.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from ..appearance import Color


class DriverError(RuntimeError):
    """The hardware cannot be opened or used. The message names the hardware."""


class LedStrip(Protocol):
    """LEDs that are set all at once, one color per LED."""

    @property
    def count(self) -> int:
        """Number of LEDs."""

    def write(self, pixels: Sequence[Color]) -> None:
        """
        Show the colors.
        :param pixels: One color per LED, in the order of the LEDs. Missing ones are dark.
        """

    def close(self) -> None:
        """Turn the LEDs off and release the hardware."""


class Closable(Protocol):
    """Hardware that only has to be released at the end."""

    def close(self) -> None:
        """Release the hardware."""


class HidWriter(Protocol):
    """A HID device that output reports can be written to."""

    def write(self, report: Sequence[int]) -> None:
        """
        Send an output report.
        :param report: The report, its id first.
        """

    def close(self) -> None:
        """Release the device."""
