"""Unit tests for animation.py."""

import pytest

from linux_peripherals_controller.animation import DisplayState, Scene, display_amount, is_animated, render, scene_for
from linux_peripherals_controller.appearance import Color, PatternName
from linux_peripherals_controller.display import DisplayFunction
from linux_peripherals_controller.light import LightState
from linux_peripherals_controller.lva_status import LvaStatus

RED = Color(255, 0, 0)
DARK = Color(0, 0, 0)
COLORS = {DisplayFunction.LISTENING: Color(0, 0, 255), DisplayFunction.VOLUME: Color(255, 255, 255)}
PATTERNS = {DisplayFunction.LISTENING: PatternName.SPIN, DisplayFunction.VOLUME: PatternName.PROGRESS}


class TestDisplayAmount:
    def test_timer_active_shows_the_time_left(self):
        assert display_amount(DisplayFunction.TIMER_ACTIVE, LvaStatus(timer_remaining_percentage=40)) == 0.4

    def test_volume_shows_the_volume(self):
        assert display_amount(DisplayFunction.VOLUME, LvaStatus(volume=75)) == 0.75

    def test_other_functions_have_no_amount(self):
        assert display_amount(DisplayFunction.LISTENING, LvaStatus(volume=75)) is None
        assert display_amount(None, LvaStatus(volume=75)) is None

    def test_unknown_value_has_no_amount(self):
        assert display_amount(DisplayFunction.VOLUME, LvaStatus()) is None

    def test_amount_is_clamped(self):
        assert display_amount(DisplayFunction.VOLUME, LvaStatus(volume=150)) == 1.0


class TestSceneFor:
    def test_display_function_uses_its_pattern_color_and_the_brightness(self):
        display = DisplayState(DisplayFunction.VOLUME, 0.5, LightState(), started_at=3.0)
        assert scene_for(display, COLORS, PATTERNS, 0.8) == Scene(PatternName.PROGRESS, Color(255, 255, 255), 0.8, 0.5, 3.0)

    def test_background_is_the_light_when_on(self):
        light = LightState(on=True, brightness=0.5, red=1.0, green=0.0, blue=0.0)
        assert scene_for(DisplayState(None, None, light), COLORS, PATTERNS, 1.0) == Scene(PatternName.SOLID, RED, 0.5)

    def test_background_is_dark_when_the_light_is_off(self):
        assert scene_for(DisplayState(None, None, LightState(on=False)), COLORS, PATTERNS, 1.0) is None

    def test_function_the_device_does_not_offer_shows_the_background(self):
        light = LightState(on=True, red=1.0, green=0.0, blue=0.0)
        scene = scene_for(DisplayState(DisplayFunction.MUTED, None, light), COLORS, PATTERNS, 1.0)
        assert scene is not None and scene.pattern == PatternName.SOLID


class TestIsAnimated:
    @pytest.mark.parametrize("pattern", [PatternName.PULSE, PatternName.SPIN, PatternName.BLINK])
    def test_moving_patterns(self, pattern):
        assert is_animated(Scene(pattern, RED, 1.0))

    @pytest.mark.parametrize("pattern", [PatternName.SOLID, PatternName.PROGRESS])
    def test_still_patterns(self, pattern):
        assert not is_animated(Scene(pattern, RED, 1.0))

    def test_nothing_shown(self):
        assert not is_animated(None)


class TestRender:
    def test_nothing_is_dark(self):
        assert render(None, 3, 0.0) == (DARK,) * 3

    def test_solid_lights_every_led_with_the_brightness(self):
        assert render(Scene(PatternName.SOLID, RED, 0.5), 2, 0.0) == (Color(128, 0, 0),) * 2

    def test_blink_is_on_then_off(self):
        scene = Scene(PatternName.BLINK, RED, 1.0, started_at=10.0)
        assert render(scene, 1, 10.1) == (RED,)
        assert render(scene, 1, 10.3) == (DARK,)

    def test_pulse_starts_dim_and_is_full_after_half_a_period(self):
        scene = Scene(PatternName.PULSE, RED, 1.0)
        assert render(scene, 1, 0.0) == (Color(38, 0, 0),)
        assert render(scene, 1, 1.0) == (RED,)

    def test_spin_runs_one_led_with_a_tail(self):
        scene = Scene(PatternName.SPIN, RED, 1.0)
        assert render(scene, 4, 0.0) == (RED, DARK, Color(26, 0, 0), Color(102, 0, 0))
        assert render(scene, 4, 0.25)[1] == RED

    def test_spin_on_one_led_lights_it(self):
        assert render(Scene(PatternName.SPIN, RED, 1.0), 1, 0.0) == (RED,)

    def test_progress_lights_the_share_and_the_last_led_partly(self):
        assert render(Scene(PatternName.PROGRESS, RED, 1.0, amount=0.5), 3, 0.0) == (RED, Color(128, 0, 0), DARK)

    def test_progress_without_amount_is_full(self):
        assert render(Scene(PatternName.PROGRESS, RED, 1.0), 2, 0.0) == (RED, RED)

    def test_time_before_the_start_counts_as_the_start(self):
        scene = Scene(PatternName.BLINK, RED, 1.0, started_at=10.0)
        assert render(scene, 1, 9.0) == (RED,)
