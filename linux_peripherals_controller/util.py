"""Small helpers shared by the controller modules."""

from pathlib import Path

_version_cache: str | None = None


def get_version() -> str:
    """
    Read the version from the version.txt file in the project root.
    :return: The version from version.txt or 'unknown' if the file does not exist or cannot be read.
    """
    global _version_cache

    if _version_cache is not None:
        return _version_cache

    version_file = Path(__file__).parent.parent / "version.txt"
    try:
        _version_cache = version_file.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        _version_cache = "unknown"

    return _version_cache
