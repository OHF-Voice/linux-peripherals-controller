"""Unit tests for appearance.py."""

import pytest

from linux_peripherals_controller.appearance import DEFAULT_COLORS, DEFAULT_PATTERNS, Color, PatternName
from linux_peripherals_controller.display import DisplayFunction


class TestColor:
    def test_from_hex(self):
        assert Color.from_hex("#ff8000") == Color(255, 128, 0)

    def test_hex_digits_may_be_upper_case(self):
        assert Color.from_hex("#FFAA0B") == Color(255, 170, 11)

    @pytest.mark.parametrize("text", ["ff8000", "#ff80", "#ff80000", "#gg0000", "", "red", "#ff 800"])
    def test_anything_else_is_refused(self, text):
        with pytest.raises(ValueError, match="is not a color"):
            Color.from_hex(text)

    def test_color_is_immutable(self):
        with pytest.raises(AttributeError):
            Color(1, 2, 3).red = 5  # type: ignore[misc]


class TestDefaults:
    def test_every_display_function_has_a_color_and_a_pattern(self):
        assert set(DEFAULT_COLORS) == set(DisplayFunction)
        assert set(DEFAULT_PATTERNS) == set(DisplayFunction)

    def test_channels_are_in_range(self):
        for color in DEFAULT_COLORS.values():
            assert all(0 <= channel <= 255 for channel in (color.red, color.green, color.blue))

    def test_patterns_are_known_names(self):
        assert set(DEFAULT_PATTERNS.values()) <= set(PatternName)

    @pytest.mark.parametrize("function", [DisplayFunction.TIMER_ACTIVE, DisplayFunction.VOLUME])
    def test_amounts_are_shown_as_progress(self, function):
        assert DEFAULT_PATTERNS[function] == PatternName.PROGRESS
