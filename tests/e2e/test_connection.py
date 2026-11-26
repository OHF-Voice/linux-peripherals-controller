"""The connection to LVA: connect, retry and reconnect, see "Bridge to LVA" and "Startup and errors" in docs/behavior.md."""

import asyncio

from .fake_lva import FakeLva
from .lpc import LpcProcess


async def test_lpc_connects_to_version_2_of_the_peripheral_api(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """LPC asks for the path /v2 of the peripheral API and shows the background once LVA reports that it is connected to Home Assistant."""
    assert fake_lva.requested_paths == ["/v2"]
    assert lpc.displays_since(0) == ["None"]


async def test_no_connection_is_shown_until_the_status_of_lva_arrives(fake_lva: FakeLva, start_lpc) -> None:
    """Until LVA has said that it is connected to Home Assistant, LPC does not show the background, even though the connection to LVA is up."""
    fake_lva.status = [("state", {"state": "idle"})]

    lpc = start_lpc(fake_lva)
    await lpc.wait_for_log_line("Connected to LVA")
    await fake_lva.wait_for_connection()
    await fake_lva.send_event("state", {"state": "idle"})
    await asyncio.sleep(0.5)
    assert lpc.displays_since(0) == []

    await fake_lva.send_event("lva_status", {"status": "connected"})
    await lpc.wait_for_display(None)


async def test_lpc_keeps_trying_until_lva_is_there(stopped_fake_lva: FakeLva, start_lpc) -> None:
    """LPC starts without LVA, logs that it cannot reach it once, keeps retrying and connects as soon as LVA is up."""
    lpc = start_lpc(stopped_fake_lva)
    await lpc.wait_for_log_line("Cannot reach LVA")
    await asyncio.sleep(3.5)

    await stopped_fake_lva.start()
    await lpc.wait_for_log_line("Connected to LVA")
    await lpc.wait_for_display(None)

    assert lpc.warning_count("Cannot reach LVA") == 1, "a failed attempt is logged as a warning once, not for every retry"


async def test_lva_without_version_2_is_reported_once_and_retried(fake_lva: FakeLva, start_lpc) -> None:
    """If LVA has no version 2 (HTTP 404) LPC says so once, with the status LVA answered, keeps retrying and connects when version 2 appears."""
    fake_lva.offer_v2 = False

    lpc = start_lpc(fake_lva)
    await lpc.wait_for_log_line("does not offer peripheral API v2")
    await asyncio.sleep(3.5)
    assert len(fake_lva.requested_paths) >= 2, "LPC must retry"
    assert lpc.warning_count("does not offer peripheral API v2") == 1
    assert "HTTP 404" in lpc.full_log()

    fake_lva.offer_v2 = True
    await lpc.wait_for_log_line("Connected to LVA")
    await lpc.wait_for_display(None)


async def test_lost_connection_shows_no_connection_and_reconnects(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """When LVA closes the connection LPC shows no_connection, reconnects by itself and shows the background again."""
    mark = lpc.log_mark()

    await fake_lva.drop_connections()
    await lpc.wait_for_display("no_connection", mark)
    await lpc.wait_for_log_line("Lost the connection to LVA", mark)
    await fake_lva.wait_for_connection()
    await lpc.wait_for_display(None, mark)

    assert lpc.displays_since(mark) == ["no_connection", "None"]


async def test_reconnect_starts_from_the_new_status_of_lva(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """After a reconnect nothing of the old status is kept: a state from before the loss is not shown again, the snapshot of LVA decides."""
    mark = lpc.log_mark()
    await fake_lva.send_event("state", {"state": "listening"})
    await lpc.wait_for_display("listening", mark)

    await fake_lva.drop_connections()
    await lpc.wait_for_display("no_connection", mark)
    await fake_lva.wait_for_connection()
    await lpc.wait_for_display(None, mark)

    assert lpc.displays_since(mark) == ["listening", "no_connection", "None"]


async def test_lpc_takes_the_state_of_a_running_request_from_the_snapshot(fake_lva: FakeLva, start_lpc) -> None:
    """If LPC connects while LVA is in the middle of a request, it shows that state at once from the snapshot."""
    fake_lva.status = [*fake_lva.status[:5], ("state", {"state": "thinking"}), *fake_lva.status[6:]]

    lpc = start_lpc(fake_lva)

    await lpc.wait_for_display("thinking")
