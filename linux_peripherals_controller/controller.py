"""The controller: connects LVA to what the device shows.

It holds the status of LVA, lets the pure functions decide which display function is shown and tells the caller when that changes.
It also reports the hardware mute of the device to LVA and passes on the requests of LVA to switch it. The device is the authority:
LVA is told the state after every (re)connect and never sets it. It sends the commands of the buttons to LVA. The hardware itself
is run by the device (``device_runner.py``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional

from .display import DisplayFunction, TransientDisplay, select_display_function, start_transient
from .hardware_mute import HardwareMute, decide_mute_request, messages_for_changes
from .lva_bridge import LvaBridge
from .lva_protocol import LvaEvent, LvaMessage, LvaRequest, lva_url
from .lva_status import LvaStatus, apply_event

_LOGGER = logging.getLogger(__name__)


class Controller:
    """
    Runs the connection to LVA and works out what the LEDs show.
    :param lva_host: Host of the peripheral API of LVA.
    :param lva_port: Port of the peripheral API of LVA.
    :param on_display_change: Called with the new display function (None for the background) whenever it changes.
    :param on_hardware_mute_request: Called with True or False when LVA asks to mute or unmute the hardware, and the device can do that.
    :param on_status_change: Called with the status of LVA after every event and every (re)connect or loss.
    :param clock: Returns the current time in seconds.
    """

    def __init__(
        self,
        lva_host: str,
        lva_port: int,
        on_display_change: Optional[Callable[[Optional[DisplayFunction]], None]] = None,
        on_hardware_mute_request: Optional[Callable[[bool], None]] = None,
        on_status_change: Optional[Callable[[LvaStatus], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bridge = LvaBridge(lva_url(lva_host, lva_port), self._handle_event, self._handle_request, self._handle_connection)
        self._on_display_change = on_display_change
        self._on_hardware_mute_request = on_hardware_mute_request
        self._on_status_change = on_status_change
        self._clock = clock
        self._link_connected = False
        self._status = LvaStatus()
        self._transient: Optional[TransientDisplay] = None
        self._display: Optional[DisplayFunction] = DisplayFunction.NO_CONNECTION
        self._reselect_handle: Optional[asyncio.TimerHandle] = None
        self._hardware_mute = HardwareMute()
        self._told_lva: Optional[HardwareMute] = None
        self._sending: set[asyncio.Task] = set()

    @property
    def display(self) -> Optional[DisplayFunction]:
        """The display function that is shown now, None for the background."""
        return self._display

    @property
    def status(self) -> LvaStatus:
        """The status of LVA, empty while LPC is not connected to it."""
        return self._status

    @property
    def link_connected(self) -> bool:
        """True while LPC is connected to LVA."""
        return self._link_connected

    def send_messages(self, messages: tuple[LvaMessage, ...]) -> None:
        """
        Send messages to LVA, in order, without waiting. Call it on the event loop.
        :param messages: The commands (or events) for LVA. They are dropped and logged while LPC is not connected to LVA.
        """
        if messages:
            self._start_sending(self._send_in_order(messages))

    def set_hardware_mute(self, hardware: HardwareMute) -> None:
        """
        Tell the controller the hardware mute of the device, as read from the device. Call it on the event loop, whenever it changes.
        :param hardware: The hardware mute. LVA is told about every change, and about the whole state after a new connection.
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
        self._report_status()
        self._send_hardware_mute()

    def _handle_event(self, event: LvaEvent) -> None:
        update = apply_event(self._status, event)
        self._status = update.status
        if update.transient is not None:
            self._transient = start_transient(update.transient, self._clock())
        self._reselect(link_connected=True)
        self._report_status()

    def _handle_request(self, request: LvaRequest) -> None:
        decision = decide_mute_request(request.name, self._hardware_mute)
        _LOGGER.debug("Request of LVA: %s", decision.reason)
        if decision.muted is not None and self._on_hardware_mute_request is not None:
            self._on_hardware_mute_request(decision.muted)

    def _send_hardware_mute(self) -> None:
        if not self._link_connected:
            return
        messages = messages_for_changes(self._told_lva, self._hardware_mute)
        if not messages:
            return
        self._told_lva = self._hardware_mute
        self._start_sending(self._send_hardware_mute_messages(messages))

    def _start_sending(self, sending: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.get_running_loop().create_task(sending)
        self._sending.add(task)
        task.add_done_callback(self._sending.discard)

    async def _send_hardware_mute_messages(self, messages: tuple[LvaMessage, ...]) -> None:
        if not await self._send_in_order(messages):
            self._told_lva = None

    async def _send_in_order(self, messages: tuple[LvaMessage, ...]) -> bool:
        for message in messages:
            if not await self._bridge.send_message(message.name, message.data):
                return False
        return True

    def _report_status(self) -> None:
        if self._on_status_change is not None:
            self._on_status_change(self._status)

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
