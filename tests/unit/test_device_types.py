"""Unit tests for device_types.py."""

import pytest

from linux_peripherals_controller.button_roles import ButtonRole
from linux_peripherals_controller.device_types import DEVICE_TYPES, UnknownDeviceType, get_device_type, known_device_types
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
        assert all(s.interval > 0 for s in sensors)

    @pytest.mark.parametrize("name", sorted(DEVICE_TYPES))
    def test_overrides_only_name_offered_functions(self, name):
        device_type = DEVICE_TYPES[name]
        assert set(device_type.colors) <= device_type.functions
        assert set(device_type.patterns) <= device_type.functions

    @pytest.mark.parametrize("name", sorted(DEVICE_TYPES))
    def test_led_count_is_positive(self, name):
        leds = DEVICE_TYPES[name].leds
        assert leds is None or leds.count > 0


class TestRespeaker2micV1:
    def test_hardware(self):
        device_type = get_device_type("respeaker_2mic_v1")
        assert (device_type.leds.driver, device_type.leds.count) == ("apa102", 3)
        assert [(b.name, b.role, b.pin) for b in device_type.buttons] == [("button", ButtonRole.ACTION, 17)]

    def test_offers_every_function(self):
        assert get_device_type("respeaker_2mic_v1").functions == frozenset(DisplayFunction)
