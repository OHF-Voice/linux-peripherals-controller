"""Announces the ESPHome API over mDNS, so Home Assistant discovers LPC like an ESPHome device.

Taken from LVA (``linux_voice_assistant/zeroconf.py``): the service ``_esphomelib._tcp`` with the MAC address, and with
``api_encryption`` when an encryption key is needed.
"""

from __future__ import annotations

import logging
import socket
from typing import Optional

from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

_LOGGER = logging.getLogger(__name__)

SERVICE_TYPE = "_esphomelib._tcp.local."


class Discovery:
    """
    The mDNS announcement of the ESPHome API.
    :param name: Device name, also the mDNS host name.
    :param port: Port of the ESPHome API.
    :param mac_address: MAC address of the device.
    :param ip_address: IPv4 address Home Assistant connects to.
    :param encrypted: True if the API needs an encryption key.
    """

    def __init__(self, name: str, port: int, mac_address: str, ip_address: str, encrypted: bool) -> None:
        self._info = AsyncServiceInfo(
            SERVICE_TYPE,
            f"{name}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip_address)],
            port=port,
            properties=service_properties(mac_address, encrypted),
            server=f"{name}.local.",
        )
        self._zeroconf: Optional[AsyncZeroconf] = None

    async def start(self) -> None:
        """Announce the service."""
        self._zeroconf = AsyncZeroconf()
        await self._zeroconf.async_register_service(self._info)
        _LOGGER.info("Announced over mDNS: %s", self._info.name)

    async def stop(self) -> None:
        """Withdraw the announcement."""
        if self._zeroconf is not None:
            await self._zeroconf.async_unregister_service(self._info)
            await self._zeroconf.async_close()
            self._zeroconf = None


def service_properties(mac_address: str, encrypted: bool) -> dict[str, str]:
    """
    The TXT record of the service, as ESPHome devices have it.
    :param mac_address: MAC address of the device.
    :param encrypted: True if the API needs an encryption key, Home Assistant then asks for it.
    """
    properties = {"version": "2025.9.0", "mac": mac_address.replace(":", "").lower(), "board": "host", "platform": "HOST", "network": "ethernet"}
    if encrypted:
        properties["api_encryption"] = "Noise_NNpsk0_25519_ChaChaPoly_SHA256"
    return properties


def local_ip_address() -> str:
    """
    The IPv4 address of the interface with the default route.
    :return: The address, ``127.0.0.1`` if there is no route. No packet is sent.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
            return str(probe.getsockname()[0])
        except OSError:
            return "127.0.0.1"
