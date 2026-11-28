"""The 12 LEDs of the ReSpeaker USB Mic Array v2.0 (XMOS XVF3000), set over USB.

The protocol is the one of Seeed's ``pixel_ring`` (``usb_pixel_ring_v2.py``): vendor control transfers to the device with
request 0, the command as value and index 0x1C. Command 6 sets every LED to its own color (red, green, blue, 0 per LED), command
0x20 sets the brightness of the ring (0 to 31). The kernel audio driver does not have to be detached for it.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from ..appearance import Color
from .base import DriverError

_LOGGER = logging.getLogger(__name__)

VENDOR_ID = 0x2886
PRODUCT_ID = 0x0018
_REQUEST_TYPE_VENDOR_OUT = 0x40
_REQUEST = 0
_INDEX = 0x1C
_COMMAND_SHOW = 6
_COMMAND_BRIGHTNESS = 0x20
_MAX_BRIGHTNESS = 0x1F
_TIMEOUT_MS = 1000


def pixel_ring_payload(pixels: Sequence[Color], count: int) -> bytes:
    """
    The data of the command that shows the colors.
    :param pixels: One color per LED. Missing ones are dark, extra ones are left out.
    :param count: Number of LEDs of the ring.
    """
    payload = bytearray()
    for index in range(count):
        color = pixels[index] if index < len(pixels) else Color(0, 0, 0)
        payload += bytes((color.red, color.green, color.blue, 0))
    return bytes(payload)


class UsbPixelRing:
    """
    The LED ring of the ReSpeaker USB Mic Array v2.0.
    :param count: Number of LEDs.
    :raises DriverError: If the device is not connected or pyusb is not installed.
    """

    def __init__(self, count: int = 12) -> None:
        self._count = count
        try:
            import usb.core  # type: ignore
        except ImportError as exc:
            raise DriverError("ReSpeaker USB Mic Array: the Python package pyusb is not installed") from exc
        self._usb_error: type[Exception] = usb.core.USBError
        try:
            self._device: Any = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
        except (usb.core.NoBackendError, self._usb_error) as exc:
            raise DriverError(f"ReSpeaker USB Mic Array: USB cannot be used (is libusb installed?): {exc}") from exc
        if self._device is None:
            raise DriverError(f"ReSpeaker USB Mic Array (USB {VENDOR_ID:04x}:{PRODUCT_ID:04x}) not found: is it connected and may LPC use it?")
        self._send(_COMMAND_BRIGHTNESS, bytes((_MAX_BRIGHTNESS,)))
        _LOGGER.info("ReSpeaker USB Mic Array opened: %s LEDs", count)

    @property
    def count(self) -> int:
        """Number of LEDs."""
        return self._count

    def write(self, pixels: Sequence[Color]) -> None:
        """
        Show the colors.
        :param pixels: One color per LED.
        """
        self._send(_COMMAND_SHOW, pixel_ring_payload(pixels, self._count))

    def close(self) -> None:
        """Turn the LEDs off."""
        self.write(())

    def _send(self, command: int, data: bytes) -> None:
        try:
            self._device.ctrl_transfer(_REQUEST_TYPE_VENDOR_OUT, _REQUEST, command, _INDEX, data, _TIMEOUT_MS)
        except self._usb_error as exc:
            _LOGGER.warning("Cannot write to the ReSpeaker USB Mic Array (command %#x): %s", command, exc)
