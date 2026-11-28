"""Unit tests for the device files in devices/ (base.py and every device type)."""

from unittest.mock import MagicMock, call

import pytest

from linux_peripherals_controller.animation import DisplayState
from linux_peripherals_controller.appearance import Color
from linux_peripherals_controller.button_roles import ButtonRole
from linux_peripherals_controller.device_config import DeviceConfig
from linux_peripherals_controller.device_setup import resolve_device
from linux_peripherals_controller.devices import DEVICE_TYPES, create_device, get_device_type
from linux_peripherals_controller.devices.base import BaseDevice, DeviceCallbacks
from linux_peripherals_controller.devices.jabra_speak_410 import LED_FLASHING, LED_HOLD, LED_OFF_HOOK, LED_RED, JabraInputs, decode_report, led_report
from linux_peripherals_controller.display import DisplayFunction
from linux_peripherals_controller.drivers import DriverError, Drivers
from linux_peripherals_controller.hardware_mute import HardwareMute
from linux_peripherals_controller.light import LightState
from linux_peripherals_controller.lva_status import LvaStatus


def resolved(name, config=None):
    return resolve_device(get_device_type(name), config or DeviceConfig())


def fake_drivers():
    drivers = MagicMock(spec=Drivers)
    drivers.led_strip.return_value.count = 3
    return drivers


class TestCreateDevice:
    @pytest.mark.parametrize("name", sorted(DEVICE_TYPES))
    def test_every_device_type_has_a_device_class(self, name):
        device = create_device(resolved(name), Drivers(simulated=True))
        assert isinstance(device, BaseDevice)
        assert device.device.device_type.name == name

    @pytest.mark.parametrize("name", sorted(DEVICE_TYPES))
    def test_every_device_type_opens_and_closes_simulated(self, name):
        device = create_device(resolved(name), Drivers(simulated=True))
        device.open(DeviceCallbacks())
        device.draw(DisplayState(DisplayFunction.LISTENING, None, LightState()), 0.0)
        device.close()


class TestBaseDevice:
    def test_open_opens_the_leds_and_a_gpio_button_per_pin(self):
        drivers = fake_drivers()
        device = BaseDevice(resolved("respeaker_2mic_v1"), drivers)
        on_button = MagicMock()
        device.open(DeviceCallbacks(on_button=on_button))
        drivers.led_strip.assert_called_once_with(get_device_type("respeaker_2mic_v1").leds)
        pin, on_change = drivers.gpio_input.call_args.args
        assert pin == 17
        on_change(True)
        on_button.assert_called_once_with("button", True)

    def test_pin_of_the_device_configuration_is_used(self):
        drivers = fake_drivers()
        from linux_peripherals_controller.device_config import ButtonConfig

        device = BaseDevice(resolved("respeaker_2mic_v1", DeviceConfig(buttons={"button": ButtonConfig(pin=27)})), drivers)
        device.open(DeviceCallbacks())
        assert drivers.gpio_input.call_args.args[0] == 27

    def test_failure_releases_what_was_opened(self):
        drivers = fake_drivers()
        drivers.gpio_input.side_effect = DriverError("GPIO 17 busy")
        device = BaseDevice(resolved("respeaker_2mic_v1"), drivers)
        with pytest.raises(DriverError):
            device.open(DeviceCallbacks())
        drivers.led_strip.return_value.close.assert_called_once()
        assert device.leds is None

    def test_draw_renders_the_pattern_onto_the_leds(self):
        drivers = fake_drivers()
        device = BaseDevice(resolved("respeaker_2mic_v1"), drivers)
        device.open(DeviceCallbacks())
        device.draw(DisplayState(DisplayFunction.MUTED, None, LightState()), 0.0)
        drivers.led_strip.return_value.write.assert_called_once_with((Color(255, 0, 0),) * 3)

    def test_draw_without_leds_does_nothing(self):
        device = BaseDevice(resolved("jabra_speak_410"), fake_drivers())
        device.draw(DisplayState(DisplayFunction.MUTED, None, LightState()), 0.0)
        assert not device.is_animated(DisplayState(DisplayFunction.LISTENING, None, LightState()))

    def test_is_animated_follows_the_pattern(self):
        device = BaseDevice(resolved("respeaker_2mic_v1"), fake_drivers())
        device.open(DeviceCallbacks())
        assert device.is_animated(DisplayState(DisplayFunction.LISTENING, None, LightState()))
        assert not device.is_animated(DisplayState(DisplayFunction.MUTED, None, LightState()))

    def test_decide_press_uses_the_role(self):
        device = BaseDevice(resolved("respeaker_2mic_v1"), fake_drivers())
        action = device.decide_press(device.device.buttons[0], "single", LvaStatus(state="idle"), True, False)
        assert [c.name for c in action.commands] == ["listening_start", "button_pressed"]

    def test_volume_buttons_repeat(self):
        device = BaseDevice(resolved("jabra_speak_410"), fake_drivers())
        configs = {button.name: device.detection_for(button) for button in device.device.buttons}
        assert configs["volume_up"].repeat_after is not None
        assert configs["call"].repeat_after is None

    def test_no_hardware_mute_by_default(self, caplog):
        device = BaseDevice(resolved("respeaker_2mic_v1"), fake_drivers())
        assert device.hardware_mute == HardwareMute()
        device.switch_hardware_mute(True)
        assert "cannot switch a hardware mute" in caplog.text
        assert device.read_sensor("temperature") is None

    def test_report_hardware_mute_calls_the_callback(self):
        device = BaseDevice(resolved("respeaker_2mic_v1"), fake_drivers())
        on_hardware_mute = MagicMock()
        device.open(DeviceCallbacks(on_hardware_mute=on_hardware_mute))
        device.report_hardware_mute()
        on_hardware_mute.assert_called_once_with(HardwareMute())

    def test_close_closes_everything_once(self):
        drivers = fake_drivers()
        device = BaseDevice(resolved("respeaker_2mic_v1"), drivers)
        device.open(DeviceCallbacks())
        device.close()
        device.close()
        drivers.led_strip.return_value.close.assert_called_once()
        drivers.gpio_input.return_value.close.assert_called_once()


