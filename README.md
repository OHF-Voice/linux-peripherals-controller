# Linux Peripheral Controller

[![CI](https://github.com/OHF-Voice/linux-peripherals-controller/actions/workflows/docker-build-release.yml/badge.svg)](https://github.com/OHF-Voice/linux-peripherals-controller/actions/workflows/docker-build-release.yml) [![GitHub License](https://img.shields.io/github/license/OHF-Voice/linux-peripherals-controller)](https://github.com/OHF-Voice/linux-peripherals-controller/blob/main/LICENSE.md)

One service for the hardware peripherals (LED rings, buttons, HAT boards, USB devices) of [Linux-Voice-Assistant](https://github.com/OHF-Voice/linux-voice-assistant) (LVA).

It connects to the [peripheral WebSocket API](https://github.com/OHF-Voice/linux-voice-assistant/blob/main/docs/peripheral_api/readme.md) of LVA and runs as a Docker container next to it. It is meant to replace the separate peripheral scripts in the `examples/` folder of LVA.

> [!NOTE]
> LPC is under construction. The drivers and device types below are written from the examples of LVA and the vendor sources, but were not tried on the hardware yet.

![Linux Peripheral Controller](docs/images/banner.svg)

[![A project from the Open Home Foundation](https://www.openhomefoundation.org/badges/ohf-project.png)](https://www.openhomefoundation.org/)

## Supported devices

| Device type | Device |
|-------------|--------|
| `respeaker_2mic_v1` | ReSpeaker 2-Mic Pi HAT v1 (3 LEDs, 1 button) |
| `respeaker_2mic_v2` | ReSpeaker 2-Mic Pi HAT v2.0 (3 LEDs, 1 button) |
| `respeaker_4mic` | ReSpeaker 4-Mic Array HAT (12 LEDs) |
| `respeaker_usb_mic_array` | ReSpeaker USB Mic Array v2.0 (12 LEDs) |
| `jabra_speak_410` | Jabra Speak 410 (4 buttons, fixed LED states) |

Details in [Configuration](docs/configuration.md#device-types).

## Planned peripherals

- ReSpeaker lite (USB)

## Not planned

- Satellite1 HAT Board has its own controller for that.

## Installation

See [Installation](docs/install.md).

## Parameter overview

There is an environment variable for each parameter, see [Configuration](docs/configuration.md).

| Parameter | Environment variable | Default | Description |
|-----------|----------------------|---------|-------------|
| `--device-type` | `DEVICE_TYPE` | | Type of the device, required (for example `respeaker_2mic_v1`) |
| `--device-config` | `DEVICE_CONFIG` | | TOML file with the settings of this device |
| `--lva-host` | `LVA_HOST` | `localhost` | Host of the LVA peripheral WebSocket API |
| `--lva-port` | `LVA_PORT` | `6055` | Port of the LVA peripheral WebSocket API |
| `--host` | `HOST` | `0.0.0.0` | Address the ESPHome API for Home Assistant listens on |
| `--port` | `PORT` | `6054` | Port of the ESPHome API for Home Assistant |
| `--name` | `CLIENT_NAME` | `lpc-<MAC>` | Device name in Home Assistant and over mDNS |
| `--enable-zeroconf` | `ENABLE_ZEROCONF` | `1` | Announce the ESPHome API over mDNS |
| `--enable-encryption` | `ENABLE_ENCRYPTION=1` | off | Encrypt the ESPHome API with a key |
| `--encryption-key-file` | `ENCRYPTION_KEY_FILE` | `encryption.key` next to the state file | File with the encryption key |
| `--state-file` | `STATE_FILE` | `state.json` (`/data/state.json` in Docker) | Keeps the child lock and the light across restarts |
| `--simulate-hardware` | `SIMULATE_HARDWARE=1` | off | Open no hardware, only log the LEDs |
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
