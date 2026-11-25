"""Unit tests for controller.py."""

import asyncio
import json
import logging

import pytest
import websockets

from linux_peripherals_controller.controller import Controller
from linux_peripherals_controller.display import DisplayFunction
from linux_peripherals_controller.lva_protocol import LvaEvent


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def make_controller(clock=None, shown=None):
    shown = shown if shown is not None else []
    controller = Controller("127.0.0.1", 1, on_display_change=shown.append, clock=clock or FakeClock())
    return controller, shown


def feed(controller, *events):
    for name, data in events:
        controller._handle_event(LvaEvent(name, data))  # pylint: disable=protected-access


CONNECTED = [("lva_status", {"status": "connected"}), ("state", {"state": "idle"})]


@pytest.mark.asyncio
async def test_starts_with_no_connection():
    controller, shown = make_controller()
    assert controller.display == DisplayFunction.NO_CONNECTION
    assert shown == []


@pytest.mark.asyncio
async def test_connection_without_status_still_shows_no_connection():
    controller, shown = make_controller()
    controller._handle_connection(True)  # pylint: disable=protected-access
    assert controller.display == DisplayFunction.NO_CONNECTION
    assert shown == []


@pytest.mark.asyncio
async def test_follows_the_events_of_lva(caplog):
    controller, shown = make_controller()
    controller._handle_connection(True)  # pylint: disable=protected-access

    with caplog.at_level(logging.DEBUG):
        feed(controller, *CONNECTED, ("state", {"state": "listening"}), ("state", {"state": "thinking"}), ("state", {"state": "idle"}))

    assert shown == [None, DisplayFunction.LISTENING, DisplayFunction.THINKING, None]
    assert "Display function: no_connection -> None" in caplog.text
    assert "Display function: None -> listening" in caplog.text


@pytest.mark.asyncio
async def test_unchanged_display_is_not_reported_again():
    controller, shown = make_controller()
    controller._handle_connection(True)  # pylint: disable=protected-access
    feed(controller, *CONNECTED, ("volume_status", {"volume": 10}), ("timer_remaining_time", {"seconds": 5}))
    assert shown == [None]


@pytest.mark.asyncio
async def test_losing_the_connection_forgets_the_status():
    controller, shown = make_controller()
    controller._handle_connection(True)  # pylint: disable=protected-access
    feed(controller, *CONNECTED, ("state", {"state": "tts"}))

    controller._handle_connection(False)  # pylint: disable=protected-access
    assert controller.display == DisplayFunction.NO_CONNECTION

    controller._handle_connection(True)  # pylint: disable=protected-access
    feed(controller, *CONNECTED)
    assert shown[-1] is None


@pytest.mark.asyncio
async def test_short_function_is_shown_and_ends_by_itself():
    clock = FakeClock()
    controller, shown = make_controller(clock)
    controller._handle_connection(True)  # pylint: disable=protected-access
    feed(controller, *CONNECTED)

    feed(controller, ("pipeline_error", {"reason": "x"}))
    assert controller.display == DisplayFunction.PIPELINE_ERROR
    assert controller._reselect_handle is not None  # pylint: disable=protected-access

    clock.now += 2.0
    controller._reselect()  # pylint: disable=protected-access
    assert controller.display is None
    assert shown[-2:] == [DisplayFunction.PIPELINE_ERROR, None]


@pytest.mark.asyncio
async def test_first_volume_is_not_shown_but_a_change_is():
    controller, _ = make_controller()
    controller._handle_connection(True)  # pylint: disable=protected-access
    feed(controller, *CONNECTED, ("volume_status", {"volume": 50}))
    assert controller.display is None

    feed(controller, ("volume_status", {"volume": 55}))
    assert controller.display == DisplayFunction.VOLUME


@pytest.mark.asyncio
async def test_timer_timeout_signal():
    controller, _ = make_controller()
    controller._handle_connection(True)  # pylint: disable=protected-access
    feed(controller, *CONNECTED, ("timer_status", {"status": "ringing"}), ("timer_auto_stopped", {"seconds": 900}), ("timer_status", {"status": "idle"}))
    assert controller.display == DisplayFunction.TIMER_TIMEOUT


@pytest.mark.asyncio
async def test_with_a_real_connection_to_lva():
    shown = []

    async def lva(websocket):
        await websocket.send(json.dumps({"event": "hello", "data": {}}))
        await websocket.send(json.dumps({"event": "lva_status", "data": {"status": "connected"}}))
        await websocket.send(json.dumps({"event": "state", "data": {"state": "listening"}}))
        await websocket.wait_closed()

    server = await websockets.serve(lva, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    controller = Controller("127.0.0.1", port, on_display_change=shown.append)
    task = asyncio.create_task(controller.run())
    try:
        async with asyncio.timeout(3):
            while DisplayFunction.LISTENING not in shown:
                await asyncio.sleep(0.01)
    finally:
        task.cancel()
        server.close()
        await server.wait_closed()
    assert shown[:2] == [None, DisplayFunction.LISTENING]
