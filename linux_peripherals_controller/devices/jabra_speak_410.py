"""Jabra Speak 410: a USB speakerphone with four buttons and fixed LED states, over HID.

Taken from the Jabra example of LVA (``examples/Jabra Speak 410/main.py``), which was tried on the device. Not checked against a
specification of Jabra: the vendor id 0x0b0e, the bits of the reports and the quirks below come only from that example.

- Input report 0x03 (telephony): bit 0 hook switch (call button), bit 3 mute, bit 4 flash and bit 11 (both seen when the call
  button ends a call). Input report 0x01: bit 0 volume down, bit 1 volume up.
- Output report 0x03 (LEDs): bit 0 off hook (green), bit 2 mute (red), bit 3 ring (flashing), bit 4 hold (partly flashing).
- The hook switch is a state the device toggles itself, so every change of it counts as one press of the call button. Right after
  a mute press the device reports a hook change that nobody pressed: such a change within 1 s after the mute button is ignored.

The device file reads the buttons itself (no GPIO) and shows the display functions with the fixed LED states instead of colors.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from ..animation import DisplayState
from ..button_roles import ButtonRole
from ..device_setup import ResolvedDevice
from ..device_types import ButtonSpec, DeviceType
from ..display import DisplayFunction
from ..drivers import DriverError, Drivers, HidWriter
from ..light import LightState
from .base import BaseDevice, ButtonCallback, HardwareMuteCallback

VENDOR_ID = 0x0B0E
TELEPHONY_REPORT = 0x03
VOLUME_REPORT = 0x01
LED_REPORT = 0x03
SPURIOUS_HOOK_SECONDS = 1.0
BLINK_PERIOD_SECONDS = 0.5

_HOOK_SWITCH = 1 << 0
_MUTE = 1 << 3
_FLASH = 1 << 4
_CALL_END = 1 << 11
_VOLUME_DOWN = 1 << 0
_VOLUME_UP = 1 << 1

LED_OFF_HOOK = 1 << 0
LED_MUTE = 1 << 2
LED_RING = 1 << 3
LED_HOLD = 1 << 4
LED_RED = LED_MUTE | LED_OFF_HOOK
LED_FLASHING = LED_RING | LED_OFF_HOOK

# The LED states of the Jabra example: green while listening, flashing while the assistant is busy or a timer rings, red when
# muted or on an error, partly flashing while it speaks.
LED_STATES: Mapping[Optional[DisplayFunction], int] = {
    None: 0,
    DisplayFunction.WAKE_WORD: LED_FLASHING,
    DisplayFunction.LISTENING: LED_OFF_HOOK,
    DisplayFunction.THINKING: LED_FLASHING,
    DisplayFunction.TTS: LED_HOLD,
    DisplayFunction.ANNOUNCE: LED_HOLD,
    DisplayFunction.TIMER_RINGING: LED_FLASHING,
    DisplayFunction.TIMER_TIMEOUT: LED_FLASHING,
    DisplayFunction.MUTED: LED_RED,
    DisplayFunction.PIPELINE_ERROR: LED_RED,
    DisplayFunction.NO_CONNECTION: LED_RED,
    DisplayFunction.VOLUME: 0,
    DisplayFunction.TIMER_ACTIVE: 0,
}
BLINKING = frozenset({DisplayFunction.PIPELINE_ERROR, DisplayFunction.NO_CONNECTION})

DEVICE_TYPE = DeviceType(
    name="jabra_speak_410",
    description="Jabra Speak 410 (USB, vendor 0b0e): call, mute and volume buttons and fixed LED states over HID",
    buttons=(
        ButtonSpec("call", ButtonRole.ACTION),
        ButtonSpec("mute", ButtonRole.MUTE),
        ButtonSpec("volume_up", ButtonRole.VOLUME_UP),
        ButtonSpec("volume_down", ButtonRole.VOLUME_DOWN),
    ),
)


@dataclass(frozen=True)
class JabraInputs:
    """What the last reports said, to find the changes."""

    telephony: Optional[int] = None
    volume: int = 0
    last_mute_press: Optional[float] = None


ButtonEdges = Tuple[Tuple[str, bool], ...]


def decode_report(report: bytes, inputs: JabraInputs, now: float) -> Tuple[JabraInputs, ButtonEdges]:
    """
    Turn an input report into button edges.
    :param report: The report, its id first.
    :param inputs: What the reports before said.
    :param now: The current time in seconds.
    :return: The new inputs and the edges as (button name, down), in order. The call button gives a down and an up at once,
    because the device only reports the toggled hook state. The first telephony report only sets the state.
    """
    if len(report) >= 2 and report[0] == VOLUME_REPORT:
        bits = report[1]
        volume_edges = tuple((name, bool(bits & bit)) for name, bit in (("volume_up", _VOLUME_UP), ("volume_down", _VOLUME_DOWN)) if (bits ^ inputs.volume) & bit)
        return JabraInputs(inputs.telephony, bits, inputs.last_mute_press), volume_edges
    if len(report) >= 3 and report[0] == TELEPHONY_REPORT:
        bits = report[1] | report[2] << 8
        previous = inputs.telephony
        if previous is None:
            return JabraInputs(bits, inputs.volume, inputs.last_mute_press), ()
        edges: ButtonEdges = ()
        last_mute_press = inputs.last_mute_press
        if (bits ^ previous) & _MUTE:
            down = bool(bits & _MUTE)
            edges += (("mute", down),)
            if down:
                last_mute_press = now
        ended = (bits & ~previous) & (_FLASH | _CALL_END)
        hook_changed = (bits ^ previous) & _HOOK_SWITCH
        spurious = hook_changed and not ended and last_mute_press is not None and now - last_mute_press < SPURIOUS_HOOK_SECONDS
        if (hook_changed and not spurious) or ended:
            edges += (("call", True), ("call", False))
        return JabraInputs(bits, inputs.volume, last_mute_press), edges
    return inputs, ()


def led_report(display: DisplayState, now: float) -> Tuple[int, int, int]:
    """
    The output report for what is to be shown.
    :param display: What is to be shown.
    :param now: The current time, for the blinking states.
    :return: The report: its id and the two bytes of LED bits. An error and a lost connection blink red every 0.5 s.
    """
    bits = LED_STATES.get(display.function, 0)
    if display.function in BLINKING and (now - display.started_at) % BLINK_PERIOD_SECONDS >= BLINK_PERIOD_SECONDS / 2:
        bits = 0
    return LED_REPORT, bits & 0xFF, bits >> 8


class Device(BaseDevice):
    """The Jabra Speak 410: buttons and LEDs over HID instead of GPIO and an LED strip."""

    def __init__(self, device: ResolvedDevice, drivers: Drivers) -> None:
        super().__init__(device, drivers)
        self._hid: Optional[HidWriter] = None
        self._inputs = JabraInputs()
        self._last_report: Optional[Tuple[int, int, int]] = None

    def open(self, on_button: ButtonCallback, on_hardware_mute: HardwareMuteCallback) -> None:
        """
        Open the speakerphone over HID.
        :param on_button: Called with the name of a button and whether it went down.
        :param on_hardware_mute: Called whenever the hardware mute changes.
        :raises DriverError: If the device cannot be opened.
        """
        super().open(on_button, on_hardware_mute)
        try:
            self._hid = self.drivers.hid(VENDOR_ID, self._handle_report)
        except DriverError:
            self.close()
            raise
        self.keep(self._hid)

    def close(self) -> None:
        """Turn the LEDs off and release the device."""
        if self._hid is not None:
            self._hid.write(led_report(DisplayState(None, None, LightState()), 0.0))
            self._hid = None
        super().close()

    def draw(self, display: DisplayState, now: float) -> None:
        """
        Set the LED state of the display function, only when it changed.
        :param display: What is to be shown.
        :param now: The current time.
        """
        report = led_report(display, now)
        if self._hid is not None and report != self._last_report:
            self._last_report = report
            self._hid.write(report)

    def is_animated(self, display: DisplayState) -> bool:
        """True while an error or a lost connection blinks."""
        return display.function in BLINKING

    def _handle_report(self, report: bytes) -> None:
        self._inputs, edges = decode_report(report, self._inputs, time.monotonic())
        for name, down in edges:
            self.report_button(name, down)
