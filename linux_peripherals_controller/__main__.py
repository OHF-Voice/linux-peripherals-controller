"""Entry point of the Linux Peripherals Controller."""

import argparse
import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional, Sequence

from .controller import Controller
from .device_config import DeviceConfigError, load_device_config
from .device_runner import DeviceRunner
from .device_setup import ResolvedDevice, resolve_device
from .device_types import UnknownDeviceType
from .devices import create_device, get_device_type, known_device_types
from .drivers import DriverError, Drivers
from .esphome.api_server import create_encryption_key_file, load_encryption_key_file
from .esphome.discovery import Discovery, local_ip_address
from .esphome.server import DeviceInfo, HomeAssistantServer
from .state_store import load_state, save_state
from .util import get_esphome_version, get_version

_LOGGER = logging.getLogger(__name__)


def run(argv: Optional[Sequence[str]] = None) -> None:
    """
    Parse the command line and start the controller.
    :param argv: Command line arguments, ``sys.argv[1:]`` when None.
    :raises SystemExit: With a non-zero status if the device type, the device configuration, the encryption key or the hardware
    cannot be used.
    """
    parser = argparse.ArgumentParser(prog="linux-peripherals-controller")
    parser.add_argument("--device-type", help="Type of the device, for example respeaker_2mic_v1 (required)")
    parser.add_argument("--device-config", type=Path, help="TOML file with the settings of this device (default: none, the device type as it is)")
    parser.add_argument("--lva-host", default="localhost", help="Host of the Linux-Voice-Assistant peripheral WebSocket API (default: %(default)s)")
    parser.add_argument("--lva-port", type=int, default=6055, help="Port of the Linux-Voice-Assistant peripheral WebSocket API (default: %(default)s)")
    parser.add_argument("--host", default="0.0.0.0", help="Address the ESPHome API for Home Assistant listens on (default: %(default)s)")
    parser.add_argument("--port", type=int, default=6054, help="Port of the ESPHome API for Home Assistant, 0 for any free port (default: %(default)s)")
    parser.add_argument("--name", help="Device name in Home Assistant and over mDNS (default: lpc-<MAC address without colons>)")
    parser.add_argument("--enable-zeroconf", type=int, choices=(0, 1), default=1, help="1: announce the ESPHome API over mDNS, 0: add LPC by hand in Home Assistant (default: %(default)s)")
    parser.add_argument("--enable-encryption", action="store_true", help="Encrypt the ESPHome API with a key, as ESPHome devices do")
    parser.add_argument("--encryption-key-file", type=Path, help="File with the encryption key, created with a new key if missing (default: encryption.key next to the state file)")
    parser.add_argument("--state-file", type=Path, default=Path("state.json"), help="JSON file that keeps the child lock and the light across restarts (default: %(default)s)")
    parser.add_argument("--simulate-hardware", action="store_true", help="Open no hardware: the LEDs are only logged at debug level and no button can be pressed")
    parser.add_argument("--debug", action="store_true", help="Print DEBUG messages to console")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.info("Version: %s", get_version())
    device = _load_device(args.device_type, args.device_config)
    _LOGGER.info("Device type: %s (%s)", device.device_type.name, device.device_type.description)
    _LOGGER.info("Peripheral API of LVA: ws://%s:%s", args.lva_host, args.lva_port)
    noise_psk = _load_encryption_key(args.encryption_key_file or args.state_file.parent / "encryption.key") if args.enable_encryption else None
    try:
        asyncio.run(_serve(args, device, noise_psk))
    except KeyboardInterrupt:
        _LOGGER.info("Stopped")


async def _serve(args: argparse.Namespace, resolved: ResolvedDevice, noise_psk: Optional[bytes]) -> None:
    """Open the hardware, start the ESPHome API and mDNS, then stay connected to LVA."""
    state_file: Path = args.state_file
    runner = DeviceRunner(create_device(resolved, Drivers(simulated=args.simulate_hardware)), load_state(state_file), lambda state: save_state(state_file, state))
    if args.simulate_hardware:
        _LOGGER.warning("Simulated hardware: the LEDs are only logged and no button can be pressed")
    try:
        runner.open()
    except DriverError as exc:
        _LOGGER.error("%s", exc)
        raise SystemExit(1) from exc

    mac_address = _mac_address()
    name = args.name or f"lpc-{mac_address.replace(':', '')}"
    info = DeviceInfo(name, "Linux Peripheral Controller", mac_address, resolved.device_type.description, get_version(), get_esphome_version())
    server = HomeAssistantServer(info, runner.entities(), noise_psk)
    controller = Controller(
        args.lva_host,
        args.lva_port,
        on_display_change=runner.display_changed,
        on_hardware_mute_request=runner.device.switch_hardware_mute,
        on_status_change=runner.status_changed,
    )
    runner.attach(controller, server)
    discovery: Optional[Discovery] = None
    try:
        try:
            port = await server.start(args.host, args.port)
        except OSError as exc:
            _LOGGER.error("The ESPHome API cannot listen on %s:%s: %s", args.host, args.port, exc)
            raise SystemExit(1) from exc
        ip_address = local_ip_address()
        if args.enable_zeroconf:
            discovery = Discovery(name, port, mac_address, ip_address, noise_psk is not None)
            await discovery.start()
        else:
            _LOGGER.info("mDNS disabled: add LPC in Home Assistant by hand with %s:%s", ip_address, port)
        await asyncio.gather(controller.run(), runner.read_sensors())
    finally:
        if discovery is not None:
            await discovery.stop()
        await server.stop()
        runner.close()


def _load_device(device_type_name: Optional[str], config_path: Optional[Path]) -> ResolvedDevice:
    """Read the device type and the device configuration, or log why that is not possible and exit."""
    if not device_type_name:
        _LOGGER.error("No device type given (--device-type). Known device types: %s", ", ".join(known_device_types()))
        raise SystemExit(1)
    try:
        device_type = get_device_type(device_type_name)
        return resolve_device(device_type, load_device_config(config_path), str(config_path or "device configuration"))
    except (UnknownDeviceType, DeviceConfigError) as exc:
        _LOGGER.error("%s", exc)
        raise SystemExit(1) from exc


def _load_encryption_key(path: Path) -> bytes:
    """Read the encryption key, create it first if the file is missing, or log why that is not possible and exit."""
    if not path.exists():
        try:
            create_encryption_key_file(path)
        except OSError as exc:
            _LOGGER.error("Cannot create the encryption key file %s: %s", path, exc)
            raise SystemExit(1) from exc
        _LOGGER.warning("Created a new encryption key in %s: enter it in Home Assistant when adding LPC", path)
    try:
        return load_encryption_key_file(path)
    except (OSError, ValueError) as exc:
        _LOGGER.error("Cannot use the encryption key file %s: %s", path, exc)
        raise SystemExit(1) from exc


def _mac_address() -> str:
    """The MAC address of this machine, as Python finds it (``uuid.getnode()``)."""
    node = uuid.getnode()
    return ":".join(f"{(node >> shift) & 0xFF:02x}" for shift in range(40, -1, -8))


if __name__ == "__main__":
    run()
