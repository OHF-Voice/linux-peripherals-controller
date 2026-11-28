"""ReSpeaker 2-Mics Pi HAT v1 (WM8960 codec): 3 APA102 LEDs and one button.

Checked against Seeed's wiki and its driver ``respeaker/mic_hat`` (``interfaces/apa102.py``, ``interfaces/pixels.py``): three
APA102 LEDs on SPI0, the user button on GPIO 17 to ground. APA102 LEDs do not use the chip select, so ``/dev/spidev0.0`` works as
well as Seeed's default ``/dev/spidev0.1``. The base device does everything this board needs.
"""

from __future__ import annotations

from ..button_roles import ButtonRole
from ..device_types import ButtonSpec, DeviceType, LedSpec
from .base import BaseDevice

DEVICE_TYPE = DeviceType(
    name="respeaker_2mic_v1",
    description="ReSpeaker 2-Mic Pi HAT v1 with WM8960 codec: 3 APA102 LEDs on SPI0 and one button on GPIO 17",
    leds=LedSpec("apa102", 3, {"spi_bus": 0, "spi_device": 0, "spi_speed_hz": 8_000_000}),
    buttons=(ButtonSpec("button", ButtonRole.ACTION, pin=17),),
)


class Device(BaseDevice):
    """The ReSpeaker 2-Mics Pi HAT v1: LEDs and button as in the base device."""
