"""Unit tests for press_detection.py."""

import pytest

from linux_peripherals_controller.press_detection import ButtonState, DetectionConfig, next_deadline, press, release, tick

CONFIG = DetectionConfig()
REPEAT = DetectionConfig(repeat_after=0.5, repeat_interval=0.25)


def play(config, steps):
    """Run (time, action) steps and return the presses together with the time they were reported."""
    state, reported = ButtonState(), []
    for now, action in steps:
        if action == "down":
            state, presses = press(state, now, config)
        elif action == "up":
            state, presses = release(state, now), ()
        else:
            state, presses = tick(state, now, config)
        reported += [(now, p) for p in presses]
    return state, reported


def tap(start, hold=0.05):
    return [(start, "down"), (start + hold, "up")]


class TestSinglePress:
    def test_nothing_is_reported_before_the_gap_has_passed(self):
        state, reported = play(CONFIG, tap(0.0) + [(0.2, "tick")])
        assert reported == []
        assert state.presses == 1

    def test_single_press_after_the_gap(self):
        _, reported = play(CONFIG, tap(0.0) + [(0.3, "tick")])
        assert reported == [(0.3, "single")]

    def test_gap_is_counted_from_the_release(self):
        _, reported = play(CONFIG, tap(0.0, hold=0.4) + [(0.6, "tick"), (0.7, "tick")])
        assert reported == [(0.7, "single")]

    def test_state_is_empty_afterwards(self):
        state, _ = play(CONFIG, tap(0.0) + [(0.3, "tick")])
        assert state == ButtonState()


class TestMultiPress:
    def test_double_press(self):
        _, reported = play(CONFIG, tap(0.0) + tap(0.15) + [(0.5, "tick")])
        assert reported == [(0.5, "double")]

    def test_triple_press(self):
        _, reported = play(CONFIG, tap(0.0) + tap(0.15) + tap(0.3) + [(0.7, "tick")])
        assert reported == [(0.7, "triple")]

    def test_a_fourth_press_still_counts_as_triple(self):
        _, reported = play(CONFIG, tap(0.0) + tap(0.15) + tap(0.3) + tap(0.45) + [(0.9, "tick")])
        assert reported == [(0.9, "triple")]

    def test_two_presses_with_a_long_gap_are_two_single_presses(self):
        _, reported = play(CONFIG, tap(0.0) + [(0.3, "tick")] + tap(1.0) + [(1.4, "tick")])
        assert reported == [(0.3, "single"), (1.4, "single")]

    def test_the_gap_between_presses_must_be_below_the_limit(self):
        _, reported = play(CONFIG, tap(0.0) + tap(0.35) + [(0.7, "tick")])
        assert [p for _, p in reported] == ["single", "single"]

    def test_late_press_reports_the_earlier_one_even_without_a_tick(self):
        _, reported = play(CONFIG, tap(0.0) + [(2.0, "down")])
        assert reported == [(2.0, "single")]


class TestLongPress:
    def test_long_press_is_reported_when_the_hold_time_is_reached(self):
        _, reported = play(CONFIG, [(0.0, "down"), (0.9, "tick"), (1.0, "tick")])
        assert reported == [(1.0, "long")]

    def test_it_is_reported_once_and_not_again_on_release(self):
        state, reported = play(CONFIG, [(0.0, "down"), (1.0, "tick"), (1.5, "tick"), (2.0, "up"), (2.5, "tick")])
        assert reported == [(1.0, "long")]
        assert state == ButtonState()

    def test_release_just_before_the_hold_time_is_a_single_press(self):
        _, reported = play(CONFIG, [(0.0, "down"), (0.95, "up"), (1.3, "tick")])
        assert reported == [(1.3, "single")]

    def test_long_press_drops_a_press_that_was_waiting(self):
        state, reported = play(CONFIG, tap(0.0) + [(0.1, "down"), (1.1, "tick"), (1.2, "up")])
        assert reported == [(1.1, "long")]
        assert state == ButtonState()

    def test_hold_time_can_be_changed(self):
        _, reported = play(DetectionConfig(long_after=2.0), [(0.0, "down"), (1.5, "tick"), (2.0, "tick")])
        assert reported == [(2.0, "long")]


