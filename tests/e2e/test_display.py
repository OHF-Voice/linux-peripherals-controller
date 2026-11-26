"""The display function LPC picks for what LVA reports, see "LEDs" and "Bridge to LVA" in docs/behavior.md.

The device has no driver yet, so the display function is read from the debug log of LPC (``Display function: a -> b``).
"""

import time

import pytest

from .fake_lva import FakeLva
from .lpc import LpcProcess


@pytest.mark.parametrize(
    ("state", "function"),
    [
        ("wake_word", "wake_word"),
        ("listening", "listening"),
        ("speech_detected", "listening"),
        ("thinking", "thinking"),
        ("tts", "tts"),
        ("announce", "announce"),
    ],
)
async def test_state_shows_its_function_and_idle_ends_it(fake_lva: FakeLva, lpc: LpcProcess, state: str, function: str) -> None:
    """A state of the assistant shows its function, and idle goes back to the background."""
    mark = lpc.log_mark()

    await fake_lva.send_event("state", {"state": state})
    await lpc.wait_for_display(function, mark)
    await fake_lva.send_event("state", {"state": "idle"})
    await lpc.wait_for_display(None, mark)


async def test_voice_pipeline_runs_through_its_functions_in_order(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """A whole request (wake word, listening, speech, thinking, spoken reply, idle) shows one function after the other."""
    mark = lpc.log_mark()

    for state in ("wake_word", "listening", "speech_detected", "thinking", "tts", "idle"):
        await fake_lva.send_event("state", {"state": state})
    await lpc.wait_for_display(None, mark)

    assert lpc.displays_since(mark) == ["wake_word", "listening", "thinking", "tts", "None"]


async def test_pipeline_error_is_shown_for_a_short_time_and_then_ends(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """The state pipeline_error shows its function for a short time even though LVA sends idle right after it, then the display returns."""
    mark = lpc.log_mark()

    await fake_lva.send_event("state", {"state": "pipeline_error"})
    await lpc.wait_for_display("pipeline_error", mark)
    shown_at = time.monotonic()
    await fake_lva.send_event("state", {"state": "idle"})
    await lpc.wait_for_display(None, mark)

    assert 1.0 <= time.monotonic() - shown_at < 3.0


async def test_ringing_timer_wins_over_the_voice_pipeline(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """A ringing timer is shown over a running request, and the request shows again when the timer is stopped."""
    start = lpc.log_mark()

    await fake_lva.send_event("state", {"state": "listening"})
    await lpc.wait_for_display("listening", start)
    await fake_lva.send_event("timer_status", {"status": "ringing", "auto_stopped": False})
    await lpc.wait_for_display("timer_ringing", start)
    ringing = lpc.log_mark()
    await fake_lva.send_event("timer_status", {"status": "idle", "auto_stopped": False})
    await lpc.wait_for_display("listening", ringing)

    assert lpc.displays_since(start) == ["listening", "timer_ringing", "listening"]


async def test_muted_wins_over_a_counting_timer(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """A counting timer is shown, mute is shown over it, and the timer comes back when the microphone is unmuted."""
    mark = lpc.log_mark()

    await fake_lva.send_event("timer_status", {"status": "active", "auto_stopped": False})
    await lpc.wait_for_display("timer_active", mark)
    await fake_lva.send_event("mute_status", {"status": "muted"})
    await lpc.wait_for_display("muted", mark)
    await fake_lva.send_event("mute_status", {"status": "unmuted"})
    await fake_lva.send_event("timer_status", {"status": "idle", "auto_stopped": False})
    await lpc.wait_for_display(None, mark)

    assert lpc.displays_since(mark) == ["timer_active", "muted", "timer_active", "None"]


async def test_timer_that_stopped_on_its_own_shows_timer_timeout_once(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """A ringing timer that stopped on its own (auto_stopped) shows timer_timeout for a short time, then the display returns."""
    mark = lpc.log_mark()

    await fake_lva.send_event("timer_status", {"status": "ringing", "auto_stopped": False})
    await lpc.wait_for_display("timer_ringing", mark)
    await fake_lva.send_event("timer_status", {"status": "idle", "auto_stopped": True})
    await lpc.wait_for_display("timer_timeout", mark)
    shown_at = time.monotonic()
    await lpc.wait_for_display(None, mark)

    assert 2.0 <= time.monotonic() - shown_at < 5.0


async def test_timer_stopped_by_the_user_does_not_show_timer_timeout(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """A ringing timer that someone stopped (auto_stopped false) ends without timer_timeout."""
    mark = lpc.log_mark()

    await fake_lva.send_event("timer_status", {"status": "ringing", "auto_stopped": False})
    await lpc.wait_for_display("timer_ringing", mark)
    await fake_lva.send_event("timer_status", {"status": "idle", "auto_stopped": False})
    await lpc.wait_for_display(None, mark)

    assert lpc.displays_since(mark) == ["timer_ringing", "None"]


async def test_changed_volume_is_shown_for_a_short_time(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """A changed volume shows the volume function for a short time. The first volume after the connect (50 in the snapshot) is not shown."""
    mark = lpc.log_mark()

    await fake_lva.send_event("volume_status", {"volume": 60})
    await lpc.wait_for_display("volume", mark)
    await lpc.wait_for_display(None, mark)

    assert lpc.displays_since(0)[:2] == ["None", "volume"], "the volume of the snapshot must not be shown"
    assert lpc.displays_since(mark) == ["volume", "None"]


async def test_lva_not_connected_to_home_assistant_shows_no_connection(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """While LVA is not connected to Home Assistant the display shows no_connection over everything else, and what was shown before returns with the connection."""
    mark = lpc.log_mark()

    await fake_lva.send_event("state", {"state": "listening"})
    await lpc.wait_for_display("listening", mark)
    await fake_lva.send_event("lva_status", {"status": "disconnected"})
    await lpc.wait_for_display("no_connection", mark)
    await fake_lva.send_event("lva_status", {"status": "connected"})
    await fake_lva.send_event("state", {"state": "tts"})
    await lpc.wait_for_display("tts", mark)

    assert lpc.displays_since(mark) == ["listening", "no_connection", "listening", "tts"]


async def test_messages_that_make_no_sense_are_ignored(fake_lva: FakeLva, lpc: LpcProcess) -> None:
    """Text that is not JSON, unknown events, events with invalid data and unknown commands change nothing, and LPC keeps working."""
    mark = lpc.log_mark()

    await fake_lva.send_raw("this is not json")
    await fake_lva.send_raw(b"\x00\x01\x02")
    await fake_lva.send_raw('["a", "list"]')
    await fake_lva.send_event("no_such_event", {"value": 1})
    await fake_lva.send_event("state", {"state": 42})
    await fake_lva.send_event("volume_status", {"volume": "loud"})
    await fake_lva.send_command("no_such_command")
    await fake_lva.send_event("state", {"state": "thinking"})
    await lpc.wait_for_display("thinking", mark)

    assert lpc.running
    assert lpc.displays_since(mark) == ["thinking"]
