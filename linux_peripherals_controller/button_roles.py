"""What a press of a button does, by the role of the button.

The role says what a button is for. A press of it either controls the assistant (commands for LVA), or is only reported to Home
Assistant, or does nothing because the child lock is on. The function takes everything it needs as parameters and returns the
decision, it sends nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Optional, Tuple

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
    data: Optional[Mapping[str, str]] = None


@dataclass(frozen=True)
class ButtonAction:
    """The decision for one press."""

    reason: str
    commands: Tuple[LvaCommand, ...] = ()
    report_to_ha: bool = False


def decide_button_action(
    role: ButtonRole,
    press: str,
    status: LvaStatus,
    link_connected: bool,
    child_lock: bool,
    report_to_ha: bool = False,
) -> ButtonAction:
    """
    Decide what a press of a button does.
    :param role: The role of the button.
    :param press: ``single``, ``double``, ``triple``, ``long`` or ``repeat``.
    :param status: The status of LVA.
    :param link_connected: True while LPC is connected to LVA.
    :param child_lock: True while the child lock is on.
    :param report_to_ha: True if every press of a button with a role other than ``user`` is also reported to Home Assistant.
    :return: The commands for LVA, in the order they are sent, and whether the press is reported to Home Assistant. ``reason`` says
    why, for the log.

    Buttons with the role ``user`` only report to Home Assistant, also while the child lock is on. For the other roles only a
    single press has an effect (the volume buttons also on ``repeat``), and nothing happens while the child lock is on. Every
    press that is not ignored is also sent to LVA as ``button_pressed``, so LVA plays its sound. Without a connection to LVA
    nothing is sent to it.
    """
    if role == ButtonRole.USER:
        return ButtonAction(f"{press} press of a user button", _button_pressed(press, link_connected), report_to_ha=press in PRESS_TYPES)
    if child_lock:
        return ButtonAction(f"{press} press ignored: the child lock is on")

    report = report_to_ha and press in PRESS_TYPES
    if not link_connected:
        return ButtonAction(f"{press} press of {role} not sent: not connected to LVA", report_to_ha=report)

    function = _function_command(role, press, status)
    commands = ((function,) if function is not None else ()) + _button_pressed(press, link_connected)
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


def _button_pressed(press: str, link_connected: bool) -> Tuple[LvaCommand, ...]:
    if not link_connected or press not in PRESS_TYPES:
        return ()
    return (LvaCommand("button_pressed", {"press": press}),)
