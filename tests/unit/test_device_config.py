"""Unit tests for device_config.py."""

import pytest

from linux_peripherals_controller.appearance import Color, PatternName
from linux_peripherals_controller.button_roles import ButtonRole
from linux_peripherals_controller.device_config import ButtonConfig, DeviceConfig, DeviceConfigError, SensorConfig, load_device_config, parse_device_config
from linux_peripherals_controller.display import DisplayFunction

FULL = """
brightness = 0.5

[buttons.button]
role = "mute"
pin = 26

[colors]
listening = "#0000ff"
muted = "#FF0000"

[patterns]
listening = "pulse"

[sensors.temperature]
interval = 60
"""


def parse(text):
    return parse_device_config(text, "device.toml")


def error_of(text):
    with pytest.raises(DeviceConfigError) as error:
        parse(text)
    return str(error.value)


class TestValidConfig:
    def test_empty_text_is_an_empty_configuration(self):
        assert parse("") == DeviceConfig()

    def test_everything_is_read(self):
        config = parse(FULL)
        assert config.brightness == 0.5
        assert config.buttons == {"button": ButtonConfig(ButtonRole.MUTE, 26)}
        assert config.colors == {DisplayFunction.LISTENING: Color(0, 0, 255), DisplayFunction.MUTED: Color(255, 0, 0)}
        assert config.patterns == {DisplayFunction.LISTENING: PatternName.PULSE}
        assert config.sensors == {"temperature": SensorConfig(60.0)}

    def test_values_that_are_left_out_stay_none(self):
        config = parse("[buttons.button]\n")
        assert config.buttons["button"] == ButtonConfig(None, None)
        assert config.brightness is None

    @pytest.mark.parametrize("text,expected", [("0", 0.0), ("1", 1.0), ("0.25", 0.25)])
    def test_brightness_from_0_to_1(self, text, expected):
        assert parse(f"brightness = {text}").brightness == expected


class TestFile:
    def test_no_file_is_an_empty_configuration(self):
        assert load_device_config(None) == DeviceConfig()

    def test_file_is_read(self, tmp_path):
        path = tmp_path / "device.toml"
        path.write_text("brightness = 0.3\n", encoding="utf-8")
        assert load_device_config(path).brightness == 0.3

    def test_missing_file_names_the_file(self, tmp_path):
        path = tmp_path / "nope.toml"
        with pytest.raises(DeviceConfigError, match="nope.toml: cannot be read"):
            load_device_config(path)

    def test_file_that_is_not_text_names_the_file(self, tmp_path):
        path = tmp_path / "device.toml"
        path.write_bytes(b"\xff\xfe\x00")
        with pytest.raises(DeviceConfigError, match="device.toml: cannot be read"):
            load_device_config(path)

    def test_errors_name_the_file_of_the_path(self, tmp_path):
        path = tmp_path / "device.toml"
        path.write_text("brightness = 5\n", encoding="utf-8")
        with pytest.raises(DeviceConfigError) as error:
            load_device_config(path)
        assert str(error.value).startswith(f"{path}: brightness")


class TestErrors:
    def test_not_valid_toml(self):
        assert "device.toml: not valid TOML" in error_of("brightness = ")

    def test_unknown_top_level_key(self):
        message = error_of("colours = 1")
        assert "device.toml: colours: unknown key" in message
        assert "brightness" in message

    @pytest.mark.parametrize("value", ["1.5", "-0.1", '"high"', "true"])
    def test_brightness_outside_0_to_1(self, value):
        assert "brightness:" in error_of(f"brightness = {value}")

    def test_unknown_key_of_a_button(self):
        assert "buttons.button.colour: unknown key" in error_of("[buttons.button]\ncolour = 1")

    def test_unknown_role(self):
        message = error_of('[buttons.button]\nrole = "jump"')
        assert "buttons.button.role: 'jump' is not a role" in message
        assert "action" in message

    def test_report_to_ha_is_not_a_setting_because_every_press_is_reported(self):
        assert "buttons.button.report_to_ha: unknown key" in error_of("[buttons.button]\nreport_to_ha = true")

    @pytest.mark.parametrize("value", ["-1", "1.5", '"17"', "true"])
    def test_pin_must_be_a_number(self, value):
        assert "buttons.button.pin:" in error_of(f"[buttons.button]\npin = {value}")

    def test_button_must_be_a_table(self):
        assert "buttons.button: must be a table" in error_of("[buttons]\nbutton = 1")

    def test_buttons_must_be_a_table(self):
        assert "buttons: must be a table" in error_of("buttons = 1")

    def test_color_for_a_function_that_does_not_exist(self):
        message = error_of('[colors]\nrainbow = "#ffffff"')
        assert "colors.rainbow: unknown key" in message
        assert "listening" in message

    @pytest.mark.parametrize("value", ['"red"', '"#12"', "5"])
    def test_color_must_be_hex(self, value):
        assert "colors.listening:" in error_of(f"[colors]\nlistening = {value}")

    def test_unknown_pattern(self):
        message = error_of('[patterns]\nlistening = "disco"')
        assert "patterns.listening: 'disco' is not a pattern" in message
        assert "pulse" in message

    @pytest.mark.parametrize("value", ["0", "-5", '"fast"', "true"])
    def test_sensor_interval_must_be_above_zero(self, value):
        assert "sensors.temperature.interval:" in error_of(f"[sensors.temperature]\ninterval = {value}")

    def test_unknown_key_of_a_sensor(self):
        assert "sensors.temperature.offset: unknown key" in error_of("[sensors.temperature]\noffset = 1")

    def test_one_error_is_enough_to_refuse_everything(self):
        with pytest.raises(DeviceConfigError):
            parse('brightness = 0.5\n[colors]\nlistening = "nope"')
