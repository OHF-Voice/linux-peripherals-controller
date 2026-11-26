"""Unit tests for lva_bridge.py, against a real WebSocket server on localhost."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from http import HTTPStatus

import pytest
import websockets

from linux_peripherals_controller.lva_bridge import LvaBridge


@asynccontextmanager
async def lva_server(handler, **kwargs):
    server = await websockets.serve(handler, "127.0.0.1", 0, **kwargs)
    try:
        yield server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()


async def wait_for(predicate, timeout=3.0):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


def make_bridge(port, events, connections, delay=0.05, requests=None):
    return LvaBridge(f"ws://127.0.0.1:{port}/v2", events.append, (requests if requests is not None else []).append, connections.append, reconnect_delay=delay)


@pytest.mark.asyncio
async def test_connects_on_the_url_of_version_2_and_hands_over_events():
    paths, events, connections = [], [], []

    async def handler(websocket):
        paths.append(websocket.path)
        await websocket.send(json.dumps({"event": "hello", "data": {"api_version": "v2"}}))
        await websocket.send("not an event")
        await websocket.send(json.dumps({"event": "state", "data": {"state": "idle"}}))
        await websocket.wait_closed()

    async with lva_server(handler) as port:
        bridge = make_bridge(port, events, connections)
        task = asyncio.create_task(bridge.run())
        await wait_for(lambda: len(events) == 2)
        assert bridge.connected
        task.cancel()

    assert paths == ["/v2"]
    assert [e.name for e in events] == ["hello", "state"]
    assert connections[0] is True


@pytest.mark.asyncio
async def test_commands_of_lva_are_handed_over_as_requests():
    events, requests, connections = [], [], []

    async def handler(websocket):
        await websocket.send(json.dumps({"command": "hardware_mute_on"}))
        await websocket.send(json.dumps({"event": "state", "data": {"state": "idle"}}))
        await websocket.wait_closed()

    async with lva_server(handler) as port:
        task = asyncio.create_task(make_bridge(port, events, connections, requests=requests).run())
        await wait_for(lambda: len(events) == 1 and len(requests) == 1)
        task.cancel()

    assert [r.name for r in requests] == ["hardware_mute_on"]
    assert [e.name for e in events] == ["state"]


@pytest.mark.asyncio
async def test_messages_that_are_neither_events_nor_commands_are_ignored_and_logged(caplog):
    events, connections = [], []

    async def handler(websocket):
        await websocket.send("[1]")
        await websocket.send(json.dumps({"event": "state", "data": {"state": "idle"}}))
        await websocket.wait_closed()

    async with lva_server(handler) as port:
        with caplog.at_level(logging.DEBUG):
            task = asyncio.create_task(make_bridge(port, events, connections).run())
            await wait_for(lambda: len(events) == 1)
            task.cancel()

    assert "neither an event nor a command" in caplog.text


@pytest.mark.asyncio
async def test_messages_reach_lva():
    received, events, connections = [], [], []

    async def handler(websocket):
        async for raw in websocket:
            received.append(json.loads(raw))

    async with lva_server(handler) as port:
        bridge = make_bridge(port, events, connections)
        task = asyncio.create_task(bridge.run())
        await wait_for(lambda: bridge.connected)

        assert await bridge.send_message("volume_set", {"volume": 30}) is True
        assert await bridge.send_message("timer_stop") is True
        assert await bridge.send_message("hardware_mute_status", {"status": "muted"}) is True
        await wait_for(lambda: len(received) == 3)
        task.cancel()

    assert received == [
        {"command": "volume_set", "data": {"volume": 30}},
        {"command": "timer_stop"},
        {"event": "hardware_mute_status", "data": {"status": "muted"}},
    ]


@pytest.mark.asyncio
async def test_message_is_dropped_and_logged_when_not_connected(caplog):
    bridge = LvaBridge("ws://127.0.0.1:1/v2", lambda e: None, lambda r: None, lambda c: None)

    with caplog.at_level(logging.DEBUG):
        assert await bridge.send_message("listening_stop") is False

    assert "Dropping message 'listening_stop': not connected to LVA" in caplog.text


@pytest.mark.asyncio
async def test_unknown_message_raises():
    bridge = LvaBridge("ws://127.0.0.1:1/v2", lambda e: None, lambda r: None, lambda c: None)
    with pytest.raises(ValueError):
        await bridge.send_message("mute_mic")


@pytest.mark.asyncio
async def test_connects_again_after_a_loss_and_tells_about_it(caplog):
    events, connections = [], []
    attempts = []

    async def handler(websocket):
        attempts.append(1)
        if len(attempts) == 1:
            await websocket.close()
        else:
            await websocket.wait_closed()

    async with lva_server(handler) as port:
        bridge = make_bridge(port, events, connections)
        with caplog.at_level(logging.INFO):
            task = asyncio.create_task(bridge.run())
            await wait_for(lambda: connections == [True, False, True])
            task.cancel()

    assert "Lost the connection to LVA" in caplog.text
    assert not [c for c in connections[:1] if not c]


@pytest.mark.asyncio
async def test_unreachable_lva_is_warned_about_once_and_retried(caplog):
    events, connections = [], []
    probe = await websockets.serve(lambda ws: None, "127.0.0.1", 0)
    port = probe.sockets[0].getsockname()[1]
    probe.close()
    await probe.wait_closed()

    bridge = make_bridge(port, events, connections, delay=0.02)
    with caplog.at_level(logging.DEBUG):
        task = asyncio.create_task(bridge.run())
        await asyncio.sleep(0.3)
        task.cancel()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "Cannot reach LVA" in r.getMessage()]
    assert len(warnings) == 1
    assert "trying again every" in warnings[0].getMessage()
    assert connections == []
    assert not bridge.connected


@pytest.mark.asyncio
async def test_lva_without_version_2_is_reported(caplog):
    async def handler(websocket):
        await websocket.wait_closed()

    async def refuse(_path, _headers):
        return HTTPStatus.NOT_FOUND, [], b"Unsupported"

    async with lva_server(handler, process_request=refuse) as port:
        with caplog.at_level(logging.WARNING):
            task = asyncio.create_task(make_bridge(port, [], []).run())
            await wait_for(lambda: "does not offer peripheral API v2" in caplog.text)
            task.cancel()

    assert "HTTP 404" in caplog.text
