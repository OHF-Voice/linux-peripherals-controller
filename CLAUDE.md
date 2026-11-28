@AGENTS.md

# AI Working Guide for Linux Peripheral Controller

Dense codebase map for AI agents. `AGENTS.md` (imported above) holds the rules; this file holds the knowledge needed to change code without re-reading every module. When this file and the code disagree, the code wins. Fix this file in the same change.

## Fast commands

| Task | Command |
|------|---------|
| Install dependencies | `./script/setup` |
| Install dev dependencies (linting, testing tools) | `./script/setup --dev` |
| All unit tests | `./script/tests` |
| End-to-end tests (real LPC process, fake LVA, no hardware, see `tests/e2e/README.md`) | `./script/e2e` (~35 s) |
| Tests in a specific path | `./script/tests <path>` |
| Tests matching a pattern | `./script/tests -k <pattern>` |
| One file / one test | `.venv/bin/python -m pytest tests/unit/test_main.py -k version -q` |
| All lint (black, isort, flake8, mypy, pylint) | `./script/lint` |
| Auto-fix formatting (black, isort) | `./script/lint_black --auto && ./script/lint_isort --auto` |
| Run app | `.venv/bin/python -m linux_peripherals_controller` |
| Show CLI help | `.venv/bin/python -m linux_peripherals_controller --help` |

Only run `./script/setup --dev` if `.venv` is missing, because the script deletes and recreates `.venv`.

## State of the project

Done: CI, Docker build, docs, lint and test setup, the connection to LVA (peripheral API version 2), the choice of the display function, device types and device configuration, the drivers, a device file per device type, buttons, the LED patterns, the ESPHome server for Home Assistant with mDNS and encryption, and the state file. None of it was tried on the hardware. The specification is `docs/behavior.md`.

## Module map

