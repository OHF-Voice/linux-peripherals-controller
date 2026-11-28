"""Unit tests for __main__.py."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from linux_peripherals_controller.__main__ import run

DEVICE = ["--device-type", "respeaker_2mic_v1"]


@pytest.fixture(autouse=True)
def _in_tmp_path(tmp_path, monkeypatch):
    """The state file and the encryption key go to a fresh folder."""
    monkeypatch.chdir(tmp_path)


def run_without_connecting(argv):
    """Run the entry point with simulated hardware, no mDNS, any free port and a controller that returns at once."""
    with patch("linux_peripherals_controller.__main__.Controller") as controller:
        controller.return_value.run = _done
        run(argv + ["--simulate-hardware", "--enable-zeroconf", "0", "--port", "0"])
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
    controller.assert_called_once()
    assert controller.call_args.args == ("lva.local", 7000)


def test_run_stops_quietly_on_ctrl_c(caplog):
    with patch("linux_peripherals_controller.__main__.asyncio.run", side_effect=KeyboardInterrupt), patch("linux_peripherals_controller.__main__._serve", new=MagicMock()):
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


def test_hardware_that_cannot_be_opened_exits(caplog):
    with patch("linux_peripherals_controller.__main__.Controller"):
        with pytest.raises(SystemExit) as exit_info:
            run(DEVICE + ["--enable-zeroconf", "0", "--port", "0"])
    assert exit_info.value.code == 1
    assert "APA102 LEDs on /dev/spidev0.0" in caplog.text


def test_simulated_hardware_is_logged(caplog):
    with caplog.at_level(logging.INFO):
        run_without_connecting(DEVICE)
    assert "Simulated hardware" in caplog.text


def test_esphome_api_and_disabled_mdns_are_logged(caplog):
    with caplog.at_level(logging.INFO):
        run_without_connecting(DEVICE)
    assert "ESPHome API for Home Assistant on 0.0.0.0:" in caplog.text
    assert "mDNS disabled: add LPC in Home Assistant by hand" in caplog.text


def test_encryption_creates_a_key_file_next_to_the_state_file(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        run_without_connecting(DEVICE + ["--enable-encryption", "--state-file", str(tmp_path / "data" / "state.json")])
    key_file = tmp_path / "data" / "encryption.key"
    assert key_file.exists()
    assert f"Created a new encryption key in {key_file}" in caplog.text
    assert "(encrypted)" in caplog.text


def test_invalid_encryption_key_exits(tmp_path, caplog):
    key_file = tmp_path / "bad.key"
    key_file.write_text("not a key\n", encoding="utf-8")
    key_file.chmod(0o600)
    with pytest.raises(SystemExit) as exit_info:
        run(DEVICE + ["--enable-encryption", "--encryption-key-file", str(key_file)])
    assert exit_info.value.code == 1
    assert f"Cannot use the encryption key file {key_file}" in caplog.text
