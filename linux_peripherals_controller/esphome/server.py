"""The ESPHome server of LPC: Home Assistant connects to it like to an ESPHome device and sees the entities of LPC.

Several clients can be connected at once. A change of a state (a press, a command of one client) is sent to every client.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import List, Optional, Sequence

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    DeviceInfoRequest,
    DeviceInfoResponse,
    LightCommandRequest,
    ListEntitiesDoneResponse,
    ListEntitiesRequest,
    NumberCommandRequest,
    SubscribeStatesRequest,
    SwitchCommandRequest,
)
from google.protobuf import message

from .api_server import APIServer
from .entities import Entity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceInfo:
    """What Home Assistant is told about the device."""

    name: str
    friendly_name: str
    mac_address: str
    model: str
    version: str
    esphome_version: str


class HomeAssistantServer:
    """
    Serves the ESPHome API to Home Assistant.
    :param info: What Home Assistant is told about the device.
    :param entities: The entities, the key of each is its place in the list.
    :param noise_psk: The encryption key (32 bytes), None for plaintext.
    """

    def __init__(self, info: DeviceInfo, entities: Sequence[Entity], noise_psk: Optional[bytes] = None) -> None:
        self.info = info
        self.entities = list(entities)
        self.noise_psk = noise_psk
        self._connections: List[_Connection] = []
        self._server: Optional[asyncio.Server] = None

    async def start(self, host: str, port: int) -> int:
        """
        Start listening.
        :param host: Address to listen on.
        :param port: Port to listen on, 0 for any free port.
        :return: The port it listens on.
        :raises OSError: If the port cannot be bound.
        """
        loop = asyncio.get_running_loop()
        self._server = await loop.create_server(lambda: _Connection(self), host=host, port=port)
        bound_port: int = self._server.sockets[0].getsockname()[1]
        _LOGGER.info("ESPHome API for Home Assistant on %s:%s%s", host, bound_port, " (encrypted)" if self.noise_psk else "")
        return bound_port

    async def stop(self) -> None:
        """Stop listening and close the connections."""
        if self._server is not None:
            self._server.close()
            for connection in list(self._connections):
                connection.close()
            await self._server.wait_closed()
            self._server = None

    def broadcast(self, msgs: Sequence[message.Message]) -> None:
        """
        Send messages to every connected client.
        :param msgs: The messages, usually states.
        """
        for connection in self._connections:
            connection.send_messages(msgs)

    def connected(self, connection: "_Connection") -> None:
        """A client connected."""
        self._connections.append(connection)
        _LOGGER.info("Home Assistant connected (%s client(s))", len(self._connections))

    def disconnected(self, connection: "_Connection") -> None:
        """A client disconnected."""
        if connection in self._connections:
            self._connections.remove(connection)
            _LOGGER.info("Home Assistant disconnected (%s client(s))", len(self._connections))

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """
        Answer a message of a client.
        :param msg: The message.
        :return: The answers for that client. A command is answered to every client.
        """
        if isinstance(msg, DeviceInfoRequest):
            yield DeviceInfoResponse(
                uses_password=False,
                name=self.info.name,
                friendly_name=self.info.friendly_name,
                mac_address=self.info.mac_address,
                manufacturer="Open Home Foundation",
                model=self.info.model,
                project_name="Open Home Foundation.Linux Peripheral Controller",
                project_version=self.info.version,
                esphome_version=self.info.esphome_version,
                api_encryption_supported=self.noise_psk is not None,
            )
        elif isinstance(msg, ListEntitiesRequest):
            for entity in self.entities:
                yield entity.list_response()
            yield ListEntitiesDoneResponse()
        elif isinstance(msg, SubscribeStatesRequest):
            for entity in self.entities:
                yield from entity.state_responses()
        elif isinstance(msg, (LightCommandRequest, NumberCommandRequest, SwitchCommandRequest)):
            target: Optional[Entity] = self.entities[msg.key] if 0 <= msg.key < len(self.entities) else None
            if target is None:
                _LOGGER.debug("Ignoring a command for the unknown entity key %s", msg.key)
                return
            self.broadcast(target.handle_command(msg))
        else:
            _LOGGER.debug("Ignoring %s", type(msg).__name__)


class _Connection(APIServer):
    """One connection of Home Assistant."""

    def __init__(self, server: HomeAssistantServer) -> None:
        super().__init__(server.info.name, server.noise_psk, server.info.mac_address)
        self._owner = server

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        return list(self._owner.handle_message(msg))

    def connection_made(self, transport) -> None:
        super().connection_made(transport)
        self._owner.connected(self)

    def connection_lost(self, exc) -> None:
        super().connection_lost(exc)
        self._owner.disconnected(self)

    def close(self) -> None:
        """Close the connection."""
        self._close()
