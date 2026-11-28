"""End-to-end tests of the ESPHome API: a real LPC process, and the client Home Assistant uses (aioesphomeapi) as Home Assistant."""

import json
from typing import AsyncIterator

import pytest
from aioesphomeapi import APIClient, EventInfo, LightInfo, SwitchInfo

from .fake_lva import FakeLva
from .lpc import DEVICE_TYPE, LpcProcess
from .waiting import wait_until


@pytest.fixture
async def home_assistant(lpc: LpcProcess) -> AsyncIterator[APIClient]:
    """The client of Home Assistant, connected to the ESPHome API of LPC."""
    client = APIClient("127.0.0.1", await lpc.esphome_port(), None)
    await client.connect(login=True)
    yield client
    await client.disconnect()


async def test_lpc_is_an_esphome_device_with_its_entities(home_assistant: APIClient) -> None:
    """Home Assistant sees LPC as an ESPHome device named lpc-<MAC>, with the light, an event per button and the child lock."""
    info = await home_assistant.device_info()
    entities, _ = await home_assistant.list_entities_services()

    assert info.name.startswith("lpc-")
    assert info.project_name == "Open Home Foundation.Linux Peripheral Controller"
    assert [(type(e), e.name) for e in entities] == [(LightInfo, "LED"), (EventInfo, "Button"), (SwitchInfo, "Child Lock")]


async def test_light_and_child_lock_of_home_assistant_are_stored(lpc: LpcProcess, home_assistant: APIClient) -> None:
    """The light and the child lock that Home Assistant sets are kept in the state file."""
    await home_assistant.list_entities_services()
    home_assistant.light_command(0, state=True, rgb=(1.0, 0.0, 0.0), brightness=0.5)
    home_assistant.switch_command(2, True)

    state_file = lpc.state_dir / "state.json"

    def stored() -> bool:
        if not state_file.exists():
            return False
        state = json.loads(state_file.read_text(encoding="utf-8"))
        return bool(state["child_lock"] and state["light"]["on"])

    await wait_until(stored, 10, "the stored light and child lock")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["light"] == {"on": True, "brightness": 0.5, "red": 1.0, "green": 0.0, "blue": 0.0}


async def test_light_is_the_background_of_the_leds(lpc: LpcProcess, home_assistant: APIClient) -> None:
    """With nothing to show, the LEDs show the light of Home Assistant (red at half brightness)."""
    mark = lpc.log_mark()
    await home_assistant.list_entities_services()
    home_assistant.light_command(0, state=True, rgb=(1.0, 0.0, 0.0), brightness=0.5)

    await lpc.wait_for_log_line("Simulated LEDs: #800000 #800000 #800000", since=mark)


async def test_leds_follow_the_state_of_lva(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """While LVA is muted, the LEDs of the 2mic HAT are solid red."""
    mark = lpc.log_mark()
    await fake_lva.send_event("mute_status", {"status": "muted"})

    await lpc.wait_for_log_line("Simulated LEDs: #ff0000 #ff0000 #ff0000", since=mark)


def test_device_type_of_the_tests_has_a_light_and_a_button() -> None:
    """The tests above rely on the 2mic HAT: a light and one button called button."""
    assert DEVICE_TYPE == "respeaker_2mic_v1"
