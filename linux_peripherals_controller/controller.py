"""The controller: connects LVA to what the device shows.

It holds the status of LVA, lets the pure functions decide which display function is shown and tells the caller when that changes.
It also tells LVA about the hardware mute of the device and passes on the requests of LVA to switch it. The hardware (LEDs,
buttons, the mute itself) is not part of it yet.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

from .button_roles import LvaCommand
from .display import DisplayFunction, TransientDisplay, select_display_function, start_transient
from .hardware_mute import REQUEST_EVENTS, HardwareMute, commands_for_changes, decide_mute_request
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
    :param on_hardware_mute_request: Called with True or False when LVA asks to mute or unmute the hardware, and the device can do that.
    :param clock: Returns the current time in seconds.
    """

    def __init__(
        self,
        lva_host: str,
        lva_port: int,
        on_display_change: Optional[Callable[[Optional[DisplayFunction]], None]] = None,
        on_hardware_mute_request: Optional[Callable[[bool], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bridge = LvaBridge(lva_url(lva_host, lva_port), self._handle_event, self._handle_connection)
        self._on_display_change = on_display_change
        self._on_hardware_mute_request = on_hardware_mute_request
        self._clock = clock
        self._link_connected = False
        self._status = LvaStatus()
        self._transient: Optional[TransientDisplay] = None
        self._display: Optional[DisplayFunction] = DisplayFunction.NO_CONNECTION
        self._reselect_handle: Optional[asyncio.TimerHandle] = None
        self._hardware_mute: Optional[HardwareMute] = None
        self._told_lva: Optional[HardwareMute] = None
        self._sending: set[asyncio.Task] = set()

    @property
    def display(self) -> Optional[DisplayFunction]:
        """The display function that is shown now, None for the background."""
        return self._display

    def set_hardware_mute(self, hardware: Optional[HardwareMute]) -> None:
        """
        Tell the controller the hardware mute of the device. Call it on the event loop, whenever it changes.
        :param hardware: The hardware mute, None if the device has none. LVA is told about every change, and about the whole
        state after a new connection.
        """
        self._hardware_mute = hardware
        self._send_hardware_mute()

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
        self._told_lva = None
        self._reselect(link_connected=connected)
        self._send_hardware_mute()

    def _handle_event(self, event: LvaEvent) -> None:
        if event.name in REQUEST_EVENTS:
            self._handle_mute_request(event.name)
            return
        update = apply_event(self._status, event)
        self._status = update.status
        if update.transient is not None:
            self._transient = start_transient(update.transient, self._clock())
        self._reselect(link_connected=True)

    def _handle_mute_request(self, event_name: str) -> None:
        request = decide_mute_request(event_name, self._hardware_mute)
        _LOGGER.debug("Request of LVA: %s", request.reason)
        if request.muted is not None and self._on_hardware_mute_request is not None:
            self._on_hardware_mute_request(request.muted)

    def _send_hardware_mute(self) -> None:
        if not self._link_connected:
            return
        commands = commands_for_changes(self._told_lva, self._hardware_mute)
        if not commands:
            return
        self._told_lva = self._hardware_mute
        task = asyncio.get_running_loop().create_task(self._send_commands(commands))
        self._sending.add(task)
        task.add_done_callback(self._sending.discard)

    async def _send_commands(self, commands: tuple[LvaCommand, ...]) -> None:
        for command in commands:
            if not await self._bridge.send_command(command.name, command.data):
                self._told_lva = None
                return

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
