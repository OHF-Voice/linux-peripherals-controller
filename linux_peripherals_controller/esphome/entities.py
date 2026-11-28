"""The entities LPC offers to Home Assistant: the light, an event per button, switches, sensors (numbers, texts, on/off) and numbers.

Every entity knows how it is listed, what its state is and what a command of Home Assistant does to it. Sending is the business of
the server. The key of an entity is its place in the list, so entities are only ever appended, never reordered or removed.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    BinarySensorStateResponse,
    EventResponse,
    LightCommandRequest,
    LightStateResponse,
    ListEntitiesBinarySensorResponse,
    ListEntitiesEventResponse,
    ListEntitiesLightResponse,
    ListEntitiesNumberResponse,
    ListEntitiesSensorResponse,
    ListEntitiesSwitchResponse,
    ListEntitiesTextSensorResponse,
    NumberCommandRequest,
    NumberStateResponse,
    SensorStateResponse,
    SwitchCommandRequest,
    SwitchStateResponse,
    TextSensorStateResponse,
)
from aioesphomeapi.model import ColorMode, EntityCategory, NumberMode, SensorStateClass
from google.protobuf import message

from ..light import LightState, apply_light_command
from ..lva_protocol import PRESS_TYPES

_LOGGER = logging.getLogger(__name__)

EVENT_TYPES = [f"{press}_press" for press in PRESS_TYPES]


class Entity:
    """
    One entity.
    :param key: Its key, the place in the list of entities.
    :param object_id: Its id, for the entity id in Home Assistant.
    :param name: Its name in Home Assistant.
    """

    def __init__(self, key: int, object_id: str, name: str) -> None:
        self.key = key
        self.object_id = object_id
        self.name = name

    def list_response(self) -> Any:
        """How the entity is listed: its ``ListEntities...Response`` message."""
        raise NotImplementedError

    def state_responses(self) -> List[message.Message]:
        """The current state, empty if there is none to tell yet."""
        return []

    def handle_command(self, msg: message.Message) -> List[message.Message]:
        """
        Carry out a command of Home Assistant for this entity.
        :param msg: The command, its key is the key of this entity.
        :return: The state after the command, for every client.
        """
        _LOGGER.debug("Ignoring %s for the entity %s", type(msg).__name__, self.object_id)
        return []


class LightEntity(Entity):
    """
    The light of the LEDs (RGB with brightness): the background of the LEDs.
    :param light: The light at startup.
    :param on_change: Called with the new light when Home Assistant changes it.
    """

    def __init__(self, key: int, object_id: str, name: str, light: LightState, on_change: Callable[[LightState], None]) -> None:
        super().__init__(key, object_id, name)
        self.light = light
        self._on_change = on_change

    def list_response(self) -> Any:
        return ListEntitiesLightResponse(
            object_id=self.object_id,
            key=self.key,
            name=self.name,
            supported_color_modes=[int(ColorMode.RGB)],
            icon="mdi:led-strip-variant",
        )

    def state_responses(self) -> List[message.Message]:
        light = self.light
        return [
            LightStateResponse(
                key=self.key,
                state=light.on,
                brightness=light.brightness,
                color_mode=int(ColorMode.RGB),
                color_brightness=1.0,
                red=light.red,
                green=light.green,
                blue=light.blue,
            )
        ]

    def handle_command(self, msg: message.Message) -> List[message.Message]:
        if not isinstance(msg, LightCommandRequest):
            return super().handle_command(msg)
        self.light = apply_light_command(
            self.light,
            on=bool(msg.state) if msg.has_state else None,
            brightness=float(msg.brightness) if msg.has_brightness else None,
            rgb=(float(msg.red), float(msg.green), float(msg.blue)) if msg.has_rgb else None,
        )
        _LOGGER.debug("Light set by Home Assistant: %s", self.light)
        self._on_change(self.light)
        return self.state_responses()


class ButtonEventEntity(Entity):
    """An event entity for a button: ``single_press``, ``double_press``, ``triple_press`` and ``long_press``."""

    def __init__(self, key: int, object_id: str, name: str) -> None:
        super().__init__(key, object_id, name)
        self._last_event: Optional[str] = None

    def list_response(self) -> Any:
        return ListEntitiesEventResponse(object_id=self.object_id, key=self.key, name=self.name, device_class="button", event_types=EVENT_TYPES)

    def state_responses(self) -> List[message.Message]:
        # An empty event type makes Home Assistant fail the whole device, so nothing is told before the first press.
        if self._last_event is None:
            return []
        return [EventResponse(key=self.key, event_type=self._last_event)]

    def press(self, press: str) -> List[message.Message]:
        """
        A press of the button.
        :param press: ``single``, ``double``, ``triple`` or ``long``.
        :return: The event for every client.
        """
        self._last_event = f"{press}_press"
        return self.state_responses()


class SwitchEntity(Entity):
    """
    A switch whose state is read from its owner, for the child lock and a hardware mute that can be switched.
    :param get_state: Returns the current state.
    :param on_command: Called with the state Home Assistant asks for.
    :param icon: Icon in Home Assistant.
    """

    def __init__(self, key: int, object_id: str, name: str, get_state: Callable[[], bool], on_command: Callable[[bool], None], icon: str) -> None:
        super().__init__(key, object_id, name)
        self._get_state = get_state
        self._on_command = on_command
        self._icon = icon

    def list_response(self) -> Any:
        return ListEntitiesSwitchResponse(object_id=self.object_id, key=self.key, name=self.name, icon=self._icon, entity_category=EntityCategory.CONFIG)

    def state_responses(self) -> List[message.Message]:
        return [SwitchStateResponse(key=self.key, state=self._get_state())]

    def handle_command(self, msg: message.Message) -> List[message.Message]:
        if not isinstance(msg, SwitchCommandRequest):
            return super().handle_command(msg)
        self._on_command(bool(msg.state))
        return self.state_responses()


class BinarySensorEntity(Entity):
    """
    An on/off sensor, for the hardware mute that can only be read and on/off sensors of the device. Unknown while ``value`` is None.
    :param icon: Icon in Home Assistant, empty for the default.
    :param device_class: Device class in Home Assistant, empty for none.
    :param diagnostic: True to show it under Diagnostic in Home Assistant.
    """

    def __init__(self, key: int, object_id: str, name: str, icon: str = "", device_class: str = "", diagnostic: bool = False) -> None:
        super().__init__(key, object_id, name)
        self.value: Optional[bool] = None
        self._icon = icon
        self._device_class = device_class
        self._diagnostic = diagnostic

    def list_response(self) -> Any:
        return ListEntitiesBinarySensorResponse(object_id=self.object_id, key=self.key, name=self.name, icon=self._icon, device_class=self._device_class, entity_category=_category(self._diagnostic))

    def state_responses(self) -> List[message.Message]:
        if self.value is None:
            return [BinarySensorStateResponse(key=self.key, missing_state=True)]
        return [BinarySensorStateResponse(key=self.key, state=self.value)]


class SensorEntity(Entity):
    """
    A sensor of the device with a number, ``unavailable`` while ``value`` is None.
    :param unit: Unit of the value, empty for none.
    :param device_class: Device class in Home Assistant, empty for none.
    :param diagnostic: True to show it under Diagnostic in Home Assistant.
    """

    def __init__(self, key: int, object_id: str, name: str, unit: str = "", device_class: str = "", diagnostic: bool = False) -> None:
        super().__init__(key, object_id, name)
        self.value: Optional[float] = None
        self._unit = unit
        self._device_class = device_class
        self._diagnostic = diagnostic

    def list_response(self) -> Any:
        return ListEntitiesSensorResponse(
            object_id=self.object_id,
            key=self.key,
            name=self.name,
            unit_of_measurement=self._unit,
            device_class=self._device_class,
            accuracy_decimals=1,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=_category(self._diagnostic),
        )

    def state_responses(self) -> List[message.Message]:
        if self.value is None:
            return [SensorStateResponse(key=self.key, missing_state=True)]
        return [SensorStateResponse(key=self.key, state=self.value)]


class TextSensorEntity(Entity):
    """
    A sensor of the device with a text (for example a firmware version), unknown while ``value`` is None.
    :param diagnostic: True to show it under Diagnostic in Home Assistant.
    """

    def __init__(self, key: int, object_id: str, name: str, diagnostic: bool = False) -> None:
        super().__init__(key, object_id, name)
        self.value: Optional[str] = None
        self._diagnostic = diagnostic

    def list_response(self) -> Any:
        return ListEntitiesTextSensorResponse(object_id=self.object_id, key=self.key, name=self.name, entity_category=_category(self._diagnostic))

    def state_responses(self) -> List[message.Message]:
        if self.value is None:
            return [TextSensorStateResponse(key=self.key, missing_state=True)]
        return [TextSensorStateResponse(key=self.key, state=self.value)]


class NumberEntity(Entity):
    """
    A setting of the hardware that Home Assistant can change, unknown while ``value`` is None.
    :param minimum: Lowest value.
    :param maximum: Highest value.
    :param step: Step between two values.
    :param unit: Unit of the value, empty for none.
    :param on_command: Called with the value Home Assistant asks for (within the range), returns the value the hardware has then.
    """

    def __init__(self, key: int, object_id: str, name: str, minimum: float, maximum: float, step: float, unit: str, on_command: Callable[[float], Optional[float]]) -> None:
        super().__init__(key, object_id, name)
        self.value: Optional[float] = None
        self._minimum = minimum
        self._maximum = maximum
        self._step = step
        self._unit = unit
        self._on_command = on_command

    def list_response(self) -> Any:
        return ListEntitiesNumberResponse(
            object_id=self.object_id,
            key=self.key,
            name=self.name,
            min_value=self._minimum,
            max_value=self._maximum,
            step=self._step,
            unit_of_measurement=self._unit,
            mode=NumberMode.SLIDER,
            entity_category=EntityCategory.CONFIG,
        )

    def state_responses(self) -> List[message.Message]:
        if self.value is None:
            return [NumberStateResponse(key=self.key, missing_state=True)]
        return [NumberStateResponse(key=self.key, state=self.value)]

    def handle_command(self, msg: message.Message) -> List[message.Message]:
        if not isinstance(msg, NumberCommandRequest):
            return super().handle_command(msg)
        requested = max(self._minimum, min(self._maximum, float(msg.state)))
        _LOGGER.debug("%s set by Home Assistant: %s", self.object_id, requested)
        value = self._on_command(requested)
        if value is not None:
            self.value = value
        return self.state_responses()


def _category(diagnostic: bool) -> int:
    return int(EntityCategory.DIAGNOSTIC if diagnostic else EntityCategory.NONE)
