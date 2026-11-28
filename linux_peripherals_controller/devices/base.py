"""The base of every device file: how a device runs its hardware, and the places where a device can do something of its own.

A device file in ``devices/`` describes its device type (``DEVICE_TYPE``) and has a ``Device`` class derived from ``BaseDevice``.
What ``BaseDevice`` does fits most devices: it opens the LEDs of the device type and a GPIO button per button with a pin, renders
the patterns onto the LEDs and lets the role of a button decide what a press does. A device file replaces only what its hardware
does differently, for example:

- ``open()`` / ``open_leds()`` / ``close()``: other hardware (a USB device, a pin that powers the LEDs, LEDs behind a daemon).
- ``draw()`` / ``is_animated()``: LEDs that are not a strip of colors, for example the fixed LED states of a speakerphone.
- ``decide_press()``: a button that does something else than its role, for one press type or in one state of the assistant.
- ``hardware_mute`` / ``switch_hardware_mute()``: a microphone mute of the hardware.
- ``read_sensor()`` / ``report_sensor()``: the sensors of the device type, read at their interval or reported by the device.
- ``read_control()`` / ``set_control()``: the settings of the hardware that Home Assistant can change.

Everything runs on the event loop. A device reports a button, its hardware mute and a changed sensor through ``DeviceCallbacks``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Union

from ..animation import DisplayState, is_animated, render, scene_for
from ..button_roles import ButtonAction, decide_button_action, detection_for_role
from ..device_setup import ResolvedButton, ResolvedDevice
from ..drivers import Closable, DriverError, Drivers, LedStrip
from ..hardware_mute import HardwareMute
from ..lva_status import LvaStatus
from ..press_detection import DetectionConfig

_LOGGER = logging.getLogger(__name__)

SensorValue = Union[float, str, bool, None]


def _ignore_button(name: str, down: bool) -> None:
    pass


def _ignore_hardware_mute(hardware: HardwareMute) -> None:
    pass


def _ignore_sensor(name: str, value: SensorValue) -> None:
    pass


@dataclass(frozen=True)
class DeviceCallbacks:
    """
    What a device reports while it runs, all called on the event loop.
    :param on_button: The name of a button and True when it goes down, False when it goes up.
    :param on_hardware_mute: The hardware mute whenever it changes.
    :param on_sensor: The name of a sensor and its new value, when the device reports it itself.
    """

    on_button: Callable[[str, bool], None] = _ignore_button
    on_hardware_mute: Callable[[HardwareMute], None] = _ignore_hardware_mute
    on_sensor: Callable[[str, SensorValue], None] = _ignore_sensor


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
        self._callbacks = DeviceCallbacks()
        self._hardware: list[Closable] = []

    def open(self, callbacks: DeviceCallbacks) -> None:
        """
        Open the hardware. Call it on the event loop.
        :param callbacks: What the device reports while it runs.
        :raises DriverError: If the hardware cannot be opened. What was opened before is released again.
        """
        self._callbacks = callbacks
        try:
            self.leds = self.open_leds()
            for button in self.device.buttons:
                if button.pin is not None:
                    self.keep(self.drivers.gpio_input(button.pin, self._button_handler(button.name)))
        except DriverError:
            self.close()
            raise

    def open_leds(self) -> Optional[LedStrip]:
        """
        Open the LEDs. By default those of the device type with their driver, None for a device without LEDs.
        :raises DriverError: If the LEDs cannot be opened.
        """
        if self.device.device_type.leds is None:
            return None
        return self.drivers.led_strip(self.device.device_type.leds)

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

    def read_sensor(self, name: str) -> SensorValue:
        """
        Read a sensor of the device type. Called in a thread, so it may block.
        :param name: Name of the sensor.
        :return: The value (a number, a text or on/off, as the kind of the sensor says), None if it cannot be read.
        """
        return None

    def read_control(self, name: str) -> Optional[float]:
        """
        Read a setting of the hardware. Called in a thread, so it may block.
        :param name: Name of the control of the device type.
        :return: The value, None if it cannot be read.
        """
        return None

    def set_control(self, name: str, value: float) -> Optional[float]:
        """
        Change a setting of the hardware, as Home Assistant asks. Called on the event loop.
        :param name: Name of the control of the device type.
        :param value: The new value, within the range of the control.
        :return: The value the hardware has now, None if it cannot be read. By default nothing changes and the value is read.
        """
        _LOGGER.warning("The device type %s cannot change '%s'", self.device.device_type.name, name)
        return self.read_control(name)

    def report_button(self, name: str, down: bool) -> None:
        """
        Report a button of the device, for a device file that reads its buttons itself.
        :param name: Name of the button of the device type.
        :param down: True when it goes down, False when it goes up.
        """
        self._callbacks.on_button(name, down)

    def report_hardware_mute(self) -> None:
        """Report the hardware mute after it changed, for a device file that has one."""
        self._callbacks.on_hardware_mute(self.hardware_mute)

    def report_sensor(self, name: str, value: SensorValue) -> None:
        """
        Report a new value of a sensor, for a device file that learns it without reading (an event of the hardware).
        :param name: Name of the sensor of the device type.
        :param value: The new value, None if it is not known.
        """
        self._callbacks.on_sensor(name, value)

    def _button_handler(self, name: str) -> Callable[[bool], None]:
        return lambda down: self.report_button(name, down)