| File | Responsibility |
|------|---------------|
| `__main__.py` | argparse, logging, encryption key, then `_serve()`: create the device (`devices.create_device`), open it (`DeviceRunner.open`, `DriverError` exits), start the ESPHome server and mDNS, run the controller and the sensors |
| `device_runner.py` | `DeviceRunner`: the hub. Display function and LVA status to the LEDs (through `LedOutput`), button edges to presses (`ButtonInput`) to `device.decide_press()` to LVA (`Controller.send_messages`) and Home Assistant (`ButtonEventEntity.press`), light and child lock from Home Assistant (stored with `save`), hardware mute between device, LVA and Home Assistant, sensors. `entities()` creates the entities in a fixed order (light, buttons, child lock, hardware mute, sensors, controls). `read_values()` reads the controls once and the sensors at their interval |
| `devices/` | One file per device type, named like it: `DEVICE_TYPE` and `class Device(BaseDevice)`. `__init__.py` is the registry (`DEVICE_FILES`, `DEVICE_TYPES`, `get_device_type()`, `known_device_types()`, `create_device()`). `base.py`: `BaseDevice` opens the LEDs of the type and a GPIO button per pin, renders the patterns, decides a press by role. `open()` takes `DeviceCallbacks` (button, hardware mute, sensor). A device file overrides `open`/`open_leds`/`close`, `draw`/`is_animated`, `decide_press`, `detection_for`, `hardware_mute`/`switch_hardware_mute`, `read_sensor`, `read_control`/`set_control`, and reports with `report_button()`, `report_hardware_mute()`, `report_sensor()`. `jabra_speak_410.py` has pure `decode_report()` and `led_report()`. `satellite1.py` opens its LEDs, buttons and sensors through the daemon (`open_leds()`) |
| `drivers/` | Thin hardware layers, hardware packages imported only when opened (extra `hardware` in `pyproject.toml`). `Drivers` (in `__init__.py`) opens them, or simulated ones (`simulated.py`) with `--simulate-hardware`. `apa102.py` (`apa102_frame()`, SPI), `usb_pixel_ring.py` (`pixel_ring_payload()`, pyusb), `gpio.py` (gpiod, edges via `loop.add_reader`, chip with a `pinctrl-` label), `hid.py` (hidapi, all interfaces, one reader thread each, reports handed to the loop), `satellite1.py` (JSON lines over the Unix socket of `satellite1d`, the daemon of the Satellite1-RPi-SDK, which owns that hardware; requests blocking with a lock, events in a loop task; GPL SDK, so only its protocol is spoken, no code taken). Every failure to open is a `DriverError` |
| `esphome/` | `api_server.py` (frames and Noise encryption, taken from LVA), `entities.py` (`LightEntity`, `ButtonEventEntity`, `SwitchEntity`, `BinarySensorEntity`, `SensorEntity`, `TextSensorEntity`, `NumberEntity`; key = place in the list; the sensor entities hold their `value`, None is unknown), `server.py` (`HomeAssistantServer`: device info, list, states, commands answered to every client), `discovery.py` (mDNS, `local_ip_address()`) |
| `animation.py` | `DisplayState` (function, amount, light, start), `display_amount()`, `scene_for()`, `render()` (one color per LED for a time), `is_animated()` |
| `led_output.py` | `LedOutput`: draws on change and every frame (`FRAME_INTERVAL_SECONDS`) while animated |
| `button_input.py` | `ButtonInput`: state per button for `press_detection`, ticks with `call_later` at `next_deadline()` |
| `light.py` | `LightState` (the light of Home Assistant, off and light blue by default), `apply_light_command()` |
| `state_store.py` | `StoredState` (child lock, light), `load_state()` (defaults on any problem), `save_state()` (atomic) |
| `controller.py` | `Controller`: holds the `LvaStatus`, lets the pure functions pick the display function, reports a change to `on_display_change` and every status to `on_status_change`, ends short functions with a timer, sends button commands (`send_messages`). A (re)connect or a loss starts from an empty status |
| `lva_bridge.py` | `LvaBridge`: WebSocket client of `/v2` with reconnect, hands events and requests (commands of LVA) to the controller, `send_message()` drops messages while not connected. Thin I/O only |
| `lva_protocol.py` | Wire format: `lva_url()`, `parse_message()` (an event or a request of LVA), `build_message()` (a command or an event for LVA), `COMMANDS`, `REPORTED_EVENTS` (version 2 only). An **event** reports something, a **command** asks for something, whatever the direction. `LvaMessage` is a message for LVA |
| `lva_status.py` | `LvaStatus` (immutable, with the list of `LvaTimer`) and `apply_event()`: new status plus the short signal (state `pipeline_error`, `auto_stopped` in `timer_status`, changed volume, not the first volume) |
| `button_roles.py` | `ButtonRole`, `decide_button_action()`: the commands for LVA (`LvaMessage`) and whether to report to Home Assistant, by role, press, `LvaStatus`, connection and child lock. `reason` is for the log. `detection_for_role()`: the volume roles repeat |
| `appearance.py` | `Color` (`from_hex()`), `PatternName`, `DEFAULT_COLORS` / `DEFAULT_PATTERNS`: one entry per `DisplayFunction` |
| `device_types.py` | `DeviceType` (LEDs, buttons, sensors, controls, offered functions, color and pattern overrides) as data, `SensorSpec` (with `SensorKind` number/text/binary, `diagnostic`, `interval` None = read once), `ControlSpec` (a number Home Assistant sets), `UnknownDeviceType`. The device types themselves are in `devices/`. Opens no hardware |
| `device_config.py` | `load_device_config()` / `parse_device_config()`: the TOML file of one device (brightness, buttons, colors, patterns, sensors) as an immutable `DeviceConfig`. The whole file is checked, any unknown key or invalid value raises `DeviceConfigError` naming file and key |
| `device_setup.py` | `resolve_device()`: merges defaults < device type < device configuration into a `ResolvedDevice`. Refuses names the device type does not have (`DeviceConfigError`) |
| `press_detection.py` | Press types from the timing of a button: `press()`/`release()`/`tick()` take the state and the time and return the new `ButtonState` and the complete presses (`single`, `double`, `triple`, `long`, `repeat`). `next_deadline()` says when to call `tick()` |
| `hardware_mute.py` | `HardwareMute(type, muted)` with `HardwareMuteType` (`none`, `changeable`, `read_only`), `messages_for_changes()` (the events to tell LVA: everything after a connect, then only changes), `decide_mute_request()` (carry out a `hardware_muted_on/off` request only for `changeable`) and `entity_for()` (switch, binary sensor or none for Home Assistant). The device is the authority. `Controller.set_hardware_mute()` is the entry for a driver, `on_hardware_mute_request` the callback to it |
| `display.py` | `DisplayFunction`, `select_display_function()` (fixed priority order), `start_transient()` for the short functions |
| `util.py` | `get_version()` (reads `version.txt`), `get_esphome_version()` (version of aioesphomeapi) |

