"""Unit tests for __main__.py."""

import logging

from linux_peripherals_controller.__main__ import run


def test_run_logs_version_and_lva_address(caplog):
    with caplog.at_level(logging.INFO):
        run(["--lva-host", "lva.local", "--lva-port", "7000"])

    assert "Version: " in caplog.text
    assert "ws://lva.local:7000" in caplog.text
