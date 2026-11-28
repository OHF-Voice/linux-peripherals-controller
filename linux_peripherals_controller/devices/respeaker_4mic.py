"""ReSpeaker 4-Mic Array HAT: a ring of 12 APA102 LEDs, no button.

Checked against Seeed's driver ``respeaker/4mics_hat`` (``interfaces/pixels.py``): 12 LEDs, and GPIO 5 has to be driven high to
power them (``self.power = LED(5)``, ``self.power.on()``). The LVA example uses ``/dev/spidev0.1``, which is kept. The board has
no button of its own.
"""

from __future__ import annotations

from ..device_types import DeviceType, LedSpec
from .base import BaseDevice, ButtonCallback, HardwareMuteCallback

LED_POWER_PIN = 5

DEVICE_TYPE = DeviceType(
    name="respeaker_4mic",
    description="ReSpeaker 4-Mic Array HAT with AC108 codec: 12 APA102 LEDs on SPI0 (powered by GPIO 5), no button",
    leds=LedSpec("apa102", 12, {"spi_bus": 0, "spi_device": 1, "spi_speed_hz": 8_000_000}),
)


class Device(BaseDevice):
    """The ReSpeaker 4-Mic Array HAT: powers its LEDs before they are opened."""

    def open(self, on_button: ButtonCallback, on_hardware_mute: HardwareMuteCallback) -> None:
        """
        Power the LEDs, then open them.
        :param on_button: Called with the name of a button and whether it went down.
        :param on_hardware_mute: Called whenever the hardware mute changes.
        """
        self.keep(self.drivers.gpio_output(LED_POWER_PIN, True))
        super().open(on_button, on_hardware_mute)
