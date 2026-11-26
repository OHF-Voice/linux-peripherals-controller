"""Unit tests for __main__.py."""

import logging
from unittest.mock import patch

import pytest

from linux_peripherals_controller.__main__ import run

DEVICE = ["--device-type", "respeaker_2mic_v1"]


def run_without_connecting(argv):
    """Run the entry point with a controller that returns at once."""
    with patch("linux_peripherals_controller.__main__.Controller") as controller:
        controller.return_value.run = _done
        run(argv)
    return controller


async def _done():
    return None


def test_run_logs_version_device_type_and_lva_address(caplog):
    with caplog.at_level(logging.INFO):
        run_without_connecting(DEVICE + ["--lva-host", "lva.local", "--lva-port", "7000"])

    assert "Version: " in caplog.text
    assert "Device type: respeaker_2mic_v1 (ReSpeaker 2-Mic Pi HAT" in caplog.text
    assert "ws://lva.local:7000" in caplog.text


def test_run_starts_the_controller_with_the_address_of_lva():
    controller = run_without_connecting(DEVICE + ["--lva-host", "lva.local", "--lva-port", "7000"])
    controller.assert_called_once_with("lva.local", 7000)


def test_run_stops_quietly_on_ctrl_c(caplog):
    with patch("linux_peripherals_controller.__main__.asyncio.run", side_effect=KeyboardInterrupt), patch("linux_peripherals_controller.__main__.Controller"):
        with caplog.at_level(logging.INFO):
            run(DEVICE)
    assert "Stopped" in caplog.text


def test_missing_device_type_lists_the_known_ones_and_exits(caplog):
    with pytest.raises(SystemExit) as exit_info:
        run([])
    assert exit_info.value.code == 1
    assert "No device type given" in caplog.text
    assert "respeaker_2mic_v1" in caplog.text


def test_unknown_device_type_lists_the_known_ones_and_exits(caplog):
    with pytest.raises(SystemExit) as exit_info:
        run(["--device-type", "toaster"])
    assert exit_info.value.code == 1
    assert "Unknown device type 'toaster'" in caplog.text
    assert "respeaker_2mic_v1" in caplog.text


def test_invalid_device_configuration_names_file_and_key_and_exits(tmp_path, caplog):
    config = tmp_path / "device.toml"
    config.write_text('[colors]\nlistening = "nope"\n', encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        run(DEVICE + ["--device-config", str(config)])
    assert exit_info.value.code == 1
    assert f"{config}: colors.listening" in caplog.text


def test_device_configuration_with_a_button_the_device_does_not_have_exits(tmp_path, caplog):
    config = tmp_path / "device.toml"
    config.write_text("[buttons.ghost]\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        run(DEVICE + ["--device-config", str(config)])
    assert "buttons.ghost" in caplog.text
    assert "no button with this name" in caplog.text


def test_missing_device_configuration_file_exits(tmp_path, caplog):
    with pytest.raises(SystemExit):
        run(DEVICE + ["--device-config", str(tmp_path / "nope.toml")])
    assert "cannot be read" in caplog.text


def test_valid_device_configuration_is_accepted(tmp_path):
    config = tmp_path / "device.toml"
    config.write_text('brightness = 0.5\n[buttons.button]\nrole = "mute"\n', encoding="utf-8")
    controller = run_without_connecting(DEVICE + ["--device-config", str(config)])
    controller.assert_called_once()
