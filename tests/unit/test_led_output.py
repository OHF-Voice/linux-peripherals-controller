"""Unit tests for led_output.py."""

import asyncio
from unittest.mock import MagicMock

from linux_peripherals_controller.animation import DisplayState
from linux_peripherals_controller.display import DisplayFunction
from linux_peripherals_controller.led_output import LedOutput
from linux_peripherals_controller.light import LightState

STILL = DisplayState(None, None, LightState())
MOVING = DisplayState(DisplayFunction.LISTENING, None, LightState())


def make_device():
    device = MagicMock()
    device.is_animated.side_effect = lambda display: display.function is not None
    return device


async def test_show_draws_once_for_a_still_display():
    device = make_device()
    output = LedOutput(device, clock=lambda: 5.0, frame_interval=0.01)
    output.show(STILL)
    await asyncio.sleep(0.03)
    device.draw.assert_called_once_with(STILL, 5.0)
    assert output.display == STILL


async def test_moving_display_is_drawn_every_frame_until_it_changes():
    device = make_device()
    output = LedOutput(device, clock=lambda: 5.0, frame_interval=0.005)
    output.show(MOVING)
    await asyncio.sleep(0.04)
    assert device.draw.call_count > 2
    output.show(STILL)
    count = device.draw.call_count
    await asyncio.sleep(0.03)
    assert device.draw.call_count == count


async def test_close_stops_the_frames():
    device = make_device()
    output = LedOutput(device, clock=lambda: 5.0, frame_interval=0.005)
    output.show(MOVING)
    output.close()
    await asyncio.sleep(0.03)
    assert device.draw.call_count == 1
