"""Unit tests for controller.py."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock

import pytest
import websockets

from linux_peripherals_controller.controller import Controller
from linux_peripherals_controller.display import DisplayFunction
from linux_peripherals_controller.hardware_mute import HardwareMute, HardwareMuteType
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


POSSIBLE = HardwareMute(HardwareMuteType.CHANGEABLE, muted=False)
READ_ONLY = HardwareMute(HardwareMuteType.READ_ONLY, muted=True)


def make_mute_controller(requests=None):
    controller = Controller("127.0.0.1", 1, on_hardware_mute_request=requests.append if requests is not None else None, clock=FakeClock())
    controller._bridge.send_command = AsyncMock(return_value=True)  # pylint: disable=protected-access
    return controller


def sent(controller):
    return [(call.args[0], call.args[1]) for call in controller._bridge.send_command.await_args_list]  # pylint: disable=protected-access


async def settle():
    for _ in range(3):
        await asyncio.sleep(0)


class TestTellLvaAboutTheHardwareMute:
    @pytest.mark.asyncio
    async def test_everything_is_told_when_connected(self):
        controller = make_mute_controller()
        controller._handle_connection(True)  # pylint: disable=protected-access
        controller.set_hardware_mute(POSSIBLE)
        await settle()
        assert sent(controller)[-2:] == [("hardware_mute_type", {"type": "changeable"}), ("hardware_mute_status", {"status": "unmuted"})]

    @pytest.mark.asyncio
    async def test_a_device_without_a_hardware_mute_tells_that_after_a_connect(self):
        controller = make_mute_controller()
        controller._handle_connection(True)  # pylint: disable=protected-access
        await settle()
        assert sent(controller) == [("hardware_mute_type", {"type": "none"})]

    @pytest.mark.asyncio
    async def test_nothing_is_sent_before_the_connection_is_up_and_all_of_it_when_it_is(self):
        controller = make_mute_controller()
        controller.set_hardware_mute(POSSIBLE)
        await settle()
        assert sent(controller) == []

        controller._handle_connection(True)  # pylint: disable=protected-access
        await settle()
        assert [name for name, _ in sent(controller)] == ["hardware_mute_type", "hardware_mute_status"]

    @pytest.mark.asyncio
    async def test_only_a_change_is_told_afterwards(self):
        controller = make_mute_controller()
        controller._handle_connection(True)  # pylint: disable=protected-access
        controller.set_hardware_mute(POSSIBLE)
        await settle()
        controller._bridge.send_command.reset_mock()  # pylint: disable=protected-access

        controller.set_hardware_mute(HardwareMute(HardwareMuteType.CHANGEABLE, muted=True))
        await settle()

        assert sent(controller) == [("hardware_mute_status", {"status": "muted"})]

    @pytest.mark.asyncio
    async def test_the_same_state_is_not_told_again(self):
        controller = make_mute_controller()
        controller._handle_connection(True)  # pylint: disable=protected-access
        controller.set_hardware_mute(POSSIBLE)
        await settle()
        controller._bridge.send_command.reset_mock()  # pylint: disable=protected-access

        controller.set_hardware_mute(POSSIBLE)
        await settle()

        assert sent(controller) == []

    @pytest.mark.asyncio
    async def test_a_new_connection_reads_the_device_again_and_tells_everything(self):
        controller = make_mute_controller()
        controller._handle_connection(True)  # pylint: disable=protected-access
        controller.set_hardware_mute(POSSIBLE)
        await settle()
        controller._handle_connection(False)  # pylint: disable=protected-access
        controller.set_hardware_mute(HardwareMute(HardwareMuteType.CHANGEABLE, muted=True))
        controller._bridge.send_command.reset_mock()  # pylint: disable=protected-access

        controller._handle_connection(True)  # pylint: disable=protected-access
        await settle()

        assert sent(controller) == [("hardware_mute_type", {"type": "changeable"}), ("hardware_mute_status", {"status": "muted"})]

    @pytest.mark.asyncio
    async def test_lva_never_sets_the_state_of_the_device(self):
        controller = make_mute_controller([])
        controller._handle_connection(True)  # pylint: disable=protected-access
        controller.set_hardware_mute(HardwareMute(HardwareMuteType.CHANGEABLE, muted=True))
        await settle()
        controller._bridge.send_command.reset_mock()  # pylint: disable=protected-access

        feed(controller, ("hardware_mute_status", {"status": "unmuted"}), ("mute_status", {"muted": False}))
        controller._handle_connection(True)  # pylint: disable=protected-access
        await settle()

        assert ("hardware_mute_status", {"status": "muted"}) in sent(controller)

    @pytest.mark.asyncio
    async def test_a_command_that_could_not_be_sent_is_told_again_next_time(self):
        controller = make_mute_controller()
        controller._bridge.send_command = AsyncMock(return_value=False)  # pylint: disable=protected-access
        controller._handle_connection(True)  # pylint: disable=protected-access
        controller.set_hardware_mute(POSSIBLE)
        await settle()

        controller._bridge.send_command = AsyncMock(return_value=True)  # pylint: disable=protected-access
        controller.set_hardware_mute(POSSIBLE)
        await settle()

        assert [name for name, _ in sent(controller)] == ["hardware_mute_type", "hardware_mute_status"]

    @pytest.mark.asyncio
    async def test_this_does_not_change_what_the_leds_show(self):
        controller = make_mute_controller()
        controller._handle_connection(True)  # pylint: disable=protected-access
        feed(controller, *CONNECTED)
        controller.set_hardware_mute(HardwareMute(HardwareMuteType.CHANGEABLE, muted=True))
        await settle()
        assert controller.display is None


class TestRequestsOfLva:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("event,muted", [("hardware_mute_on", True), ("hardware_mute_off", False)])
    async def test_a_request_for_a_changeable_hardware_mute_reaches_the_device(self, event, muted, caplog):
        requests = []
        controller = make_mute_controller(requests)
        controller._handle_connection(True)  # pylint: disable=protected-access
        controller.set_hardware_mute(POSSIBLE)

        with caplog.at_level(logging.DEBUG):
            feed(controller, (event, {}))

        assert requests == [muted]
        assert f"Request of LVA: {event}: switching the hardware mute" in caplog.text

    @pytest.mark.asyncio
    async def test_ignored_if_it_can_only_be_read(self, caplog):
        requests = []
        controller = make_mute_controller(requests)
        controller._handle_connection(True)  # pylint: disable=protected-access
        controller.set_hardware_mute(READ_ONLY)

        with caplog.at_level(logging.DEBUG):
            feed(controller, ("hardware_mute_on", {}))

        assert requests == []
        assert "can only be read" in caplog.text

    @pytest.mark.asyncio
    async def test_ignored_if_the_device_has_no_hardware_mute(self, caplog):
        requests = []
        controller = make_mute_controller(requests)
        with caplog.at_level(logging.DEBUG):
            feed(controller, ("hardware_mute_off", {}))
        assert requests == []
        assert "the device has no hardware mute" in caplog.text

    @pytest.mark.asyncio
    async def test_a_request_without_anyone_to_carry_it_out_is_fine(self):
        controller = make_mute_controller()
        controller.set_hardware_mute(POSSIBLE)
        feed(controller, ("hardware_mute_on", {}))

    @pytest.mark.asyncio
    async def test_a_request_does_not_change_the_display_or_the_status(self):
        controller = make_mute_controller([])
        controller._handle_connection(True)  # pylint: disable=protected-access
        feed(controller, *CONNECTED)
        controller.set_hardware_mute(POSSIBLE)
        before = controller.display

        feed(controller, ("hardware_mute_on", {}))

        assert controller.display == before

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name,data", [("hardware_mute_status", {"status": "muted"}), ("hardware_mute_type", {"type": "changeable"})])
    async def test_reports_of_other_peripherals_are_not_requests(self, name, data):
        requests = []
        controller = make_mute_controller(requests)
        controller.set_hardware_mute(POSSIBLE)
        feed(controller, (name, data))
        assert requests == []
