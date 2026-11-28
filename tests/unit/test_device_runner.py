"""Unit tests for device_runner.py."""

import asyncio
import logging
from unittest.mock import MagicMock

import pytest
from aioesphomeapi.api_pb2 import EventResponse, SwitchStateResponse  # type: ignore[attr-defined]

from linux_peripherals_controller.animation import DisplayState
from linux_peripherals_controller.button_roles import ButtonRole
from linux_peripherals_controller.device_config import DeviceConfig
from linux_peripherals_controller.device_runner import DeviceRunner
from linux_peripherals_controller.device_setup import resolve_device
from linux_peripherals_controller.device_types import ButtonSpec, ControlSpec, DeviceType, LedSpec, SensorKind, SensorSpec
from linux_peripherals_controller.devices import create_device, get_device_type
from linux_peripherals_controller.devices.base import BaseDevice
from linux_peripherals_controller.display import DisplayFunction
from linux_peripherals_controller.drivers import Drivers
from linux_peripherals_controller.esphome.entities import BinarySensorEntity, ButtonEventEntity, LightEntity, NumberEntity, SensorEntity, SwitchEntity, TextSensorEntity
from linux_peripherals_controller.hardware_mute import HardwareMute, HardwareMuteType
from linux_peripherals_controller.light import LightState
from linux_peripherals_controller.lva_protocol import LvaMessage
from linux_peripherals_controller.lva_status import LvaStatus
from linux_peripherals_controller.state_store import StoredState


class RecordingDevice(BaseDevice):
    """A device that records what it is asked to draw and can have a hardware mute and a sensor."""

    hardware = HardwareMute()
    sensor_value = None
    control_value = None

    def __init__(self, device, drivers):
        super().__init__(device, drivers)
        self.drawn = []
        self.switched = []
        self.controls_set = []
        self.sensors_read = []

    def draw(self, display, now):
        self.drawn.append(display)

    def is_animated(self, display):
        return False

    @property
    def hardware_mute(self):
        return self.hardware

    def switch_hardware_mute(self, muted):
        self.switched.append(muted)

    def read_sensor(self, name):
        self.sensors_read.append(name)
        return "v1" if name == "firmware" else self.sensor_value

    def read_control(self, name):
        return self.control_value

    def set_control(self, name, value):
        self.controls_set.append((name, value))
        return value


TYPE = DeviceType(
    name="test",
    description="Test device",
    leds=LedSpec("apa102", 3),
    buttons=(ButtonSpec("talk", ButtonRole.ACTION, pin=17), ButtonSpec("volume_up", ButtonRole.VOLUME_UP)),
    sensors=(
        SensorSpec("temperature", interval=0.01),
        SensorSpec("jack", interval=None, kind=SensorKind.BINARY),
        SensorSpec("firmware", interval=None, kind=SensorKind.TEXT, diagnostic=True),
    ),
    controls=(ControlSpec("level", 0, 20),),
)


def make_runner(stored=None, hardware=None, device_type=TYPE):
    device = RecordingDevice(resolve_device(device_type, DeviceConfig()), Drivers(simulated=True))
    if hardware is not None:
        device.hardware = hardware
    saved = []
    runner = DeviceRunner(device, stored or StoredState(), saved.append, clock=lambda: 50.0)
    return runner, device, saved


def attach(runner, link_connected=True, status=None, create_entities=True):
    controller = MagicMock()
    controller.link_connected = link_connected
    controller.status = status or LvaStatus(lva_status="connected", state="idle")
    home_assistant = MagicMock()
    if create_entities:
        runner.entities()
    runner.attach(controller, home_assistant)
    return controller, home_assistant


