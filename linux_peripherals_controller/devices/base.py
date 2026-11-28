"""The base of every device file: how a device runs its hardware, and the places where a device can do something of its own.

A device file in ``devices/`` describes its device type (``DEVICE_TYPE``) and has a ``Device`` class derived from ``BaseDevice``.
What ``BaseDevice`` does fits most devices: it opens the LEDs of the device type and a GPIO button per button with a pin, renders
the patterns onto the LEDs and lets the role of a button decide what a press does. A device file replaces only what its hardware
does differently, for example:

- ``open()`` / ``close()``: other hardware (a USB device, a pin that powers the LEDs).
- ``draw()`` / ``is_animated()``: LEDs that are not a strip of colors, for example the fixed LED states of a speakerphone.
- ``decide_press()``: a button that does something else than its role, for one press type or in one state of the assistant.
- ``hardware_mute`` / ``switch_hardware_mute()``: a microphone mute of the hardware.
- ``read_sensor()``: the sensors of the device type.

Everything runs on the event loop. A device reports a button with ``on_button`` and its hardware mute with ``on_hardware_mute``.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from ..animation import DisplayState, is_animated, render, scene_for
from ..button_roles import ButtonAction, decide_button_action, detection_for_role
from ..device_setup import ResolvedButton, ResolvedDevice
from ..drivers import Closable, DriverError, Drivers, LedStrip
from ..hardware_mute import HardwareMute
from ..lva_status import LvaStatus
from ..press_detection import DetectionConfig

_LOGGER = logging.getLogger(__name__)

ButtonCallback = Callable[[str, bool], None]
HardwareMuteCallback = Callable[[HardwareMute], None]


class BaseDevice:
    """
    Runs the hardware of one device.
    :param device: The device type with the device configuration applied.
    :param drivers: Opens the drivers (real or simulated).
    """

    def __init__(self, device: ResolvedDevice, drivers: Drivers) -> None:
        self.device = device
        self.drivers = drivers
        self.leds: Optional[LedStrip] = None
        self._on_button: ButtonCallback = _ignore_button
        self._on_hardware_mute: HardwareMuteCallback = _ignore_hardware_mute
        self._hardware: list[Closable] = []

    def open(self, on_button: ButtonCallback, on_hardware_mute: HardwareMuteCallback) -> None:
        """
        Open the hardware. Call it on the event loop.
        :param on_button: Called with the name of a button and True when it goes down, False when it goes up.
        :param on_hardware_mute: Called whenever the hardware mute of the device changes.
        :raises DriverError: If the hardware cannot be opened. What was opened before is released again.
        """
        self._on_button = on_button
        self._on_hardware_mute = on_hardware_mute
        try:
            if self.device.device_type.leds is not None:
                self.leds = self.drivers.led_strip(self.device.device_type.leds)
            for button in self.device.buttons:
                if button.pin is not None:
                    self.keep(self.drivers.gpio_input(button.pin, self._button_handler(button.name)))
        except DriverError:
            self.close()
            raise

    def close(self) -> None:
        """Turn the LEDs off and release the hardware."""
        if self.leds is not None:
            self.leds.close()
            self.leds = None
        while self._hardware:
            self._hardware.pop().close()

    def keep(self, hardware: Closable) -> None:
        """
        Keep a piece of opened hardware, so ``close()`` releases it.
        :param hardware: A driver that was opened.
        """
        self._hardware.append(hardware)

    def draw(self, display: DisplayState, now: float) -> None:
        """
        Show what is to be shown. Called when it changes, and again every frame while ``is_animated()`` is true.
        :param display: What is to be shown.
        :param now: The current time.
        """
        if self.leds is None:
            return
        scene = scene_for(display, self.device.colors, self.device.patterns, self.device.brightness)
        self.leds.write(render(scene, self.leds.count, now))

    def is_animated(self, display: DisplayState) -> bool:
        """True if ``draw()`` has to be called again and again for what is shown."""
        if self.leds is None:
            return False
        return is_animated(scene_for(display, self.device.colors, self.device.patterns, self.device.brightness))

    def detection_for(self, button: ResolvedButton) -> DetectionConfig:
        """How the presses of a button are told apart. By default by its role, the volume buttons repeat."""
        return detection_for_role(button.role)

    def decide_press(self, button: ResolvedButton, press: str, status: LvaStatus, link_connected: bool, child_lock: bool) -> ButtonAction:
        """
        Decide what a press does. By default by the role of the button, see ``decide_button_action()``.
        :param button: The button.
        :param press: ``single``, ``double``, ``triple``, ``long`` or ``repeat``.
        :param status: The status of LVA.
        :param link_connected: True while LPC is connected to LVA.
        :param child_lock: True while the child lock is on.
        :return: The commands for LVA and whether the press is reported to Home Assistant. A device that replaces it keeps the
        rules of ``docs/behavior.md``: every press is reported to Home Assistant, nothing goes to LVA while the child lock is on.
        """
        return decide_button_action(button.role, press, status, link_connected, child_lock)

    @property
    def hardware_mute(self) -> HardwareMute:
        """The hardware mute of the device as read from it. By default the device has none."""
        return HardwareMute()

    def switch_hardware_mute(self, muted: bool) -> None:
        """
        Switch the hardware mute. Only called for a device whose hardware mute is ``changeable``.
        :param muted: True to mute. The device reports the new state with ``on_hardware_mute`` once the hardware has changed.
        """
        _LOGGER.warning("The device type %s cannot switch a hardware mute", self.device.device_type.name)

    def read_sensor(self, name: str) -> Optional[float]:
        """
        Read a sensor of the device type. Called in a thread, so it may block.
        :param name: Name of the sensor.
        :return: The value, None if it cannot be read.
        """
        return None

    def report_button(self, name: str, down: bool) -> None:
        """
        Report a button of the device, for a device file that reads its buttons itself.
        :param name: Name of the button of the device type.
        :param down: True when it goes down, False when it goes up.
        """
        self._on_button(name, down)

    def report_hardware_mute(self) -> None:
        """Report the hardware mute after it changed, for a device file that has one."""
        self._on_hardware_mute(self.hardware_mute)

    def _button_handler(self, name: str) -> Callable[[bool], None]:
        return lambda down: self.report_button(name, down)


def _ignore_button(name: str, down: bool) -> None:
    pass


def _ignore_hardware_mute(hardware: HardwareMute) -> None:
    pass
