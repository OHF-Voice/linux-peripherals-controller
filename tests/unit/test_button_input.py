"""Unit tests for button_input.py."""

import asyncio
import logging

from linux_peripherals_controller.button_input import ButtonInput
from linux_peripherals_controller.press_detection import DetectionConfig


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def make_input(config=None):
    clock = Clock()
    presses = []
    button_input = ButtonInput({"button": config or DetectionConfig()}, lambda name, press: presses.append((name, press)), clock)
    return button_input, clock, presses


async def test_single_press_is_reported_after_the_gap():
    button_input, clock, presses = make_input(DetectionConfig(gap=0.01))
    button_input.change("button", True)
    clock.now += 0.05
    button_input.change("button", False)
    clock.now += 0.02
    await asyncio.sleep(0.03)
    assert presses == [("button", "single")]
    button_input.close()


async def test_long_press_is_reported_while_held():
    button_input, clock, presses = make_input(DetectionConfig(long_after=0.01))
    button_input.change("button", True)
    clock.now += 0.02
    await asyncio.sleep(0.03)
    assert presses == [("button", "long")]
    button_input.close()


async def test_unknown_button_is_ignored(caplog):
    button_input, _, presses = make_input()
    with caplog.at_level(logging.DEBUG):
        button_input.change("ghost", True)
    assert presses == []
    assert "Ignoring button 'ghost'" in caplog.text


async def test_close_stops_the_pending_ticks():
    button_input, clock, presses = make_input(DetectionConfig(gap=0.01))
    button_input.change("button", True)
    button_input.change("button", False)
    button_input.close()
    clock.now += 1.0
    await asyncio.sleep(0.03)
    assert presses == []


async def test_presses_are_logged(caplog):
    button_input, clock, _ = make_input(DetectionConfig(long_after=0.01))
    with caplog.at_level(logging.DEBUG):
        button_input.change("button", True)
        clock.now += 0.02
        await asyncio.sleep(0.03)
    assert "Button 'button': long press" in caplog.text
    button_input.close()
