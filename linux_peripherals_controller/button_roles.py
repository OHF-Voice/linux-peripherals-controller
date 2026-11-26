"""What a press of a button does, by the role of the button.

The role says what a button is for. A press of it controls the assistant (commands for LVA) and is reported to Home Assistant. The
two are independent of each other. The function takes everything it needs as parameters and returns the decision, it sends
nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Optional, Tuple

from .lva_protocol import PRESS_TYPES
from .lva_status import LvaStatus

_BUSY_STATES = ("listening", "thinking", "tts", "announce")


class ButtonRole(StrEnum):
    """What a button is for."""

    ACTION = "action"
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    MUTE = "mute"
    USER = "user"


@dataclass(frozen=True)
class LvaCommand:
    """A command for LVA."""

    name: str
    data: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class ButtonAction:
    """The decision for one press."""

    reason: str
    commands: Tuple[LvaCommand, ...] = ()
    report_to_ha: bool = False


def decide_button_action(role: ButtonRole, press: str, status: LvaStatus, link_connected: bool, child_lock: bool) -> ButtonAction:
    """
    Decide what a press of a button does.
    :param role: The role of the button.
    :param press: ``single``, ``double``, ``triple``, ``long`` or ``repeat``.
    :param status: The status of LVA.
    :param link_connected: True while LPC is connected to LVA.
    :param child_lock: True while the child lock is on.
    :return: The commands for LVA, in the order they are sent, and whether the press is reported to Home Assistant. ``reason``
    says why, for the log.

    The two destinations are independent. Every press (not ``repeat``) is reported to Home Assistant, whatever the role, the
    child lock or the connection to LVA. For LVA, only a single press has a function (the volume buttons also on ``repeat``) and
    every press is also sent as ``button_pressed``, so LVA plays its sound. Nothing is sent to LVA while the child lock is on or
    LPC is not connected to it.
    """
    report = press in PRESS_TYPES
    if child_lock:
        return ButtonAction(f"{press} press of {role} not sent to LVA: the child lock is on", report_to_ha=report)
    if not link_connected:
        return ButtonAction(f"{press} press of {role} not sent to LVA: not connected to LVA", report_to_ha=report)

    function = _function_command(role, press, status)
    commands = ((function,) if function is not None else ()) + _button_pressed(press)
    reason = f"{press} press of {role}" + (f": {function.name}" if function is not None else " has no function")
    return ButtonAction(reason, commands, report_to_ha=report)


def _function_command(role: ButtonRole, press: str, status: LvaStatus) -> Optional[LvaCommand]:
    if role == ButtonRole.VOLUME_UP and press in ("single", "repeat"):
        return LvaCommand("volume_up")
    if role == ButtonRole.VOLUME_DOWN and press in ("single", "repeat"):
        return LvaCommand("volume_down")
    if press != "single":
        return None
    if role == ButtonRole.MUTE:
        return LvaCommand("mute_off" if status.muted else "mute_on")
    if role == ButtonRole.ACTION:
        if status.timer_status == "ringing":
            return LvaCommand("timer_stop")
        if status.state in _BUSY_STATES:
            return LvaCommand("stop")
        return LvaCommand("start_listening")
    return None


def _button_pressed(press: str) -> Tuple[LvaCommand, ...]:
    if press not in PRESS_TYPES:
        return ()
    return (LvaCommand("button_pressed", {"press": press}),)
