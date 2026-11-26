"""Unit tests for hardware_mute.py."""

import pytest

from linux_peripherals_controller.hardware_mute import (
    HardwareMute,
    HardwareMuteEntity,
    HardwareMuteType,
    MuteRequest,
    decide_mute_request,
    entity_for,
    messages_for_changes,
)
from linux_peripherals_controller.lva_protocol import COMMANDS, REPORTED_EVENTS, LvaMessage

NONE = HardwareMute()
CHANGEABLE_UNMUTED = HardwareMute(HardwareMuteType.CHANGEABLE, muted=False)
CHANGEABLE_MUTED = HardwareMute(HardwareMuteType.CHANGEABLE, muted=True)
READ_ONLY_MUTED = HardwareMute(HardwareMuteType.READ_ONLY, muted=True)


class TestType:
    def test_values_are_the_words_of_the_api(self):
        assert [t.value for t in HardwareMuteType] == ["none", "changeable", "read_only"]

    def test_a_device_has_no_hardware_mute_by_default(self):
        assert HardwareMute() == HardwareMute(HardwareMuteType.NONE, False)


class TestCommandsForChanges:
    def test_new_connection_tells_the_type_first_then_the_status(self):
        assert messages_for_changes(None, CHANGEABLE_UNMUTED) == (
            LvaMessage("hardware_mute_type", {"type": "changeable"}),
            LvaMessage("hardware_mute_status", {"status": "unmuted"}),
        )

    def test_muted_is_told_as_muted(self):
        assert messages_for_changes(None, CHANGEABLE_MUTED)[1] == LvaMessage("hardware_mute_status", {"status": "muted"})

    def test_read_only_is_told_with_its_status(self):
        assert messages_for_changes(None, READ_ONLY_MUTED) == (
            LvaMessage("hardware_mute_type", {"type": "read_only"}),
            LvaMessage("hardware_mute_status", {"status": "muted"}),
        )

    def test_a_device_without_a_hardware_mute_tells_only_the_type(self):
        assert messages_for_changes(None, NONE) == (LvaMessage("hardware_mute_type", {"type": "none"}),)

    def test_only_the_status_if_only_that_changed(self):
        assert messages_for_changes(CHANGEABLE_UNMUTED, CHANGEABLE_MUTED) == (LvaMessage("hardware_mute_status", {"status": "muted"}),)

    def test_only_the_type_if_only_that_changed(self):
        assert messages_for_changes(CHANGEABLE_MUTED, READ_ONLY_MUTED) == (LvaMessage("hardware_mute_type", {"type": "read_only"}),)

    def test_the_status_is_told_when_a_hardware_mute_appears(self):
        assert [c.name for c in messages_for_changes(NONE, CHANGEABLE_UNMUTED)] == ["hardware_mute_type", "hardware_mute_status"]

    def test_the_status_is_not_told_when_the_hardware_mute_goes_away(self):
        assert [c.name for c in messages_for_changes(CHANGEABLE_MUTED, NONE)] == ["hardware_mute_type"]

    @pytest.mark.parametrize("hardware", [NONE, CHANGEABLE_MUTED, READ_ONLY_MUTED])
    def test_nothing_if_nothing_changed(self, hardware):
        assert messages_for_changes(hardware, hardware) == ()

    def test_the_status_of_a_device_without_hardware_mute_is_never_told(self):
        assert messages_for_changes(NONE, HardwareMute(HardwareMuteType.NONE, muted=True)) == ()

    def test_every_message_is_an_event_of_version_2(self):
        for hardware in (NONE, CHANGEABLE_MUTED, READ_ONLY_MUTED):
            for message in messages_for_changes(None, hardware):
                assert message.name in REPORTED_EVENTS
                assert message.name not in COMMANDS

    def test_the_old_name_is_not_an_event_any_more(self):
        assert "hardware_mute_possible" not in REPORTED_EVENTS


class TestDecideMuteRequest:
    @pytest.mark.parametrize("event,muted", [("hardware_mute_on", True), ("hardware_mute_off", False)])
    def test_a_changeable_hardware_mute_is_switched(self, event, muted):
        request = decide_mute_request(event, CHANGEABLE_UNMUTED)
        assert request.muted is muted
        assert event in request.reason

    @pytest.mark.parametrize("event", ["hardware_mute_on", "hardware_mute_off"])
    def test_ignored_if_it_can_only_be_read(self, event):
        request = decide_mute_request(event, READ_ONLY_MUTED)
        assert request.muted is None
        assert "can only be read" in request.reason

    @pytest.mark.parametrize("event", ["hardware_mute_on", "hardware_mute_off"])
    def test_ignored_if_the_device_has_no_hardware_mute(self, event):
        request = decide_mute_request(event, NONE)
        assert request.muted is None
        assert "no hardware mute" in request.reason

    def test_a_request_for_the_state_it_already_has_is_still_carried_out(self):
        assert decide_mute_request("hardware_mute_on", CHANGEABLE_MUTED).muted is True

    @pytest.mark.parametrize("event", ["state", "hardware_mute_status", ""])
    def test_other_names_are_no_request(self, event):
        assert decide_mute_request(event, CHANGEABLE_UNMUTED) == MuteRequest(f"{event} is not a request to switch the hardware mute")


class TestEntityFor:
    def test_a_changeable_hardware_mute_gets_a_switch(self):
        assert entity_for(CHANGEABLE_UNMUTED) == HardwareMuteEntity.SWITCH

    def test_a_read_only_hardware_mute_gets_a_binary_sensor(self):
        assert entity_for(READ_ONLY_MUTED) == HardwareMuteEntity.BINARY_SENSOR

    def test_no_hardware_mute_gets_no_entity(self):
        assert entity_for(NONE) is None

    def test_the_state_does_not_matter(self):
        assert entity_for(CHANGEABLE_MUTED) == entity_for(CHANGEABLE_UNMUTED)
