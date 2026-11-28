"""Unit tests for light.py."""

from linux_peripherals_controller.appearance import Color
from linux_peripherals_controller.light import LightState, apply_light_command


class TestLightState:
    def test_starts_off_in_light_blue(self):
        light = LightState()
        assert not light.on
        assert light.brightness == 0.66
        assert light.color == Color(24, 187, 242)

    def test_round_trip_through_a_dict(self):
        light = LightState(on=True, brightness=0.3, red=1.0, green=0.5, blue=0.0)
        assert LightState.from_dict(light.to_dict()) == light

    def test_missing_or_invalid_values_keep_their_default(self):
        assert LightState.from_dict({"on": "yes", "brightness": True, "red": "x"}) == LightState()

    def test_stored_values_are_clamped(self):
        assert LightState.from_dict({"brightness": 7}).brightness == 1.0


class TestApplyLightCommand:
    def test_only_the_given_values_change(self):
        light = apply_light_command(LightState(), on=True)
        assert light == LightState(on=True)

    def test_brightness_and_color_are_clamped(self):
        light = apply_light_command(LightState(), brightness=2.0, rgb=(-1.0, 0.5, 3.0))
        assert (light.brightness, light.red, light.green, light.blue) == (1.0, 0.0, 0.5, 1.0)
