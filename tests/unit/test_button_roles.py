"""Unit tests for button_roles.py."""

import pytest

from linux_peripherals_controller.button_roles import ButtonAction, ButtonRole, LvaCommand, decide_button_action
from linux_peripherals_controller.lva_protocol import COMMANDS
from linux_peripherals_controller.lva_status import LvaStatus

IDLE = LvaStatus(lva_status="connected", state="idle", muted=False, timer_status="idle")


def decide(role, press="single", **overrides):
    values = {"status": IDLE, "link": True, "lock": False, "report": False, **overrides}
    return decide_button_action(role, press, values["status"], values["link"], values["lock"], values["report"])


def names(action):
    return [command.name for command in action.commands]


def with_status(**changes):
    return LvaStatus(**{**IDLE.__dict__, **changes})


class TestActionRole:
    def test_idle_starts_listening(self):
        assert names(decide(ButtonRole.ACTION)) == ["start_listening", "button_pressed"]

    @pytest.mark.parametrize("state", ["listening", "thinking", "tts", "announce"])
    def test_busy_assistant_is_stopped(self, state):
        assert names(decide(ButtonRole.ACTION, status=with_status(state=state))) == ["stop", "button_pressed"]

    def test_wake_word_state_is_not_stopped(self):
        assert names(decide(ButtonRole.ACTION, status=with_status(state="wake_word")))[0] == "start_listening"

    def test_ringing_timer_is_stopped_first(self):
        assert names(decide(ButtonRole.ACTION, status=with_status(timer_status="ringing", state="idle")))[0] == "timer_stop"

    def test_ringing_timer_wins_over_a_busy_assistant(self):
        assert names(decide(ButtonRole.ACTION, status=with_status(timer_status="ringing", state="tts")))[0] == "timer_stop"

    def test_counting_timer_does_not_matter(self):
        assert names(decide(ButtonRole.ACTION, status=with_status(timer_status="active")))[0] == "start_listening"

    @pytest.mark.parametrize("press", ["double", "triple", "long"])
    def test_other_presses_only_play_their_sound(self, press):
        assert decide(ButtonRole.ACTION, press).commands == (LvaCommand("button_pressed", {"press": press}),)


class TestVolumeRoles:
    @pytest.mark.parametrize("role,command", [(ButtonRole.VOLUME_UP, "volume_up"), (ButtonRole.VOLUME_DOWN, "volume_down")])
    def test_single_press(self, role, command):
        assert names(decide(role)) == [command, "button_pressed"]

    @pytest.mark.parametrize("role,command", [(ButtonRole.VOLUME_UP, "volume_up"), (ButtonRole.VOLUME_DOWN, "volume_down")])
    def test_repeat_sends_only_the_command(self, role, command):
        assert decide(role, "repeat").commands == (LvaCommand(command),)

    @pytest.mark.parametrize("press", ["double", "triple", "long"])
    def test_other_presses_have_no_function(self, press):
        assert names(decide(ButtonRole.VOLUME_UP, press)) == ["button_pressed"]


class TestMuteRole:
    def test_mutes_when_not_muted(self):
        assert names(decide(ButtonRole.MUTE))[0] == "mute_on"

    def test_unmutes_when_muted(self):
        assert names(decide(ButtonRole.MUTE, status=with_status(muted=True)))[0] == "mute_off"

    def test_unknown_mute_state_mutes(self):
        assert names(decide(ButtonRole.MUTE, status=LvaStatus()))[0] == "mute_on"

    def test_long_press_has_no_function(self):
        assert names(decide(ButtonRole.MUTE, "long")) == ["button_pressed"]


class TestButtonPressedForLva:
    def test_it_carries_the_press_type(self):
        assert decide(ButtonRole.ACTION).commands[-1] == LvaCommand("button_pressed", {"press": "single"})

    def test_repeat_is_not_a_press_type_of_lva(self):
        assert "button_pressed" not in names(decide(ButtonRole.VOLUME_UP, "repeat"))

    def test_every_command_is_one_of_version_2(self):
        for role in ButtonRole:
            for press in ("single", "double", "triple", "long", "repeat"):
                assert {c.name for c in decide(role, press).commands} <= COMMANDS


class TestUserRole:
    @pytest.mark.parametrize("press", ["single", "double", "triple", "long"])
    def test_reports_to_home_assistant_and_plays_the_sound(self, press):
        action = decide(ButtonRole.USER, press)
        assert action.report_to_ha is True
        assert action.commands == (LvaCommand("button_pressed", {"press": press}),)

    def test_still_reports_with_the_child_lock_on(self):
        action = decide(ButtonRole.USER, lock=True)
        assert action.report_to_ha is True
        assert names(action) == ["button_pressed"]

    def test_reports_without_connection_to_lva_but_sends_nothing(self):
        action = decide(ButtonRole.USER, link=False)
        assert action.report_to_ha is True
        assert action.commands == ()

    def test_repeat_is_not_reported(self):
        assert decide(ButtonRole.USER, "repeat").report_to_ha is False


class TestChildLock:
    @pytest.mark.parametrize("role", [ButtonRole.ACTION, ButtonRole.VOLUME_UP, ButtonRole.VOLUME_DOWN, ButtonRole.MUTE])
    def test_nothing_happens_for_the_other_roles(self, role):
        assert decide(role, lock=True, report=True) == ButtonAction("single press ignored: the child lock is on")


class TestNotConnected:
    def test_nothing_is_sent_and_the_reason_says_why(self):
        action = decide(ButtonRole.ACTION, link=False)
        assert action.commands == ()
        assert "not connected to LVA" in action.reason

    def test_report_to_home_assistant_still_works(self):
        assert decide(ButtonRole.ACTION, link=False, report=True).report_to_ha is True


class TestReportToHomeAssistant:
    def test_off_by_default_for_the_other_roles(self):
        assert decide(ButtonRole.ACTION).report_to_ha is False

    @pytest.mark.parametrize("press", ["single", "double", "triple", "long"])
    def test_on_when_configured(self, press):
        assert decide(ButtonRole.ACTION, press, report=True).report_to_ha is True

    def test_repeat_is_never_reported(self):
        assert decide(ButtonRole.VOLUME_UP, "repeat", report=True).report_to_ha is False


class TestReason:
    def test_reason_names_the_function(self):
        assert decide(ButtonRole.ACTION).reason == "single press of action: start_listening"

    def test_reason_for_a_press_without_function(self):
        assert decide(ButtonRole.ACTION, "long").reason == "long press of action has no function"
