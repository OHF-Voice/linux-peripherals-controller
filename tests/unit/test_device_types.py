"""Unit tests for the device types: device_types.py and the registry in devices/__init__.py."""

import pytest

from linux_peripherals_controller.button_roles import ButtonRole
from linux_peripherals_controller.device_types import UnknownDeviceType
from linux_peripherals_controller.devices import DEVICE_FILES, DEVICE_TYPES, get_device_type, known_device_types
from linux_peripherals_controller.display import DisplayFunction


class TestRegistry:
    def test_get_device_type(self):
        assert get_device_type("respeaker_2mic_v1").name == "respeaker_2mic_v1"

    def test_unknown_type_names_the_known_ones(self):
        with pytest.raises(UnknownDeviceType) as error:
            get_device_type("toaster")
        assert "Unknown device type 'toaster'" in str(error.value)
        assert "respeaker_2mic_v1" in str(error.value)
        assert error.value.known == known_device_types()

    def test_known_types_are_sorted(self):
        assert list(known_device_types()) == sorted(DEVICE_TYPES)

    def test_name_is_the_key(self):
        for name, device_type in DEVICE_TYPES.items():
            assert device_type.name == name

    def test_every_device_file_is_a_device_type(self):
        assert sorted(DEVICE_FILES) == sorted(DEVICE_TYPES)


class TestEveryDeviceType:
    @pytest.mark.parametrize("name", sorted(DEVICE_TYPES))
    def test_buttons_have_unique_names_and_valid_roles(self, name):
        buttons = DEVICE_TYPES[name].buttons
        assert len({b.name for b in buttons}) == len(buttons)
        assert all(isinstance(b.role, ButtonRole) for b in buttons)

    @pytest.mark.parametrize("name", sorted(DEVICE_TYPES))
    def test_sensors_have_unique_names_and_positive_intervals(self, name):
        sensors = DEVICE_TYPES[name].sensors
        assert len({s.name for s in sensors}) == len(sensors)
        assert all(s.interval is None or s.interval > 0 for s in sensors)

    @pytest.mark.parametrize("name", sorted(DEVICE_TYPES))
    def test_controls_have_unique_names_and_a_range(self, name):
        controls = DEVICE_TYPES[name].controls
        assert len({c.name for c in controls}) == len(controls)
        assert all(c.minimum < c.maximum and c.step > 0 for c in controls)

    @pytest.mark.parametrize("name", sorted(DEVICE_TYPES))
    def test_overrides_only_name_offered_functions(self, name):
        device_type = DEVICE_TYPES[name]
        assert set(device_type.colors) <= device_type.functions
        assert set(device_type.patterns) <= device_type.functions

    @pytest.mark.parametrize("name", sorted(DEVICE_TYPES))
    def test_led_count_is_positive(self, name):
        leds = DEVICE_TYPES[name].leds
        assert leds is None or leds.count > 0


class TestHardware:
    @pytest.mark.parametrize("name", ["respeaker_2mic_v1", "respeaker_2mic_v2"])
    def test_respeaker_2mic(self, name):
        device_type = get_device_type(name)
        assert (device_type.leds.driver, device_type.leds.count) == ("apa102", 3)
        assert [(b.name, b.role, b.pin) for b in device_type.buttons] == [("button", ButtonRole.ACTION, 17)]

    def test_respeaker_4mic(self):
        device_type = get_device_type("respeaker_4mic")
        assert (device_type.leds.driver, device_type.leds.count, device_type.leds.options["spi_device"]) == ("apa102", 12, 1)
        assert device_type.buttons == ()

    def test_respeaker_xvf3000(self):
        device_type = get_device_type("respeaker_xvf3000")
        assert (device_type.leds.driver, device_type.leds.count) == ("usb_pixel_ring", 12)
        assert device_type.buttons == ()

    def test_jabra_speak_410(self):
        device_type = get_device_type("jabra_speak_410")
        assert device_type.leds is None
        assert [(b.name, b.role, b.pin) for b in device_type.buttons] == [
            ("call", ButtonRole.ACTION, None),
            ("mute", ButtonRole.MUTE, None),
            ("volume_up", ButtonRole.VOLUME_UP, None),
            ("volume_down", ButtonRole.VOLUME_DOWN, None),
        ]

    @pytest.mark.parametrize("name", sorted(DEVICE_TYPES))
    def test_offers_every_function(self, name):
        assert get_device_type(name).functions == frozenset(DisplayFunction)
