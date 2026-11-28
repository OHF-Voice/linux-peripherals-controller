"""A USB HID device read and written with the ``hidapi`` package, for example the Jabra Speak 410.

A device can have several HID interfaces, and the reports of its buttons can come from any of them. All interfaces of the device
are opened, input reports are read in one thread per interface (``hidapi`` only reads blocking or by polling) and handed to the
event loop, and an output report is written to every interface. What the bytes of a report mean is up to the device file.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Callable, Optional, Sequence

from .base import DriverError

_LOGGER = logging.getLogger(__name__)

_READ_SIZE = 64
_READ_TIMEOUT_MS = 500


class HidDevice:
    """
    Every HID interface with the vendor id (and product id, if given).
    :param vendor_id: USB vendor id.
    :param on_report: Called on the event loop with every input report (the report id is the first byte).
    :param product_id: USB product id, any product of the vendor when None.
    :raises DriverError: If ``hidapi`` is not installed or no interface can be opened.
    """

    def __init__(self, vendor_id: int, on_report: Callable[[bytes], None], product_id: Optional[int] = None) -> None:
        try:
            import hid  # type: ignore
        except ImportError as exc:
            raise DriverError("HID: the Python package hidapi is not installed") from exc
        self._name = f"USB {vendor_id:04x}:{product_id:04x}" if product_id is not None else f"USB vendor {vendor_id:04x}"
        found = hid.enumerate(vendor_id, product_id or 0)
        if not found:
            raise DriverError(f"HID device ({self._name}) not found: is it connected and may LPC use /dev/hidraw*?")
        self._on_report = on_report
        self._loop = asyncio.get_running_loop()
        self._closing = threading.Event()
        self._interfaces: list[Any] = []
        self._threads: list[threading.Thread] = []
        for info in found:
            interface = hid.device()
            try:
                interface.open_path(info["path"])
            except OSError as exc:
                self.close()
                raise DriverError(f"HID device {info.get('product_string') or self._name} cannot be opened: {exc}") from exc
            self._interfaces.append(interface)
            thread = threading.Thread(target=self._read_loop, args=(interface,), name="hid-reader", daemon=True)
            self._threads.append(thread)
            thread.start()
        _LOGGER.info("HID device opened: %s (%s, %s interfaces)", found[0].get("product_string") or self._name, self._name, len(found))

    def write(self, report: Sequence[int]) -> None:
        """
        Send an output report to every interface.
        :param report: The report, its id first.
        """
        for interface in self._interfaces:
            try:
                interface.write(list(report))
            except (OSError, ValueError) as exc:
                _LOGGER.debug("Cannot write to an interface of the HID device %s: %s", self._name, exc)

    def close(self) -> None:
        """Stop reading and release the device."""
        self._closing.set()
        for thread in self._threads:
            thread.join(timeout=2 * _READ_TIMEOUT_MS / 1000)
        for interface in self._interfaces:
            interface.close()
        self._interfaces = []
        self._threads = []

    def _read_loop(self, interface: Any) -> None:
        while not self._closing.is_set():
            try:
                data = interface.read(_READ_SIZE, _READ_TIMEOUT_MS)
            except (OSError, ValueError) as exc:
                _LOGGER.warning("Cannot read from the HID device %s, stopped reading this interface: %s", self._name, exc)
                return
            if data:
                self._loop.call_soon_threadsafe(self._on_report, bytes(data))
