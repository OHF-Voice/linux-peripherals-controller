"""A fake LVA for the end-to-end tests: the server side of the peripheral WebSocket API version 2.

It answers like LVA does (``hello`` and the whole status after a connect, HTTP 404 for a path that is not offered), lets a test send events
and commands as LVA, and records every message LPC sends. See docs/peripheral_api/v2.md of LVA.
"""

import asyncio
import json
from http import HTTPStatus
from typing import Any, Dict, List, Optional, Tuple

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from .waiting import wait_until

#: The status LVA sends after ``hello``: connected to Home Assistant, nothing happens
IDLE_STATUS: Tuple[Tuple[str, Dict[str, Any]], ...] = (
    ("lva_status", {"status": "connected"}),
    ("timer_status", {"status": "idle", "auto_stopped": False}),
    ("timer_remaining_time", {"seconds": 0}),
    ("timer_remaining_percentage", {"percentage": 0}),
    ("timer_full_data_set", {"timers": []}),
    ("state", {"state": "idle"}),
    ("mute_status", {"status": "unmuted"}),
    ("volume_status", {"volume": 50}),
    ("media_player_status", {"status": "idle"}),
)


class FakeLva:
    """
    The peripheral API of LVA, as far as LPC uses it.
    :param port: Port to listen on.
    """

    def __init__(self, port: int) -> None:
        self.port = port
        #: Whether ``/v2`` is offered. Without it the server answers 404 like an LVA that only knows version 1.
        self.offer_v2 = True
        #: The events sent to every new connection after ``hello``
        self.status: List[Tuple[str, Dict[str, Any]]] = list(IDLE_STATUS)
        #: Every message LPC sent, as the JSON object (or the raw text if it was not JSON)
        self.received: List[Any] = []
        #: Every path a client asked for, also the ones that were refused
        self.requested_paths: List[str] = []
        self.connections: List[ServerConnection] = []
        self._server: Optional[Server] = None

    async def start(self) -> None:
        """Start listening. Can be called again after :meth:`stop`."""
        self._server = await serve(self._handle, "127.0.0.1", self.port, process_request=self._check_path)

    async def stop(self) -> None:
        """Stop listening and close every connection."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def wait_for_connection(self, timeout: float = 10.0) -> None:
        """
        Wait until LPC is connected.
        :param timeout: Seconds to wait before a TimeoutError is raised.
        """
        await wait_until(lambda: bool(self.connections), timeout, "a connection of LPC")

    async def send_event(self, name: str, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Send an event to LPC, as LVA does when its status changes.
        :param name: Name of the event, for example ``state``.
        :param data: Data of the event.
        """
        await self.send_raw(json.dumps({"event": name, **({"data": data} if data is not None else {})}))

    async def send_command(self, name: str, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Send a command to LPC, as LVA does when it asks for something.
        :param name: Name of the command, for example ``hardware_muted_on``.
        :param data: Data of the command.
        """
        await self.send_raw(json.dumps({"command": name, **({"data": data} if data is not None else {})}))

    async def send_raw(self, text: str | bytes) -> None:
        """
        Send a message as it is, to check how LPC reacts to input that is not valid.
        :param text: The WebSocket message.
        """
        await asyncio.gather(*(connection.send(text) for connection in self.connections))

    async def drop_connections(self) -> None:
        """Close the connection of every client, the server keeps listening."""
        await asyncio.gather(*(connection.close() for connection in list(self.connections)))

    def _check_path(self, connection: ServerConnection, request: Request) -> Optional[Response]:
        self.requested_paths.append(request.path)
        if request.path != "/v2" or not self.offer_v2:
            return connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")
        return None

    async def _handle(self, connection: ServerConnection) -> None:
        self.connections.append(connection)
        try:
            await connection.send(json.dumps({"event": "hello", "data": {"api_version": "v2", "supported_versions": ["v1", "v2"]}}))
            for name, data in self.status:
                await connection.send(json.dumps({"event": name, "data": data}))
            async for raw in connection:
                try:
                    self.received.append(json.loads(raw))
                except json.JSONDecodeError:
                    self.received.append(raw)
        except ConnectionClosed:
            pass
        finally:
            self.connections.remove(connection)
