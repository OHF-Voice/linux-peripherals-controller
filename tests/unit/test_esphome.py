"""Unit tests for esphome/: entities, server, discovery and the encryption key, also with the client Home Assistant uses."""

import base64
import logging
from unittest.mock import MagicMock

import pytest
from aioesphomeapi import APIClient
from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    DeviceInfoRequest,
    EventResponse,
    LightCommandRequest,
    LightStateResponse,
    ListEntitiesDoneResponse,
    ListEntitiesRequest,
    SensorStateResponse,
    SubscribeStatesRequest,
    SwitchCommandRequest,
    SwitchStateResponse,
)
from aioesphomeapi.model import EventInfo, LightInfo, SwitchInfo

from linux_peripherals_controller.esphome.api_server import create_encryption_key_file, decode_encryption_key, load_encryption_key_file
from linux_peripherals_controller.esphome.discovery import local_ip_address, service_properties
from linux_peripherals_controller.esphome.entities import EVENT_TYPES, BinarySensorEntity, ButtonEventEntity, LightEntity, SensorEntity, SwitchEntity
from linux_peripherals_controller.esphome.server import DeviceInfo, HomeAssistantServer
from linux_peripherals_controller.light import LightState

INFO = DeviceInfo("lpc-test", "Linux Peripheral Controller", "aa:bb:cc:dd:ee:ff", "Test device", "1.0", "46.30.1")


class TestEntities:
    def test_light_command_changes_the_light_and_calls_back(self):
        on_change = MagicMock()
        light = LightEntity(0, "led", "LED", LightState(), on_change)
        responses = light.handle_command(LightCommandRequest(key=0, has_state=True, state=True, has_rgb=True, red=1.0, green=0.0, blue=0.0))
        on_change.assert_called_once_with(LightState(on=True, red=1.0, green=0.0, blue=0.0))
        assert isinstance(responses[0], LightStateResponse) and responses[0].state

    def test_light_ignores_other_commands(self):
        light = LightEntity(0, "led", "LED", LightState(), MagicMock())
        assert light.handle_command(SwitchCommandRequest(key=0, state=True)) == []

    def test_button_event_has_no_state_before_the_first_press(self):
        button = ButtonEventEntity(1, "button", "Button")
        assert button.state_responses() == []
        assert button.press("double") == [EventResponse(key=1, event_type="double_press")]
        assert button.list_response().event_types == EVENT_TYPES

    def test_switch_asks_its_owner_and_reports_its_state(self):
        state = {"on": False}
        switch = SwitchEntity(2, "child_lock", "Child Lock", lambda: state["on"], lambda value: state.update(on=value), "mdi:lock")
        assert switch.handle_command(SwitchCommandRequest(key=2, state=True)) == [SwitchStateResponse(key=2, state=True)]

    def test_binary_sensor_reports_its_state(self):
        sensor = BinarySensorEntity(3, "hardware_mute", "Hardware Mute", lambda: True, "mdi:microphone-off")
        assert sensor.state_responses()[0].state

    def test_sensor_is_missing_until_read(self):
        sensor = SensorEntity(4, "temperature", "Temperature")
        assert sensor.state_responses() == [SensorStateResponse(key=4, missing_state=True)]
        sensor.value = 21.5
        assert sensor.state_responses() == [SensorStateResponse(key=4, state=21.5)]


class TestServerMessages:
    def make_server(self):
        light = LightEntity(0, "led", "LED", LightState(), MagicMock())
        button = ButtonEventEntity(1, "button", "Button")
        return HomeAssistantServer(INFO, [light, button])

    def test_device_info(self):
        (response,) = list(self.make_server().handle_message(DeviceInfoRequest()))
        assert (response.name, response.mac_address, response.model, response.project_version) == ("lpc-test", "aa:bb:cc:dd:ee:ff", "Test device", "1.0")
        assert not response.api_encryption_supported

    def test_list_entities_ends_with_done(self):
        responses = list(self.make_server().handle_message(ListEntitiesRequest()))
        assert [r.key for r in responses[:2]] == [0, 1]
        assert isinstance(responses[-1], ListEntitiesDoneResponse)

    def test_states_leave_out_entities_without_a_state(self):
        responses = list(self.make_server().handle_message(SubscribeStatesRequest()))
        assert len(responses) == 1 and isinstance(responses[0], LightStateResponse)

    def test_command_is_answered_to_every_client(self):
        server = self.make_server()
        connection = MagicMock()
        server.connected(connection)
        assert not list(server.handle_message(LightCommandRequest(key=0, has_state=True, state=True)))
        connection.send_messages.assert_called_once()

    def test_command_for_an_unknown_key_is_ignored(self, caplog):
        with caplog.at_level(logging.DEBUG):
            assert not list(self.make_server().handle_message(SwitchCommandRequest(key=9, state=True)))
        assert "unknown entity key 9" in caplog.text


class TestWithTheClientOfHomeAssistant:
    async def connect(self, noise_psk=None):
        state = {"locked": False}
        entities = [
            LightEntity(0, "led", "LED", LightState(), MagicMock()),
            ButtonEventEntity(1, "button", "Button"),
            SwitchEntity(2, "child_lock", "Child Lock", lambda: state["locked"], lambda value: state.update(locked=value), "mdi:lock"),
        ]
        server = HomeAssistantServer(INFO, entities, noise_psk)
        port = await server.start("127.0.0.1", 0)
        client = APIClient("127.0.0.1", port, None, noise_psk=base64.b64encode(noise_psk).decode() if noise_psk else None)
        await client.connect(login=True)
        return server, client, state

    async def test_device_info_and_entities(self):
        server, client, _ = await self.connect()
        try:
            info = await client.device_info()
            assert (info.name, info.model, info.project_name) == ("lpc-test", "Test device", "Open Home Foundation.Linux Peripheral Controller")
            entities, _ = await client.list_entities_services()
            assert [type(e) for e in entities] == [LightInfo, EventInfo, SwitchInfo]
        finally:
            await client.disconnect()
            await server.stop()

    async def test_switch_command(self):
        server, client, state = await self.connect()
        try:
            await client.list_entities_services()
            client.switch_command(2, True)
            await client.device_info()
            assert state["locked"]
        finally:
            await client.disconnect()
            await server.stop()

    async def test_encrypted_connection(self):
        server, client, _ = await self.connect(noise_psk=bytes(range(32)))
        try:
            info = await client.device_info()
            assert info.api_encryption_supported
        finally:
            await client.disconnect()
            await server.stop()


class TestEncryptionKey:
    def test_created_key_is_read_again(self, tmp_path):
        path = tmp_path / "keys" / "encryption.key"
        key = create_encryption_key_file(path)
        assert load_encryption_key_file(path) == base64.b64decode(key)
        assert path.stat().st_mode & 0o077 == 0

    def test_wrong_length_is_refused(self):
        with pytest.raises(ValueError, match="32 bytes"):
            decode_encryption_key(base64.b64encode(b"short").decode())


class TestDiscovery:
    def test_service_properties(self):
        assert service_properties("AA:BB:CC:DD:EE:FF", False)["mac"] == "aabbccddeeff"
        assert "api_encryption" not in service_properties("aa", False)
        assert service_properties("aa", True)["api_encryption"] == "Noise_NNpsk0_25519_ChaChaPoly_SHA256"

    def test_local_ip_address_is_an_ipv4_address(self):
        assert local_ip_address().count(".") == 3
