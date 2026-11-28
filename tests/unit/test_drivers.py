"""Unit tests for the drivers in drivers/. The hardware packages are replaced by fakes, so no hardware is needed."""

import asyncio
import logging
import sys
import time
import types
from unittest.mock import MagicMock

import pytest

from linux_peripherals_controller.appearance import Color
from linux_peripherals_controller.device_types import LedSpec
from linux_peripherals_controller.drivers import DriverError, Drivers
from linux_peripherals_controller.drivers.apa102 import Apa102Strip, apa102_frame
from linux_peripherals_controller.drivers.simulated import SimulatedHardware, SimulatedLedStrip
from linux_peripherals_controller.drivers.usb_pixel_ring import PRODUCT_ID, VENDOR_ID, UsbPixelRing, pixel_ring_payload
from linux_peripherals_controller.drivers.ws2812 import SPI_SPEED_HZ, Ws2812Strip, ws2812_payload

RED = Color(255, 0, 0)
BLUE = Color(0, 0, 255)


class TestApa102Frame:
    def test_start_frame_led_frames_in_blue_green_red_and_end_frame(self):
        assert apa102_frame([RED, BLUE], 2) == bytes([0, 0, 0, 0, 0xFF, 0, 0, 255, 0xFF, 255, 0, 0, 0xFF, 0xFF, 0xFF, 0xFF])

    def test_missing_leds_are_dark_and_extra_ones_left_out(self):
        assert apa102_frame([], 1)[4:8] == bytes([0xFF, 0, 0, 0])
        assert len(apa102_frame([RED, RED, RED], 1)) == 4 + 4 + 4

    def test_end_frame_grows_with_many_leds(self):
        assert apa102_frame([], 100)[-7:] == b"\xff" * 7


class TestApa102Strip:
    @pytest.fixture
    def spidev(self, monkeypatch):
        spi_dev = MagicMock()
        module = types.SimpleNamespace(SpiDev=spi_dev)
        monkeypatch.setitem(sys.modules, "spidev", module)
        return spi_dev.return_value

    def test_opens_the_spi_device_and_writes_frames(self, spidev):
        strip = Apa102Strip(2, spi_bus=0, spi_device=1, spi_speed_hz=1000)
        spidev.open.assert_called_once_with(0, 1)
        assert spidev.max_speed_hz == 1000
        assert spidev.mode == 1
        strip.write([RED])
        spidev.xfer2.assert_called_once_with(list(apa102_frame([RED], 2)))
        assert strip.count == 2

    def test_close_turns_off_and_closes(self, spidev):
        strip = Apa102Strip(1)
        strip.close()
        spidev.xfer2.assert_called_once_with(list(apa102_frame([], 1)))
        spidev.close.assert_called_once()

    def test_device_that_cannot_be_opened_is_a_driver_error(self, spidev):
        spidev.open.side_effect = FileNotFoundError("no such file")
        with pytest.raises(DriverError, match="/dev/spidev0.0 cannot be opened"):
            Apa102Strip(3)

    def test_write_error_is_logged_not_raised(self, spidev, caplog):
        spidev.xfer2.side_effect = OSError("gone")
        Apa102Strip(1).write([RED])
        assert "Cannot write to the APA102 LEDs" in caplog.text

    def test_missing_package_is_a_driver_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "spidev", None)
        with pytest.raises(DriverError, match="spidev is not installed"):
            Apa102Strip(3)


class TestWs2812Payload:
    def test_each_bit_is_three_spi_bits_in_green_red_blue_order(self):
        data = ws2812_payload([Color(0x80, 0xFF, 0x00)], 1)[100:-100]
        # green 0xFF: eight 110, red 0x80: one 110 then seven 100, blue 0x00: eight 100
        assert data == bytes([0xDB, 0x6D, 0xB6]) + bytes([0xD2, 0x49, 0x24]) + bytes([0x92, 0x49, 0x24])

    def test_reset_phase_before_and_after_the_data(self):
        payload = ws2812_payload([RED], 1)
        assert payload[:100] == bytes(100)
        assert payload[-100:] == bytes(100)
        assert len(payload) == 100 + 9 + 100

    def test_missing_leds_are_dark_and_extra_ones_left_out(self):
        assert ws2812_payload([], 2)[100:-100] == bytes([0x92, 0x49, 0x24]) * 6
        assert len(ws2812_payload([RED, RED, RED], 1)) == 100 + 9 + 100


class TestWs2812Strip:
    @pytest.fixture
    def spidev(self, monkeypatch):
        spi_dev = MagicMock()
        module = types.SimpleNamespace(SpiDev=spi_dev)
        monkeypatch.setitem(sys.modules, "spidev", module)
        return spi_dev.return_value

    def test_opens_the_spi_device_at_the_ws2812_speed_and_writes(self, spidev, caplog):
        caplog.set_level(logging.INFO)
        strip = Ws2812Strip(1, spi_bus=0, spi_device=1)
        spidev.open.assert_called_once_with(0, 1)
        assert spidev.max_speed_hz == SPI_SPEED_HZ == 2_400_000
        assert spidev.mode == 0
        strip.write([RED])
        spidev.xfer2.assert_called_once_with(list(ws2812_payload([RED], 1)))
        assert strip.count == 1
        assert "WS2812 LEDs opened: 1 LEDs on /dev/spidev0.1 at 2400000 Hz" in caplog.text

    def test_close_turns_off_and_closes(self, spidev):
        Ws2812Strip(1).close()
        spidev.xfer2.assert_called_once_with(list(ws2812_payload([], 1)))
        spidev.close.assert_called_once()

    def test_device_that_cannot_be_opened_is_a_driver_error(self, spidev):
        spidev.open.side_effect = FileNotFoundError("no such file")
        with pytest.raises(DriverError, match="WS2812 LEDs on /dev/spidev0.0 cannot be opened"):
            Ws2812Strip(1)

    def test_write_error_is_logged_not_raised(self, spidev, caplog):
        spidev.xfer2.side_effect = OSError("gone")
        Ws2812Strip(1).write([RED])
        assert "Cannot write to the WS2812 LEDs on /dev/spidev0.0: gone" in caplog.text

    def test_missing_package_is_a_driver_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "spidev", None)
        with pytest.raises(DriverError, match="spidev is not installed"):
            Ws2812Strip(1)

    def test_drivers_open_it_with_the_options_of_the_device_type(self, spidev):
        strip = Drivers().led_strip(LedSpec("ws2812", 1, {"spi_bus": 0, "spi_device": 0}))
        assert isinstance(strip, Ws2812Strip)
        spidev.open.assert_called_once_with(0, 0)


