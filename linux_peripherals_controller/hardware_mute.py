"""The hardware mute of the microphone of a device.

Some hardware can mute its microphone itself, and sometimes software can switch that. The device is always the authority: the
driver reads the state from the device, and LPC reports the kind of hardware mute and its state to LVA (as events). LVA asks to switch it with
the commands ``hardware_mute_on`` and ``hardware_mute_off``. Home Assistant gets its own
entity from LPC. The functions only decide what to send, what to do and which entity to offer, they send and switch nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Optional, Tuple

from .lva_protocol import LvaMessage

REQUEST_COMMANDS = {"hardware_mute_on": True, "hardware_mute_off": False}


class HardwareMuteType(StrEnum):
    """What kind of hardware mute a device has."""

    NONE = "none"
    CHANGEABLE = "changeable"
    READ_ONLY = "read_only"


class HardwareMuteEntity(StrEnum):
    """The entity that LPC offers to Home Assistant for the hardware mute."""

    SWITCH = "switch"
    BINARY_SENSOR = "binary_sensor"


@dataclass(frozen=True)
class HardwareMute:
    """The hardware mute of a device. Without a hardware mute (``NONE``) ``muted`` has no meaning."""

    type: HardwareMuteType = HardwareMuteType.NONE
    muted: bool = False


@dataclass(frozen=True)
class MuteRequest:
    """The decision about a request to switch the hardware mute."""

    reason: str
    muted: Optional[bool] = None


def messages_for_changes(previous: Optional[HardwareMute], current: HardwareMute) -> Tuple[LvaMessage, ...]:
    """
    Work out what LVA has to be told about the hardware mute, as events.
    :param previous: What LVA was told before, None if it was told nothing (a new connection).
    :param current: What the device has now.
    :return: The events for LVA, ``hardware_mute_type`` first. Only the values that differ from ``previous``, all of them after a
    new connection. The status is only told for a device that has a hardware mute.
    """
    messages = []
    if previous is None or previous.type != current.type:
        messages.append(LvaMessage("hardware_mute_type", {"type": current.type.value}))
    if current.type != HardwareMuteType.NONE:
        status_is_new = previous is None or previous.type == HardwareMuteType.NONE or previous.muted != current.muted
        if status_is_new:
            messages.append(LvaMessage("hardware_mute_status", {"status": "muted" if current.muted else "unmuted"}))
    return tuple(messages)


def decide_mute_request(command: str, hardware: HardwareMute) -> MuteRequest:
    """
    Decide what to do with a request to switch the hardware mute.
    :param command: ``hardware_mute_on`` or ``hardware_mute_off``.
    :param hardware: The hardware mute of the device.
    :return: ``muted`` is the state to switch the hardware to, None if the request is ignored. ``reason`` says why, for the log.
    """
    if command not in REQUEST_COMMANDS:
        return MuteRequest(f"{command} is not a request to switch the hardware mute")
    if hardware.type == HardwareMuteType.NONE:
        return MuteRequest(f"{command} ignored: the device has no hardware mute")
    if hardware.type == HardwareMuteType.READ_ONLY:
        return MuteRequest(f"{command} ignored: the hardware mute of this device can only be read")
    return MuteRequest(f"{command}: switching the hardware mute", REQUEST_COMMANDS[command])


def entity_for(hardware: HardwareMute) -> Optional[HardwareMuteEntity]:
    """
    Choose the entity that Home Assistant gets for the hardware mute.
    :param hardware: The hardware mute of the device.
    :return: A switch if it can be changed, a binary sensor (status only) if it can only be read, None if the device has none.
    """
    if hardware.type == HardwareMuteType.CHANGEABLE:
        return HardwareMuteEntity.SWITCH
    if hardware.type == HardwareMuteType.READ_ONLY:
        return HardwareMuteEntity.BINARY_SENSOR
    return None
