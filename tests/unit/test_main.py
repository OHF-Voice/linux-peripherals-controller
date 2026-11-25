"""Unit tests for __main__.py."""

import logging
from unittest.mock import patch

from linux_peripherals_controller.__main__ import run


def run_without_connecting(argv):
    """Run the entry point with a controller that returns at once."""
    with patch("linux_peripherals_controller.__main__.Controller") as controller:
        controller.return_value.run = _done
        run(argv)
    return controller


async def _done():
    return None


def test_run_logs_version_and_lva_address(caplog):
    with caplog.at_level(logging.INFO):
        run_without_connecting(["--lva-host", "lva.local", "--lva-port", "7000"])

    assert "Version: " in caplog.text
    assert "ws://lva.local:7000" in caplog.text


def test_run_starts_the_controller_with_the_address_of_lva():
    controller = run_without_connecting(["--lva-host", "lva.local", "--lva-port", "7000"])
    controller.assert_called_once_with("lva.local", 7000)


def test_run_stops_quietly_on_ctrl_c(caplog):
    with patch("linux_peripherals_controller.__main__.asyncio.run", side_effect=KeyboardInterrupt), patch("linux_peripherals_controller.__main__.Controller"):
        with caplog.at_level(logging.INFO):
            run([])
    assert "Stopped" in caplog.text
