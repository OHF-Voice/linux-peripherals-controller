"""Unit tests for display.py."""

import pytest

from linux_peripherals_controller.display import DEFAULT_TRANSIENT_SECONDS, DisplayFunction, TransientDisplay, select_display_function, start_transient
from linux_peripherals_controller.lva_status import LvaStatus

CONNECTED = LvaStatus(lva_status="connected", state="idle", muted=False, timer_status="idle")


def select(status=CONNECTED, link=True, transient=None, now=0.0):
    return select_display_function(status, link, transient, now)


def with_status(**changes):
    return LvaStatus(**{**CONNECTED.__dict__, **changes})


class TestStartTransient:
    @pytest.mark.parametrize("name", ["pipeline_error", "timer_timeout", "volume"])
    def test_ends_after_its_duration(self, name):
        transient = start_transient(name, now=10.0)
        assert transient == TransientDisplay(DisplayFunction(name), 10.0 + DEFAULT_TRANSIENT_SECONDS[DisplayFunction(name)])

    @pytest.mark.parametrize("name", ["listening", "muted", "nonsense"])
    def test_other_names_are_not_short_functions(self, name):
        assert start_transient(name, now=0.0) is None

    def test_durations_can_be_replaced(self):
        assert start_transient("volume", 1.0, {DisplayFunction.VOLUME: 5.0}).ends_at == 6.0


class TestNoConnection:
    def test_link_to_lva_is_down(self):
        assert select(link=False) == DisplayFunction.NO_CONNECTION

    def test_lva_has_not_said_anything_yet(self):
        assert select(LvaStatus()) == DisplayFunction.NO_CONNECTION

    def test_lva_is_not_connected_to_home_assistant(self):
        assert select(with_status(lva_status="disconnected")) == DisplayFunction.NO_CONNECTION

    def test_wins_over_everything(self):
        status = with_status(lva_status="disconnected", timer_status="ringing", state="listening")
        assert select(status) == DisplayFunction.NO_CONNECTION


class TestPriority:
    def test_nothing_to_show_is_the_background(self):
        assert select() is None

    def test_ringing_timer_wins_over_the_pipeline(self):
        assert select(with_status(timer_status="ringing", state="listening")) == DisplayFunction.TIMER_RINGING

    @pytest.mark.parametrize("state", ["wake_word", "listening", "thinking", "tts", "announce"])
    def test_pipeline_state(self, state):
        assert select(with_status(state=state)) == DisplayFunction(state)

    def test_pipeline_wins_over_short_functions_muted_and_timer(self):
        transient = TransientDisplay(DisplayFunction.VOLUME, 5.0)
        status = with_status(state="thinking", muted=True, timer_status="active")
        assert select(status, transient=transient, now=1.0) == DisplayFunction.THINKING

    def test_short_function_wins_over_muted_and_timer(self):
        transient = TransientDisplay(DisplayFunction.PIPELINE_ERROR, 5.0)
        assert select(with_status(muted=True, timer_status="active"), transient=transient, now=1.0) == DisplayFunction.PIPELINE_ERROR

    def test_short_function_is_gone_after_its_end(self):
        transient = TransientDisplay(DisplayFunction.VOLUME, 5.0)
        assert select(with_status(muted=True), transient=transient, now=5.0) == DisplayFunction.MUTED

    def test_muted_wins_over_a_counting_timer(self):
        assert select(with_status(muted=True, timer_status="active")) == DisplayFunction.MUTED

    def test_counting_timer(self):
        assert select(with_status(timer_status="active")) == DisplayFunction.TIMER_ACTIVE

    def test_idle_state_shows_nothing(self):
        assert select(with_status(state="idle")) is None
