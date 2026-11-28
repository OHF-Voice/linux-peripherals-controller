"""ReSpeaker 2-Mics Pi HAT v2.0 (TLV320AIC3x codec): 3 APA102 LEDs and one button, like v1.

LVA has no example for this board. Seeed's wiki for v2.0 names the same user button on GPIO 17 and APA102 LEDs on SPI ("each
on-board APA102 LED has an additional driver chip"), and says the layout of v1 and v2 "remains basically the same". Only the audio
codec differs, which is not LPC's business. The LED count of 3 is taken from v1, the v2.0 page does not name it.
"""

from __future__ import annotations

import dataclasses

from .base import BaseDevice
from .respeaker_2mic_v1 import DEVICE_TYPE as V1_DEVICE_TYPE

DEVICE_TYPE = dataclasses.replace(
    V1_DEVICE_TYPE,
    name="respeaker_2mic_v2",
    description="ReSpeaker 2-Mic Pi HAT v2.0 with TLV320AIC3x codec: 3 APA102 LEDs on SPI0 and one button on GPIO 17",
)


class Device(BaseDevice):
    """The ReSpeaker 2-Mics Pi HAT v2.0: LEDs and button as in the base device."""
