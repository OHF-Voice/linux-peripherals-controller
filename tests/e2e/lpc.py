"""Runs LPC as a subprocess for the end-to-end tests and collects its log."""

import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import List, Optional, Sequence

from .waiting import wait_until

REPO_DIR = Path(__file__).resolve().parents[2]
DEVICE_TYPE = "respeaker_2mic_v1"


def run_to_exit(args: Sequence[str], timeout: float = 30.0) -> subprocess.CompletedProcess:
    """
    Run LPC until it ends by itself, for the cases where it must refuse to start.
    :param args: Command line arguments of LPC.
    :param timeout: Seconds to wait before the process is killed and the call fails.
    :return: The finished process, its log (stdout and stderr) is ``stdout``.
    """
    return subprocess.run(
        [sys.executable, "-m", "linux_peripherals_controller", *args],
        cwd=REPO_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )


class LpcProcess:
    """
    One LPC instance with simulated hardware, its ESPHome API on a free port of 127.0.0.1, no mDNS and its own state file in a
    temporary folder. Its log is collected so tests can wait for and search log lines.
    :param lva_port: Port of the peripheral API of the (fake) LVA.
    :param extra_args: More command line arguments, they come after the defaults.
    """

    def __init__(self, lva_port: int, extra_args: Optional[Sequence[str]] = None) -> None:
        self.state_dir = Path(tempfile.mkdtemp(prefix="lpc-e2e-"))
        self._command = [
            sys.executable,
            "-m",
            "linux_peripherals_controller",
            "--debug",
            "--device-type",
            DEVICE_TYPE,
            "--lva-host",
            "127.0.0.1",
            "--lva-port",
            str(lva_port),
            "--simulate-hardware",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--enable-zeroconf",
            "0",
            "--state-file",
            str(self.state_dir / "state.json"),
            *(extra_args or []),
        ]
        self._lines: List[str] = []
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None

    def start(self) -> None:
        """Start the process."""
        # pylint: disable-next=consider-using-with
        self._process = subprocess.Popen(self._command, cwd=REPO_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()

    def stop(self) -> None:
        """End the process, with a kill if it does not follow."""
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        shutil.rmtree(self.state_dir, ignore_errors=True)

    async def interrupt(self, timeout: float = 10.0) -> int:
        """
        Send Ctrl+C and wait for the end of the process without blocking the event loop (the fake LVA runs in it and has to answer the closing of the connection).
        :param timeout: Seconds to wait before a TimeoutError is raised.
        :return: The exit status.
        """
        assert self._process is not None
        self._process.send_signal(signal.SIGINT)
        await wait_until(lambda: not self.running, timeout, "the end of LPC after Ctrl+C")
        return int(self._process.returncode)

    @property
    def running(self) -> bool:
        """True while the process runs."""
        return self._process is not None and self._process.poll() is None

    def log_mark(self) -> int:
        """Position in the log that later waits and searches use as their start, so earlier lines are ignored."""
        with self._lock:
            return len(self._lines)

    def log_since(self, mark: int) -> str:
        """
        The log after a mark.
        :param mark: Position from :meth:`log_mark`.
        """
        with self._lock:
            return "\n".join(self._lines[mark:])

    def full_log(self) -> str:
        """The whole log."""
        return self.log_since(0)

    async def wait_for_log_line(self, text: str, since: int = 0, timeout: float = 15.0) -> None:
        """
        Wait without blocking the event loop until a log line after the mark contains the text.
        :param text: Part of the log line, for example ``Connected to LVA``.
        :param since: Position from :meth:`log_mark`.
        :param timeout: Seconds to wait before a TimeoutError is raised.
        """
        await self._wait_for(lambda: text in self.log_since(since), f"log line {text!r}", since, timeout)

    async def esphome_port(self, timeout: float = 15.0) -> int:
        """
        Wait until the ESPHome API listens and return its port, as LPC logs it (``ESPHome API for Home Assistant on host:port``).
        :param timeout: Seconds to wait before a TimeoutError is raised.
        """
        pattern = re.compile(r"ESPHome API for Home Assistant on [\d.]+:(\d+)")
        await self._wait_for(lambda: pattern.search(self.full_log()) is not None, "the ESPHome API", 0, timeout)
        match = pattern.search(self.full_log())
        assert match is not None
        return int(match.group(1))

    async def wait_for_display(self, function: Optional[str], since: int = 0, timeout: float = 10.0) -> None:
        """
        Wait until the display function changes to the given one, as LPC logs it (``Display function: a -> b``).
        :param function: Name of the display function, None for the background.
        :param since: Position from :meth:`log_mark`.
        :param timeout: Seconds to wait before a TimeoutError is raised.
        """
        pattern = re.compile(rf"Display function: \S+ -> {re.escape(str(function))}$", re.MULTILINE)
        await self._wait_for(lambda: pattern.search(self.log_since(since)) is not None, f"display function {function}", since, timeout)

    def displays_since(self, since: int) -> List[str]:
        """
        The display functions LPC switched to after the mark, in order.
        :param since: Position from :meth:`log_mark`.
        """
        return re.findall(r"Display function: \S+ -> (\S+)$", self.log_since(since), re.MULTILINE)

    def warning_count(self, text: str) -> int:
        """
        How often LPC logged a warning that contains the text.
        :param text: Part of the warning.
        """
        return sum(1 for line in self.full_log().splitlines() if line.startswith("WARNING") and text in line)

    async def _wait_for(self, condition, description: str, since: int, timeout: float) -> None:
        try:
            await wait_until(lambda: condition() or not self.running, timeout, description)
        except TimeoutError as error:
            raise TimeoutError(f"{error}, log since the mark:\n{self.log_since(since)}") from error
        if not condition():
            raise RuntimeError(f"LPC ended while waiting for {description}, log since the mark:\n{self.log_since(since)}")

    def _read(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            with self._lock:
                self._lines.append(line.rstrip("\n"))
