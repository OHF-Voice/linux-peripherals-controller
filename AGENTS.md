# Project Context for AI Agents

## Behaviour

- NEVER automatically reply on Github (PRs or Discussions) without explicit consent from the developer.
- Always run `./script/lint` and `./script/tests` after code changes to ensure standards are met.

- `docs/behavior.md` is the source of truth for user-visible behavior. Follow it when changing code. If the code contradicts it, ask which one is wrong instead of silently picking one.
- When a change alters user-visible behavior, update `docs/behavior.md` in the same change and list every behavior change separately under "Behavior changes" in the PR description (see `.github/PULL_REQUEST_TEMPLATE.md`).

## Project Overview

LPC always means **Linux Peripherals Controller**, this project. LVA means **Linux Voice Assistant** ([OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant)).

**Linux Peripherals Controller (LPC)** - One service that runs the peripheral drivers (LED rings, buttons, HAT boards, USB devices) for LVA. It connects to the peripheral WebSocket API of LVA and is built and operated as a Docker container.

### Purpose
- Replaces the separate peripheral scripts in `examples/` of LVA (Satellite1 HAT, ReSpeaker 2mic/4mic HAT, ReSpeaker USB Mic Array, Jabra Speak 410) with one service
- Talks to LVA only through its peripheral WebSocket API, see the LVA repository: `docs/peripheral_api/readme.md`
- Runs on x64/ARM64/ARMv7 Linux hardware, typically on the same Raspberry Pi as LVA

### Architecture
- **Protocol**: Peripheral WebSocket API of LVA (JSON events and commands, port 6055) via `websockets`
- **Deployment**: Docker image `ghcr.io/ohf-voice/linux-peripherals-controller`, `network_mode: host`

### Key Components
- `linux_peripherals_controller/__main__.py` - Main entry point with CLI argument parsing
- `linux_peripherals_controller/util.py` - Small helpers (`get_version()`)

The peripheral drivers are not implemented yet and will be added as separate modules.

## Development Commands

### Setup
```bash
./script/setup --dev    # Install dev dependencies in virtual environment
```

### Linting
```bash
./script/lint           # Run all linting checks
./script/lint_black     # Black formatting check (add --auto to fix)
./script/lint_isort     # isort import sorting check (add --auto to fix)
./script/lint_flake8    # flake8 style checks
./script/lint_mypy      # mypy type checking
./script/lint_pylint    # pylint code quality checks
```

### Testing
```bash
./script/tests          # Run pytest unit tests
```

## Code Quality Standards

- **Python**: 3.13
- **Formatting**: Black (200 char line length, py313 target)
- **Import Sorting**: isort with black profile
- **Type Checking**: mypy (non-strict, configured in `mypy.ini`, targets Python 3.13)
- **Linting**: pylint (many checks disabled in pyproject.toml for practical reasons)

## Testing Strategy

- Unit tests in `tests/unit/` using pytest with asyncio mode
- Mocks used heavily for hardware dependencies (GPIO, SPI, USB, WebSocket)

## CI/CD

- GitHub Actions for lint checks and unit tests
- Tests run on Python 3.13
- Lint runs on Python 3.13
- Docker images are built by GitHub Actions, see `.github/workflow.md`

## Branching and PRs

- All PRs target `main` (primary development branch). `stable` is for production releases.
- PRs labeled `bugfix` + `backport-to-stable` are automatically backported to `stable` — use only for bugs also present in `stable`.

## Agent Commands

When making code changes, run these commands in order:

1. **Format code**: `./script/lint_black --auto` and `./script/lint_isort --auto`
2. **Run linting**: `./script/lint`
3. **Run tests**: `./script/tests`

## Code Style

### Language

All documentation (`docs/`, `README.md`, `*.md`), code comments, docstrings and commit/PR text are written in English, regardless of the language used in the conversation with the developer.

### Comments

Only use comments to explain complex, multi-line blocks of code. Do not comment obvious operations. Inline comments are there to explain code parts that need explaining - keep them when editing code.

### Docstring Format

Use Sphinx-style docstrings with `:param:` syntax. For simple functions, a single-line docstring is fine. The docstring should provide clarity to the caller, not explain how it works technically.

```python
def my_function(param1: str, param2: int, param3: bool = False) -> str:
    """
    Brief one-line description of the function.
    :param param1: Description of what param1 is used for.
    :param param2: Description of what param2 is used for.
    :param param3: Description of what param3 is used for.
    """
```

Do **not** use Google-style (`Args:`) or bullet-style (`- param:`) docstrings.

### File structure

Private methods should be at the bottom of the file, public at the top.

## Verification Checklist

Before claiming completion:
- [ ] Ran `./script/lint` - all checks passed
- [ ] Ran `./script/tests` - all tests passed
- [ ] For hardware-related changes (GPIO, LEDs, buttons, USB): Note that hardware testing was NOT performed
- [ ] Did NOT claim hardware behavior is verified unless actually exercised
- [ ] Changes are focused on one feature or fix per change
- [ ] `docs/behavior.md` still matches the code, and behavior changes are listed separately in the PR description

## Areas Requiring Extra Care

- Peripheral drivers - hardware access (GPIO, SPI, PWM/DMA, USB HID) cannot be verified by unit tests
- Protocol handling towards LVA - keep in sync with `docs/peripheral_api/readme.md` of LVA
