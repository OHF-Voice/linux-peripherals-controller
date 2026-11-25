"""What LPC knows about LVA, worked out from the events of LVA.

The status is an immutable value. Every event of LVA gives a new status and, for the events that are only a short signal, the name
of the display function to show for a short time. Nothing here sends or shows anything.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Optional

from .lva_protocol import LvaEvent


@dataclass(frozen=True)
class LvaStatus:
    """The status of LVA. A value is None until LVA has reported it."""

    lva_status: Optional[str] = None
    state: Optional[str] = None
    muted: Optional[bool] = None
    volume: Optional[int] = None
    timer_status: Optional[str] = None
    timer_remaining_time: Optional[int] = None
    timer_remaining_percentage: Optional[int] = None
    media_player_status: Optional[str] = None


@dataclass(frozen=True)
class StatusUpdate:
    """The result of one event of LVA."""

    status: LvaStatus
    transient: Optional[str] = None


_STATUS_EVENTS: dict[str, tuple[str, str, type]] = {
    "lva_status": ("status", "lva_status", str),
    "state": ("state", "state", str),
    "mute_status": ("muted", "muted", bool),
    "volume_status": ("volume", "volume", int),
    "timer_status": ("status", "timer_status", str),
    "timer_remaining_time": ("seconds", "timer_remaining_time", int),
    "timer_remaining_percentage": ("percentage", "timer_remaining_percentage", int),
    "media_player_status": ("status", "media_player_status", str),
}
_SIGNAL_EVENTS = {"pipeline_error": "pipeline_error", "timer_auto_stopped": "timer_timeout"}


def apply_event(status: LvaStatus, event: LvaEvent) -> StatusUpdate:
    """
    Take an event of LVA into account.
    :param status: The status before the event.
    :param event: The event of LVA.
    :return: The new status. ``transient`` names the display function to show for a short time: the signal events
    (``pipeline_error``, ``timer_auto_stopped``) and a changed volume, but not the first volume LVA reports.
    Events that are not known, or have invalid data, change nothing.
    """
    if event.name in _SIGNAL_EVENTS:
        return StatusUpdate(status, _SIGNAL_EVENTS[event.name])

    spec = _STATUS_EVENTS.get(event.name)
    if spec is None:
        return StatusUpdate(status)

    key, attribute, expected_type = spec
    value = event.data.get(key)
    if not _is_valid(value, expected_type):
        return StatusUpdate(status)

    updated = dataclasses.replace(status, **{attribute: value})
    volume_changed = attribute == "volume" and status.volume is not None and status.volume != value
    return StatusUpdate(updated, "volume" if volume_changed else None)


def _is_valid(value: Any, expected_type: type) -> bool:
    if expected_type is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, expected_type)
