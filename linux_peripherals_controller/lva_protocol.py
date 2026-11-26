"""Messages of the LVA peripheral API version 2, as LPC reads and writes them.

A message is an event when it reports something and a command when it asks for something, whatever the direction. LVA sends events
(its status) and commands (switch the hardware mute). LPC sends commands (what the buttons do) and events (the hardware mute of the
device). Only the wire format lives here. What a message means is decided in ``lva_status.py`` and ``hardware_mute.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

API_VERSION = "v2"
COMMANDS = frozenset({"listening_start", "listening_stop", "mute_on", "mute_off", "volume_up", "volume_down", "volume_set", "volume_silent", "timer_stop", "button_pressed"})
REPORTED_EVENTS = frozenset({"hardware_mute_status", "hardware_mute_type"})
PRESS_TYPES = ("single", "double", "triple", "long")


@dataclass(frozen=True)
class LvaEvent:
    """An event that LVA sent: it reports its status."""

    name: str
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LvaRequest:
    """A command that LVA sent: it asks LPC to do something."""

    name: str
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LvaMessage:
    """A message for LVA: a command (``COMMANDS``) or an event (``REPORTED_EVENTS``)."""

    name: str
    data: Optional[Mapping[str, Any]] = None


def lva_url(host: str, port: int) -> str:
    """
    Address of the peripheral API of LVA in version 2.
    :param host: Host of LVA.
    :param port: Port of the peripheral API of LVA.
    """
    return f"ws://{host}:{port}/{API_VERSION}"


def parse_message(raw: str | bytes) -> Optional[LvaEvent | LvaRequest]:
    """
    Read a message of LVA.
    :param raw: The WebSocket message.
    :return: The event, or the request if it is a command. None if the message is not a JSON object with an event or command name.
    """
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(message, dict):
        return None
    data = message.get("data")
    data = data if isinstance(data, dict) else {}
    if isinstance(message.get("event"), str):
        return LvaEvent(name=message["event"], data=data)
    if isinstance(message.get("command"), str):
        return LvaRequest(name=message["command"], data=data)
    return None


def build_message(name: str, data: Optional[Mapping[str, Any]] = None) -> str:
    """
    Build a message for LVA.
    :param name: Name of the message, one of ``COMMANDS`` (sent as a command) or ``REPORTED_EVENTS`` (sent as an event).
    :param data: Data of the message, left out when None.
    :raises ValueError: If the name is not one of version 2.
    """
    if name in COMMANDS:
        kind = "command"
    elif name in REPORTED_EVENTS:
        kind = "event"
    else:
        raise ValueError(f"Unknown message for LVA API {API_VERSION}: {name}")
    message: dict[str, Any] = {kind: name}
    if data is not None:
        message["data"] = dict(data)
    return json.dumps(message)
