"""Messages of the LVA peripheral API version 2, as LPC reads and writes them.

Only the wire format lives here: parsing an event of LVA and building a command for it. What an event means is decided in
``lva_status.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

API_VERSION = "v2"
COMMANDS = frozenset({"start_listening", "stop", "mute_on", "mute_off", "volume_up", "volume_down", "volume_set", "timer_stop", "button_pressed"})
PRESS_TYPES = ("single", "double", "triple", "long")


@dataclass(frozen=True)
class LvaEvent:
    """An event that LVA sent."""

    name: str
    data: Mapping[str, Any] = field(default_factory=dict)


def lva_url(host: str, port: int) -> str:
    """
    Address of the peripheral API of LVA in version 2.
    :param host: Host of LVA.
    :param port: Port of the peripheral API of LVA.
    """
    return f"ws://{host}:{port}/{API_VERSION}"


def parse_event(raw: str | bytes) -> Optional[LvaEvent]:
    """
    Read a message of LVA.
    :param raw: The WebSocket message.
    :return: The event, None if the message is not a JSON object with an event name.
    """
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(message, dict) or not isinstance(message.get("event"), str):
        return None
    data = message.get("data")
    return LvaEvent(name=message["event"], data=data if isinstance(data, dict) else {})


def build_command(name: str, data: Optional[Mapping[str, Any]] = None) -> str:
    """
    Build a command for LVA.
    :param name: Name of the command, one of ``COMMANDS``.
    :param data: Data of the command, left out when None.
    :raises ValueError: If the command is not one of version 2.
    """
    if name not in COMMANDS:
        raise ValueError(f"Unknown command for LVA API {API_VERSION}: {name}")
    message: dict[str, Any] = {"command": name}
    if data is not None:
        message["data"] = dict(data)
    return json.dumps(message)
