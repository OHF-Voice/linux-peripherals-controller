"""Unit tests for lva_protocol.py."""

import json

import pytest

from linux_peripherals_controller.lva_protocol import COMMANDS, LvaEvent, build_command, lva_url, parse_event


class TestLvaUrl:
    def test_url_asks_for_version_2(self):
        assert lva_url("lva.local", 6055) == "ws://lva.local:6055/v2"


class TestParseEvent:
    def test_event_with_data(self):
        assert parse_event('{"event": "state", "data": {"state": "idle"}}') == LvaEvent("state", {"state": "idle"})

    def test_event_without_data_has_empty_data(self):
        assert parse_event('{"event": "hello"}') == LvaEvent("hello", {})

    def test_bytes_are_accepted(self):
        assert parse_event(b'{"event": "hello"}') == LvaEvent("hello", {})

    def test_data_that_is_not_an_object_is_empty(self):
        assert parse_event('{"event": "state", "data": 5}') == LvaEvent("state", {})

    @pytest.mark.parametrize("raw", ["not json", "[1]", '{"command": "x"}', '{"event": 5}', "\xff".encode("latin-1")])
    def test_anything_else_is_not_an_event(self, raw):
        assert parse_event(raw) is None


class TestBuildCommand:
    def test_command_without_data(self):
        assert json.loads(build_command("start_listening")) == {"command": "start_listening"}

    def test_command_with_data(self):
        assert json.loads(build_command("volume_set", {"volume": 40})) == {"command": "volume_set", "data": {"volume": 40}}

    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_every_command_of_version_2_can_be_built(self, name):
        assert json.loads(build_command(name))["command"] == name

    @pytest.mark.parametrize("name", ["mute_mic", "stop_pipeline", "register_light", ""])
    def test_commands_of_version_1_are_refused(self, name):
        with pytest.raises(ValueError):
            build_command(name)
