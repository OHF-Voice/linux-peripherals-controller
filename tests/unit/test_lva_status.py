"""Unit tests for lva_status.py."""

import pytest

from linux_peripherals_controller.lva_protocol import LvaEvent
from linux_peripherals_controller.lva_status import LvaStatus, apply_event


def event(name, **data):
    return LvaEvent(name, data)


class TestStatusEvents:
    def test_new_status_knows_nothing(self):
        assert LvaStatus() == LvaStatus(None, None, None, None, None, None, None, None)

    @pytest.mark.parametrize(
        "name,data,attribute,expected",
        [
            ("lva_status", {"status": "connected"}, "lva_status", "connected"),
            ("state", {"state": "listening"}, "state", "listening"),
            ("mute_status", {"muted": True}, "muted", True),
            ("volume_status", {"volume": 40}, "volume", 40),
            ("timer_status", {"status": "active"}, "timer_status", "active"),
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
        [("state", {}), ("state", {"state": 5}), ("mute_status", {"muted": "yes"}), ("volume_status", {"volume": "40"}), ("volume_status", {"volume": True})],
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
    def test_pipeline_error(self):
        update = apply_event(LvaStatus(state="idle"), event("pipeline_error", reason="x"))
        assert update.transient == "pipeline_error"
        assert update.status == LvaStatus(state="idle")

    def test_timer_auto_stopped_is_a_timeout(self):
        assert apply_event(LvaStatus(), event("timer_auto_stopped", seconds=900)).transient == "timer_timeout"


class TestVolumeSignal:
    def test_first_volume_is_not_a_signal(self):
        assert apply_event(LvaStatus(), event("volume_status", volume=50)).transient is None

    def test_changed_volume_is_a_signal(self):
        update = apply_event(LvaStatus(volume=50), event("volume_status", volume=55))
        assert update.transient == "volume"
        assert update.status.volume == 55

    def test_same_volume_is_not_a_signal(self):
        assert apply_event(LvaStatus(volume=50), event("volume_status", volume=50)).transient is None
