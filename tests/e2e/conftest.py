"""Fixtures of the end-to-end tests.

Every test gets its own fake LVA and its own LPC process, so tests do not influence each other. See tests/e2e/README.md.
"""

import os
import socket
from pathlib import Path
from typing import AsyncIterator, Callable, Iterator, Sequence

import pytest

from .fake_lva import FakeLva
from .lpc import LpcProcess


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    """Add the docstring of a test to the JUnit XML as its description, which the job summary shows next to the test."""
    test_function = getattr(item, "function", None)
    description = (test_function.__doc__ or "").strip() if test_function is not None else ""
    if description:
        item.user_properties.append(("description", description))


@pytest.fixture
async def fake_lva() -> AsyncIterator[FakeLva]:
    """A fake LVA that is listening."""
    server = FakeLva(_free_port())
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
async def stopped_fake_lva() -> AsyncIterator[FakeLva]:
    """A fake LVA that is not listening yet, for the tests where LVA starts after LPC."""
    server = FakeLva(_free_port())
    yield server
    await server.stop()


@pytest.fixture
def start_lpc(request: pytest.FixtureRequest) -> Iterator[Callable[..., LpcProcess]]:
    """Start LPC against a fake LVA. The process ends with the test and its log is stored (``E2E_LOG_DIR``) or printed."""
    started: list[LpcProcess] = []

    def start(server: FakeLva, extra_args: Sequence[str] = ()) -> LpcProcess:
        process = LpcProcess(server.port, extra_args)
        process.start()
        started.append(process)
        return process

    yield start
    for index, process in enumerate(started):
        process.stop()
        _store_log(process, f"{request.node.name}-{index}.log")


@pytest.fixture
async def lpc(fake_lva: FakeLva, start_lpc: Callable[..., LpcProcess]) -> LpcProcess:
    """LPC connected to the fake LVA and showing the background, which is what an idle LVA that is connected to Home Assistant gives."""
    process = start_lpc(fake_lva)
    await fake_lva.wait_for_connection()
    await process.wait_for_display(None)
    return process


def _store_log(process: LpcProcess, file_name: str) -> None:
    log_dir = os.environ.get("E2E_LOG_DIR")
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        (Path(log_dir) / file_name).write_text(process.full_log(), encoding="utf-8")
    else:
        print(f"\n----- {file_name} -----\n" + process.full_log())


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
