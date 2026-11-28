"""Unit tests for button_roles.py."""

import pytest

from linux_peripherals_controller.button_roles import ButtonAction, ButtonRole, LvaMessage, decide_button_action, detection_for_role
from linux_peripherals_controller.lva_protocol import COMMANDS
from linux_peripherals_controller.lva_status import LvaStatus
from linux_peripherals_controller.press_detection import REPEAT_AFTER_SECONDS

IDLE = LvaStatus(lva_status="connected", state="idle", muted=False, timer_status="idle")
PRESSES = ("single", "double", "triple", "long", "repeat")


def decide(role, press="single", **overrides):
    values = {"status": IDLE, "link": True, "lock": False, **overrides}
    return decide_button_action(role, press, values["status"], values["link"], values["lock"])


def names(action):
    return [command.name for command in action.commands]


def with_status(**changes):
    return LvaStatus(**{**IDLE.__dict__, **changes})


class TestActionRole:
    def test_idle_starts_listening(self):
        assert names(decide(ButtonRole.ACTION)) == ["listening_start", "button_pressed"]

    @pytest.mark.parametrize("state", ["listening", "speech_detected", "thinking", "tts", "announce"])
    def test_busy_assistant_is_stopped(self, state):
        assert names(decide(ButtonRole.ACTION, status=with_status(state=state))) == ["listening_stop", "button_pressed"]

    def test_wake_word_state_is_not_stopped(self):
        assert names(decide(ButtonRole.ACTION, status=with_status(state="wake_word")))[0] == "listening_start"

    def test_ringing_timer_is_stopped_first(self):
        assert names(decide(ButtonRole.ACTION, status=with_status(timer_status="ringing", state="idle")))[0] == "timer_stop"

    def test_ringing_timer_wins_over_a_busy_assistant(self):
        assert names(decide(ButtonRole.ACTION, status=with_status(timer_status="ringing", state="tts")))[0] == "timer_stop"

    def test_counting_timer_does_not_matter(self):
        assert names(decide(ButtonRole.ACTION, status=with_status(timer_status="active")))[0] == "listening_start"

    @pytest.mark.parametrize("press", ["double", "triple", "long"])
    def test_other_presses_only_play_their_sound(self, press):
        assert decide(ButtonRole.ACTION, press).commands == (LvaMessage("button_pressed", {"press": press}),)


class TestVolumeRoles:
    @pytest.mark.parametrize("role,command", [(ButtonRole.VOLUME_UP, "volume_up"), (ButtonRole.VOLUME_DOWN, "volume_down")])
    def test_single_press(self, role, command):
        assert names(decide(role)) == [command, "button_pressed"]

    @pytest.mark.parametrize("role,command", [(ButtonRole.VOLUME_UP, "volume_up"), (ButtonRole.VOLUME_DOWN, "volume_down")])
    def test_repeat_sends_only_the_command(self, role, command):
        assert decide(role, "repeat").commands == (LvaMessage(command),)

    @pytest.mark.parametrize("press", ["double", "triple", "long"])
    def test_other_presses_have_no_function(self, press):
        assert names(decide(ButtonRole.VOLUME_UP, press)) == ["button_pressed"]


class TestMuteRole:
    def test_mutes_when_not_muted(self):
        assert names(decide(ButtonRole.MUTE))[0] == "muted_on"

    def test_unmutes_when_muted(self):
        assert names(decide(ButtonRole.MUTE, status=with_status(muted=True)))[0] == "muted_off"

    def test_unknown_mute_state_mutes(self):
        assert names(decide(ButtonRole.MUTE, status=LvaStatus()))[0] == "muted_on"

    def test_long_press_has_no_function(self):
        assert names(decide(ButtonRole.MUTE, "long")) == ["button_pressed"]


class TestUserRole:
    @pytest.mark.parametrize("press", ["single", "double", "triple", "long"])
    def test_has_no_function_and_plays_the_sound(self, press):
        assert decide(ButtonRole.USER, press).commands == (LvaMessage("button_pressed", {"press": press}),)


class TestButtonPressedForLva:
    def test_it_carries_the_press_type(self):
        assert decide(ButtonRole.ACTION).commands[-1] == LvaMessage("button_pressed", {"press": "single"})

    def test_repeat_is_not_a_press_type_of_lva(self):
        assert "button_pressed" not in names(decide(ButtonRole.VOLUME_UP, "repeat"))

    def test_every_command_is_one_of_version_2(self):
        for role in ButtonRole:
            for press in PRESSES:
                assert {c.name for c in decide(role, press).commands} <= COMMANDS


class TestReportToHomeAssistant:
    @pytest.mark.parametrize("role", list(ButtonRole))
    @pytest.mark.parametrize("press", ["single", "double", "triple", "long"])
    def test_every_press_of_every_button_is_reported(self, role, press):
        assert decide(role, press).report_to_ha is True

    @pytest.mark.parametrize("role", list(ButtonRole))
    def test_repeat_is_not_a_press(self, role):
        assert decide(role, "repeat").report_to_ha is False


class TestPathsAreIndependent:
    """LVA and the child lock only concern what is sent to LVA, never the report to Home Assistant."""

    @pytest.mark.parametrize("role", list(ButtonRole))
    @pytest.mark.parametrize("press", PRESSES)
    @pytest.mark.parametrize("link", [True, False])
    @pytest.mark.parametrize("lock", [True, False])
    def test_report_does_not_depend_on_lva_or_the_child_lock(self, role, press, link, lock):
        assert decide(role, press, link=link, lock=lock).report_to_ha == decide(role, press).report_to_ha

    @pytest.mark.parametrize("role", list(ButtonRole))
    def test_nothing_is_sent_to_lva_without_a_connection(self, role):
        action = decide(role, link=False)
        assert action.commands == ()
        assert "not connected to LVA" in action.reason

    @pytest.mark.parametrize("role", list(ButtonRole))
    @pytest.mark.parametrize("press", PRESSES)
    def test_nothing_is_sent_to_lva_while_the_child_lock_is_on(self, role, press):
        action = decide(role, press, lock=True)
        assert action == ButtonAction(f"{press} press of {role} not sent to LVA: the child lock is on", (), press != "repeat")

    def test_child_lock_wins_over_a_missing_connection_in_the_reason(self):
        assert "child lock" in decide(ButtonRole.ACTION, link=False, lock=True).reason


class TestReason:
    def test_reason_names_the_function(self):
        assert decide(ButtonRole.ACTION).reason == "single press of action: listening_start"

    def test_reason_for_a_press_without_function(self):
        assert decide(ButtonRole.ACTION, "long").reason == "long press of action has no function"


class TestDetectionForRole:
    @pytest.mark.parametrize("role", [ButtonRole.VOLUME_UP, ButtonRole.VOLUME_DOWN])
    def test_volume_buttons_repeat_after_half_a_second(self, role):
        assert detection_for_role(role).repeat_after == REPEAT_AFTER_SECONDS == 0.5

    @pytest.mark.parametrize("role", [ButtonRole.ACTION, ButtonRole.MUTE, ButtonRole.USER])
    def test_other_buttons_do_not_repeat(self, role):
        assert detection_for_role(role).repeat_after is None
