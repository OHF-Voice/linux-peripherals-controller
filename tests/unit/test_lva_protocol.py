"""Unit tests for lva_protocol.py."""

import json

import pytest

from linux_peripherals_controller.lva_protocol import COMMANDS, REPORTED_EVENTS, LvaEvent, LvaRequest, build_message, lva_url, parse_message


class TestLvaUrl:
    def test_url_asks_for_version_2(self):
        assert lva_url("lva.local", 6055) == "ws://lva.local:6055/v2"


class TestParseMessage:
    def test_event_with_data(self):
        assert parse_message('{"event": "state", "data": {"state": "idle"}}') == LvaEvent("state", {"state": "idle"})

    def test_event_without_data_has_empty_data(self):
        assert parse_message('{"event": "hello"}') == LvaEvent("hello", {})

    def test_bytes_are_accepted(self):
        assert parse_message(b'{"event": "hello"}') == LvaEvent("hello", {})

    def test_data_that_is_not_an_object_is_empty(self):
        assert parse_message('{"event": "state", "data": 5}') == LvaEvent("state", {})

    def test_a_command_of_lva_is_a_request(self):
        assert parse_message('{"command": "hardware_mute_on"}') == LvaRequest("hardware_mute_on", {})

    def test_a_request_keeps_its_data(self):
        assert parse_message('{"command": "x", "data": {"a": 1}}') == LvaRequest("x", {"a": 1})

    @pytest.mark.parametrize("raw", ["not json", "[1]", '{"event": 5}', '{"command": 5}', "{}", "\xff".encode("latin-1")])
    def test_anything_else_is_neither(self, raw):
        assert parse_message(raw) is None


class TestBuildMessage:
    def test_command_without_data(self):
        assert json.loads(build_message("listening_start")) == {"command": "listening_start"}

    def test_command_with_data(self):
        assert json.loads(build_message("volume_set", {"volume": 40})) == {"command": "volume_set", "data": {"volume": 40}}

    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_every_command_of_version_2_is_sent_as_a_command(self, name):
        assert json.loads(build_message(name))["command"] == name

    def test_the_hardware_mute_is_reported_as_an_event(self):
        assert json.loads(build_message("hardware_mute_status", {"status": "muted"})) == {"event": "hardware_mute_status", "data": {"status": "muted"}}
        assert json.loads(build_message("hardware_mute_type", {"type": "changeable"})) == {"event": "hardware_mute_type", "data": {"type": "changeable"}}

    @pytest.mark.parametrize("name", sorted(REPORTED_EVENTS))
    def test_reported_events_are_not_commands(self, name):
        assert name not in COMMANDS
        assert "event" in json.loads(build_message(name))

    @pytest.mark.parametrize("name", ["stop", "start_listening", "hardware_mute_on", "hardware_mute_off", "mute_mic", "register_light", ""])
    def test_old_and_unknown_names_are_refused(self, name):
        with pytest.raises(ValueError):
            build_message(name)

    def test_volume_silent_and_the_listening_commands_exist(self):
        assert {"listening_start", "listening_stop", "volume_silent"} <= COMMANDS
