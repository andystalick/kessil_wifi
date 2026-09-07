# Kessil WiFi — Home Assistant integration

Local control of Kessil A360X aquarium lights through the Kessil WiFi Dongle.
No cloud, no account, no polling of anyone's servers — just JSON over TCP on
your own LAN.

## What it gives you

A single `light` entity per lamp group, supporting:

- **On / off**
- **Brightness** (the fixture's intensity channel)
- **Colour temperature** (the fixture's warm↔cool channel)

That is deliberately all. Scheduling is left to Home Assistant, which already
does it better than this integration could — see [Scheduling](#scheduling).

## Requirements

- A Kessil WiFi Dongle reachable on your network (tested against firmware
  **1.5.13** with two **A360X Tuna Sun** fixtures)
- Home Assistant 2025.2 or newer
- A **static DHCP reservation for the dongle**. The integration talks to a
  fixed IP and does not follow address changes on its own.

## Installation

### HACS (custom repository)

1. HACS → ⋮ → *Custom repositories*
2. Add this repository, category *Integration*
3. Install **Kessil WiFi**, then restart Home Assistant

### Manual

Copy `custom_components/kessil_wifi` into your Home Assistant `config/custom_components/`
directory and restart.

## Setup

*Settings → Devices & Services → Add Integration → Kessil WiFi*, then enter the
dongle's IP address. The port defaults to 8888 and rarely needs changing.

The integration reads the dongle's serial number to identify the device, and
controls whichever group your lamps are actually in.

## Scheduling

This integration intentionally ships **no scheduling of its own**. Point Home
Assistant's own tools at the light entity instead:

- **Schedule helper** (*Settings → Devices & Services → Helpers → Schedule*)
  plus an automation, for fixed on/off or level-by-time-of-day.
- **[Adaptive Lighting](https://github.com/basnijholt/adaptive-lighting)** for
  smooth sunrise/sunset ramps of brightness and colour temperature — close to
  what most reef tanks want, with no YAML.
- **Scenes** for named lighting states you can call from anything.

### Important: HA control replaces the lamp's onboard program

The dongle has exactly one manual-override mode. **The first time Home Assistant
sets a value, the group leaves its onboard Kessil program and does not go back.**
The entity exposes this as a `manual_mode` attribute.

The practical consequence: once you drive these lights from Home Assistant, Home
Assistant is the only thing driving them. If HA is down, the lamps hold their
last value rather than falling back to the onboard schedule. For a tank, decide
deliberately whether that is acceptable before automating.

Restoring an onboard program from the network is not currently possible — the
command that would do it (`dtype 4`) rejects every payload tried. Use the Kessil
phone app to put a group back on a program.

## Known limitations

| Limitation | Detail |
|---|---|
| Channel mapping unconfirmed | Brightness is assumed to be `UI1` and colour `UI2`. Both are confirmed writable; which knob is which has not been checked by eye. If they turn out reversed, swap `CHANNEL_INTENSITY` / `CHANNEL_COLOR` in `const.py`. |
| Kelvin range uncalibrated | The 2700–6500 K range is nominal, not measured. The slider is proportional to the channel, not true colour temperature. |
| `UI3`–`UI5` unused | Present in the protocol, believed inert on a Tuna Sun. Untested. |
| Polling only | The dongle has no push channel. State is polled every 30 s, so changes made in the Kessil app take up to that long to appear. |
| No discovery | The dongle broadcasts on UDP 19276, but setup is manual IP entry. |
| No authentication | Not a choice this integration makes — the dongle's TCP port has no auth at all. Anything on your LAN can control these lights. |

## Development

This project uses [uv](https://docs.astral.sh/uv/). It needs no separate install
step — `uv run` creates and syncs the environment from `uv.lock` on first use.

```bash
uv run pytest                                  # 43 tests
uv run ruff check custom_components tests
uv run ruff format custom_components tests
```

`uv sync` up front works too if you'd rather materialise `.venv` explicitly.

Tests run against `tests/fake_dongle.py`, which reproduces the real device's
quirks — including the ones that make writes silently fail.

To check the client against real hardware:

```bash
uv run python verify_live.py <dongle-ip>
```

It reads state, writes values, verifies them, and restores the original levels.

### A note on the dependency setup

- **The integration has no runtime dependencies.** `custom_components/kessil_wifi/`
  is pure stdlib, and `[project.dependencies]` is deliberately empty. Anything it
  needed later would go in `manifest.json`, because Home Assistant installs
  integration requirements itself (with uv, as it happens).
- **`package = false`.** Home Assistant consumes this repo by copying the
  `custom_components/kessil_wifi/` directory into its config, so there is nothing
  to build or install. uv treats the project as an environment, not a package.
- **`requires-python` is upper-bounded** at `<3.14`. uv resolves across the whole
  declared range rather than just the interpreter in use, and the pinned Home
  Assistant test harness does not support 3.14 yet. Raise both together.
- **`uv.lock` is committed** so tests run against exactly the Home Assistant
  version they were verified on.

## Protocol notes

The protocol was recovered by reverse-engineering the dongle. The parts that
matter most:

```jsonc
// Read group state
{"dtype": 3, "data": {"GID": 2}}

// Write channels — note UI1..UI5 (not a UI array) and save:1 (not 0)
{"dtype": 3, "data": {"GID": 2, "UI1": 200, "UI2": 60,
                      "UI3": 0, "UI4": 0, "UI5": 0, "save": 1}}
```

Three traps cost this project months of dead ends:

1. `GID` is **uppercase** and lives **inside** `data`. Lowercase `gid` is rejected.
2. Writes need `save: 1`. With `save: 0` the dongle replies `code: 0` and does nothing.
3. Writes take `UI1`…`UI5`; reads return a `UI` array. Sending an array on a
   write is accepted and ignored.

And one transport quirk: the dongle refuses rapid reconnects and sometimes holds
the socket open after replying, so the client serialises commands, paces them,
and stops reading once a complete JSON object has arrived rather than waiting
for EOF.

## Disclaimer

Not affiliated with or endorsed by Kessil. Built by reverse-engineering a
device on the author's own network.
