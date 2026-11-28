# Configuration

LPC is configured with command line options. In Docker, set the environment variable of an option in `.env` (see `.env.example`).

| Option | Environment variable | Default | Description |
|--------|----------------------|---------|-------------|
| `--device-type` | `DEVICE_TYPE` | | Type of the device. Required: without it, or with an unknown name, LPC logs the known device types and exits. See [Device types](#device-types). |
| `--device-config` | `DEVICE_CONFIG` | | TOML file with the settings of this device, see [Device configuration](#device-configuration). Without it the device type is used as it is. In Docker the file is read from the `config` folder next to `docker-compose.yml` (`DEVICE_CONFIG=/config/device.toml`). |
| `--lva-host` | `LVA_HOST` | `localhost` | Host of the LVA peripheral WebSocket API. |
| `--lva-port` | `LVA_PORT` | `6055` | Port of the LVA peripheral WebSocket API. |
| `--host` | `HOST` | `0.0.0.0` | Address the ESPHome API for Home Assistant listens on. `0.0.0.0` is every interface. |
| `--port` | `PORT` | `6054` | Port of the ESPHome API for Home Assistant. `6054`, so it does not clash with LVA on `6053`. `0` takes any free port (it is logged). |
| `--name` | `CLIENT_NAME` | `lpc-<MAC>` | Device name in Home Assistant and over mDNS. The default is `lpc-` and the MAC address of the machine without colons. |
| `--enable-zeroconf` | `ENABLE_ZEROCONF` | `1` | `1` announces the ESPHome API over mDNS, so Home Assistant discovers LPC. `0` announces nothing: add LPC by hand in the ESPHome integration with the IP address and the port. |
| `--enable-encryption` | `ENABLE_ENCRYPTION` | off | Encrypts the ESPHome API with a key, as ESPHome devices with an API encryption key do. Home Assistant asks for the key when adding LPC. In Docker set `ENABLE_ENCRYPTION="1"`. |
| `--encryption-key-file` | `ENCRYPTION_KEY_FILE` | `encryption.key` next to the state file | File with the encryption key (32 bytes, base64). Only used with `--enable-encryption`. A missing file is created with a new random key (readable only by its user) and its path is logged. LPC exits if the file cannot be read or holds no valid key. |
| `--state-file` | `STATE_FILE` | `state.json` (`/data/state.json` in Docker) | JSON file that keeps the child lock and the light across restarts. A missing file is the first start. A file that cannot be read gives the defaults and a warning. |
| `--simulate-hardware` | `SIMULATE_HARDWARE` | off | Opens no hardware: the LEDs are only logged at debug level and no button can be pressed. For development and tests. In Docker set `SIMULATE_HARDWARE="1"`. |
| `--debug` | `ENABLE_DEBUG` | off | Print DEBUG messages to console. In Docker set `ENABLE_DEBUG="1"`. |

Docker Compose only:

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `LPC_IMAGE` | `ghcr.io/ohf-voice/linux-peripherals-controller` | Docker image to use. |
| `LPC_IMAGE_TAG` | `latest` (`nightly` in the dev file) | Tag of the Docker image. |

## Device types

Every device type is one file in `linux_peripherals_controller/devices/`, named like the device type. It describes the hardware and runs it, and it can do things of its own (for example its own LED states or what a button does).

| Device type | Device | LEDs | Buttons (default role) |
|-------------|--------|------|------------------------|
| `respeaker_2mic_v1` | ReSpeaker 2-Mic Pi HAT v1 (WM8960 codec) | 3 APA102 on SPI0 (`/dev/spidev0.0`) | `button` on GPIO 17 (`action`) |
| `respeaker_2mic_v2` | ReSpeaker 2-Mic Pi HAT v2.0 (TLV320AIC3x codec) | 3 APA102 on SPI0 (`/dev/spidev0.0`) | `button` on GPIO 17 (`action`) |
| `respeaker_4mic` | ReSpeaker 4-Mic Array HAT (AC108 codec) | 12 APA102 on SPI0 (`/dev/spidev0.1`), powered by GPIO 5 | none |
| `respeaker_usb_mic_array` | ReSpeaker USB Mic Array v2.0 (USB `2886:0018`) | 12, set over USB | none |
| `jabra_speak_410` | Jabra Speak 410 (USB, vendor `0b0e`) | fixed states over HID: green, red, flashing, partly flashing | `call` (`action`), `mute` (`mute`), `volume_up`, `volume_down` |
| `satellite1` | Satellite1 HAT (FutureProofHomes), through `satellite1d` | 24, set through the daemon | `action` (`action`), `volume_up`, `volume_down` |

The Jabra Speak 410 has no colored LEDs, so `[colors]`, `[patterns]` and `brightness` do not change it, and there is no `LED` light in Home Assistant. It shows: listening green, wake word, thinking and a ringing timer flashing, a reply or an announcement partly flashing, muted red, an error and a lost connection blinking red, everything else off.

A button without a GPIO pin of its own (the Jabra, the Satellite1) is read by its device file, so `pin` in the device configuration does not apply to it.

### Satellite1 HAT

The Satellite1 HAT is driven through `satellite1d`, the daemon of the [Satellite1-RPi-SDK](https://github.com/FutureProofHomes/Satellite1-RPi-SDK). The daemon owns the hardware, LPC talks to it over its socket `/run/satellite1/satellite1d.sock`. The SDK has to be installed and the daemon running.

- In `/etc/satellite1.conf` of the daemon, the LED ring must be enabled (`[led_ring] enabled = true`), otherwise LPC exits. Turn off `[workflows.volume-buttons]`, or a volume button changes the volume twice (in the daemon and in LVA). Keep `[lva]` of the daemon disabled, LPC is the connection to LVA. The LED workflows of the daemon (`[workflows.mute-led]`, `[workflows.volume]`, `[workflows.jack-led]`) draw over what LPC shows, turn them off if LPC alone shall drive the LEDs.
- In Docker, the socket folder is passed to the container (`/run/satellite1:/run/satellite1` in `docker-compose.yml`).
- The daemon reports only that a button was pressed, not how long: single, double and triple presses work, long presses and the repeat of a held volume button do not.
- Sensors (`[sensors.<name>] interval` changes how often they are read):

| Sensor | Kind | Read | In Home Assistant |
|--------|------|------|-------------------|
| `temperature` | number, °C | every 60 s | sensor |
| `humidity` | number, % | every 60 s | sensor |
| `illuminance` | number, lx | every 60 s | sensor |
| `line_out_jack` | on/off | at startup, then when the daemon reports a change | binary sensor (plug) |
| `usb_c_voltage` | number, V | every 60 s | sensor, Diagnostic. Unknown without a USB-C power contract. |
| `usb_c_current` | number, A | every 60 s | sensor, Diagnostic. Unknown without a USB-C power contract. |
| `xmos_firmware` | text | at startup | text sensor, Diagnostic |

- Control `amplifier_level`: the gain of the speaker amplifier, 0 to 20, a number entity in Home Assistant. Read at startup, kept by the daemon.
- The microphone mute switch of the HAT is its hardware mute, of the type `read_only`: a `Hardware Mute` binary sensor in Home Assistant, and LVA is told about it (see [behavior.md](behavior.md#hardware-mute)).

## Device configuration

The device configuration is a TOML file with the settings of one device. Everything in it is optional, and it only changes what you write. The most specific layer wins: the built-in defaults, then the device type, then this file.

LPC reads the whole file at startup. A key that is not known, or a value that is not valid, is an error: LPC logs the file and the key and exits, it never starts with a part of the file.

```toml
# Brightness of the display functions, 0 to 1 (default 1)
brightness = 0.5

# Settings of a button of the device type, by its name.
# Every press of every button is reported to Home Assistant, whatever the role.
[buttons.button]
role = "mute"          # action, volume_up, volume_down, mute or user
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
