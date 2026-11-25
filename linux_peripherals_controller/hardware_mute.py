"""The hardware mute of the microphone of a device.

Some hardware can mute its microphone itself, and sometimes software can switch that. LPC tells LVA whether the device has such a
mute, whether software can switch it and whether it is on. LVA shows it in Home Assistant and asks LPC to switch it. The
functions only decide what to send and what to do, they send and switch nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .button_roles import LvaCommand

REQUEST_EVENTS = {"hardware_mute_on": True, "hardware_mute_off": False}


@dataclass(frozen=True)
class HardwareMute:
    """The hardware mute of a device that has one."""

    possible: bool
    muted: bool


@dataclass(frozen=True)
class MuteRequest:
    """The decision about a request of LVA to switch the hardware mute."""

    reason: str
    muted: Optional[bool] = None


def commands_for_changes(previous: Optional[HardwareMute], current: Optional[HardwareMute]) -> Tuple[LvaCommand, ...]:
    """
    Work out what LVA has to be told about the hardware mute.
    :param previous: What LVA was told before, None if it was told nothing (a new connection).
    :param current: What the device has now, None if it has no hardware mute.
    :return: The commands for LVA, ``hardware_mute_possible`` first. Only the values that differ from ``previous``, all of them
    after a new connection. Nothing for a device without a hardware mute.
    """
    if current is None:
        return ()
    commands = []
    if previous is None or previous.possible != current.possible:
        commands.append(LvaCommand("hardware_mute_possible", {"possible": current.possible}))
    if previous is None or previous.muted != current.muted:
        commands.append(LvaCommand("hardware_mute_status", {"status": "muted" if current.muted else "unmuted"}))
    return tuple(commands)


def decide_mute_request(event: str, hardware: Optional[HardwareMute]) -> MuteRequest:
    """
    Decide what to do with a request of LVA to switch the hardware mute.
    :param event: ``hardware_mute_on`` or ``hardware_mute_off``.
    :param hardware: The hardware mute of the device, None if it has none.
    :return: ``muted`` is the state to switch the hardware to, None if the request is ignored. ``reason`` says why, for the log.
    """
    if event not in REQUEST_EVENTS:
        return MuteRequest(f"{event} is not a request to switch the hardware mute")
    if hardware is None:
        return MuteRequest(f"{event} ignored: the device has no hardware mute")
    if not hardware.possible:
        return MuteRequest(f"{event} ignored: software cannot switch the hardware mute of this device")
    return MuteRequest(f"{event}: switching the hardware mute", REQUEST_EVENTS[event])