class TestRespeaker4mic:
    def test_powers_the_leds_before_opening_them(self):
        drivers = fake_drivers()
        order = MagicMock()
        drivers.gpio_output.side_effect = order.power
        drivers.led_strip.side_effect = lambda spec: order.leds(spec.count)
        create_device(resolved("respeaker_4mic"), drivers).open(DeviceCallbacks())
        assert order.mock_calls[:2] == [call.power(5, True), call.leds(12)]


class TestJabraDecodeReport:
    def test_first_telephony_report_only_sets_the_state(self):
        inputs, edges = decode_report(bytes([3, 1, 0]), JabraInputs(), 0.0)
        assert (inputs.telephony, edges) == (1, ())

    def test_hook_change_is_a_click_of_the_call_button(self):
        _, edges = decode_report(bytes([3, 1, 0]), JabraInputs(telephony=0), 10.0)
        assert edges == (("call", True), ("call", False))

    def test_mute_bit_is_down_and_up(self):
        inputs, edges = decode_report(bytes([3, 8, 0]), JabraInputs(telephony=0), 10.0)
        assert edges == (("mute", True),)
        assert inputs.last_mute_press == 10.0
        _, edges = decode_report(bytes([3, 0, 0]), inputs, 10.1)
        assert edges == (("mute", False),)

    def test_hook_change_right_after_a_mute_press_is_ignored(self):
        _, edges = decode_report(bytes([3, 1, 0]), JabraInputs(telephony=0, last_mute_press=10.0), 10.5)
        assert edges == ()
        _, edges = decode_report(bytes([3, 1, 0]), JabraInputs(telephony=0, last_mute_press=10.0), 11.5)
        assert edges == (("call", True), ("call", False))

    def test_flash_or_bit_11_ends_a_call(self):
        _, edges = decode_report(bytes([3, 0, 8]), JabraInputs(telephony=0, last_mute_press=10.0), 10.1)
        assert edges == (("call", True), ("call", False))
        _, edges = decode_report(bytes([3, 0x10, 0]), JabraInputs(telephony=0), 10.1)
        assert edges == (("call", True), ("call", False))

    def test_volume_buttons(self):
        inputs, edges = decode_report(bytes([1, 2]), JabraInputs(), 0.0)
        assert edges == (("volume_up", True),)
        _, edges = decode_report(bytes([1, 1]), inputs, 0.1)
        assert edges == (("volume_up", False), ("volume_down", True))

    def test_other_reports_are_ignored(self):
        inputs = JabraInputs(telephony=0)
        assert decode_report(bytes([5, 1]), inputs, 0.0) == (inputs, ())


class TestJabraLeds:
    @pytest.mark.parametrize(
        "function,bits",
        [
            (None, 0),
            (DisplayFunction.LISTENING, LED_OFF_HOOK),
            (DisplayFunction.THINKING, LED_FLASHING),
            (DisplayFunction.TTS, LED_HOLD),
            (DisplayFunction.MUTED, LED_RED),
            (DisplayFunction.TIMER_RINGING, LED_FLASHING),
        ],
    )
    def test_led_state_of_the_function(self, function, bits):
        assert led_report(DisplayState(function, None, LightState()), 0.0) == (3, bits, 0)

    def test_error_blinks(self):
        display = DisplayState(DisplayFunction.PIPELINE_ERROR, None, LightState(), started_at=1.0)
        assert led_report(display, 1.1) == (3, LED_RED, 0)
        assert led_report(display, 1.3) == (3, 0, 0)

    def test_device_writes_only_changes_and_reports_buttons(self):
        drivers = fake_drivers()
        device = create_device(resolved("jabra_speak_410"), drivers)
        on_button = MagicMock()
        device.open(DeviceCallbacks(on_button=on_button))
        vendor_id, on_report = drivers.hid.call_args.args
        assert vendor_id == 0x0B0E
        hid = drivers.hid.return_value
        listening = DisplayState(DisplayFunction.LISTENING, None, LightState())
        device.draw(listening, 0.0)
        device.draw(listening, 0.1)
        hid.write.assert_called_once_with((3, LED_OFF_HOOK, 0))
        assert device.is_animated(DisplayState(DisplayFunction.NO_CONNECTION, None, LightState()))
        on_report(bytes([1, 2]))
        on_button.assert_called_once_with("volume_up", True)
        device.close()
        hid.write.assert_called_with((3, 0, 0))
        hid.close.assert_called_once()

    def test_buttons_keep_their_roles(self):
        roles = {b.name: b.role for b in resolved("jabra_speak_410").buttons}
        assert roles == {"call": ButtonRole.ACTION, "mute": ButtonRole.MUTE, "volume_up": ButtonRole.VOLUME_UP, "volume_down": ButtonRole.VOLUME_DOWN}
