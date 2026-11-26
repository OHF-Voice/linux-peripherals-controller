# Linux-Peripherals-Controller

[![CI](https://github.com/OHF-Voice/linux-peripherals-controller/actions/workflows/docker-build-release.yml/badge.svg)](https://github.com/OHF-Voice/linux-peripherals-controller/actions/workflows/docker-build-release.yml) [![GitHub License](https://img.shields.io/github/license/OHF-Voice/linux-peripherals-controller)](https://github.com/OHF-Voice/linux-peripherals-controller/blob/main/LICENSE.md)

One service for the hardware peripherals (LED rings, buttons, HAT boards, USB devices) of [Linux-Voice-Assistant](https://github.com/OHF-Voice/linux-voice-assistant) (LVA).

It connects to the [peripheral WebSocket API](https://github.com/OHF-Voice/linux-voice-assistant/blob/main/docs/peripheral_api/readme.md) of LVA and runs as a Docker container next to it. It is meant to replace the separate peripheral scripts in the `examples/` folder of LVA.

> [!NOTE]
> LPC is under construction. So far it connects to LVA and works out what the LEDs would show. The peripheral drivers are added later.

![Linux Peripherals Controller](docs/images/banner.svg)

[![A project from the Open Home Foundation](https://www.openhomefoundation.org/badges/ohf-project.png)](https://www.openhomefoundation.org/)

## Planned peripherals

- ReSpeaker 2mic HAT v1.1
- ReSpeaker 2mic HAT v2.0
- ReSpeaker 4mic HAT
- ReSpeaker lite (USB)
- Jabra Speak 410

## Not planned

- Satellite1 HAT Board has its own controller for that.

## Installation

See [Installation](docs/install.md).

## Parameter overview

There is an environment variable for each parameter, see [Configuration](docs/configuration.md).

| Parameter | Environment variable | Default | Description |
|-----------|----------------------|---------|-------------|
| `--lva-host` | `LVA_HOST` | `localhost` | Host of the LVA peripheral WebSocket API |
| `--lva-port` | `LVA_PORT` | `6055` | Port of the LVA peripheral WebSocket API |
| `--debug` | `ENABLE_DEBUG=1` | off | Print DEBUG messages to console |

## Development

```sh
./script/setup --dev      # create .venv and install the dev dependencies
./script/lint_black --auto && ./script/lint_isort --auto
./script/lint             # black, isort, flake8, pylint, mypy
./script/tests            # unit tests
```

Pull requests target `main`. See [CONTRIBUTING](.github/CONTRIBUTING.md) and the [AI policy](.github/AI_POLICY.md).

## License

[Apache License 2.0](LICENSE.md)
