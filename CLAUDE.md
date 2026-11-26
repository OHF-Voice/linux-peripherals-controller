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

Done so far: CI, Docker build, docs, lint and test setup, the connection to LVA (peripheral API version 2) and the choice of the display function. The peripheral drivers (to be ported from `examples/` of LVA), buttons, device types and device configuration, and the ESPHome server for Home Assistant are added later. The specification is `docs/behavior.md`.

## Module map

| File | Responsibility |
|------|---------------|
| `__main__.py` | argparse, logging, start of the controller (`asyncio.run(Controller(...).run())`) |
| `controller.py` | `Controller`: holds the `LvaStatus`, lets the pure functions pick the display function, reports a change to `on_display_change`, ends short functions with a timer. A (re)connect or a loss starts from an empty status |
| `lva_bridge.py` | `LvaBridge`: WebSocket client of `/v2` with reconnect, hands events and requests (commands of LVA) to the controller, `send_message()` drops messages while not connected. Thin I/O only |
| `lva_protocol.py` | Wire format: `lva_url()`, `parse_message()` (an event or a request of LVA), `build_message()` (a command or an event for LVA), `COMMANDS`, `REPORTED_EVENTS` (version 2 only). An **event** reports something, a **command** asks for something, whatever the direction. `LvaMessage` is a message for LVA |
| `lva_status.py` | `LvaStatus` (immutable, with the list of `LvaTimer`) and `apply_event()`: new status plus the short signal (state `pipeline_error`, `auto_stopped` in `timer_status`, changed volume, not the first volume) |
| `button_roles.py` | `ButtonRole`, `decide_button_action()`: the commands for LVA (`LvaMessage`) and whether to report to Home Assistant, by role, press, `LvaStatus`, connection and child lock. `reason` is for the log |
| `appearance.py` | `Color` (`from_hex()`), `PatternName`, `DEFAULT_COLORS` / `DEFAULT_PATTERNS`: one entry per `DisplayFunction` |
| `device_types.py` | `DeviceType` (LEDs, buttons, sensors, offered functions, color and pattern overrides) as data, `DEVICE_TYPES`, `get_device_type()` (raises `UnknownDeviceType` with the known names). Opens no hardware |
| `device_config.py` | `load_device_config()` / `parse_device_config()`: the TOML file of one device (brightness, buttons, colors, patterns, sensors) as an immutable `DeviceConfig`. The whole file is checked, any unknown key or invalid value raises `DeviceConfigError` naming file and key |
| `device_setup.py` | `resolve_device()`: merges defaults < device type < device configuration into a `ResolvedDevice`. Refuses names the device type does not have (`DeviceConfigError`) |
| `press_detection.py` | Press types from the timing of a button: `press()`/`release()`/`tick()` take the state and the time and return the new `ButtonState` and the complete presses (`single`, `double`, `triple`, `long`, `repeat`). `next_deadline()` says when to call `tick()` |
| `hardware_mute.py` | `HardwareMute(type, muted)` with `HardwareMuteType` (`none`, `changeable`, `read_only`), `messages_for_changes()` (the events to tell LVA: everything after a connect, then only changes), `decide_mute_request()` (carry out a `hardware_muted_on/off` request only for `changeable`) and `entity_for()` (switch, binary sensor or none for Home Assistant). The device is the authority. `Controller.set_hardware_mute()` is the entry for a driver, `on_hardware_mute_request` the callback to it |
| `display.py` | `DisplayFunction`, `select_display_function()` (fixed priority order), `start_transient()` for the short functions |
| `util.py` | `get_version()` (reads `version.txt`) |

## Change checklists

**New CLI option**
1. `__main__.py` argparse. Set the default as a literal in `parser.add_argument(default=...)`.
2. `docker-entrypoint.sh` env → flag mapping.
3. `.env.example`.
4. `docs/configuration.md` and the `README.md` parameter table.

## Code structure for new logic

- Put logic that can run on its own (mapping, filtering, state decisions) into its own module under `linux_peripherals_controller/`, as plain functions that take the state they need as parameters and return the result.
- Hardware access (GPIO, SPI, USB) and I/O stay in thin driver modules, so the logic stays unit-testable with mocks.
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
