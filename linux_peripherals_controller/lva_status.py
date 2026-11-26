"""What LPC knows about LVA, worked out from the events of LVA.

The status is an immutable value. Every event of LVA gives a new status and, for the events that are only a short signal, the name
of the display function to show for a short time. Nothing here sends or shows anything.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from .lva_protocol import LvaEvent


@dataclass(frozen=True)
class LvaTimer:
    """One timer as LVA reports it in ``timer_full_data_set``."""

    id: str
    name: str
    status: str
    total_seconds: int
    seconds_left: int
    percentage: int


@dataclass(frozen=True)
class LvaStatus:
    """
    The status of LVA. A value is None until LVA has reported it.

    ``timer_status`` and the two ``timer_remaining_*`` values describe the timer that is nearest to ringing, ``timers`` holds all of them.
    """

    lva_status: Optional[str] = None
    state: Optional[str] = None
    muted: Optional[bool] = None
    volume: Optional[int] = None
    timer_status: Optional[str] = None
    timer_remaining_time: Optional[int] = None
    timer_remaining_percentage: Optional[int] = None
    timers: Optional[Tuple[LvaTimer, ...]] = None
    media_player_status: Optional[str] = None


@dataclass(frozen=True)
class StatusUpdate:
    """The result of one event of LVA."""

    status: LvaStatus
    transient: Optional[str] = None


_STATUS_EVENTS: dict[str, tuple[str, str, type]] = {
    "lva_status": ("status", "lva_status", str),
    "state": ("state", "state", str),
    "volume_status": ("volume", "volume", int),
    "timer_status": ("status", "timer_status", str),
    "timer_remaining_time": ("seconds", "timer_remaining_time", int),
    "timer_remaining_percentage": ("percentage", "timer_remaining_percentage", int),
    "media_player_status": ("status", "media_player_status", str),
}
_MUTE_STATUSES = {"muted": True, "unmuted": False}


def apply_event(status: LvaStatus, event: LvaEvent) -> StatusUpdate:
    """
    Take an event of LVA into account.
    :param status: The status before the event.
    :param event: The event of LVA.
    :return: The new status. ``transient`` names the display function to show for a short time: the state ``pipeline_error``, a
    ringing timer that stopped on its own (``auto_stopped`` in ``timer_status``) and a changed volume, but not the first volume LVA
    reports. Events that are not known, or have invalid data, change nothing.
    """
    if event.name == "mute_status":
        return _apply_mute_status(status, event)
    if event.name == "timer_full_data_set":
        return _apply_timers(status, event)

    spec = _STATUS_EVENTS.get(event.name)
    if spec is None:
        return StatusUpdate(status)

    key, attribute, expected_type = spec
    value = event.data.get(key)
    if not _is_valid(value, expected_type):
        return StatusUpdate(status)

    updated = dataclasses.replace(status, **{attribute: value})
    return StatusUpdate(updated, _transient_after(status, event, attribute, value))


def _apply_mute_status(status: LvaStatus, event: LvaEvent) -> StatusUpdate:
    muted = _MUTE_STATUSES.get(event.data.get("status"))  # type: ignore[arg-type]
    if muted is None:
        return StatusUpdate(status)
    return StatusUpdate(dataclasses.replace(status, muted=muted))


def _apply_timers(status: LvaStatus, event: LvaEvent) -> StatusUpdate:
    raw_timers = event.data.get("timers")
    if not isinstance(raw_timers, list):
        return StatusUpdate(status)
    timers = tuple(timer for timer in (_parse_timer(raw) for raw in raw_timers) if timer is not None)
    if len(timers) != len(raw_timers):
        return StatusUpdate(status)
    return StatusUpdate(dataclasses.replace(status, timers=timers))


def _parse_timer(raw: Any) -> Optional[LvaTimer]:
    if not isinstance(raw, dict):
        return None
    texts = (raw.get("id"), raw.get("name"), raw.get("status"))
    numbers = (raw.get("total_seconds"), raw.get("seconds_left"), raw.get("percentage"))
    if not all(isinstance(text, str) for text in texts) or not all(_is_valid(number, int) for number in numbers):
        return None
    return LvaTimer(*texts, *numbers)  # type: ignore[arg-type]


def _transient_after(status: LvaStatus, event: LvaEvent, attribute: str, value: Any) -> Optional[str]:
    if attribute == "state" and value == "pipeline_error":
        return "pipeline_error"
    if attribute == "timer_status" and event.data.get("auto_stopped") is True:
        return "timer_timeout"
    if attribute == "volume" and status.volume is not None and status.volume != value:
        return "volume"
    return None


def _is_valid(value: Any, expected_type: type) -> bool:
    if expected_type is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, expected_type)
