"""Unit tests for lva_status.py."""

import pytest

from linux_peripherals_controller.lva_protocol import LvaEvent
from linux_peripherals_controller.lva_status import LvaStatus, LvaTimer, apply_event


def event(name, **data):
    return LvaEvent(name, data)


class TestStatusEvents:
    def test_new_status_knows_nothing(self):
        assert LvaStatus() == LvaStatus(None, None, None, None, None, None, None, None, None)

    @pytest.mark.parametrize(
        "name,data,attribute,expected",
        [
            ("lva_status", {"status": "connected"}, "lva_status", "connected"),
            ("state", {"state": "listening"}, "state", "listening"),
            ("mute_status", {"status": "muted"}, "muted", True),
            ("mute_status", {"status": "unmuted"}, "muted", False),
            ("volume_status", {"volume": 40}, "volume", 40),
            ("timer_status", {"status": "active", "auto_stopped": False}, "timer_status", "active"),
            ("timer_remaining_time", {"seconds": 90}, "timer_remaining_time", 90),
            ("timer_remaining_percentage", {"percentage": 30}, "timer_remaining_percentage", 30),
            ("media_player_status", {"status": "silent"}, "media_player_status", "silent"),
        ],
    )
    def test_event_sets_its_value(self, name, data, attribute, expected):
        update = apply_event(LvaStatus(), event(name, **data))
        assert getattr(update.status, attribute) == expected
        assert update.transient is None

    def test_other_values_are_kept(self):
        before = LvaStatus(state="idle", muted=False)
        assert apply_event(before, event("state", state="tts")).status == LvaStatus(state="tts", muted=False)

    def test_status_is_not_modified(self):
        before = LvaStatus()
        apply_event(before, event("state", state="tts"))
        assert before == LvaStatus()

    @pytest.mark.parametrize(
        "name,data",
        [
            ("state", {}),
            ("state", {"state": 5}),
            ("mute_status", {"muted": True}),
            ("mute_status", {"status": "yes"}),
            ("mute_status", {}),
            ("volume_status", {"volume": "40"}),
            ("volume_status", {"volume": True}),
        ],
    )
    def test_invalid_data_changes_nothing(self, name, data):
        before = LvaStatus(state="idle")
        update = apply_event(before, event(name, **data))
        assert update == apply_event(before, event("unknown"))
        assert update.status == before

    @pytest.mark.parametrize("name", ["hello", "something_new"])
    def test_events_that_say_nothing_change_nothing(self, name):
        update = apply_event(LvaStatus(state="idle"), event(name))
        assert update.status == LvaStatus(state="idle")
        assert update.transient is None


class TestSignals:
    def test_the_state_pipeline_error_is_a_signal(self):
        update = apply_event(LvaStatus(state="idle"), event("state", state="pipeline_error"))
        assert update.transient == "pipeline_error"
        assert update.status.state == "pipeline_error"

    def test_pipeline_error_is_no_event_of_its_own_any_more(self):
        update = apply_event(LvaStatus(state="idle"), event("pipeline_error", reason="x"))
        assert update.transient is None
        assert update.status == LvaStatus(state="idle")

    def test_a_timer_that_stopped_on_its_own_is_a_timeout(self):
        update = apply_event(LvaStatus(timer_status="ringing"), event("timer_status", status="idle", auto_stopped=True))
        assert update.transient == "timer_timeout"
        assert update.status.timer_status == "idle"

    def test_timer_auto_stopped_is_no_event_of_its_own_any_more(self):
        assert apply_event(LvaStatus(), event("timer_auto_stopped", seconds=900)).transient is None

    @pytest.mark.parametrize("data", [{"status": "idle", "auto_stopped": False}, {"status": "idle"}, {"status": "idle", "auto_stopped": "yes"}])
    def test_a_timer_that_was_stopped_by_someone_is_no_timeout(self, data):
        assert apply_event(LvaStatus(timer_status="ringing"), event("timer_status", **data)).transient is None

    @pytest.mark.parametrize("state", ["idle", "listening", "speech_detected", "thinking"])
    def test_other_states_are_no_signal(self, state):
        assert apply_event(LvaStatus(), event("state", state=state)).transient is None


class TestTimers:
    TIMER = {"id": "t1", "name": "tea", "status": "active", "total_seconds": 300, "seconds_left": 150, "percentage": 50}

    def test_all_timers_are_kept(self):
        update = apply_event(LvaStatus(), event("timer_full_data_set", timers=[self.TIMER, {**self.TIMER, "id": "t2", "status": "ringing"}]))
        assert update.status.timers == (LvaTimer("t1", "tea", "active", 300, 150, 50), LvaTimer("t2", "tea", "ringing", 300, 150, 50))
        assert update.transient is None

    def test_no_timers_is_an_empty_set_not_unknown(self):
        assert apply_event(LvaStatus(), event("timer_full_data_set", timers=[])).status.timers == ()

    @pytest.mark.parametrize("timers", [None, "x", [5], [{"id": "t1"}], [{**TIMER, "seconds_left": "9"}], [{**TIMER, "percentage": True}]])
    def test_invalid_data_changes_nothing(self, timers):
        before = LvaStatus(timers=())
        assert apply_event(before, event("timer_full_data_set", timers=timers)).status == before


class TestVolumeSignal:
    def test_first_volume_is_not_a_signal(self):
        assert apply_event(LvaStatus(), event("volume_status", volume=50)).transient is None

    def test_changed_volume_is_a_signal(self):
        update = apply_event(LvaStatus(volume=50), event("volume_status", volume=55))
        assert update.transient == "volume"
        assert update.status.volume == 55

    def test_same_volume_is_not_a_signal(self):
        assert apply_event(LvaStatus(volume=50), event("volume_status", volume=50)).transient is None
