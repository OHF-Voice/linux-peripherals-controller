"""What LPC keeps across restarts: the child lock and the light of Home Assistant, in a JSON file.

A missing file is the first start and gives the defaults. A file that cannot be read gives the defaults too and is logged, so LPC
still starts. Writing goes to a temporary file first, so a crash never leaves half a file behind.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .light import LightState

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredState:
    """The values that are kept across restarts."""

    child_lock: bool = False
    light: LightState = field(default_factory=LightState)

    def to_dict(self) -> dict[str, Any]:
        """The values for the state file."""
        return {"child_lock": self.child_lock, "light": self.light.to_dict()}

    @classmethod
    def from_dict(cls, data: Any) -> "StoredState":
        """
        Read the values of the state file.
        :param data: The content of the file. Missing or invalid values keep their default.
        """
        if not isinstance(data, dict):
            return cls()
        child_lock = data.get("child_lock")
        light = data.get("light")
        return cls(
            child_lock=child_lock if isinstance(child_lock, bool) else False,
            light=LightState.from_dict(light) if isinstance(light, dict) else LightState(),
        )


def load_state(path: Path) -> StoredState:
    """
    Read the state file.
    :param path: The file.
    :return: The stored values, the defaults if the file does not exist or cannot be read (logged as a warning).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _LOGGER.info("No state file yet (%s), starting with the defaults", path)
        return StoredState()
    except OSError as exc:
        _LOGGER.warning("Cannot read the state file %s, starting with the defaults: %s", path, exc)
        return StoredState()
    try:
        return StoredState.from_dict(json.loads(text))
    except json.JSONDecodeError as exc:
        _LOGGER.warning("The state file %s is not valid JSON, starting with the defaults: %s", path, exc)
        return StoredState()


def save_state(path: Path, state: StoredState) -> None:
    """
    Write the state file.
    :param path: The file. Its folder is created if needed.
    :param state: The values to keep. A failure is logged, it does not stop LPC.
    """
    temporary = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        _LOGGER.warning("Cannot write the state file %s: %s", path, exc)
