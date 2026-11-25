"""The controller: connects LVA to what the device shows.

It holds the status of LVA, lets the pure functions decide which display function is shown and tells the caller when that changes.
The hardware (LEDs, buttons) is not part of it yet.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

from .display import DisplayFunction, TransientDisplay, select_display_function, start_transient
from .lva_bridge import LvaBridge
from .lva_protocol import LvaEvent, lva_url
from .lva_status import LvaStatus, apply_event

_LOGGER = logging.getLogger(__name__)


class Controller:
    """
    Runs the connection to LVA and works out what the LEDs show.
    :param lva_host: Host of the peripheral API of LVA.
    :param lva_port: Port of the peripheral API of LVA.
    :param on_display_change: Called with the new display function (None for the background) whenever it changes.
    :param clock: Returns the current time in seconds.
    """

    def __init__(
        self,
        lva_host: str,
        lva_port: int,
        on_display_change: Optional[Callable[[Optional[DisplayFunction]], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bridge = LvaBridge(lva_url(lva_host, lva_port), self._handle_event, self._handle_connection)
        self._on_display_change = on_display_change
        self._clock = clock
        self._link_connected = False
        self._status = LvaStatus()
        self._transient: Optional[TransientDisplay] = None
        self._display: Optional[DisplayFunction] = DisplayFunction.NO_CONNECTION
        self._reselect_handle: Optional[asyncio.TimerHandle] = None

    @property
    def display(self) -> Optional[DisplayFunction]:
        """The display function that is shown now, None for the background."""
        return self._display

    async def run(self) -> None:
        """Stay connected to LVA until the task is cancelled."""
        try:
            await self._bridge.run()
        finally:
            if self._reselect_handle is not None:
                self._reselect_handle.cancel()

    def _handle_connection(self, connected: bool) -> None:
        """A (re)connect or a loss starts from an empty status, so nothing old is shown."""
        self._status = LvaStatus()
        self._transient = None
        self._reselect(link_connected=connected)

    def _handle_event(self, event: LvaEvent) -> None:
        update = apply_event(self._status, event)
        self._status = update.status
        if update.transient is not None:
            self._transient = start_transient(update.transient, self._clock())
        self._reselect(link_connected=True)

    def _reselect(self, link_connected: Optional[bool] = None) -> None:
        if link_connected is not None:
            self._link_connected = link_connected
        now = self._clock()
        selected = select_display_function(self._status, self._link_connected, self._transient, now)
        if selected != self._display:
            _LOGGER.debug("Display function: %s -> %s", self._display, selected)
            self._display = selected
            if self._on_display_change is not None:
                self._on_display_change(selected)
        self._schedule_transient_end(now)

    def _schedule_transient_end(self, now: float) -> None:
        if self._reselect_handle is not None:
            self._reselect_handle.cancel()
            self._reselect_handle = None
        if self._transient is not None and now < self._transient.ends_at:
            self._reselect_handle = asyncio.get_running_loop().call_later(self._transient.ends_at - now, self._reselect)
