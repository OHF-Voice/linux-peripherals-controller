"""LPC as a process: what it does at the start and when it is stopped, see "Startup and errors" in docs/behavior.md."""

from pathlib import Path

from .fake_lva import FakeLva
from .lpc import DEVICE_TYPE, run_to_exit


def test_missing_device_type_lists_the_known_ones_and_exits() -> None:
    """Without --device-type LPC logs the known device types and exits with a non-zero status."""
    result = run_to_exit([])
    assert result.returncode == 1
    assert "No device type given" in result.stdout
    assert DEVICE_TYPE in result.stdout


def test_unknown_device_type_lists_the_known_ones_and_exits() -> None:
    """An unknown device type is refused with the list of the known ones."""
    result = run_to_exit(["--device-type", "toaster"])
    assert result.returncode == 1
    assert "Unknown device type 'toaster'" in result.stdout
    assert DEVICE_TYPE in result.stdout


def test_invalid_device_configuration_names_file_and_key_and_exits(tmp_path: Path) -> None:
    """A device configuration with an unknown key is refused as a whole, the log names the file and the key."""
    config = tmp_path / "device.toml"
    config.write_text("no_such_setting = 1\n", encoding="utf-8")

    result = run_to_exit(["--device-type", DEVICE_TYPE, "--device-config", str(config)])

    assert result.returncode == 1
    assert str(config) in result.stdout
    assert "no_such_setting" in result.stdout


async def test_valid_device_configuration_starts_and_connects(fake_lva: FakeLva, start_lpc, tmp_path: Path) -> None:
    """A valid device configuration is accepted and LPC connects to LVA as without one."""
    config = tmp_path / "device.toml"
    config.write_text("brightness = 0.5\n", encoding="utf-8")

    lpc = start_lpc(fake_lva, ["--device-config", str(config)])

    await lpc.wait_for_log_line("Connected to LVA")
    await fake_lva.wait_for_connection()


async def test_startup_logs_version_device_type_and_address_of_lva(fake_lva: FakeLva, start_lpc) -> None:
    """The first log lines name the version, the device type and the peripheral API of LVA that LPC connects to."""
    lpc = start_lpc(fake_lva)

    await lpc.wait_for_log_line("Connected to LVA")

    log = lpc.full_log()
    assert "Version: " in log
    assert f"Device type: {DEVICE_TYPE}" in log
    assert f"Peripheral API of LVA: ws://127.0.0.1:{fake_lva.port}" in log


async def test_ctrl_c_stops_quietly(lpc) -> None:
    """Ctrl+C ends LPC with exit status 0 and one "Stopped" line, no traceback."""
    status = await lpc.interrupt()

    assert status == 0
    assert "Stopped" in lpc.full_log()
    assert "Traceback" not in lpc.full_log()
