"""The hardware drivers: thin layers that open the hardware, write to it and report what they read.

``Drivers`` opens them for a device file. With ``simulated`` it hands out drivers that open nothing and only log, so LPC runs
without the device (``--simulate-hardware``). A device file only asks ``Drivers``, so it works the same in both cases.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from ..device_types import LedSpec
from .base import Closable, DriverError, HidWriter, LedStrip
from .simulated import SimulatedHardware, SimulatedLedStrip, SimulatedSatellite1

if TYPE_CHECKING:
    from .satellite1 import Satellite1Event, Satellite1Link

__all__ = ["Closable", "DriverError", "Drivers", "HidWriter", "LedStrip"]


class Drivers:
    """
    Opens the drivers for a device.
    :param simulated: True to open no hardware and only log what the drivers would do.
    """

    def __init__(self, simulated: bool = False) -> None:
        self.simulated = simulated

    def led_strip(self, spec: LedSpec) -> LedStrip:
        """
        Open the LEDs of a device type.
        :param spec: The LEDs. ``driver`` is ``apa102`` (options ``spi_bus``, ``spi_device``, ``spi_speed_hz``), ``ws2812`` (options ``spi_bus``,
            ``spi_device``) or ``usb_pixel_ring``.
        :raises DriverError: If the LEDs cannot be opened or the driver is not known.
        """
        if self.simulated:
            return SimulatedLedStrip(spec.count, spec.driver)
        if spec.driver == "apa102":
            from .apa102 import Apa102Strip

            return Apa102Strip(spec.count, **spec.options)
        if spec.driver == "ws2812":
            from .ws2812 import Ws2812Strip

            return Ws2812Strip(spec.count, **spec.options)
        if spec.driver == "usb_pixel_ring":
            from .usb_pixel_ring import UsbPixelRing

            return UsbPixelRing(spec.count)
        raise DriverError(f"Unknown LED driver '{spec.driver}'")

    def gpio_input(self, pin: int, on_change: Callable[[bool], None]) -> Closable:
        """
        Open a button on a GPIO pin.
        :param pin: BCM number of the pin.
        :param on_change: Called on the event loop with True when the button goes down and False when it goes up.
        :raises DriverError: If the pin cannot be used.
        """
        if self.simulated:
            return SimulatedHardware(f"button on GPIO {pin}")
        from .gpio import GpioInput

        return GpioInput(pin, on_change)

    def gpio_output(self, pin: int, active: bool) -> Closable:
        """
        Drive a GPIO pin.
        :param pin: BCM number of the pin.
        :param active: True for high, False for low.
        :raises DriverError: If the pin cannot be used.
        """
        if self.simulated:
            return SimulatedHardware(f"GPIO {pin} set {'high' if active else 'low'}")
        from .gpio import GpioOutput

        return GpioOutput(pin, active)

    def hid(self, vendor_id: int, on_report: Callable[[bytes], None], product_id: Optional[int] = None) -> HidWriter:
        """
        Open a USB HID device, all its interfaces.
        :param vendor_id: USB vendor id.
        :param on_report: Called on the event loop with every input report.
        :param product_id: USB product id, any product of the vendor when None.
        :raises DriverError: If the device cannot be opened.
        """
        if self.simulated:
            return SimulatedHardware(f"HID device of vendor {vendor_id:04x}")
        from .hid import HidDevice

        return HidDevice(vendor_id, on_report, product_id)

    def satellite1(self, on_event: Callable[["Satellite1Event"], None], socket_path: Optional[Path] = None) -> "Satellite1Link":
        """
        Connect to ``satellite1d``, the daemon of the Satellite1 HAT: its LED ring, sensors, settings and events.
        :param on_event: Called on the event loop with every event of the daemon that LPC uses.
        :param socket_path: The socket of the daemon, its default path when None.
        :raises DriverError: If the daemon cannot be used.
        """
        if self.simulated:
            return SimulatedSatellite1()
        from .satellite1 import DEFAULT_SOCKET_PATH, Satellite1Daemon

        return Satellite1Daemon(on_event, socket_path or DEFAULT_SOCKET_PATH)
