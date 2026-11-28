"""The device types LPC knows. Every device type is one file in this folder, named like the device type.

A device file has ``DEVICE_TYPE`` (the description of the hardware, see ``device_types.py``) and a ``Device`` class derived from
``BaseDevice`` (``base.py``), which runs the hardware and can do things of its own. A new device type is a new file and a line in
``DEVICE_FILES``.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Mapping, Tuple

from ..device_setup import ResolvedDevice
from ..device_types import DeviceType, UnknownDeviceType
from ..drivers import Drivers
from .base import BaseDevice

DEVICE_FILES = (
    "jabra_speak_410",
    "respeaker_2mic_v1",
    "respeaker_2mic_v2",
    "respeaker_4mic",
    "respeaker_lite",
    "respeaker_xvf3000",
    "satellite1",
)


def _load(name: str) -> ModuleType:
    return importlib.import_module(f"{__name__}.{name}")


DEVICE_TYPES: Mapping[str, DeviceType] = {name: _load(name).DEVICE_TYPE for name in DEVICE_FILES}


def get_device_type(name: str) -> DeviceType:
    """
    Look up a device type.
    :param name: The name of the device type.
    :raises UnknownDeviceType: If there is no such device type. The error names the known ones.
    """
    try:
        return DEVICE_TYPES[name]
    except KeyError:
        raise UnknownDeviceType(name, known_device_types()) from None


def known_device_types() -> Tuple[str, ...]:
    """The names of all device types, sorted."""
    return tuple(sorted(DEVICE_TYPES))


def create_device(device: ResolvedDevice, drivers: Drivers) -> BaseDevice:
    """
    Create the device of the file of its device type. It opens no hardware yet, see ``BaseDevice.open()``.
    :param device: The device type with the device configuration applied.
    :param drivers: Opens the drivers (real or simulated).
    """
    device_class: type[BaseDevice] = _load(device.device_type.name).Device
    return device_class(device, drivers)
