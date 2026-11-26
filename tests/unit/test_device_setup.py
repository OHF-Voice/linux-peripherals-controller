"""Unit tests for device_setup.py."""

import pytest

from linux_peripherals_controller.appearance import DEFAULT_COLORS, DEFAULT_PATTERNS, Color, PatternName
from linux_peripherals_controller.button_roles import ButtonRole
from linux_peripherals_controller.device_config import ButtonConfig, DeviceConfig, DeviceConfigError, SensorConfig
from linux_peripherals_controller.device_setup import DEFAULT_BRIGHTNESS, resolve_device
from linux_peripherals_controller.device_types import ButtonSpec, DeviceType, SensorSpec
from linux_peripherals_controller.display import DisplayFunction

TYPE = DeviceType(
    name="test",
    description="a test device",
    buttons=(ButtonSpec("main", ButtonRole.ACTION, pin=17), ButtonSpec("side", ButtonRole.USER)),
    sensors=(SensorSpec("temperature", 30.0),),
    colors={DisplayFunction.LISTENING: Color(1, 1, 1)},
    patterns={DisplayFunction.LISTENING: PatternName.SOLID},
)


def resolve(config=None, device_type=TYPE):
    return resolve_device(device_type, config or DeviceConfig(), "device.toml")


class TestLayers:
    def test_default_when_nothing_overrides(self):
        device = resolve()
        assert device.colors[DisplayFunction.TTS] == DEFAULT_COLORS[DisplayFunction.TTS]
        assert device.patterns[DisplayFunction.TTS] == DEFAULT_PATTERNS[DisplayFunction.TTS]

    def test_device_type_wins_over_the_default(self):
        device = resolve()
        assert device.colors[DisplayFunction.LISTENING] == Color(1, 1, 1)
        assert device.patterns[DisplayFunction.LISTENING] == PatternName.SOLID

    def test_device_configuration_wins_over_the_device_type(self):
        config = DeviceConfig(colors={DisplayFunction.LISTENING: Color(9, 9, 9)}, patterns={DisplayFunction.LISTENING: PatternName.SPIN})
        device = resolve(config)
        assert device.colors[DisplayFunction.LISTENING] == Color(9, 9, 9)
        assert device.patterns[DisplayFunction.LISTENING] == PatternName.SPIN

    def test_a_setting_is_replaced_alone(self):
        config = DeviceConfig(colors={DisplayFunction.TTS: Color(9, 9, 9)})
        device = resolve(config)
        assert device.colors[DisplayFunction.LISTENING] == Color(1, 1, 1)

    def test_only_offered_functions_are_kept(self):
        device = resolve(device_type=DeviceType("small", "", functions=frozenset({DisplayFunction.LISTENING, DisplayFunction.MUTED})))
        assert set(device.colors) == {DisplayFunction.LISTENING, DisplayFunction.MUTED}
        assert set(device.patterns) == {DisplayFunction.LISTENING, DisplayFunction.MUTED}

    def test_inputs_are_not_modified(self):
        config = DeviceConfig(colors={DisplayFunction.TTS: Color(9, 9, 9)})
        resolve(config)
        assert DEFAULT_COLORS[DisplayFunction.TTS] != Color(9, 9, 9)
        assert TYPE.colors == {DisplayFunction.LISTENING: Color(1, 1, 1)}


class TestBrightness:
    def test_default(self):
        assert resolve().brightness == DEFAULT_BRIGHTNESS == 1.0

    def test_from_the_configuration(self):
        assert resolve(DeviceConfig(brightness=0.4)).brightness == 0.4

    def test_zero_is_a_value(self):
        assert resolve(DeviceConfig(brightness=0.0)).brightness == 0.0


class TestButtons:
    def test_as_the_device_type_says(self):
        buttons = {b.name: b for b in resolve().buttons}
        assert (buttons["main"].role, buttons["main"].pin) == (ButtonRole.ACTION, 17)
        assert buttons["side"].pin is None

    def test_configuration_replaces_one_value_at_a_time(self):
        config = DeviceConfig(buttons={"main": ButtonConfig(role=ButtonRole.MUTE)})
        main = {b.name: b for b in resolve(config).buttons}["main"]
        assert (main.role, main.pin) == (ButtonRole.MUTE, 17)

    def test_configuration_can_change_the_pin(self):
        config = DeviceConfig(buttons={"main": ButtonConfig(pin=26)})
        main = {b.name: b for b in resolve(config).buttons}["main"]
        assert (main.role, main.pin) == (ButtonRole.ACTION, 26)

    def test_button_that_the_device_type_does_not_have_is_refused(self):
        with pytest.raises(DeviceConfigError) as error:
            resolve(DeviceConfig(buttons={"ghost": ButtonConfig()}))
        assert "device.toml: buttons.ghost: the device type test has no button with this name (main, side)" in str(error.value)

    def test_the_order_of_the_device_type_is_kept(self):
        assert [b.name for b in resolve().buttons] == ["main", "side"]


class TestSensors:
    def test_default_interval(self):
        assert resolve().sensors[0].interval == 30.0

    def test_interval_from_the_configuration(self):
        assert resolve(DeviceConfig(sensors={"temperature": SensorConfig(5.0)})).sensors[0].interval == 5.0

    def test_sensor_without_interval_keeps_the_default(self):
        assert resolve(DeviceConfig(sensors={"temperature": SensorConfig()})).sensors[0].interval == 30.0

    def test_unknown_sensor_is_refused(self):
        with pytest.raises(DeviceConfigError, match="sensors.humidity: the device type test has no sensor"):
            resolve(DeviceConfig(sensors={"humidity": SensorConfig(5.0)}))

    def test_device_without_sensors_says_so(self):
        with pytest.raises(DeviceConfigError, match=r"\(no sensors\)"):
            resolve(DeviceConfig(sensors={"x": SensorConfig()}), DeviceType("bare", ""))


class TestFunctionsThatAreNotOffered:
    def test_color_for_a_function_the_device_does_not_show(self):
        device_type = DeviceType("small", "", functions=frozenset({DisplayFunction.LISTENING}))
        with pytest.raises(DeviceConfigError, match="colors.tts: the device type small does not offer this display function"):
            resolve(DeviceConfig(colors={DisplayFunction.TTS: Color(1, 2, 3)}), device_type)

    def test_pattern_for_a_function_the_device_does_not_show(self):
        device_type = DeviceType("small", "", functions=frozenset({DisplayFunction.LISTENING}))
        with pytest.raises(DeviceConfigError, match="patterns.tts: "):
            resolve(DeviceConfig(patterns={DisplayFunction.TTS: PatternName.SOLID}), device_type)
