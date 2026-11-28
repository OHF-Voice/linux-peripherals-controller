"""Runs a device: connects its hardware with LVA (through the controller) and with Home Assistant (through the ESPHome server).

- What the controller chooses to show, and the light of Home Assistant as the background, goes to the LEDs of the device.
- A press of a button is decided by the device and goes to LVA and to Home Assistant, each on its own.
- The child lock and the light come from Home Assistant and are stored across restarts.
- The hardware mute of the device goes to LVA and to Home Assistant, and their requests to switch it go to the device.
- The sensors of the device are read at their interval (or reported by the device) and go to Home Assistant, the controls of the
  hardware are read at startup and changed by Home Assistant.

Nothing here talks to hardware directly: the device does.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import time
from typing import Callable, Dict, List, Optional, Union

from .animation import DisplayState, display_amount
from .button_input import ButtonInput
from .controller import Controller
from .device_setup import ResolvedButton, ResolvedSensor
from .device_types import ControlSpec, SensorKind
from .devices.base import BaseDevice, DeviceCallbacks, SensorValue
from .display import DisplayFunction
from .esphome.entities import BinarySensorEntity, ButtonEventEntity, Entity, LightEntity, NumberEntity, SensorEntity, SwitchEntity, TextSensorEntity
from .esphome.server import HomeAssistantServer
from .hardware_mute import HardwareMute, HardwareMuteEntity, decide_mute_request, entity_for
from .led_output import LedOutput
from .light import LightState
from .lva_status import LvaStatus
from .state_store import StoredState

_LOGGER = logging.getLogger(__name__)

ValueEntity = Union[SensorEntity, TextSensorEntity, BinarySensorEntity]


class DeviceRunner:
    """
    Runs one device.
    :param device: The device, not opened yet.
    :param stored: The values stored before (child lock, light).
    :param save: Called with the values to store whenever one changes.
    :param clock: Returns the current time in seconds.
    """

    def __init__(self, device: BaseDevice, stored: StoredState, save: Callable[[StoredState], None], clock: Callable[[], float] = time.monotonic) -> None:
        self.device = device
        self._stored = stored
        self._save = save
        self._clock = clock
        self._controller: Optional[Controller] = None
        self._home_assistant: Optional[HomeAssistantServer] = None
        self._leds = LedOutput(device, clock)
        self._buttons: Dict[str, ResolvedButton] = {button.name: button for button in device.device.buttons}
        self._input = ButtonInput({button.name: device.detection_for(button) for button in device.device.buttons}, self._handle_press, clock)
        self._function: Optional[DisplayFunction] = DisplayFunction.NO_CONNECTION
        self._started_at = clock()
        self._status = LvaStatus()
        self._hardware_mute = HardwareMute()
        self._button_entities: Dict[str, ButtonEventEntity] = {}
        self._sensor_entities: Dict[str, ValueEntity] = {}
        self._control_entities: Dict[str, NumberEntity] = {}
        self._hardware_mute_entity: Optional[Union[SwitchEntity, BinarySensorEntity]] = None
        self._sensors_failed: set[str] = set()

    @property
    def child_lock(self) -> bool:
        """True while the child lock is on."""
        return self._stored.child_lock

    @property
    def light(self) -> LightState:
        """The light of Home Assistant."""
        return self._stored.light

    def open(self) -> None:
        """
        Open the hardware and show that LVA is not connected yet. Call it on the event loop.
        :raises DriverError: If the hardware cannot be opened.
        """
        self.device.open(DeviceCallbacks(self._input.change, self._hardware_mute_changed, self._sensor_reported))
        self._hardware_mute = self.device.hardware_mute
        self._redraw()

    def close(self) -> None:
        """Stop the LEDs and the buttons and release the hardware."""
        self._leds.close()
        self._input.close()
        self.device.close()

    def entities(self) -> List[Entity]:
        """
        Create the entities for Home Assistant. Call it once, after ``open()``.
        :return: The light (if the device has LEDs), an event per button, the child lock, the hardware mute (if the device has one),
        a sensor per sensor and a number per control, in this order.
        """
        entities: List[Entity] = []
        if self.device.device.device_type.leds is not None:
            entities.append(LightEntity(len(entities), "led", "LED", self.light, self.set_light))
        for button in self.device.device.buttons:
            entity = ButtonEventEntity(len(entities), _object_id(button.name), _display_name(button.name))
            self._button_entities[button.name] = entity
            entities.append(entity)
        entities.append(SwitchEntity(len(entities), "child_lock", "Child Lock", lambda: self.child_lock, self.set_child_lock, "mdi:lock"))
        kind = entity_for(self._hardware_mute)
        if kind == HardwareMuteEntity.SWITCH:
            self._hardware_mute_entity = SwitchEntity(len(entities), "hardware_mute", "Hardware Mute", lambda: self._hardware_mute.muted, self.request_hardware_mute, "mdi:microphone-off")
        elif kind == HardwareMuteEntity.BINARY_SENSOR:
            self._hardware_mute_entity = BinarySensorEntity(len(entities), "hardware_mute", "Hardware Mute", "mdi:microphone-off", diagnostic=True)
            self._hardware_mute_entity.value = self._hardware_mute.muted
        if self._hardware_mute_entity is not None:
            entities.append(self._hardware_mute_entity)
        for sensor in self.device.device.sensors:
            sensor_entity = _sensor_entity(len(entities), sensor)
            self._sensor_entities[sensor.name] = sensor_entity
            entities.append(sensor_entity)
        for control in self.device.device.device_type.controls:
            control_entity = NumberEntity(
                len(entities), _object_id(control.name), _display_name(control.name), control.minimum, control.maximum, control.step, control.unit, self._control_setter(control)
            )
            self._control_entities[control.name] = control_entity
            entities.append(control_entity)
        return entities

    def attach(self, controller: Controller, home_assistant: HomeAssistantServer) -> None:
        """
        Connect the runner with LVA and Home Assistant, and tell LVA the hardware mute.
        :param controller: The connection to LVA.
        :param home_assistant: The ESPHome server with the entities of ``entities()``.
        """
        self._controller = controller
        self._home_assistant = home_assistant
        controller.set_hardware_mute(self._hardware_mute)

    async def read_values(self) -> None:
        """
        Read the controls once and every sensor at its interval, until the task is cancelled. A sensor without an interval is read
        once. Returns when nothing is left to read.
        """
        await asyncio.gather(*(self._read_control(control) for control in self.device.device.device_type.controls), *(self._read_sensor(sensor) for sensor in self.device.device.sensors))

    def display_changed(self, function: Optional[DisplayFunction]) -> None:
        """
        The controller chose another display function.
        :param function: The display function, None for the background.
        """
        self._function = function
        self._started_at = self._clock()
        self._redraw()

    def status_changed(self, status: LvaStatus) -> None:
        """
        The status of LVA changed, the amount shown (time left, volume) may follow.
        :param status: The status of LVA.
        """
        self._status = status
        self._redraw()

    def set_light(self, light: LightState) -> None:
        """
        Home Assistant changed the light.
        :param light: The new light.
        """
        self._store(dataclasses.replace(self._stored, light=light))
        self._redraw()

    def set_child_lock(self, locked: bool) -> None:
        """
        Home Assistant switched the child lock.
        :param locked: True to lock.
        """
        _LOGGER.info("Child lock %s", "on" if locked else "off")
        self._store(dataclasses.replace(self._stored, child_lock=locked))

    def request_hardware_mute(self, muted: bool) -> None:
        """
        Home Assistant or LVA asks to switch the hardware mute. The device decides, and reports the new state itself.
        :param muted: True to mute.
        """
        decision = decide_mute_request("hardware_muted_on" if muted else "hardware_muted_off", self._hardware_mute)
        _LOGGER.debug("Request to switch the hardware mute: %s", decision.reason)
        if decision.muted is not None:
            self.device.switch_hardware_mute(decision.muted)

    def _hardware_mute_changed(self, hardware: HardwareMute) -> None:
        _LOGGER.debug("Hardware mute of the device: %s", hardware)
        self._hardware_mute = hardware
        if self._controller is not None:
            self._controller.set_hardware_mute(hardware)
        if isinstance(self._hardware_mute_entity, BinarySensorEntity):
            self._hardware_mute_entity.value = hardware.muted
        if self._home_assistant is not None and self._hardware_mute_entity is not None:
            self._home_assistant.broadcast(self._hardware_mute_entity.state_responses())

    def _sensor_reported(self, name: str, value: SensorValue) -> None:
        _LOGGER.debug("Sensor '%s' reported by the device: %s", name, value)
        self._update_sensor(name, value)

    def _update_sensor(self, name: str, value: SensorValue) -> None:
        entity = self._sensor_entities.get(name)
        if entity is None:
            return
        value = _checked_value(entity, value)
        if value != entity.value:
            entity.value = value  # type: ignore[assignment]
            if self._home_assistant is not None:
                self._home_assistant.broadcast(entity.state_responses())

    def _control_setter(self, control: ControlSpec) -> Callable[[float], Optional[float]]:
        return lambda value: self.device.set_control(control.name, value)

    def _handle_press(self, name: str, press: str) -> None:
        button = self._buttons[name]
        controller = self._controller
        status = controller.status if controller is not None else LvaStatus()
        link_connected = controller.link_connected if controller is not None else False
        action = self.device.decide_press(button, press, status, link_connected, self.child_lock)
        _LOGGER.debug("Button '%s': %s", name, action.reason)
        if action.commands and controller is not None:
            controller.send_messages(action.commands)
        if action.report_to_ha and self._home_assistant is not None and name in self._button_entities:
            self._home_assistant.broadcast(self._button_entities[name].press(press))

    def _redraw(self) -> None:
        display = DisplayState(self._function, display_amount(self._function, self._status), self.light, self._started_at)
        if display != self._leds.display:
            self._leds.show(display)

    def _store(self, stored: StoredState) -> None:
        self._stored = stored
        self._save(stored)

    async def _read_sensor(self, sensor: ResolvedSensor) -> None:
        while True:
            value = await asyncio.to_thread(self.device.read_sensor, sensor.name)
            if value is None and sensor.name not in self._sensors_failed:
                _LOGGER.warning("Sensor '%s' cannot be read, it is unavailable in Home Assistant", sensor.name)
                self._sensors_failed.add(sensor.name)
            elif value is not None:
                self._sensors_failed.discard(sensor.name)
            self._update_sensor(sensor.name, value)
            if sensor.interval is None:
                return
            await asyncio.sleep(sensor.interval)

    async def _read_control(self, control: ControlSpec) -> None:
        value = await asyncio.to_thread(self.device.read_control, control.name)
        if value is None:
            _LOGGER.warning("'%s' cannot be read, it is unknown in Home Assistant until it is set", control.name)
        entity = self._control_entities.get(control.name)
        if entity is not None and value != entity.value:
            entity.value = value
            if self._home_assistant is not None:
                self._home_assistant.broadcast(entity.state_responses())


def _sensor_entity(key: int, sensor: ResolvedSensor) -> ValueEntity:
    object_id, name = _object_id(sensor.name), _display_name(sensor.name)
    if sensor.kind == SensorKind.TEXT:
        return TextSensorEntity(key, object_id, name, sensor.diagnostic)
    if sensor.kind == SensorKind.BINARY:
        return BinarySensorEntity(key, object_id, name, device_class=sensor.device_class, diagnostic=sensor.diagnostic)
    return SensorEntity(key, object_id, name, sensor.unit, sensor.device_class, sensor.diagnostic)


def _checked_value(entity: ValueEntity, value: SensorValue) -> SensorValue:
    """The value if it fits the kind of the entity, else None (unknown)."""
    if isinstance(entity, BinarySensorEntity):
        return value if isinstance(value, bool) else None
    if isinstance(entity, TextSensorEntity):
        return value if isinstance(value, str) else None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _object_id(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "entity"


def _display_name(name: str) -> str:
    return name.replace("_", " ").capitalize()
