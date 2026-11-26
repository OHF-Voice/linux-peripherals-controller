"""The hardware mute towards LVA, see "Hardware mute" in docs/behavior.md.

No device driver reports a hardware mute yet, so the device type of these tests has none (type ``none``).
"""

# pylint: disable=unused-argument

import asyncio

from .fake_lva import FakeLva
from .lpc import LpcProcess
from .waiting import wait_until


async def test_requests_to_switch_the_hardware_mute_are_ignored_without_hardware_mute(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """LVA asks to switch the hardware mute of a device that has none: LPC logs why it ignores it and the display does not change."""
    mark = lpc.log_mark()

    await fake_lva.send_command("hardware_muted_on")
    await lpc.wait_for_log_line("hardware_muted_on ignored: the device has no hardware mute", mark)
    await fake_lva.send_command("hardware_muted_off")
    await lpc.wait_for_log_line("hardware_muted_off ignored: the device has no hardware mute", mark)

    assert lpc.displays_since(mark) == []


async def test_other_commands_of_lva_are_ignored_and_logged(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """Any command of LVA that is not a request to switch the hardware mute is ignored and logged."""
    mark = lpc.log_mark()

    await fake_lva.send_command("volume_up")

    await lpc.wait_for_log_line("volume_up is not a request to switch the hardware mute", mark)


async def test_lpc_tells_lva_the_type_none_after_every_connect_and_no_status(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """For a device without hardware mute LPC tells LVA the type none after every (re)connect, sends no hardware_mute_status and no command on its own."""
    await _wait_for_received(fake_lva, 1)
    await fake_lva.drop_connections()
    await fake_lva.wait_for_connection()
    await _wait_for_received(fake_lva, 2)
    await asyncio.sleep(0.5)

    assert fake_lva.received == [{"event": "hardware_mute_type", "data": {"type": "none"}}] * 2


async def _wait_for_received(fake_lva: FakeLva, count: int) -> None:
    await wait_until(lambda: len(fake_lva.received) >= count, 5.0, f"{count} message(s) of LPC")
