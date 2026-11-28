"""Unit tests for util.py."""

from pathlib import Path

from linux_peripherals_controller import util


def test_get_version_reads_version_file(monkeypatch, tmp_path: Path):
    (tmp_path / "version.txt").write_text("1.2.3\n", encoding="utf-8")
    monkeypatch.setattr(util, "_version_cache", None)
    monkeypatch.setattr(util, "__file__", str(tmp_path / "linux_peripherals_controller" / "util.py"))

    assert util.get_version() == "1.2.3"


def test_get_version_without_file_is_unknown(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(util, "_version_cache", None)
    monkeypatch.setattr(util, "__file__", str(tmp_path / "linux_peripherals_controller" / "util.py"))

    assert util.get_version() == "unknown"


def test_get_esphome_version_is_the_version_of_aioesphomeapi():
    assert util.get_esphome_version() == "46.30.1"


def test_get_esphome_version_without_the_package_is_unknown(monkeypatch):
    def missing(name):
        raise util.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(util.metadata, "version", missing)
    assert util.get_esphome_version() == "unknown"
