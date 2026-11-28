"""APA102 LEDs on an SPI bus, as on the ReSpeaker 2mic and 4mic HATs.

The frame follows the driver of Seeed (``interfaces/apa102.py`` in ``respeaker/mic_hat``): four zero bytes, then per LED
``0xE0 | brightness``, blue, green, red, then 0xFF bytes so the last LEDs take their data. The colors are already scaled, so the
5 bit brightness of every LED stays at its maximum. The SPI bus runs in mode 1, as in the ReSpeaker 2mic example of LVA (Seeed's
driver leaves the default mode 0).
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from ..appearance import Color
from .base import DriverError

_LOGGER = logging.getLogger(__name__)

_START_FRAME = bytes(4)
_LED_START = 0xE0
_MAX_BRIGHTNESS = 0x1F
_SPI_MODE = 0b01


def apa102_frame(pixels: Sequence[Color], count: int) -> bytes:
    """
    The bytes that show the colors on a strip of APA102 LEDs.
    :param pixels: One color per LED. Missing ones are dark, extra ones are left out.
    :param count: Number of LEDs on the strip.
    """
    frame = bytearray(_START_FRAME)
    for index in range(count):
        color = pixels[index] if index < len(pixels) else Color(0, 0, 0)
        frame += bytes((_LED_START | _MAX_BRIGHTNESS, color.blue, color.green, color.red))
    # At least half a clock per LED is needed after the data; Seeed sends four bytes, enough for 64 LEDs.
    frame += b"\xff" * max(4, (count + 15) // 16)
    return bytes(frame)


class Apa102Strip:
    """
    APA102 LEDs on ``/dev/spidev<bus>.<device>``.
    :param count: Number of LEDs.
    :param spi_bus: SPI bus.
    :param spi_device: Chip select of the SPI bus. APA102 LEDs do not use it, but the device node must exist.
    :param spi_speed_hz: Clock of the SPI bus.
    :raises DriverError: If the SPI device cannot be opened.
    """

    def __init__(self, count: int, spi_bus: int = 0, spi_device: int = 0, spi_speed_hz: int = 8_000_000) -> None:
        self._count = count
        self._name = f"/dev/spidev{spi_bus}.{spi_device}"
        try:
            import spidev  # type: ignore
        except ImportError as exc:
            raise DriverError(f"APA102 LEDs on {self._name}: the Python package spidev is not installed") from exc
        self._spi: Any = spidev.SpiDev()
        try:
            self._spi.open(spi_bus, spi_device)
            self._spi.max_speed_hz = spi_speed_hz
            self._spi.mode = _SPI_MODE
        except OSError as exc:
            raise DriverError(f"APA102 LEDs on {self._name} cannot be opened (is SPI enabled with dtparam=spi=on?): {exc}") from exc
        _LOGGER.info("APA102 LEDs opened: %s LEDs on %s at %s Hz", count, self._name, spi_speed_hz)

    @property
    def count(self) -> int:
        """Number of LEDs."""
        return self._count

    def write(self, pixels: Sequence[Color]) -> None:
        """
        Show the colors.
        :param pixels: One color per LED.
        """
        try:
            self._spi.xfer2(list(apa102_frame(pixels, self._count)))
        except OSError as exc:
            _LOGGER.warning("Cannot write to the APA102 LEDs on %s: %s", self._name, exc)

    def close(self) -> None:
        """Turn the LEDs off and release the SPI device."""
        self.write(())
        self._spi.close()
