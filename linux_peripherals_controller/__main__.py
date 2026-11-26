"""Entry point of the Linux Peripherals Controller."""

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Optional, Sequence

from .controller import Controller
from .device_config import DeviceConfigError, load_device_config
from .device_setup import ResolvedDevice, resolve_device
from .device_types import UnknownDeviceType, get_device_type, known_device_types
from .util import get_version

_LOGGER = logging.getLogger(__name__)


def run(argv: Optional[Sequence[str]] = None) -> None:
    """
    Parse the command line and start the controller.
    :param argv: Command line arguments, ``sys.argv[1:]`` when None.
    :raises SystemExit: With a non-zero status if the device type or the device configuration cannot be used.
    """
    parser = argparse.ArgumentParser(prog="linux-peripherals-controller")
    parser.add_argument("--device-type", help="Type of the device, for example respeaker_2mic_v1 (required)")
    parser.add_argument("--device-config", type=Path, help="TOML file with the settings of this device (default: none, the device type as it is)")
    parser.add_argument("--lva-host", default="localhost", help="Host of the Linux-Voice-Assistant peripheral WebSocket API (default: %(default)s)")
    parser.add_argument("--lva-port", type=int, default=6055, help="Port of the Linux-Voice-Assistant peripheral WebSocket API (default: %(default)s)")
    parser.add_argument("--debug", action="store_true", help="Print DEBUG messages to console")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.info("Version: %s", get_version())
    device = _load_device(args.device_type, args.device_config)
    _LOGGER.info("Device type: %s (%s)", device.device_type.name, device.device_type.description)
    _LOGGER.info("Peripheral API of LVA: ws://%s:%s", args.lva_host, args.lva_port)
    _LOGGER.warning("No peripheral drivers are implemented yet, the display function is only logged")
    try:
        asyncio.run(Controller(args.lva_host, args.lva_port).run())
    except KeyboardInterrupt:
        _LOGGER.info("Stopped")


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


if __name__ == "__main__":
    run()
