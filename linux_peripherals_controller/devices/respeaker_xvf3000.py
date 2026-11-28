"""ReSpeaker USB Mic Array v2.0 with the XMOS XVF3000: a ring of 12 LEDs set over USB, no button.

Checked against Seeed's ``pixel_ring`` (``usb_pixel_ring_v2.py``) and the README of ``respeaker/usb_4_mic_array`` (12 RGB LEDs,
no button listed). The LEDs are written by the ``usb_pixel_ring`` driver. The base device does everything else.
"""

from __future__ import annotations

from ..device_types import DeviceType, LedSpec
from .base import BaseDevice

DEVICE_TYPE = DeviceType(
    name="respeaker_xvf3000",
    description="ReSpeaker USB Mic Array v2.0 with XMOS XVF3000 (USB 2886:0018): 12 LEDs set over USB, no button",
    leds=LedSpec("usb_pixel_ring", 12),
)


class Device(BaseDevice):
    """The ReSpeaker USB Mic Array v2.0 (XVF3000): LEDs as in the base device."""