class TestRepeat:
    def test_holding_repeats_after_the_start_delay(self):
        _, reported = play(REPEAT, [(0.0, "down"), (0.4, "tick"), (0.5, "tick"), (0.7, "tick"), (0.75, "tick"), (1.0, "tick")])
        assert reported == [(0.5, "repeat"), (0.75, "repeat"), (1.0, "repeat"), (1.0, "long")]

    def test_a_button_that_repeats_also_has_a_long_press_once(self):
        _, reported = play(REPEAT, [(0.0, "down"), (0.5, "tick"), (0.75, "tick"), (1.0, "tick"), (1.25, "tick"), (1.5, "tick")])
        assert [p for _, p in reported].count("long") == 1
        assert (1.0, "long") in reported

    def test_the_repeat_goes_on_after_the_long_press(self):
        _, reported = play(REPEAT, [(0.0, "down"), (0.5, "tick"), (0.75, "tick"), (1.0, "tick"), (1.25, "tick"), (1.5, "tick")])
        assert [p for _, p in reported] == ["repeat", "repeat", "repeat", "long", "repeat", "repeat"]

    def test_repeat_and_long_press_that_are_due_in_one_tick_come_in_that_order(self):
        _, reported = play(REPEAT, [(0.0, "down"), (1.2, "tick")])
        assert [p for _, p in reported] == ["repeat", "long"]

    def test_release_after_the_long_press_reports_nothing_more(self):
        state, reported = play(REPEAT, [(0.0, "down"), (1.0, "tick"), (1.1, "up"), (1.5, "tick")])
        assert "single" not in [p for _, p in reported]
        assert state == ButtonState()

    def test_release_stops_the_repeat(self):
        state, reported = play(REPEAT, [(0.0, "down"), (0.5, "tick"), (0.6, "up"), (1.0, "tick")])
        assert reported == [(0.5, "repeat")]
        assert state == ButtonState()

    def test_a_short_press_is_still_a_single_press(self):
        _, reported = play(REPEAT, tap(0.0, hold=0.2) + [(0.5, "tick")])
        assert reported == [(0.5, "single")]


class TestRobustness:
    def test_second_down_while_down_changes_nothing(self):
        state, _ = play(CONFIG, [(0.0, "down")])
        again, reported = press(state, 0.5, CONFIG)
        assert again is state
        assert reported == ()

    def test_up_without_down_changes_nothing(self):
        assert release(ButtonState(), 1.0) == ButtonState()

    def test_tick_while_idle_changes_nothing(self):
        assert tick(ButtonState(), 5.0, CONFIG) == (ButtonState(), ())

    def test_state_is_not_modified(self):
        before = ButtonState(down_since=0.0)
        tick(before, 2.0, CONFIG)
        assert before == ButtonState(down_since=0.0)


class TestNextDeadline:
    def test_nothing_waits_when_idle(self):
        assert next_deadline(ButtonState(), CONFIG) is None

    def test_held_button_waits_for_the_long_press(self):
        assert next_deadline(ButtonState(down_since=2.0), CONFIG) == 3.0

    def test_held_button_that_repeats_waits_for_the_repeat(self):
        assert next_deadline(ButtonState(down_since=2.0), REPEAT) == 2.5

    def test_repeating_button_waits_for_the_next_repeat(self):
        assert next_deadline(ButtonState(down_since=2.0, repeating=True, next_repeat=2.75), REPEAT) == 2.75

    def test_repeating_button_waits_for_the_long_press_if_it_comes_first(self):
        assert next_deadline(ButtonState(down_since=2.0, repeating=True, next_repeat=3.5), REPEAT) == 3.0

    def test_repeating_button_after_the_long_press_waits_for_the_repeat(self):
        assert next_deadline(ButtonState(down_since=2.0, repeating=True, long_reported=True, next_repeat=3.25), REPEAT) == 3.25

    def test_held_after_a_long_press_waits_for_nothing(self):
        assert next_deadline(ButtonState(down_since=2.0, long_reported=True), CONFIG) is None

    def test_released_press_waits_for_the_gap(self):
        assert next_deadline(ButtonState(presses=1, last_release=2.0), CONFIG) == 2.25

    @pytest.mark.parametrize("steps", [tap(0.0), tap(0.0) + tap(0.15), [(0.0, "down")]])
    def test_ticking_at_the_deadline_always_completes_or_advances(self, steps):
        state, _ = play(CONFIG, steps)
        deadline = next_deadline(state, CONFIG)
        assert deadline is not None
        new_state, reported = tick(state, deadline, CONFIG)
        assert reported or new_state != state