class TestEntities:
    def test_light_buttons_child_lock_and_sensors_in_order(self):
        runner, _, _ = make_runner()
        entities = runner.entities()
        assert [(type(e), e.key, e.object_id, e.name) for e in entities] == [
            (LightEntity, 0, "led", "LED"),
            (ButtonEventEntity, 1, "talk", "Talk"),
            (ButtonEventEntity, 2, "volume_up", "Volume up"),
            (SwitchEntity, 3, "child_lock", "Child Lock"),
            (SensorEntity, 4, "temperature", "Temperature"),
            (BinarySensorEntity, 5, "jack", "Jack"),
            (TextSensorEntity, 6, "firmware", "Firmware"),
            (NumberEntity, 7, "level", "Level"),
        ]

    def test_no_light_without_leds(self):
        runner, _, _ = make_runner(device_type=get_device_type("jabra_speak_410"))
        assert not any(isinstance(e, LightEntity) for e in runner.entities())

    @pytest.mark.parametrize("kind,entity_class", [(HardwareMuteType.CHANGEABLE, SwitchEntity), (HardwareMuteType.READ_ONLY, BinarySensorEntity)])
    def test_hardware_mute_entity_follows_its_type(self, kind, entity_class):
        runner, _, _ = make_runner(hardware=HardwareMute(kind, True))
        runner.open()
        entity = [e for e in runner.entities() if e.object_id == "hardware_mute"][0]
        assert isinstance(entity, entity_class)
        assert entity.state_responses()[0].state

    async def test_read_only_mute_change_updates_the_binary_sensor(self):
        runner, device, _ = make_runner(hardware=HardwareMute(HardwareMuteType.READ_ONLY, False))
        runner.open()
        entity = [e for e in runner.entities() if e.object_id == "hardware_mute"][0]
        attach(runner, create_entities=False)
        device.hardware = HardwareMute(HardwareMuteType.READ_ONLY, True)
        device.report_hardware_mute()
        assert entity.value is True


class TestDisplay:
    async def test_open_shows_no_connection(self):
        runner, device, _ = make_runner()
        runner.open()
        assert device.drawn == [DisplayState(DisplayFunction.NO_CONNECTION, None, LightState(), 50.0)]

    async def test_display_function_and_amount(self):
        runner, device, _ = make_runner()
        runner.open()
        runner.display_changed(DisplayFunction.VOLUME)
        runner.status_changed(LvaStatus(volume=40))
        assert device.drawn[-1] == DisplayState(DisplayFunction.VOLUME, 0.4, LightState(), 50.0)

    async def test_unchanged_display_is_not_drawn_again(self):
        runner, device, _ = make_runner()
        runner.open()
        runner.status_changed(LvaStatus(volume=40))
        assert len(device.drawn) == 1

    async def test_light_change_is_stored_and_drawn(self):
        runner, device, saved = make_runner()
        runner.open()
        runner.display_changed(None)
        light = LightState(on=True)
        runner.set_light(light)
        assert device.drawn[-1].light == light
        assert saved == [StoredState(light=light)]


class TestButtons:
    async def test_press_goes_to_lva_and_to_home_assistant(self, caplog):
        runner, _, _ = make_runner()
        runner.open()
        controller, home_assistant = attach(runner)
        with caplog.at_level(logging.DEBUG):
            runner._handle_press("talk", "single")  # pylint: disable=protected-access
        controller.send_messages.assert_called_once_with((LvaMessage("listening_start"), LvaMessage("button_pressed", {"press": "single"})))
        home_assistant.broadcast.assert_called_once_with([EventResponse(key=1, event_type="single_press")])
        assert "Button 'talk': single press of action: listening_start" in caplog.text

    async def test_child_lock_keeps_lva_out_but_not_home_assistant(self):
        runner, _, saved = make_runner()
        runner.open()
        controller, home_assistant = attach(runner)
        runner.set_child_lock(True)
        runner._handle_press("talk", "double")  # pylint: disable=protected-access
        controller.send_messages.assert_not_called()
        home_assistant.broadcast.assert_called_once()
        assert saved[-1].child_lock

    async def test_repeat_is_not_reported_to_home_assistant(self):
        runner, _, _ = make_runner()
        runner.open()
        controller, home_assistant = attach(runner)
        runner._handle_press("volume_up", "repeat")  # pylint: disable=protected-access
        controller.send_messages.assert_called_once_with((LvaMessage("volume_up"),))
        home_assistant.broadcast.assert_not_called()

    async def test_press_before_attach_does_nothing(self):
        runner, _, _ = make_runner()
        runner.open()
        runner._handle_press("talk", "single")  # pylint: disable=protected-access


