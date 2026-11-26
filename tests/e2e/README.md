# End-to-end tests

These tests start a real LPC process and drive it the way LVA does, without LVA and without hardware. The other direction of the end-to-end tests of LVA (`tests/e2e` in the LVA repository starts a real LVA and a fake peripheral): here LPC is the real one and LVA is the fake.

```
 test ──events, commands──▶ fake LVA ◀──WebSocket /v2──▶ LPC (real process)
                                │                            │
                      what LPC sent                    debug log
                                └────────────▶ test ◀────────┘
```

| Part | File | Job |
|------|------|-----|
| Fake LVA | `fake_lva.py` | The server side of the [peripheral API version 2](https://github.com/OHF-Voice/linux-voice-assistant/blob/main/docs/peripheral_api/v2.md): sends `hello` and the whole status after a connect, answers HTTP 404 for a path it does not offer, lets a test send events and commands as LVA, records every message of LPC |
| LPC process | `lpc.py` | Starts `python -m linux_peripherals_controller --debug` against the fake LVA and collects the log. Tests wait for its debug log lines (`Connected to LVA`, `Display function: a -> b`, ...) to follow what LPC does |

Every test gets its own fake LVA on a free port and its own LPC process, so tests do not influence each other.

## What the tests prove

LPC has no device driver yet, so the LEDs cannot be looked at. What a test checks:

* **From LVA to LPC:** the events and commands the fake LVA sends must lead to the display function that `docs/behavior.md` names (read from the log line `Display function: a -> b`), in the right order of priority and with the short functions ending by themselves.
* **From LPC to LVA:** the messages LPC sends reach the fake LVA as they are specified (`hardware_mute_type` after every connect, no command on its own).
* **The connection:** retry while LVA is not there, the message for an LVA without version 2, reconnect after a loss with the old status dropped.
* **The process:** refusing a missing or unknown device type or an invalid device configuration with a non-zero status, a clean end on Ctrl+C.

When drivers, buttons and the ESPHome server are added, the tests for them go here too (a button press must arrive at the fake LVA as the command of its role, the entities must be visible to a fake Home Assistant).

## Running locally

```bash
./script/e2e                              # everything, about 35 seconds
./script/e2e tests/e2e/test_display.py    # one file
./script/e2e -k timer                     # selected tests
./script/e2e -s                           # also show the LPC log
```

Without a path argument `./script/e2e` runs all of `tests/e2e`. With a path argument only that path runs, other arguments go to pytest unchanged. The suite is not part of `./script/tests`, which only runs the fast unit tests. In CI the workflow `.github/workflows/e2e-tests.yml` (E2E-Tests) runs it in the same cases as the image builds (main, pull requests, version tags), with a job summary table (the docstring of every test is its description column), annotations for failed tests and an artifact with the LPC logs and `junit.xml` (`E2E_LOG_DIR` writes the logs to a directory locally, add `--junitxml=<file>` for the XML).

The reconnect delay of LPC is 3 s, so the tests about reconnecting wait for it.
