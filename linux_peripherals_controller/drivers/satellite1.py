"""The Satellite1 HAT, through its daemon ``satellite1d`` of the Satellite1-RPi-SDK (FutureProofHomes).

``satellite1d`` owns the hardware of the HAT (the XMOS chip on SPI, the GPIO of the action button, the sensors on I2C), so LPC never
touches it directly. It talks to the daemon over its Unix socket, as the public client of the SDK does: one JSON object per line,
requests ``{"id", "method", "params"}`` answered with ``{"id", "result"}`` or ``{"id", "error"}``. A second connection subscribes to
the events of the daemon (``events.subscribe``).

- ``led.render``: 24 pixels as ``[red, green, blue]``. Only offered while the LED ring is enabled in ``/etc/satellite1.conf``.
- ``environment.get_readings``: ``temperature_c``, ``humidity_percent`` and ``illuminance_lux``, each None if it cannot be read.
- ``mics.get_muted``: ``muted``, the latching microphone mute switch of the HAT.
- ``dac.get_plugged_in``: ``plugged_in``, whether a plug is in the line-out jack.
- ``dac.get_amp_level`` / ``dac.set_amp_level`` (``level``): ``amp_level``, the gain of the speaker amplifier, 0 to 20.
- ``power.get_contract``: ``available``, ``voltage`` (V) and ``current`` (A) of the USB-C power contract.
- ``xmos.get_firmware``: ``firmware``, the firmware version of the XMOS chip.
- Events: ``buttons.pressed`` (``name`` ``action``, ``volume_up`` or ``volume_down``, a press, the release is not reported),
  ``mics.muted_changed`` (``muted``) and ``audio.line_out_jack_changed`` (``plugged_in``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, TypeGuard, TypeVar, Union, cast

from ..appearance import Color
from .base import DriverError

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_SOCKET_PATH = Path("/run/satellite1/satellite1d.sock")
LED_COUNT = 24
PROTOCOL_VERSION = 1
BUTTON_NAMES = frozenset({"action", "volume_up", "volume_down"})
AMP_LEVEL_MAX = 20
_TIMEOUT_SECONDS = 2.0
_RECONNECT_SECONDS = 3.0


@dataclass(frozen=True)
class Satellite1Event:
    """
    An event of the daemon that LPC uses.
    :param kind: ``button`` (``value`` is its name), ``mic_muted`` or ``line_out_jack`` (``value`` is True or False).
    """

    kind: str
    value: Union[str, bool]


@dataclass(frozen=True)
class PowerContract:
    """The USB-C power contract: volts and amperes."""

    voltage: float
    current: float


class Satellite1Link(Protocol):
    """What a device file uses of ``satellite1d``, the real connection or a simulated one."""

    @property
    def count(self) -> int:
        """Number of LEDs of the ring."""

    def write(self, pixels: Sequence[Color]) -> None:
        """Show the colors on the LED ring."""

    def close(self) -> None:
        """Clear the LED ring and close the connection."""

    def read_environment(self) -> Mapping[str, Optional[float]]:
        """Read the environment sensors."""

    def mic_muted(self) -> Optional[bool]:
        """The microphone mute switch."""

    def line_out_plugged_in(self) -> Optional[bool]:
        """Whether a plug is in the line-out jack."""

    def amp_level(self) -> Optional[int]:
        """The gain of the speaker amplifier."""

    def set_amp_level(self, level: int) -> Optional[int]:
        """Change the gain of the speaker amplifier."""

    def power_contract(self) -> Optional[PowerContract]:
        """The USB-C power contract."""

    def firmware(self) -> Optional[str]:
        """The firmware version of the XMOS chip."""


class Satellite1Daemon:
    """
    The connection to ``satellite1d``: the LED ring (an LED strip), the sensors, the settings and the events of the HAT.
    :param on_event: Called on the event loop with every event of the daemon that LPC uses.
    :param socket_path: The socket of the daemon.
    :raises DriverError: If the daemon cannot be reached, speaks another protocol version or has its LED ring disabled.
    """

    def __init__(self, on_event: Callable[[Satellite1Event], None], socket_path: Path = DEFAULT_SOCKET_PATH) -> None:
        self._socket_path = socket_path
        self._on_event = on_event
        self._lock = threading.Lock()
        self._socket: Optional[socket.socket] = None
        self._buffer = b""
        self._next_id = 1
        self._write_failed = False
        try:
            hello = self._request("hello")
        except (OSError, ValueError) as exc:
            raise DriverError(f"satellite1d cannot be reached at {socket_path} (is it running and the socket passed to the container?): {exc}") from exc
        if hello.get("protocol_version") != PROTOCOL_VERSION:
            raise DriverError(f"satellite1d speaks protocol version {hello.get('protocol_version')}, LPC speaks {PROTOCOL_VERSION}")
        capabilities = hello.get("capabilities") or []
        if "led.render" not in capabilities:
            raise DriverError("satellite1d offers no LED ring: enable it in /etc/satellite1.conf ([led_ring] enabled = true)")
        self._events = asyncio.get_running_loop().create_task(self._follow_events(), name="satellite1d-events")
        _LOGGER.info("Satellite1 HAT through satellite1d at %s", socket_path)

    @property
    def count(self) -> int:
        """Number of LEDs of the ring."""
        return LED_COUNT

    def write(self, pixels: Sequence[Color]) -> None:
        """
        Show the colors on the LED ring.
        :param pixels: One color per LED. Missing ones are dark.
        """
        try:
            self._request("led.render", {"pixels": led_frame(pixels)})
            self._write_failed = False
        except (OSError, ValueError) as exc:
            if not self._write_failed:
                _LOGGER.warning("Cannot show the LEDs through satellite1d: %s", exc)
                self._write_failed = True

    def read_environment(self) -> Mapping[str, Optional[float]]:
        """
        Read the environment sensors. It blocks, call it in a thread.
        :return: ``temperature_c``, ``humidity_percent`` and ``illuminance_lux``. Empty if the daemon cannot be asked.
        """
        try:
            return environment_readings(self._request("environment.get_readings"))
        except (OSError, ValueError) as exc:
            _LOGGER.debug("Cannot read the sensors through satellite1d: %s", exc)
            return {}

    def mic_muted(self) -> Optional[bool]:
        """The microphone mute switch of the HAT, None if it cannot be read."""
        return self._read("mics.get_muted", "muted", bool)

    def line_out_plugged_in(self) -> Optional[bool]:
        """Whether a plug is in the line-out jack, None if it cannot be read."""
        return self._read("dac.get_plugged_in", "plugged_in", bool)

    def amp_level(self) -> Optional[int]:
        """The gain of the speaker amplifier (0 to 20), None if it cannot be read."""
        return self._read("dac.get_amp_level", "amp_level", int, {"dac": "speaker"})

    def set_amp_level(self, level: int) -> Optional[int]:
        """
        Change the gain of the speaker amplifier.
        :param level: 0 to 20.
        :return: The level the daemon reports afterwards, None if it refused or cannot be reached.
        """
        return self._read("dac.set_amp_level", "amp_level", int, {"dac": "speaker", "level": level})

    def power_contract(self) -> Optional[PowerContract]:
        """The USB-C power contract, None if there is none or it cannot be read."""
        try:
            result = self._request("power.get_contract")
        except (OSError, ValueError) as exc:
            _LOGGER.debug("Cannot read the power contract through satellite1d: %s", exc)
            return None
        voltage, current = result.get("voltage"), result.get("current")
        if result.get("available") is not True or not _is_number(voltage) or not _is_number(current):
            return None
        return PowerContract(float(voltage), float(current))

    def firmware(self) -> Optional[str]:
        """The firmware version of the XMOS chip, None if it cannot be read."""
        return self._read("xmos.get_firmware", "firmware", str)

    def close(self) -> None:
        """Clear the LED ring, stop following the events and close the connection."""
        self.write(())
        self._events.cancel()
        with self._lock:
            self._disconnect()

    def _read(self, method: str, key: str, expected: type[T], params: Optional[Mapping[str, Any]] = None) -> Optional[T]:
        try:
            value = self._request(method, params).get(key)
        except (OSError, ValueError) as exc:
            _LOGGER.debug("satellite1d: %s failed: %s", method, exc)
            return None
        valid = isinstance(value, expected) and (expected is bool or not isinstance(value, bool))
        return cast(T, value) if valid else None

    def _request(self, method: str, params: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        with self._lock:
            try:
                return self._exchange(method, params)
            except OSError:
                # The daemon may have been restarted: one new connection, then give up.
                self._disconnect()
                return self._exchange(method, params)

    def _exchange(self, method: str, params: Optional[Mapping[str, Any]]) -> dict[str, Any]:
        if self._socket is None:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.settimeout(_TIMEOUT_SECONDS)
            self._socket.connect(str(self._socket_path))
            self._buffer = b""
        request_id = self._next_id
        self._next_id += 1
        self._socket.sendall(json.dumps({"id": request_id, "method": method, "params": dict(params or {})}).encode() + b"\n")
        while b"\n" not in self._buffer:
            chunk = self._socket.recv(65536)
            if not chunk:
                raise ConnectionError("satellite1d closed the connection")
            self._buffer += chunk
        line, self._buffer = self._buffer.split(b"\n", 1)
        return parse_response(line, request_id)

    def _disconnect(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    async def _follow_events(self) -> None:
        failure_logged = False
        while True:
            try:
                reader, writer = await asyncio.open_unix_connection(str(self._socket_path))
                try:
                    writer.write(json.dumps({"id": 1, "method": "events.subscribe", "params": {"include_current": False}}).encode() + b"\n")
                    await writer.drain()
                    parse_response(await reader.readline(), 1)
                    failure_logged = False
                    while line := await reader.readline():
                        event = parse_event(line)
                        if event is not None:
                            _LOGGER.debug("satellite1d: %s %s", event.kind, event.value)
                            self._on_event(event)
                finally:
                    writer.close()
            except (OSError, ValueError) as exc:
                if not failure_logged:
                    _LOGGER.warning("Lost the events of satellite1d, trying again every %.0f s: %s", _RECONNECT_SECONDS, exc)
                    failure_logged = True
            await asyncio.sleep(_RECONNECT_SECONDS)


def led_frame(pixels: Sequence[Color]) -> list[list[int]]:
    """
    The pixels of ``led.render``.
    :param pixels: One color per LED. Missing ones are dark, extra ones are left out.
    """
    frame = [[pixel.red, pixel.green, pixel.blue] for pixel in pixels[:LED_COUNT]]
    return frame + [[0, 0, 0]] * (LED_COUNT - len(frame))


def parse_response(line: bytes, request_id: int) -> dict[str, Any]:
    """
    Read the answer of the daemon to a request.
    :param line: The answer, one JSON object.
    :param request_id: The id of the request.
    :raises ValueError: If the answer is not valid, belongs to another request or is an error of the daemon.
    :return: The result.
    """
    if not line:
        raise ValueError("satellite1d closed the connection without an answer")
    answer = json.loads(line)
    if not isinstance(answer, dict) or answer.get("id") != request_id:
        raise ValueError("satellite1d returned an invalid answer")
    error = answer.get("error")
    if error is not None:
        message = error.get("message") if isinstance(error, dict) else error
        raise ValueError(f"satellite1d refused the request: {message}")
    result = answer.get("result")
    if not isinstance(result, dict):
        raise ValueError("satellite1d returned an invalid answer")
    return result


def environment_readings(result: Mapping[str, Any]) -> dict[str, Optional[float]]:
    """
    The readings of ``environment.get_readings``.
    :param result: The result of the daemon.
    :return: The three readings, None for each one that is missing or not a number.
    """
    readings: dict[str, Optional[float]] = {}
    for key in ("temperature_c", "humidity_percent", "illuminance_lux"):
        value = result.get(key)
        readings[key] = float(value) if _is_number(value) else None
    return readings


def parse_event(line: bytes) -> Optional[Satellite1Event]:
    """
    Read an event of the daemon.
    :param line: The event, one JSON object.
    :return: A button press, a change of the microphone mute switch or of the line-out jack. None for every other event and for
    invalid data.
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
        return None
    name, data = event.get("event"), event["data"]
    if name == "buttons.pressed" and data.get("name") in BUTTON_NAMES:
        return Satellite1Event("button", data["name"])
    if name == "mics.muted_changed" and isinstance(data.get("muted"), bool):
        return Satellite1Event("mic_muted", data["muted"])
    if name == "audio.line_out_jack_changed" and isinstance(data.get("plugged_in"), bool):
        return Satellite1Event("line_out_jack", data["plugged_in"])
    return None


def _is_number(value: Any) -> TypeGuard[float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