class TestHardwareMute:
    async def test_attach_tells_lva(self):
        hardware = HardwareMute(HardwareMuteType.CHANGEABLE, False)
        runner, _, _ = make_runner(hardware=hardware)
        runner.open()
        controller, _ = attach(runner)
        controller.set_hardware_mute.assert_called_once_with(hardware)

    async def test_change_of_the_device_goes_to_lva_and_home_assistant(self):
        runner, device, _ = make_runner(hardware=HardwareMute(HardwareMuteType.CHANGEABLE, False))
        runner.open()
        controller, home_assistant = attach(runner)
        device.hardware = HardwareMute(HardwareMuteType.CHANGEABLE, True)
        device.report_hardware_mute()
        controller.set_hardware_mute.assert_called_with(device.hardware)
        home_assistant.broadcast.assert_called_once_with([SwitchStateResponse(key=4, state=True)])

    async def test_request_switches_only_a_changeable_mute(self):
        runner, device, _ = make_runner(hardware=HardwareMute(HardwareMuteType.READ_ONLY, False))
        runner.open()
        runner.request_hardware_mute(True)
        assert device.switched == []
        runner, device, _ = make_runner(hardware=HardwareMute(HardwareMuteType.CHANGEABLE, False))
        runner.open()
        runner.request_hardware_mute(True)
        assert device.switched == [True]


class TestSensors:
    async def test_failed_reading_is_warned_once_and_a_value_is_broadcast(self, caplog):
        runner, device, _ = make_runner()
        runner.open()
        _, home_assistant = attach(runner)
        task = asyncio.create_task(runner.read_values())
        await asyncio.sleep(0.05)
        device.sensor_value = 21.0
        await asyncio.sleep(0.05)
        task.cancel()
        assert caplog.text.count("Sensor 'temperature' cannot be read") == 1
        assert home_assistant.broadcast.called

    async def test_device_without_sensors_returns_at_once(self):
        runner, _, _ = make_runner(device_type=get_device_type("respeaker_2mic_v1"))
        await asyncio.wait_for(runner.read_values(), 1)

    async def test_sensor_without_interval_is_read_once(self):
        runner, device, _ = make_runner()
        runner.open()
        entities = runner.entities()
        attach(runner, create_entities=False)
        task = asyncio.create_task(runner.read_values())
        await asyncio.sleep(0.05)
        task.cancel()
        assert device.sensors_read.count("firmware") == 1
        assert device.sensors_read.count("temperature") > 1
        assert [e for e in entities if e.object_id == "firmware"][0].value == "v1"

    async def test_reported_sensor_is_broadcast_and_a_wrong_kind_is_unknown(self, caplog):
        runner, device, _ = make_runner()
        runner.open()
        entities = runner.entities()
        _, home_assistant = attach(runner, create_entities=False)
        jack = [e for e in entities if e.object_id == "jack"][0]
        with caplog.at_level(logging.DEBUG):
            device.report_sensor("jack", True)
        assert jack.value is True
        home_assistant.broadcast.assert_called_once_with(jack.state_responses())
        assert "Sensor 'jack' reported by the device: True" in caplog.text
        device.report_sensor("jack", "yes")
        assert jack.value is None
        device.report_sensor("unknown", True)


class TestControls:
    async def test_control_is_read_at_startup_and_set_by_home_assistant(self):
        runner, device, _ = make_runner()
        device.control_value = 8.0
        runner.open()
        level = [e for e in runner.entities() if e.object_id == "level"][0]
        _, home_assistant = attach(runner, create_entities=False)
        task = asyncio.create_task(runner.read_values())
        await asyncio.sleep(0.02)
        task.cancel()
        assert level.value == 8.0
        home_assistant.broadcast.assert_any_call(level.state_responses())
        from aioesphomeapi.api_pb2 import NumberCommandRequest  # type: ignore[attr-defined]

        level.handle_command(NumberCommandRequest(key=level.key, state=12))
        assert device.controls_set == [("level", 12.0)]
        assert level.value == 12.0

    async def test_unreadable_control_is_warned(self, caplog):
        runner, _, _ = make_runner()
        runner.open()
        runner.entities()
        attach(runner)
        task = asyncio.create_task(runner.read_values())
        await asyncio.sleep(0.02)
        task.cancel()
        assert "'level' cannot be read" in caplog.text


class TestWithARealDevice:
    async def test_simulated_2mic_opens_and_closes(self):
        device = create_device(resolve_device(get_device_type("respeaker_2mic_v1"), DeviceConfig()), Drivers(simulated=True))
        runner = DeviceRunner(device, StoredState(), MagicMock())
        runner.open()
        runner.display_changed(DisplayFunction.LISTENING)
        await asyncio.sleep(0.05)
        runner.close()
