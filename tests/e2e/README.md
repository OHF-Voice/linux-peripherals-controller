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
| LPC process | `lpc.py` | Starts `python -m linux_peripherals_controller --debug` against the fake LVA and collects the log. It runs with `--simulate-hardware` (the LEDs are only logged), its ESPHome API on a free port of 127.0.0.1, no mDNS and its own state file in a temporary folder. Tests wait for its debug log lines (`Connected to LVA`, `Display function: a -> b`, `Simulated LEDs: ...`) to follow what LPC does |
| Home Assistant | `test_home_assistant.py` | The client Home Assistant uses (`aioesphomeapi`) connects to the ESPHome API of LPC, lists its entities and sends commands |

Every test gets its own fake LVA on a free port and its own LPC process, so tests do not influence each other.

## What the tests prove

There is no hardware, so the LEDs are simulated: LPC logs their colors (`Simulated LEDs: #rrggbb ...`). What a test checks:

* **From LVA to LPC:** the events and commands the fake LVA sends must lead to the display function that `docs/behavior.md` names (read from the log line `Display function: a -> b`), in the right order of priority and with the short functions ending by themselves.
* **From LPC to LVA:** the messages LPC sends reach the fake LVA as they are specified (`hardware_mute_type` after every connect, no command on its own).
* **The connection:** retry while LVA is not there, the message for an LVA without version 2, reconnect after a loss with the old status dropped.
* **The process:** refusing a missing or unknown device type or an invalid device configuration with a non-zero status, a clean end on Ctrl+C.
* **Home Assistant:** LPC is an ESPHome device with the entities of its device type, the light and the child lock that Home Assistant sets are stored, the light is the background of the LEDs.
* **The LEDs:** the colors the simulated LEDs get for a state of LVA.

A simulated button cannot be pressed, so the buttons are only covered by the unit tests.

## Running locally

```bash
./script/e2e                              # everything, about 35 seconds
./script/e2e tests/e2e/test_display.py    # one file
./script/e2e -k timer                     # selected tests
./script/e2e -s                           # also show the LPC log
```

Without a path argument `./script/e2e` runs all of `tests/e2e`. With a path argument only that path runs, other arguments go to pytest unchanged. The suite is not part of `./script/tests`, which only runs the fast unit tests. In CI the workflow `.github/workflows/e2e-tests.yml` (E2E-Tests) runs it in the same cases as the image builds (main, pull requests, version tags), with a job summary table (the docstring of every test is its description column), annotations for failed tests and an artifact with the LPC logs and `junit.xml` (`E2E_LOG_DIR` writes the logs to a directory locally, add `--junitxml=<file>` for the XML).

The reconnect delay of LPC is 3 s, so the tests about reconnecting wait for it.
