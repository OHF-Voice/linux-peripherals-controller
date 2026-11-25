"""Connection to the peripheral API of LVA (version 2).

The bridge only carries messages: it connects, reconnects after a loss, hands every event to the controller and sends commands.
What the events mean is decided elsewhere (``lva_status.py``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Mapping, Optional

import websockets
from websockets.exceptions import InvalidStatusCode, WebSocketException

from .lva_protocol import API_VERSION, LvaEvent, build_command, parse_event

_LOGGER = logging.getLogger(__name__)


class LvaBridge:
    """
    Client of the peripheral API of LVA that connects again when the connection is lost.
    :param url: Address of the API, see ``lva_url()``.
    :param on_event: Called with every event of LVA.
    :param on_connection: Called with True when the connection is up and with False when it was lost.
    :param reconnect_delay: Seconds to wait before the next attempt to connect.
    """

    def __init__(
        self,
        url: str,
        on_event: Callable[[LvaEvent], None],
        on_connection: Callable[[bool], None],
        reconnect_delay: float = 3.0,
    ) -> None:
        self._url = url
        self._on_event = on_event
        self._on_connection = on_connection
        self._reconnect_delay = reconnect_delay
        self._websocket: Optional[Any] = None
        self._failure_logged = False

    @property
    def connected(self) -> bool:
        """True while the connection to LVA is up."""
        return self._websocket is not None

    async def run(self) -> None:
        """Connect and stay connected until the task is cancelled."""
        while True:
            await self._connect_once()
            await asyncio.sleep(self._reconnect_delay)

    async def send_command(self, name: str, data: Optional[Mapping[str, Any]] = None) -> bool:
        """
        Send a command to LVA.
        :param name: Name of the command, see ``COMMANDS``.
        :param data: Data of the command.
        :return: True if it was sent. False if LPC is not connected to LVA, the command is then dropped.
        """
        message = build_command(name, data)
        websocket = self._websocket
        if websocket is None:
            _LOGGER.debug("Dropping command '%s': not connected to LVA", name)
            return False
        try:
            await websocket.send(message)
        except WebSocketException as exc:
            _LOGGER.debug("Dropping command '%s': %s", name, exc)
            return False
        _LOGGER.debug("Sent command '%s' to LVA", name)
        return True

    async def _connect_once(self) -> None:
        try:
            async with websockets.connect(self._url) as websocket:
                self._websocket = websocket
                self._failure_logged = False
                _LOGGER.info("Connected to LVA at %s", self._url)
                self._on_connection(True)
                async for raw in websocket:
                    event = parse_event(raw)
                    if event is None:
                        _LOGGER.debug("Ignoring a message of LVA that is not an event: %.200s", raw)
                        continue
                    self._on_event(event)
        except InvalidStatusCode as exc:
            self._log_failure("LVA does not offer peripheral API %s at %s (HTTP %s)", API_VERSION, self._url, exc.status_code)
        except (OSError, WebSocketException) as exc:
            self._log_failure("Cannot reach LVA at %s: %s", self._url, exc)
        finally:
            if self._websocket is not None:
                self._websocket = None
                _LOGGER.warning("Lost the connection to LVA at %s", self._url)
                self._on_connection(False)

    def _log_failure(self, message: str, *args: Any) -> None:
        """Log a failed attempt once, and again only after a connection worked in between."""
        if not self._failure_logged:
            _LOGGER.warning(message + ", trying again every %.0f s", *args, self._reconnect_delay)
            self._failure_logged = True
        else:
            _LOGGER.debug(message, *args)
