"""Satellite1 HAT (FutureProofHomes): LED ring, buttons, sensors, microphone mute switch and speaker amplifier, through its SDK.

Built on the Satellite1-RPi-SDK (``FutureProofHomes/Satellite1-RPi-SDK``, branch ``develop``). Its daemon ``satellite1d`` owns the
hardware: the XMOS chip on SPI (LED ring, volume buttons, microphone mute switch), GPIO 7 (action button), the sensors (AHT20 for
temperature and humidity, LTR303 for light), the speaker amplifier and the USB-C power controller. LPC only talks to the daemon
(``drivers/satellite1.py``), as the SDK asks applications to do, so both can run at the same time.

- The daemon reports a press of a button, not its release. Every press is therefore a short click: single, double and triple
  presses work, a long press and the repeat of a held volume button do not.
- The microphone mute switch latches and mutes the microphones in the hardware. It is the hardware mute of the device, of the kind
  that can only be read (``read_only``).
- The line-out jack and the mute switch are reported by the daemon when they change. The other sensors are read at their interval,
  the firmware once at startup.
"""

from __future__ import annotations

from typing import Optional

from ..button_roles import ButtonRole
from ..device_setup import ResolvedDevice
from ..device_types import ButtonSpec, ControlSpec, DeviceType, LedSpec, SensorKind, SensorSpec
from ..drivers import Drivers, LedStrip
from ..drivers.satellite1 import AMP_LEVEL_MAX, Satellite1Event, Satellite1Link
from ..hardware_mute import HardwareMute, HardwareMuteType
from .base import BaseDevice, SensorValue

SENSOR_INTERVAL_SECONDS = 60.0
ENVIRONMENT_READINGS = {"temperature": "temperature_c", "humidity": "humidity_percent", "illuminance": "illuminance_lux"}

DEVICE_TYPE = DeviceType(
    name="satellite1",
    description="Satellite1 HAT through satellite1d: 24 LEDs, action and volume buttons, sensors, microphone mute switch",
    leds=LedSpec("satellite1d", 24),
    buttons=(
        ButtonSpec("action", ButtonRole.ACTION),
        ButtonSpec("volume_up", ButtonRole.VOLUME_UP),
        ButtonSpec("volume_down", ButtonRole.VOLUME_DOWN),
    ),
    sensors=(
        SensorSpec("temperature", SENSOR_INTERVAL_SECONDS, "°C", "temperature"),
        SensorSpec("humidity", SENSOR_INTERVAL_SECONDS, "%", "humidity"),
        SensorSpec("illuminance", SENSOR_INTERVAL_SECONDS, "lx", "illuminance"),
        SensorSpec("line_out_jack", None, device_class="plug", kind=SensorKind.BINARY),
        SensorSpec("usb_c_voltage", SENSOR_INTERVAL_SECONDS, "V", "voltage", diagnostic=True),
        SensorSpec("usb_c_current", SENSOR_INTERVAL_SECONDS, "A", "current", diagnostic=True),
        SensorSpec("xmos_firmware", None, kind=SensorKind.TEXT, diagnostic=True),
    ),
    controls=(ControlSpec("amplifier_level", 0, AMP_LEVEL_MAX),),
)


class Device(BaseDevice):
    """The Satellite1 HAT: everything comes from ``satellite1d``."""

    def __init__(self, device: ResolvedDevice, drivers: Drivers) -> None:
        super().__init__(device, drivers)
        self._daemon: Optional[Satellite1Link] = None
        self._mic_muted = False

    def open_leds(self) -> Optional[LedStrip]:
        """
        Connect to ``satellite1d`` and read the microphone mute switch.
        :raises DriverError: If the daemon cannot be used.
        """
        daemon = self.drivers.satellite1(self._handle_event)
        self._daemon = daemon
        self._mic_muted = bool(daemon.mic_muted())
        return daemon

    @property
    def hardware_mute(self) -> HardwareMute:
        """The microphone mute switch of the HAT: it can only be read."""
        return HardwareMute(HardwareMuteType.READ_ONLY, self._mic_muted)

    def read_sensor(self, name: str) -> SensorValue:
        """
        Read a sensor through the daemon. It blocks, it is called in a thread.
        :param name: A sensor of the device type.
        :return: The value, None if the daemon or the sensor cannot be read.
        """
        daemon = self._daemon
        if daemon is None:
            return None
        if name in ENVIRONMENT_READINGS:
            return daemon.read_environment().get(ENVIRONMENT_READINGS[name])
        if name == "line_out_jack":
            return daemon.line_out_plugged_in()
        if name in ("usb_c_voltage", "usb_c_current"):
            contract = daemon.power_contract()
            if contract is None:
                return None
            return contract.voltage if name == "usb_c_voltage" else contract.current
        if name == "xmos_firmware":
            return daemon.firmware()
        return None

    def read_control(self, name: str) -> Optional[float]:
        """
        Read the level of the speaker amplifier. It blocks, it is called in a thread.
        :param name: ``amplifier_level``.
        """
        if self._daemon is None or name != "amplifier_level":
            return None
        level = self._daemon.amp_level()
        return None if level is None else float(level)

    def set_control(self, name: str, value: float) -> Optional[float]:
        """
        Change the level of the speaker amplifier.
        :param name: ``amplifier_level``.
        :param value: 0 to 20, rounded to a whole level.
        :return: The level the daemon reports afterwards.
        """
        if self._daemon is None or name != "amplifier_level":
            return super().set_control(name, value)
        level = self._daemon.set_amp_level(round(value))
        return None if level is None else float(level)

    def _handle_event(self, event: Satellite1Event) -> None:
        if event.kind == "button":
            self.report_button(str(event.value), True)
            self.report_button(str(event.value), False)
        elif event.kind == "mic_muted":
            self._mic_muted = bool(event.value)
            self.report_hardware_mute()
        elif event.kind == "line_out_jack":
            self.report_sensor("line_out_jack", bool(event.value))