## Change checklists

**New CLI option**
1. `__main__.py` argparse. Set the default as a literal in `parser.add_argument(default=...)`.
2. `docker-entrypoint.sh` env → flag mapping.
3. `.env.example`.
4. `docs/configuration.md` and the `README.md` parameter table.

## Code structure for new logic

- Put logic that can run on its own (mapping, filtering, state decisions) into its own module under `linux_peripherals_controller/`, as plain functions that take the state they need as parameters and return the result.
- Hardware access (GPIO, SPI, USB) and I/O stay in thin driver modules in `drivers/`, so the logic stays unit-testable with mocks. What is special about one device goes into its device file in `devices/`, not into the shared code.
- Add `tests/unit/test_<module>.py` for every new module.
- Log decisions at debug level with the value and the threshold. `%`-style arguments, never f-strings.
- Do not refactor unrelated code in the same change.

## Tests

- One test file per module in `tests/unit/`.
- `tests/e2e/`: a real LPC process against a fake LVA (`fake_lva.py`, the server side of the peripheral API v2) that observes the debug log (`Display function: a -> b`) and the messages LPC sends. Every test gets its own LPC and its own fake LVA. Not part of `./script/tests`, CI runs it in `.github/workflows/e2e-tests.yml`. Wait for a log line with a fresh `log_mark()` when the same line can appear twice. New behavior that is visible over the bridge (a new display function, a new message to LVA) gets an end-to-end test next to its unit test.
- `asyncio_mode = "auto"`, so `async def test_*` works without a decorator.
- Pylint for tests uses `tests/.pylintrc`.

## Gotchas

- `mypy` runs non-strict with `python_version = 3.13` (`mypy.ini`).
- The hardware packages (`gpiod`, `hidapi`, `pyusb`, `spidev`) are the extra `hardware`: the Docker image installs them, `./script/setup --dev` does not. Unit tests replace them with fake modules in `sys.modules`. `lgpio`/`gpiozero` are not used, because `lgpio` does not build on x86 and `gpiod` works on the Raspberry Pi 3, 4 and 5 alike.
- `--simulate-hardware` runs without the device. A real device type without its hardware exits at startup (`DriverError`).
- The Docker image is **not** built locally by compose. `docker-compose.yml` pulls `ghcr.io/ohf-voice/linux-peripherals-controller:${LPC_IMAGE_TAG:-latest}` (dev file: `-pr` image, tag `nightly`).
- `version.txt` and `version_githash.txt` are git-ignored and written by the Docker build workflows. Locally `get_version()` returns `unknown`.

## Documentation map

| Doc | Contents |
|-----|----------|
| `README.md` | Features, requirements, installation, parameter table, dev setup |
| `docs/install.md` | Docker Compose installation |
| `docs/configuration.md` | CLI options and environment variables |
| `docs/behavior.md` | User-visible behavior. Binding for code changes, see AGENTS.md |
| `tests/e2e/README.md` | End-to-end test setup: fake LVA, LPC process, what is checked, CI |
| `.github/workflow.md` | Docker build workflows (release/nightly/PR), breaking change log |

## Contribution constraints

- **Never commit or push directly to `main`**, whatever the instruction says (even "commit and push to main"). Every change, documentation only included, goes on its own branch and into a PR against `main`. If asked to push to `main`, do not do it: say so and offer a branch and a PR instead.
- PR titles describe the change functionally, with **no** `feat:`/`fix:` prefixes. Labels come from the ticked box in `.github/PULL_REQUEST_TEMPLATE.md`.
- `.github/AI_POLICY.md`: no autonomous contributions, a human must review everything, and nothing is posted to GitHub without explicit consent.
- The PR template checkbox "The code change is tested and works locally." may only be ticked by a human, by hand. AI agents never tick it, whatever tests they ran, and leave it unchecked in every PR description they write.
- `CHANGELOG.md` is generated from release notes. Don't edit it by hand.
- `breaking_change.md` is written by workflows (`.github/scripts/breaking_change.py`) from the "Breaking change migration" section of `breaking-change` PRs. Don't edit it by hand. Details: `.github/workflow.md`.
