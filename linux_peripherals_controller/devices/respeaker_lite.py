"""ReSpeaker Lite (XMOS XU316) on USB: its RGB LED and its user button, wired to the GPIO header of the Raspberry Pi.

Checked against Seeed's wiki (``respeaker_rgb_test``, ``respeaker_button``) and the repository ``respeaker/ReSpeaker_Lite``:
the board has one WS2812 LED, driven by GPIO1 of the XIAO ESP32S3 (pin D0 of the XIAO header), and the USB firmware (v2.0.6
and newer) lets go of it after boot. The user button is wired to the XU316, which does nothing with it, and Seeed's examples
solder it to a free pin of the XIAO header and read it pulled up, low when pressed. Over USB the host can reach neither of
them, so they are wired to the Raspberry Pi instead: the LED to MOSI of SPI0 (GPIO 10), the button to GPIO 17. The mute button
stays with the XU316 (it mutes the microphones and lights the red mute LED); its state cannot be read over USB, so the device
has no hardware mute. The base device does everything else.
"""

from __future__ import annotations

from ..button_roles import ButtonRole
from ..device_types import ButtonSpec, DeviceType, LedSpec
from .base import BaseDevice

DEVICE_TYPE = DeviceType(
    name="respeaker_lite",
    description="ReSpeaker Lite with XMOS XU316 on USB: 1 WS2812 LED wired to SPI0 MOSI (GPIO 10) and the user button wired to GPIO 17",
    leds=LedSpec("ws2812", 1, {"spi_bus": 0, "spi_device": 0}),
    buttons=(ButtonSpec("user", ButtonRole.ACTION, pin=17),),
)


class Device(BaseDevice):
    """The ReSpeaker Lite: LED and button as in the base device, once they are wired to the Raspberry Pi."""