class TestUsbPixelRing:
    @pytest.fixture
    def usb_device(self, monkeypatch):
        core = types.ModuleType("usb.core")
        core.USBError = type("USBError", (Exception,), {})
        core.NoBackendError = type("NoBackendError", (Exception,), {})
        core.find = MagicMock()
        usb = types.ModuleType("usb")
        usb.core = core
        monkeypatch.setitem(sys.modules, "usb", usb)
        monkeypatch.setitem(sys.modules, "usb.core", core)
        return core

    def test_payload_is_red_green_blue_zero_per_led(self):
        assert pixel_ring_payload([RED], 2) == bytes([255, 0, 0, 0, 0, 0, 0, 0])

    def test_opens_sets_the_brightness_and_shows_colors(self, usb_device):
        ring = UsbPixelRing(2)
        usb_device.find.assert_called_once_with(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
        device = usb_device.find.return_value
        device.ctrl_transfer.assert_called_once_with(0x40, 0, 0x20, 0x1C, bytes([0x1F]), 1000)
        ring.write([BLUE])
        device.ctrl_transfer.assert_called_with(0x40, 0, 6, 0x1C, pixel_ring_payload([BLUE], 2), 1000)

    def test_missing_device_is_a_driver_error(self, usb_device):
        usb_device.find.return_value = None
        with pytest.raises(DriverError, match="2886:0018"):
            UsbPixelRing()

    def test_usb_error_while_writing_is_logged(self, usb_device, caplog):
        ring = UsbPixelRing(1)
        usb_device.find.return_value.ctrl_transfer.side_effect = usb_device.USBError("pipe")
        ring.write([RED])
        assert "Cannot write to the ReSpeaker USB Mic Array" in caplog.text


class TestHidDevice:
    @pytest.fixture
    def hid(self, monkeypatch):
        module = types.ModuleType("hid")
        interface = MagicMock()
        interface.read.return_value = []
        module.device = MagicMock(return_value=interface)
        module.enumerate = MagicMock(return_value=[{"path": b"/dev/hidraw0", "product_string": "Jabra SPEAK 410"}])
        monkeypatch.setitem(sys.modules, "hid", module)
        return module

    async def test_reports_are_handed_to_the_event_loop_and_writes_go_out(self, hid):
        from linux_peripherals_controller.drivers.hid import HidDevice

        reports = []
        interface = hid.device.return_value
        pending = [[3, 1, 0]]

        def read(*_args):
            time.sleep(0.005)
            return pending.pop() if pending else []

        interface.read.side_effect = read
        device = HidDevice(0x0B0E, reports.append)
        await asyncio.sleep(0.05)
        device.write([3, 1, 0])
        device.close()
        assert reports == [bytes([3, 1, 0])]
        interface.write.assert_called_once_with([3, 1, 0])
        interface.close.assert_called_once()

    async def test_missing_device_is_a_driver_error(self, hid):
        from linux_peripherals_controller.drivers.hid import HidDevice

        hid.enumerate.return_value = []
        with pytest.raises(DriverError, match="not found"):
            HidDevice(0x0B0E, print)


class TestSimulated:
    def test_led_strip_logs_changes_once(self, caplog):
        strip = SimulatedLedStrip(2, "apa102")
        with caplog.at_level(logging.DEBUG):
            strip.write([RED, BLUE])
            strip.write([RED, BLUE])
        assert caplog.text.count("Simulated LEDs: #ff0000 #0000ff") == 1
        assert strip.count == 2

    def test_hardware_logs_writes(self, caplog):
        with caplog.at_level(logging.DEBUG):
            SimulatedHardware("HID device").write([3, 1])
        assert "Simulated HID device: write 03 01" in caplog.text


class TestDrivers:
    def test_simulated_drivers_open_nothing(self):
        drivers = Drivers(simulated=True)
        assert isinstance(drivers.led_strip(LedSpec("apa102", 3)), SimulatedLedStrip)
        assert isinstance(drivers.gpio_input(17, print), SimulatedHardware)
        assert isinstance(drivers.gpio_output(5, True), SimulatedHardware)
        assert isinstance(drivers.hid(0x0B0E, print), SimulatedHardware)

    def test_unknown_led_driver_is_a_driver_error(self):
        with pytest.raises(DriverError, match="Unknown LED driver 'neon'"):
            Drivers().led_strip(LedSpec("neon", 3))

    def test_missing_gpiod_is_a_driver_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "gpiod", None)
        with pytest.raises(DriverError, match="gpiod is not installed"):
            Drivers().gpio_output(5, True)
