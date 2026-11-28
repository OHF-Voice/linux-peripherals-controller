"""Unit tests for the Satellite1 HAT: drivers/satellite1.py against a fake satellite1d, and devices/satellite1.py."""

import asyncio
import json
import socket
import socketserver
import threading
from unittest.mock import MagicMock

import pytest

from linux_peripherals_controller.appearance import Color
from linux_peripherals_controller.button_roles import ButtonRole
from linux_peripherals_controller.device_config import DeviceConfig
from linux_peripherals_controller.device_setup import resolve_device
from linux_peripherals_controller.device_types import SensorKind
from linux_peripherals_controller.devices import create_device, get_device_type
from linux_peripherals_controller.devices.base import DeviceCallbacks
from linux_peripherals_controller.drivers import DriverError, Drivers
from linux_peripherals_controller.drivers.satellite1 import (
    PowerContract,
    Satellite1Daemon,
    Satellite1Event,
    environment_readings,
    led_frame,
    parse_event,
    parse_response,
)
from linux_peripherals_controller.hardware_mute import HardwareMute, HardwareMuteType

CAPABILITIES = ["system.health", "environment.get_readings", "led.render", "events.subscribe"]


class FakeDaemon:
    """A satellite1d on a Unix socket in a thread: answers requests, records them and sends events to subscribers."""

    def __init__(self, path, capabilities=None, protocol_version=1):
        self.requests = []
        self.subscribers = []
        self.connections = []
        self.capabilities = CAPABILITIES if capabilities is None else capabilities
        self.protocol_version = protocol_version
        self.results = {
            "led.render": {"ok": True},
            "environment.get_readings": {"temperature_c": 21.5, "humidity_percent": 40.0, "illuminance_lux": None},
            "mics.get_muted": {"muted": True},
            "dac.get_plugged_in": {"plugged_in": False},
            "dac.get_amp_level": {"amp_level": 8},
            "dac.set_amp_level": {"amp_level": 12},
            "power.get_contract": {"available": True, "voltage": 5.0, "current": 3.0},
            "xmos.get_firmware": {"firmware": "v1.2.0"},
        }
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                owner.connections.append(self.request)
                for line in self.rfile:
                    request = json.loads(line)
                    owner.requests.append(request)
                    if request["method"] == "events.subscribe":
                        self.wfile.write(json.dumps({"id": request["id"], "result": {"subscribed": True}}).encode() + b"\n")
                        owner.subscribers.append(self.wfile)
                        continue
                    self.wfile.write(json.dumps({"id": request["id"], **owner.answer(request)}).encode() + b"\n")

        self._server = socketserver.ThreadingUnixStreamServer(str(path), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def answer(self, request):
        if request["method"] == "hello":
            return {"result": {"protocol_version": self.protocol_version, "service": "satellite1d", "capabilities": self.capabilities}}
        if request["method"] in self.results:
            return {"result": self.results[request["method"]]}
        return {"error": {"code": "method_not_found", "message": "unsupported"}}

    def send_event(self, name, data):
        for subscriber in self.subscribers:
            subscriber.write(json.dumps({"event": name, "data": data}).encode() + b"\n")
            subscriber.flush()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        for connection in self.connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()


@pytest.fixture
def socket_path(tmp_path):
    return tmp_path / "satellite1d.sock"


@pytest.fixture
def daemon(socket_path):
    fake = FakeDaemon(socket_path)
    yield fake
    fake.stop()


async def wait_for(condition):
    for _ in range(100):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met")


class TestProtocol:
    def test_led_frame_fills_up_to_24_pixels(self):
        frame = led_frame([Color(1, 2, 3)])
        assert len(frame) == 24
        assert frame[0] == [1, 2, 3] and frame[1] == [0, 0, 0]

    def test_led_frame_leaves_out_extra_pixels(self):
        assert len(led_frame([Color(1, 2, 3)] * 30)) == 24

    def test_response_result_and_errors(self):
        assert parse_response(b'{"id": 3, "result": {"a": 1}}', 3) == {"a": 1}
        with pytest.raises(ValueError, match="refused the request: nope"):
            parse_response(b'{"id": 3, "error": {"code": "x", "message": "nope"}}', 3)
        with pytest.raises(ValueError, match="invalid answer"):
            parse_response(b'{"id": 4, "result": {}}', 3)
        with pytest.raises(ValueError, match="closed the connection"):
            parse_response(b"", 3)

    def test_environment_readings_keep_numbers_only(self):
        assert environment_readings({"temperature_c": 20, "humidity_percent": "wet", "illuminance_lux": True}) == {
            "temperature_c": 20.0,
            "humidity_percent": None,
            "illuminance_lux": None,
        }

    def test_events(self):
        assert parse_event(b'{"event": "buttons.pressed", "data": {"name": "action"}}') == Satellite1Event("button", "action")
        assert parse_event(b'{"event": "mics.muted_changed", "data": {"muted": true}}') == Satellite1Event("mic_muted", True)
        assert parse_event(b'{"event": "audio.line_out_jack_changed", "data": {"plugged_in": false}}') == Satellite1Event("line_out_jack", False)

    def test_other_or_invalid_events_are_none(self):
        assert parse_event(b'{"event": "buttons.pressed", "data": {"name": "mic_mute"}}') is None
        assert parse_event(b'{"event": "mics.muted_changed", "data": {"muted": "yes"}}') is None
        assert parse_event(b'{"event": "audio.volume_changed", "data": {}}') is None
        assert parse_event(b'{"event": "buttons.pressed"}') is None
        assert parse_event(b"nope") is None


class TestDaemonConnection:
    async def test_leds_sensors_settings_and_events(self, daemon, socket_path):
        events = []
        connection = Satellite1Daemon(events.append, socket_path)
        connection.write([Color(255, 0, 0)])
        assert daemon.requests[-1]["method"] == "led.render"
        assert daemon.requests[-1]["params"]["pixels"][0] == [255, 0, 0]
        assert connection.read_environment() == {"temperature_c": 21.5, "humidity_percent": 40.0, "illuminance_lux": None}
        assert connection.mic_muted() is True
        assert connection.line_out_plugged_in() is False
        assert connection.amp_level() == 8
        assert connection.set_amp_level(12) == 12
        assert daemon.requests[-1]["params"] == {"dac": "speaker", "level": 12}
        assert connection.power_contract() == PowerContract(5.0, 3.0)
        assert connection.firmware() == "v1.2.0"
        await wait_for(lambda: daemon.subscribers)
        daemon.send_event("buttons.pressed", {"name": "volume_up"})
        daemon.send_event("mics.muted_changed", {"muted": False})
        await wait_for(lambda: len(events) == 2)
        assert events == [Satellite1Event("button", "volume_up"), Satellite1Event("mic_muted", False)]
        connection.close()

    async def test_invalid_or_missing_values_are_none(self, daemon, socket_path):
        connection = Satellite1Daemon(print, socket_path)
        daemon.results["dac.get_amp_level"] = {"amp_level": True}
        daemon.results["power.get_contract"] = {"available": False, "voltage": None, "current": None}
        del daemon.results["xmos.get_firmware"]
        assert connection.amp_level() is None
        assert connection.power_contract() is None
        assert connection.firmware() is None
        connection.close()

    async def test_missing_daemon_is_a_driver_error(self, socket_path):
        with pytest.raises(DriverError, match="satellite1d cannot be reached"):
            Satellite1Daemon(print, socket_path)

    async def test_disabled_led_ring_is_a_driver_error(self, socket_path):
        fake = FakeDaemon(socket_path, capabilities=["system.health"])
        try:
            with pytest.raises(DriverError, match=r"\[led_ring\] enabled = true"):
                Satellite1Daemon(print, socket_path)
        finally:
            fake.stop()

    async def test_other_protocol_version_is_a_driver_error(self, socket_path):
        fake = FakeDaemon(socket_path, protocol_version=2)
        try:
            with pytest.raises(DriverError, match="protocol version 2"):
                Satellite1Daemon(print, socket_path)
        finally:
            fake.stop()

    async def test_lost_daemon_is_logged_once_and_reads_give_nothing(self, daemon, socket_path, caplog):
        connection = Satellite1Daemon(print, socket_path)
        daemon.stop()
        socket_path.unlink()
        connection.write([Color(1, 1, 1)])
        connection.write([Color(2, 2, 2)])
        assert caplog.text.count("Cannot show the LEDs through satellite1d") == 1
        assert connection.read_environment() == {}
        assert connection.mic_muted() is None
        connection.close()


class TestDevice:
    def make(self):
        drivers = MagicMock(spec=Drivers)
        drivers.satellite1.return_value.mic_muted.return_value = False
        device = create_device(resolve_device(get_device_type("satellite1"), DeviceConfig()), drivers)
        return device, drivers

    def test_device_type(self):
        device_type = get_device_type("satellite1")
        assert device_type.leds.count == 24
        assert [(b.name, b.role, b.pin) for b in device_type.buttons] == [
            ("action", ButtonRole.ACTION, None),
            ("volume_up", ButtonRole.VOLUME_UP, None),
            ("volume_down", ButtonRole.VOLUME_DOWN, None),
        ]
        assert [(s.name, s.kind, s.unit, s.device_class, s.diagnostic, s.interval) for s in device_type.sensors] == [
            ("temperature", SensorKind.NUMBER, "°C", "temperature", False, 60.0),
            ("humidity", SensorKind.NUMBER, "%", "humidity", False, 60.0),
            ("illuminance", SensorKind.NUMBER, "lx", "illuminance", False, 60.0),
            ("line_out_jack", SensorKind.BINARY, "", "plug", False, None),
            ("usb_c_voltage", SensorKind.NUMBER, "V", "voltage", True, 60.0),
            ("usb_c_current", SensorKind.NUMBER, "A", "current", True, 60.0),
            ("xmos_firmware", SensorKind.TEXT, "", "", True, None),
        ]
        assert [(c.name, c.minimum, c.maximum, c.step) for c in device_type.controls] == [("amplifier_level", 0, 20, 1.0)]

    def test_the_daemon_is_the_led_strip_and_a_press_is_a_click(self):
        device, drivers = self.make()
        on_button = MagicMock()
        device.open(DeviceCallbacks(on_button=on_button))
        assert device.leds is drivers.satellite1.return_value
        on_event = drivers.satellite1.call_args.args[0]
        on_event(Satellite1Event("button", "action"))
        assert [c.args for c in on_button.call_args_list] == [("action", True), ("action", False)]
        drivers.gpio_input.assert_not_called()

    def test_mute_switch_is_a_read_only_hardware_mute(self):
        device, drivers = self.make()
        drivers.satellite1.return_value.mic_muted.return_value = True
        on_hardware_mute = MagicMock()
        device.open(DeviceCallbacks(on_hardware_mute=on_hardware_mute))
        assert device.hardware_mute == HardwareMute(HardwareMuteType.READ_ONLY, True)
        drivers.satellite1.call_args.args[0](Satellite1Event("mic_muted", False))
        on_hardware_mute.assert_called_once_with(HardwareMute(HardwareMuteType.READ_ONLY, False))

    def test_unreadable_mute_switch_counts_as_not_muted(self):
        device, drivers = self.make()
        drivers.satellite1.return_value.mic_muted.return_value = None
        device.open(DeviceCallbacks())
        assert not device.hardware_mute.muted

    def test_jack_is_reported_as_a_sensor(self):
        device, drivers = self.make()
        on_sensor = MagicMock()
        device.open(DeviceCallbacks(on_sensor=on_sensor))
        drivers.satellite1.return_value.line_out_plugged_in.return_value = True
        assert device.read_sensor("line_out_jack") is True
        drivers.satellite1.call_args.args[0](Satellite1Event("line_out_jack", False))
        on_sensor.assert_called_once_with("line_out_jack", False)

    def test_sensors_are_read_through_the_daemon(self):
        device, drivers = self.make()
        device.open(DeviceCallbacks())
        daemon = drivers.satellite1.return_value
        daemon.read_environment.return_value = {"temperature_c": 21.5, "illuminance_lux": None}
        daemon.power_contract.return_value = PowerContract(9.0, 2.0)
        daemon.firmware.return_value = "v1.2.0"
        assert device.read_sensor("temperature") == 21.5
        assert device.read_sensor("illuminance") is None
        assert device.read_sensor("humidity") is None
        assert device.read_sensor("usb_c_voltage") == 9.0
        assert device.read_sensor("usb_c_current") == 2.0
        assert device.read_sensor("xmos_firmware") == "v1.2.0"
        assert device.read_sensor("pressure") is None
        daemon.power_contract.return_value = None
        assert device.read_sensor("usb_c_voltage") is None

    def test_amplifier_level(self):
        device, drivers = self.make()
        device.open(DeviceCallbacks())
        daemon = drivers.satellite1.return_value
        daemon.amp_level.return_value = 8
        daemon.set_amp_level.return_value = 13
        assert device.read_control("amplifier_level") == 8.0
        assert device.set_control("amplifier_level", 12.6) == 13.0
        daemon.set_amp_level.assert_called_once_with(13)
        assert device.read_control("other") is None

    def test_nothing_before_open(self):
        device, _ = self.make()
        assert device.read_sensor("temperature") is None
        assert device.read_control("amplifier_level") is None

    def test_simulated(self):
        device = create_device(resolve_device(get_device_type("satellite1"), DeviceConfig()), Drivers(simulated=True))
        device.open(DeviceCallbacks())
        assert device.leds.count == 24
        assert device.read_sensor("temperature") is None
        assert device.read_sensor("usb_c_voltage") is None
        assert device.read_control("amplifier_level") is None
        assert device.set_control("amplifier_level", 5) is None
        device.close()
