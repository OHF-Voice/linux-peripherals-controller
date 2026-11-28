"""GPIO pins of the Raspberry Pi through the Linux GPIO character device (``/dev/gpiochip*``), with the ``gpiod`` package.

It works on the Raspberry Pi 3, 4 and 5 alike: the chip of the pin header is the one whose label starts with ``pinctrl-``
(``pinctrl-bcm2835``, ``pinctrl-bcm2711``, ``pinctrl-rp1``). Pins are BCM numbers. Edges of an input are read on the event loop
(``add_reader`` on the file of the request), so no thread is started.
"""

from __future__ import annotations

import asyncio
import glob
import logging
from datetime import timedelta
from typing import Any, Callable, Optional

from .base import DriverError

_LOGGER = logging.getLogger(__name__)

_HEADER_CHIP_PREFIX = "pinctrl-"
_CONSUMER = "linux-peripherals-controller"


def find_gpio_chip() -> str:
    """
    Find the GPIO chip of the pin header.
    :raises DriverError: If ``gpiod`` is not installed or no GPIO chip can be opened.
    :return: Path of the chip, ``/dev/gpiochip0`` if none has a ``pinctrl-`` label.
    """
    gpiod = _import_gpiod()
    paths = sorted(path for path in glob.glob("/dev/gpiochip*") if gpiod.is_gpiochip_device(path))
    if not paths:
        raise DriverError("No GPIO chip found (/dev/gpiochip*): is the device passed to the container?")
    for path in paths:
        try:
            with gpiod.Chip(path) as chip:
                if chip.get_info().label.startswith(_HEADER_CHIP_PREFIX):
                    return path
        except OSError as exc:
            _LOGGER.debug("GPIO chip %s cannot be read: %s", path, exc)
    return paths[0]


class GpioInput:
    """
    A button on a GPIO pin that connects the pin to ground (pull-up, active low).
    :param pin: BCM number of the pin.
    :param on_change: Called on the event loop with True when the button goes down and False when it goes up.
    :param debounce: Seconds in which further edges are ignored.
    :param chip: Path of the GPIO chip, found with ``find_gpio_chip()`` when None.
    :raises DriverError: If the pin cannot be requested.
    """

    def __init__(self, pin: int, on_change: Callable[[bool], None], debounce: float = 0.03, chip: Optional[str] = None) -> None:
        gpiod = _import_gpiod()
        from gpiod.line import Bias, Direction, Edge

        self._pin = pin
        self._on_change = on_change
        self._loop = asyncio.get_running_loop()
        chip = chip or find_gpio_chip()
        settings = gpiod.LineSettings(
            direction=Direction.INPUT,
            edge_detection=Edge.BOTH,
            bias=Bias.PULL_UP,
            active_low=True,
            debounce_period=timedelta(seconds=debounce),
        )
        try:
            self._request: Any = gpiod.request_lines(chip, consumer=_CONSUMER, config={pin: settings})
        except OSError as exc:
            raise DriverError(f"GPIO {pin} on {chip} cannot be used as a button: {exc}") from exc
        self._rising = gpiod.EdgeEvent.Type.RISING_EDGE
        self._loop.add_reader(self._request.fd, self._read_edges)
        _LOGGER.info("Button on GPIO %s (%s)", pin, chip)

    def close(self) -> None:
        """Release the pin."""
        self._loop.remove_reader(self._request.fd)
        self._request.release()

    def _read_edges(self) -> None:
        for event in self._request.read_edge_events():
            # Active low: the rising edge of the logical value is the button going down.
            down = event.event_type == self._rising
            _LOGGER.debug("GPIO %s: %s", self._pin, "down" if down else "up")
            self._on_change(down)


class GpioOutput:
    """
    A GPIO pin that is driven high or low, for example the power of LEDs.
    :param pin: BCM number of the pin.
    :param active: The value the pin is set to.
    :param chip: Path of the GPIO chip, found with ``find_gpio_chip()`` when None.
    :raises DriverError: If the pin cannot be requested.
    """

    def __init__(self, pin: int, active: bool = True, chip: Optional[str] = None) -> None:
        gpiod = _import_gpiod()
        from gpiod.line import Direction, Value

        chip = chip or find_gpio_chip()
        settings = gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE if active else Value.INACTIVE)
        try:
            self._request: Any = gpiod.request_lines(chip, consumer=_CONSUMER, config={pin: settings})
        except OSError as exc:
            raise DriverError(f"GPIO {pin} on {chip} cannot be used as an output: {exc}") from exc
        _LOGGER.info("GPIO %s (%s) set %s", pin, chip, "high" if active else "low")

    def close(self) -> None:
        """Release the pin. It keeps its value or returns to its default, depending on the kernel."""
        self._request.release()


def _import_gpiod() -> Any:
    try:
        import gpiod
    except ImportError as exc:
        raise DriverError("GPIO: the Python package gpiod is not installed") from exc
    return gpiod
