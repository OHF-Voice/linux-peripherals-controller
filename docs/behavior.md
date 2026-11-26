# Behavior Guide

This page describes what Linux Peripheral Controller (LPC) does, from the user's point of view. It is the source of truth for the behavior of LPC: code changes follow it, and a change of the behavior updates it.

> **Status:** specified here, implementation follows. Implemented so far: the connection to LVA (version 2, reconnecting), the choice of the display function, device types and the device configuration (read, checked and merged), and the reports about the hardware mute to LVA with the handling of its requests and the choice of the entity for it (the device type does not say yet which hardware mute a device has, so a driver has to report it, and the entity itself follows with the ESPHome server). Without a device driver the display function is only logged at debug level, and there are no Home Assistant entities and no buttons or LEDs yet.

---

## Contents

- [Basics](#basics)
- [Device type and device configuration](#device-type-and-device-configuration)
- [Functions](#functions)
- [LEDs](#leds)
- [Buttons](#buttons)
- [Child lock](#child-lock)
- [Hardware mute](#hardware-mute)
- [Sensors](#sensors)
- [Home Assistant](#home-assistant)
- [Bridge to LVA](#bridge-to-lva)
- [Startup and errors](#startup-and-errors)

---

## Basics

LPC runs the hardware of one device: LEDs, buttons and sensors. Two connections lead out of it, and they are independent of each other:

```
 Hardware (LEDs, buttons, sensors)
              │
             LPC ──────── ESPHome API ──────► Home Assistant
              │
              └─ peripheral API v2 ─► LVA   (the bridge)
```

- **LPC is its own ESPHome device in Home Assistant.** LEDs, button presses, child lock and sensors reach Home Assistant through LPC, whether LVA runs or not. LVA publishes none of this.
- **The connection to LVA is only a bridge.** It carries the state of the assistant to LPC (so the LEDs can show it) and a few commands back (so buttons can control the assistant). See [Bridge to LVA](#bridge-to-lva).
- **LPC works without LVA.** If LVA is not reachable, LPC keeps retrying, the Home Assistant entities keep working and the LEDs show that there is no connection.
- **The two paths are independent. This is the rule for every component.** What a component reports (a button press, a sensor reading, the state of the light) goes to each destination on its own: to LVA over the bridge and to Home Assistant over ESPHome. Whether one destination can be reached never changes what is sent to the other. A lost connection to LVA does not stop the reports to Home Assistant, and a lost connection to Home Assistant does not stop the commands to LVA. Nothing waits for the other path, and what cannot be delivered is dropped and logged, not held back.

---

## Device type and device configuration

What LPC controls is chosen by the **device type** (`--device-type`, for example `respeaker_2mic_v2`). Two layers describe the device:

| Layer | Who writes it | Contains |
|-------|---------------|----------|
| **Device type** (profile) | Shipped with LPC | How the device is driven (LED chip, number and layout of LEDs, buttons and their pins, sensors) and which [functions](#functions) it offers. It may replace the default patterns and colors with its own. |
| **Device configuration** | The user (`--device-config`, a TOML file) | Settings of this one device: pins that differ, which function a button has, brightness, and colors or patterns that replace those of the device type. |

For every setting the most specific layer wins:

```
built-in defaults  <  device type  <  device configuration
```

Everything is optional in the device configuration. An empty or missing file means the device type as shipped.

Planned device types: ReSpeaker 2mic HAT v1.1 and v2.0, ReSpeaker 4mic HAT, ReSpeaker lite (USB), Jabra Speak 410. More device types are added as profiles, without a change to the rest of LPC.

---

## Functions

The device is controlled at the top by **functions**. A function says *what* happens (for example "show that the assistant is listening", "volume up"), not *how* the hardware does it. Functions are predefined and the same for every device type.

Below a function sit **patterns** (how LEDs move, for example `solid`, `pulse`, `spin`, `progress`, `blink`) and **colors** (named color sets with a color per function). Both are predefined as well. A device type or the device configuration can replace the pattern or the colors of a function, or leave the function out, if the hardware cannot do it.

A device type states which functions it supports. LEDs show only the functions of the device, and a button can only be given a function the device supports.

---

## LEDs

### Display functions

These functions show the state of the assistant on the LEDs. They follow the [events of LVA](#bridge-to-lva) and have a predefined pattern and color each.

| Function | Shown while |
|----------|-------------|
| `wake_word` | The wake word was detected, the wake sound plays. |
| `listening` | The assistant listens. |
| `thinking` | Home Assistant processes the request. |
| `tts` | The assistant speaks. |
| `announce` | An announcement plays. |
| `pipeline_error` | The voice pipeline failed. Shown once for a short time (three red flashes in the default pattern), then the previous display returns. |
| `muted` | The microphone is muted. |
| `timer_active` | A timer counts down. The time left in percent of the whole duration (`timer_remaining_percentage` of LVA) is the amount shown, for example as a progress ring. |
| `timer_ringing` | A timer rings. |
| `timer_timeout` | A ringing timer was not dismissed and stopped on its own (`auto_stopped` in the `timer_status` of LVA). Shown once for a short time, then the previous display returns. |
| `volume` | The volume changed. Shown for a short time, then the previous display returns. |
| `no_connection` | LVA is not connected to LPC or LVA is not connected to Home Assistant. |

### What is shown when

Several things can be true at once, so the display follows a fixed order, highest first:

1. `no_connection`
2. `timer_ringing`
3. `wake_word`, `listening`, `thinking`, `tts`, `announce`
4. `pipeline_error`, `timer_timeout` and `volume` (short, over everything below them)
5. `muted`
6. `timer_active`
7. The background: the light of Home Assistant, see below.

Only the highest entry is shown. When it ends, the next one appears.

### The light in Home Assistant

LPC offers one light entity (`LED`) with color and brightness, see [Home Assistant](#home-assistant). It is the **background**: what the LEDs show when no display function is active. Turned off, the LEDs are dark when nothing else is shown. The display functions above are shown over it and are not affected by it. Brightness of the light applies to the background only. The brightness of the display functions is set in the device configuration.

---

## Buttons

### Press types

LPC detects the press type of every button itself, with the timing of the Home Assistant Voice PE center button:

| Press | Pattern |
|-------|---------|
| Single | One press, then more than 250 ms without another. |
| Double | Press, gap below 250 ms, press, then more than 250 ms without another. |
| Triple | Press, gap below 250 ms, press, gap below 250 ms, press, then more than 250 ms without another. |
| Long | The button is held for at least 1 s. It is reported as soon as the second is over, not on release. A press that waits for its gap is dropped when the next press turns into a long one. |

### Roles

Every button has a **role**. The device type gives each button a default role, and the device configuration can change it.

| Role | What a press does |
|------|-------------------|
| `action` | Controls the assistant by its state, see below. |
| `volume_up`, `volume_down` | Sends `volume_up` / `volume_down` to LVA. Held down, it repeats after 0.5 s every 0.25 s until the button is released. Held for 1 s, it is also a long press (see below). |
| `mute` | Toggles the microphone mute (`muted_on` / `muted_off`). |
| `user` | Has no function. The press is only reported (to Home Assistant, as for every button) and sent to LVA for its sound. |

For the roles other than `user` only the **single press** has an effect.

**Every press is reported to Home Assistant.** Every button, whatever its role, reports every press (single, double, triple and long) to Home Assistant, see [Home Assistant](#home-assistant). This does not depend on LVA (connected or not), on the child lock or on the function of the button. The `repeat` of a volume button is not a press and is not reported. A volume button that is held for 1 s also reports one `long` press while it goes on repeating.

**The `action` role.** One button does the sensible thing for what the assistant is doing right now:

| State of the assistant | Single press |
|------------------------|--------------|
| A timer rings | `timer_stop` |
| `listening`, `speech_detected`, `thinking`, `tts` or `announce` | `listening_stop` |
| Anything else | `listening_start` |

The state comes from LVA. Without a connection to LVA, a press does nothing towards LVA and is logged. The report to Home Assistant does not depend on it, see above.

**Button sounds.** Every press of a button is also sent to LVA as `button_pressed` with its press type, so LVA plays the sound for it (double, triple and long press; a single press has none). This applies to all roles. It is not sent while the child lock is on or LVA is not connected.

**Volume sounds.** A volume change by `volume_up` or `volume_down` plays a short step sound in LVA. At the limit (`volume_up` at 100 %, `volume_down` at 0 %) nothing changes and a different short sound (the limit) plays.

---

## Child lock

The child lock is a switch in Home Assistant (`Child Lock`). While it is on:

- No button sends anything to LVA: no function (start listening, stop, mute, volume, timer stop) and no `button_pressed` for the sound. The child lock only concerns LVA.
- Every press is still reported to Home Assistant.
- The LEDs and everything that comes from LVA or Home Assistant are not affected.

The state is stored and restored after a restart. LVA does not know about the child lock. LPC alone enforces it. Home Assistant shows the state, because the `Child Lock` switch has a state: it is on or off there, and follows a change from any side.

---

## Hardware mute

Some hardware can mute its microphone itself, with a switch or a button, and sometimes software can switch that too. A device type says which kind of hardware mute the device has, and the driver reads its state from the device.

| Type | Meaning | In Home Assistant |
|------|---------|-------------------|
| `none` | The device has no hardware mute. | No entity. |
| `changeable` | The device has one that software can switch. | A switch (`Hardware Mute`): it shows the state and switches the hardware. |
| `read_only` | The device has one that can only be read (for example a slide switch). | A binary sensor (`Hardware Mute`): the state only, it cannot be switched. |

- **The device is always the authority.** LPC reads the state from the device, also right after a (re)connect to LVA and after startup. Neither LVA nor Home Assistant ever sets the state: they can only ask the hardware to switch (if it is `changeable`), and the state that Home Assistant and LVA see is the one the device reports afterwards.
- **LPC offers the entity itself,** over ESPHome, as in the table. LVA creates no entity for it.
- **LPC tells LVA** with the events `hardware_mute_type` (`none`, `changeable` or `read_only`) and `hardware_mute_status` (`muted` or `unmuted`, not for the type `none`). Both are sent after every (re)connect to LVA, and afterwards whenever a value changes. LVA uses them only for its own processing.
- **LVA may ask to switch it.** LVA can send the commands `hardware_muted_on` or `hardware_muted_off`. LPC carries it out only if the type is `changeable`, otherwise it ignores the request and logs why. LPC then reports the new state itself, once the hardware has changed. The same rule applies to the switch in Home Assistant.
- **It is separate from the Mute of the assistant.** Neither follows the other, and the LEDs do not change. LVA will be able to sync its mute with the hardware mute with a parameter that comes later.
- **Without a connection to LVA** nothing is told and no request can arrive. The entity in Home Assistant works as before.

---

## Sensors

A device type can have sensors (for example temperature or light). Each one is a sensor entity in Home Assistant, read at a fixed interval (default set by the device type, `interval` in the device configuration changes it). A sensor that cannot be read is `unavailable` in Home Assistant and a warning is logged once. Reading a sensor never depends on LVA.

---

## Home Assistant

LPC is discovered by Home Assistant over mDNS as an ESPHome device, like LVA (`--port`, default `6054`, so it does not clash with LVA on `6053`; `--enable-encryption` works as for LVA). It is a separate device from LVA, with these entities:

| Entity | Type | Notes |
|--------|------|-------|
| `LED` | Light | On/off, color and brightness. Only if the device has LEDs. |
| `<Button name>` | Event | One per button, whatever its role. Event types `single_press`, `double_press`, `triple_press`, `long_press`. |
| `Child Lock` | Switch | See [Child lock](#child-lock). |
| `Hardware Mute` | Switch or binary sensor | Only for a device with a hardware mute: a switch if it is `changeable`, a binary sensor (status only) if it is `read_only`. See [Hardware mute](#hardware-mute). |
| `<Sensor name>` | Sensor | One per sensor of the device type. |

Entities are never reordered or removed once they exist (as in LVA), so Home Assistant keeps its history. The light state is stored and restored after a restart.

---

## Bridge to LVA

LPC connects to `ws://<--lva-host>:<--lva-port>/v2`, the [peripheral API version 2](https://github.com/OHF-Voice/linux-voice-assistant/blob/main/docs/peripheral_api/v2.md) of LVA. If the connection is lost, LPC reconnects every few seconds and shows `no_connection` meanwhile. After a reconnect it takes the state from the snapshot that LVA sends.

**Events from LVA to LPC** (what LPC shows):

| LVA event | Effect in LPC |
|-----------|---------------|
| `lva_status` | `disconnected` shows `no_connection`. |
| `state` | `wake_word`, `listening`, `thinking`, `tts`, `announce` show the matching function. `speech_detected` (Home Assistant hears speech) shows `listening`. `pipeline_error` shows `pipeline_error` for a short time, LVA sends `idle` right after it. `idle` shows none. The `action` role uses the state. |
| `mute_status` | `muted` function (`status` is `muted` or `unmuted`). |
| `volume_status` | `volume` function, with the volume as the amount shown. Not shown for the first value after a connect. |
| `timer_status` | `active` shows `timer_active`, `ringing` shows `timer_ringing`. `idle` with `auto_stopped: true` (a ringing timer that stopped on its own) shows `timer_timeout`. It describes the timer that is nearest to ringing. |
| `timer_remaining_time`, `timer_remaining_percentage` | The amount shown by `timer_active`, for the timer that is nearest to ringing. A device type may show the seconds instead of the percentage. |
| `timer_full_data_set` | All timers (id, name, status, total, time left, percentage). Kept as state, so a device type can show several timers, for example in different colors. No function in the default setup. |
| `media_player_status` | Kept as state. No function in the default setup, a device type may use it. |

**Commands from LVA to LPC** (a request to LPC):

| LVA command | Effect in LPC |
|-------------|---------------|
| `hardware_muted_on`, `hardware_muted_off` | Mute or unmute the hardware of the microphone, only if the type is `changeable`, see [Hardware mute](#hardware-mute). |

Any other command is ignored and logged.

**Events from LPC to LVA** (what LPC reports about the hardware):

| LPC event | When |
|-----------|------|
| `hardware_mute_type` | After every (re)connect to LVA and when the value changes. See [Hardware mute](#hardware-mute). |
| `hardware_mute_status` | After every (re)connect to LVA and when the value changes. Not for the type `none`. |

**Commands from LPC to LVA** (what buttons do), as described for the roles above:

| LPC command | Sent when |
|-------------|-----------|
| `listening_start` | A button starts listening. |
| `listening_stop` | A button stops the reply, the announcement and the pipeline. |
| `muted_on`, `muted_off` | A button mutes or unmutes the microphone of LVA. |
| `volume_up`, `volume_down`, `volume_set`, `volume_silent` | A button changes the volume. |
| `timer_stop` | A button stops a ringing timer. |
| `button_pressed` | Every press, with its press type, so LVA plays the button sound. |

Nothing else is sent. A message is dropped and logged when LVA is not connected. That never changes what is reported to Home Assistant.

LPC does not tell LVA anything about Home Assistant entities, the light, sensors or the child lock. The hardware mute is the only thing about the hardware that LVA is told, and it only uses that internally.

---

## Startup and errors

1. LPC logs its version, the device type and the addresses of the ESPHome API and LVA.
2. It reads the device type and the device configuration and starts the hardware.
3. It starts the ESPHome API and registers itself over mDNS, then connects to LVA.

| Situation | What happens |
|-----------|--------------|
| `--device-type` missing or unknown | LPC logs the known device types and exits with a non-zero status. |
| Device configuration cannot be read, has an unknown key or an invalid value | LPC logs the key and the file and exits with a non-zero status. LPC never starts with a part of the configuration. |
| Hardware cannot be opened (pins, bus, USB device) | LPC logs the error and exits with a non-zero status, so Docker (`restart: unless-stopped`) or systemd restarts it. |
| LVA is not reachable | LPC keeps running and retries, see [Bridge to LVA](#bridge-to-lva). |
| Home Assistant is not connected | Nothing changes for the hardware. Buttons and LEDs work as before. |
| Peripheral API of LVA has no version 2 | LPC logs once that LVA does not offer version 2 (the HTTP status it answered) and retries. |

> **Note:** This page was written from the planned program logic. Behavior that depends on hardware (LED timing, button debounce, sensor values) depends on the device.
