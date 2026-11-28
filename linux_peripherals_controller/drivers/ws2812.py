"""WS2812 LEDs (NeoPixel) on the MOSI line of an SPI bus, as the RGB LED of the ReSpeaker Lite.

A WS2812 has no clock line, it reads its bits from the length of the high pulse. With the SPI bus at 2.4 MHz, one SPI bit lasts
about 417 ns, so three SPI bits make one WS2812 bit: ``110`` is a 1 (833 ns high), ``100`` is a 0 (417 ns high). The colors go
out in the order green, red, blue, most significant bit first. A low phase before and after the data resets the LEDs, so
they take the new colors. Only MOSI is used, the clock and chip select lines of the bus stay unconnected.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from ..appearance import Color
from .base import DriverError

_LOGGER = logging.getLogger(__name__)

SPI_SPEED_HZ = 2_400_000
_SPI_MODE = 0b00
_ONE = 0b110
_ZERO = 0b100
# 100 zero bytes at 2.4 MHz keep the line low for 333 µs, longer than the 280 µs a WS2812B needs to reset.
_RESET = bytes(100)


def ws2812_payload(pixels: Sequence[Color], count: int) -> bytes:
    """
    The SPI bytes that show the colors on a chain of WS2812 LEDs.
    :param pixels: One color per LED. Missing ones are dark, extra ones are left out.
    :param count: Number of LEDs in the chain.
    """
    payload = bytearray(_RESET)
    for index in range(count):
        color = pixels[index] if index < len(pixels) else Color(0, 0, 0)
        for value in (color.green, color.red, color.blue):
            payload += _encode_byte(value)
    payload += _RESET
    return bytes(payload)


class Ws2812Strip:
    """
    WS2812 LEDs on the MOSI line of ``/dev/spidev<bus>.<device>``.
    :param count: Number of LEDs.
    :param spi_bus: SPI bus. Bus 0 has MOSI on GPIO 10 of the Raspberry Pi.
    :param spi_device: Chip select of the SPI bus. WS2812 LEDs do not use it, but the device node must exist.
    :raises DriverError: If the SPI device cannot be opened.
    """

    def __init__(self, count: int, spi_bus: int = 0, spi_device: int = 0) -> None:
        self._count = count
        self._name = f"/dev/spidev{spi_bus}.{spi_device}"
        try:
            import spidev  # type: ignore
        except ImportError as exc:
            raise DriverError(f"WS2812 LEDs on {self._name}: the Python package spidev is not installed") from exc
        self._spi: Any = spidev.SpiDev()
        try:
            self._spi.open(spi_bus, spi_device)
            self._spi.max_speed_hz = SPI_SPEED_HZ
            self._spi.mode = _SPI_MODE
        except OSError as exc:
            raise DriverError(f"WS2812 LEDs on {self._name} cannot be opened (is SPI enabled with dtparam=spi=on?): {exc}") from exc
        _LOGGER.info("WS2812 LEDs opened: %s LEDs on %s at %s Hz", count, self._name, SPI_SPEED_HZ)

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
            self._spi.xfer2(list(ws2812_payload(pixels, self._count)))
        except OSError as exc:
            _LOGGER.warning("Cannot write to the WS2812 LEDs on %s: %s", self._name, exc)

    def close(self) -> None:
        """Turn the LEDs off and release the SPI device."""
        self.write(())
        self._spi.close()


def _encode_byte(value: int) -> bytes:
    bits = 0
    for position in range(7, -1, -1):
        bits = (bits << 3) | (_ONE if value >> position & 1 else _ZERO)
    return bits.to_bytes(3, "big")
