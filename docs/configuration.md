# Configuration

LPC is configured with command line options. In Docker, set the environment variable of an option in `.env` (see `.env.example`).

| Option | Environment variable | Default | Description |
|--------|----------------------|---------|-------------|
| `--device-type` | `DEVICE_TYPE` | | Type of the device. Required: without it, or with an unknown name, LPC logs the known device types and exits. See [Device types](#device-types). |
| `--device-config` | `DEVICE_CONFIG` | | TOML file with the settings of this device, see [Device configuration](#device-configuration). Without it the device type is used as it is. In Docker the file is read from the `config` folder next to `docker-compose.yml` (`DEVICE_CONFIG=/config/device.toml`). |
| `--lva-host` | `LVA_HOST` | `localhost` | Host of the LVA peripheral WebSocket API. |
| `--lva-port` | `LVA_PORT` | `6055` | Port of the LVA peripheral WebSocket API. |
| `--debug` | `ENABLE_DEBUG` | off | Print DEBUG messages to console. In Docker set `ENABLE_DEBUG="1"`. |

Docker Compose only:

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `LPC_IMAGE` | `ghcr.io/ohf-voice/linux-peripherals-controller` | Docker image to use. |
| `LPC_IMAGE_TAG` | `latest` (`nightly` in the dev file) | Tag of the Docker image. |

## Device types

| Device type | Device |
|-------------|--------|
| `respeaker_2mic_v1` | ReSpeaker 2-Mic Pi HAT with WM8960 codec: 3 APA102 LEDs on SPI0 and one button on GPIO 17 (default role `action`). |

More device types are added with their drivers. The ReSpeaker 2mic HAT v2.0 is not described yet.

## Device configuration

The device configuration is a TOML file with the settings of one device. Everything in it is optional, and it only changes what you write. The most specific layer wins: the built-in defaults, then the device type, then this file.

LPC reads the whole file at startup. A key that is not known, or a value that is not valid, is an error: LPC logs the file and the key and exits, it never starts with a part of the file.

```toml
# Brightness of the display functions, 0 to 1 (default 1)
brightness = 0.5

# Settings of a button of the device type, by its name
[buttons.button]
role = "mute"          # action, volume_up, volume_down, mute or user
report_to_ha = true    # also report every press to Home Assistant (default false)
pin = 17               # GPIO pin (BCM), when it differs from the device type

# Color of a display function, #rrggbb
[colors]
listening = "#0000ff"

# Pattern of a display function: solid, pulse, spin, progress or blink
[patterns]
listening = "pulse"

# Settings of a sensor of the device type, by its name
[sensors.temperature]
interval = 60          # seconds between two readings
```

- `[buttons.<name>]` and `[sensors.<name>]` must name a button or sensor that the device type has, and `[colors]` and `[patterns]` must name a display function that the device type offers. Otherwise LPC exits.
- The display functions are `no_connection`, `timer_ringing`, `wake_word`, `listening`, `thinking`, `tts`, `announce`, `pipeline_error`, `timer_timeout`, `volume`, `muted` and `timer_active`.
- The predefined colors and patterns:

| Display function | Color | Pattern |
|------------------|-------|---------|
| `no_connection` | `#ff0000` | `pulse` |
| `timer_ringing` | `#0000ff` | `blink` |
| `wake_word` | `#ffffff` | `blink` |
| `listening` | `#0080ff` | `spin` |
| `thinking` | `#ffc800` | `pulse` |
| `tts` | `#00ff00` | `pulse` |
| `announce` | `#00ff80` | `pulse` |
| `pipeline_error` | `#ff0000` | `blink` |
| `timer_timeout` | `#ff8000` | `blink` |
| `volume` | `#ffffff` | `progress` |
| `muted` | `#ff0000` | `solid` |
| `timer_active` | `#00ffff` | `progress` |
