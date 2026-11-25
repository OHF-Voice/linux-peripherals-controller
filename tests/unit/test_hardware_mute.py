"""Unit tests for hardware_mute.py."""

import pytest

from linux_peripherals_controller.button_roles import LvaCommand
from linux_peripherals_controller.hardware_mute import HardwareMute, MuteRequest, commands_for_changes, decide_mute_request
from linux_peripherals_controller.lva_protocol import COMMANDS

POSSIBLE_UNMUTED = HardwareMute(possible=True, muted=False)
POSSIBLE_MUTED = HardwareMute(possible=True, muted=True)
FIXED_MUTED = HardwareMute(possible=False, muted=True)


class TestCommandsForChanges:
    def test_new_connection_tells_everything_possible_first(self):
        assert commands_for_changes(None, POSSIBLE_UNMUTED) == (
            LvaCommand("hardware_mute_possible", {"possible": True}),
            LvaCommand("hardware_mute_status", {"status": "unmuted"}),
        )

    def test_muted_is_told_as_muted(self):
        assert commands_for_changes(None, POSSIBLE_MUTED)[1] == LvaCommand("hardware_mute_status", {"status": "muted"})

    def test_not_possible_is_told_as_false(self):
        assert commands_for_changes(None, FIXED_MUTED)[0] == LvaCommand("hardware_mute_possible", {"possible": False})

    def test_only_the_status_if_only_that_changed(self):
        assert commands_for_changes(POSSIBLE_UNMUTED, POSSIBLE_MUTED) == (LvaCommand("hardware_mute_status", {"status": "muted"}),)

    def test_only_possible_if_only_that_changed(self):
        assert commands_for_changes(POSSIBLE_MUTED, FIXED_MUTED) == (LvaCommand("hardware_mute_possible", {"possible": False}),)

    def test_nothing_if_nothing_changed(self):
        assert commands_for_changes(POSSIBLE_MUTED, POSSIBLE_MUTED) == ()

    @pytest.mark.parametrize("previous", [None, POSSIBLE_MUTED])
    def test_nothing_for_a_device_without_a_hardware_mute(self, previous):
        assert commands_for_changes(previous, None) == ()

    def test_every_command_is_one_of_version_2(self):
        for command in commands_for_changes(None, POSSIBLE_MUTED):
            assert command.name in COMMANDS


class TestDecideMuteRequest:
    @pytest.mark.parametrize("event,muted", [("hardware_mute_on", True), ("hardware_mute_off", False)])
    def test_a_possible_request_is_carried_out(self, event, muted):
        request = decide_mute_request(event, POSSIBLE_UNMUTED)
        assert request.muted is muted
        assert event in request.reason

    @pytest.mark.parametrize("event", ["hardware_mute_on", "hardware_mute_off"])
    def test_ignored_if_software_cannot_switch_it(self, event):
        request = decide_mute_request(event, FIXED_MUTED)
        assert request.muted is None
        assert "software cannot switch" in request.reason

    @pytest.mark.parametrize("event", ["hardware_mute_on", "hardware_mute_off"])
    def test_ignored_if_the_device_has_no_hardware_mute(self, event):
        request = decide_mute_request(event, None)
        assert request.muted is None
        assert "no hardware mute" in request.reason

    def test_a_request_for_the_state_it_already_has_is_still_carried_out(self):
        assert decide_mute_request("hardware_mute_on", POSSIBLE_MUTED).muted is True

    @pytest.mark.parametrize("event", ["state", "hardware_mute_status", ""])
    def test_other_events_are_no_request(self, event):
        assert decide_mute_request(event, POSSIBLE_UNMUTED) == MuteRequest(f"{event} is not a request to switch the hardware mute")
