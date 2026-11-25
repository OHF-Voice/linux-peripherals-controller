"""Entry point of the Linux Peripherals Controller."""

import argparse
import logging
from typing import Optional, Sequence

from .util import get_version

_LOGGER = logging.getLogger(__name__)


def run(argv: Optional[Sequence[str]] = None) -> None:
    """
    Parse the command line and start the controller.
    :param argv: Command line arguments, ``sys.argv[1:]`` when None.
    """
    parser = argparse.ArgumentParser(prog="linux-peripherals-controller")
    parser.add_argument("--lva-host", default="localhost", help="Host of the Linux-Voice-Assistant peripheral WebSocket API (default: %(default)s)")
    parser.add_argument("--lva-port", type=int, default=6055, help="Port of the Linux-Voice-Assistant peripheral WebSocket API (default: %(default)s)")
    parser.add_argument("--debug", action="store_true", help="Print DEBUG messages to console")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.info("Version: %s", get_version())
    _LOGGER.info("Peripheral API of LVA: ws://%s:%s", args.lva_host, args.lva_port)
    _LOGGER.warning("No peripheral drivers are implemented yet")


if __name__ == "__main__":
    run()
